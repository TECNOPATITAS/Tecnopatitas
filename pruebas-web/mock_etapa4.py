"""
Simulador de la Etapa 4 (mascotas, carnet, placa QR y Storage), SOLO para pruebas de interfaz.
Imita las reglas de las políticas RLS y los disparadores de database/*.sql (propiedad por dueño, límites de plan,
validaciones CHECK) y las respuestas documentadas de PostgREST y Supabase Storage. No es Supabase.
"""
import datetime, json, re, urllib.parse, uuid
from mock_supabase import Backend

SPECIES = ['perro', 'gato', 'ave', 'conejo', 'pequeno_mamifero', 'otro']
PLANS = {
    'basica': dict(id='basica', name='Huellita Básica', tagline='Plan Comunidad', health_card_pet_limit=0, qr_enabled=False),
    'pro': dict(id='pro', name='Huellita Pro', tagline='Cuidado digital', health_card_pet_limit=2, qr_enabled=False),
    'vip': dict(id='vip', name='Huellita VIP', tagline='Protección completa', health_card_pet_limit=None, qr_enabled=True),
}
BUCKETS = {'avatars': dict(limit=2 * 1024 * 1024, room=3), 'pet-photos': dict(limit=5 * 1024 * 1024, room=60), 'qr-photos': dict(limit=1024 * 1024, room=30),
           'business-media': dict(limit=5 * 1024 * 1024, room=30)}
PUBLIC_BUCKETS = ('qr-photos', 'business-media')
INSERT_COLS = {
    'pets': {'id', 'name', 'photo_path', 'species', 'breed', 'sex', 'birth_date', 'weight_kg', 'description', 'vet_info'},
    'pet_vaccinations': {'pet_id', 'vaccine_name', 'applied_on', 'next_due_on', 'veterinarian', 'notes'},
    'pet_deworming': {'pet_id', 'product_name', 'kind', 'applied_on', 'next_due_on', 'notes'},
    'pet_appointments': {'pet_id', 'kind', 'scheduled_at', 'status', 'clinic', 'reason', 'notes'},
    'pet_qr_profiles': {'pet_id', 'is_active', 'show_name', 'show_photo', 'show_breed', 'public_message', 'contact_name', 'contact_phone', 'show_phone', 'qr_photo_path'},
}
UPDATE_COLS = {t: (c - {'id', 'pet_id'}) for t, c in INSERT_COLS.items()}
TABLES = list(INSERT_COLS)
CHILD = ['pet_vaccinations', 'pet_deworming', 'pet_appointments']
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


class Fail(Exception):
    def __init__(self, status, code, msg): self.status, self.code, self.msg = status, code, msg


def parse_multipart(ct, raw):
    """Devuelve (content_type_del_archivo, bytes) de la primera parte de un cuerpo multipart/form-data cuyo nombre es ''."""
    m = re.search(r'boundary=([^;]+)', ct or '')
    if not m or raw is None: return None, None
    b = ('--' + m.group(1).strip('"')).encode()
    for part in raw.split(b):
        if b'\r\n\r\n' not in part: continue
        head, body = part.split(b'\r\n\r\n', 1)
        hs = head.decode('latin-1')
        if 'name=""' in hs:
            ctm = re.search(r'content-type:\s*([^\r\n]+)', hs, re.I)
            return (ctm.group(1).strip() if ctm else None), body.rsplit(b'\r\n', 1)[0]
    return None, None


class Backend4(Backend):
    def reset(self, **kw):
        super().reset(**kw)
        self.tables = {t: [] for t in TABLES}
        self.objects = {}                    # (bucket, path) -> dict(owner, size, type, data)
        self.user_plan = {}                  # uid -> 'basica' | 'pro' | 'vip'
        self.storage_fail = None             # p. ej. 500 para simular un fallo de Storage

    def set_plan(self, email, plan): self.user_plan[self.users[email]['id']] = plan
    def plan_of(self, uid): return PLANS[self.user_plan.get(uid, 'basica')]
    def pets_of(self, uid): return [p for p in self.tables['pets'] if p['owner_id'] == uid]
    def owner_of(self, pet_id): return next((p['owner_id'] for p in self.tables['pets'] if p['id'] == pet_id), None)

    # ----------------------------------------------------------------
    def handle(self, method, url, headers, body_text, raw=None):
        p = urllib.parse.urlparse(url); path = p.path
        if path.startswith('/storage/v1/'):
            h = {k.lower(): v for k, v in headers.items()}
            try: sbody = json.loads(body_text) if body_text else None
            except Exception: sbody = None
            self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=sbody, raw_len=len(raw) if raw else 0, text_len=len(body_text or ''), cl=h.get('content-length')))
            res = self.storage(method, path, p.query, h, body_text, raw)
            self.calls[-1]['status'] = res[0]; self.calls[-1]['resp'] = (res[1] if isinstance(res[1], (list, dict)) else '<bytes>')
            return res
        if path.startswith('/rest/v1/'):
            name = path[len('/rest/v1/'):]
            if name in TABLES or name in ('rpc/get_public_pet_profile', 'rpc/regenerate_pet_qr_token', 'rpc/my_entitlements'):
                h = {k.lower(): v for k, v in headers.items()}
                try: body = json.loads(body_text) if body_text else None
                except Exception: body = None
                self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
                if h.get('apikey') != self.key: return 401, dict(code=401, error_code='no_api_key', msg='No API key found in request')
                try: return self.rest(method, name, urllib.parse.parse_qs(p.query), h, body)
                except Fail as f: return f.status, dict(code=f.code, details=None, hint=None, message=f.msg)
        return super().handle(method, url, headers, body_text)

    # ---------------- PostgREST ----------------
    def rest(self, method, name, q, h, body):
        u = self.user_for(h)
        if 'authorization' in h and not u: raise Fail(401, 'PGRST301', 'JWT expired')
        if name == 'rpc/get_public_pet_profile': return 200, self.public_profile((body or {}).get('p_token', ''))
        if not u: raise Fail(401, '42501', 'permission denied for table ' + name.replace('rpc/', ''))
        uid = u['id']; susp = self.profiles[uid]['is_suspended']
        if name == 'rpc/my_entitlements': return 200, dict(plan=self.plan_of(uid), subscription=None)
        if name == 'rpc/regenerate_pet_qr_token':
            if susp: raise Fail(403, '42501', 'No autorizado.')
            row = next((r for r in self.tables['pet_qr_profiles'] if r['pet_id'] == (body or {}).get('p_pet_id') and self.owner_of(r['pet_id']) == uid), None)
            if not row: raise Fail(403, '42501', 'Placa QR no encontrada.')
            row['public_token'] = uuid.uuid4().hex + uuid.uuid4().hex
            return 204, None
        t = name
        mine = lambda r: (r['owner_id'] == uid) if t == 'pets' else (self.owner_of(r['pet_id']) == uid)
        rows = [r for r in self.tables[t] if mine(r)]
        flt = {k: v[0] for k, v in q.items() if k not in ('select', 'order', 'limit') and v and v[0].startswith('eq.')}
        for k, v in flt.items(): rows = [r for r in rows if str(r.get(k)) == v[3:]]
        if method == 'GET':
            for spec in reversed((q.get('order', [''])[0]).split(',')):
                if not spec: continue
                col, _, d = spec.partition('.')
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col) or ''), reverse=(d == 'desc'))
            if 'limit' in q: rows = rows[:int(q['limit'][0])]
            sel = q.get('select', ['*'])[0]
            if sel != '*': cols = sel.split(','); rows = [{c: r.get(c) for c in cols} for r in rows]
            if 'pgrst.object' in h.get('accept', ''):
                return (200, rows[0]) if len(rows) == 1 else (406, dict(code='PGRST116', message='JSON object requested, multiple (or no) rows returned'))
            return 200, [dict(r) for r in rows]
        rep = 'return=representation' in h.get('prefer', '')
        if method == 'POST':
            if susp: raise Fail(403, '42501', 'new row violates row-level security policy for table "%s"' % t)
            b = dict(body or {})
            if set(b) - INSERT_COLS[t]: raise Fail(403, '42501', 'permission denied for table ' + t)
            row = self.check_insert(t, b, uid)
            self.tables[t].append(row)
            return (201, [dict(row)]) if rep else (201, None)
        if method in ('PATCH', 'DELETE'):
            if susp and method == 'PATCH': return (200, []) if rep else (204, None)
            if method == 'PATCH':
                b = dict(body or {})
                if set(b) - UPDATE_COLS[t]: raise Fail(403, '42501', 'permission denied for table ' + t)
                for r in rows:
                    self.check_row(t, {**r, **b})
                    if t == 'pet_qr_profiles' and 'qr_photo_path' in b: self.check_qr_photo(b['qr_photo_path'], uid)
                    r.update(b)
                return (200, [dict(r) for r in rows]) if rep else (204, None)
            for r in rows:
                self.tables[t].remove(r)
                if t == 'pets':
                    for c in CHILD + ['pet_qr_profiles']: self.tables[c] = [x for x in self.tables[c] if x['pet_id'] != r['id']]
            return (200, [dict(r) for r in rows]) if rep else (204, None)
        raise Fail(405, 'PGRST000', 'method not allowed')

    def check_row(self, t, r):                       # restricciones CHECK de las tablas
        def bad(): raise Fail(400, '23514', 'new row for relation "%s" violates check constraint' % t)
        today = datetime.date.today().isoformat(); tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        if t == 'pets':
            if not (1 <= len((r.get('name') or '').strip()) <= 60) or r.get('species') not in SPECIES: bad()
            if r.get('sex') not in (None, 'macho', 'hembra'): bad()
            if r.get('birth_date') and not ('1990-01-01' <= r['birth_date'] <= tomorrow): bad()
            if r.get('weight_kg') is not None and not (0 < float(r['weight_kg']) <= 200): bad()
            if r.get('description') and len(r['description']) > 1000: bad()
            if r.get('vet_info') and len(r['vet_info']) > 2000: bad()
        elif t in ('pet_vaccinations', 'pet_deworming'):
            n = r.get('vaccine_name') if t == 'pet_vaccinations' else r.get('product_name')
            if not (1 <= len((n or '').strip()) <= 100): bad()
            if not r.get('applied_on') or not DATE_RE.match(r['applied_on']) or not ('1990-01-01' <= r['applied_on'] <= tomorrow): bad()
            if r.get('next_due_on') and r['next_due_on'] < r['applied_on']: bad()
            if t == 'pet_deworming' and r.get('kind', 'interna') not in ('interna', 'externa', 'ambas'): bad()
        elif t == 'pet_appointments':
            if r.get('kind', 'consulta') not in ('consulta', 'vacunacion', 'desparasitacion', 'estetica', 'otra'): bad()
            if r.get('status', 'programada') not in ('programada', 'realizada', 'cancelada'): bad()
            if not r.get('scheduled_at'): bad()
        elif t == 'pet_qr_profiles':
            if r.get('public_message') and len(r['public_message']) > 300: bad()
            if r.get('contact_phone') and not re.match(r'^[0-9+() .-]{7,20}$', r['contact_phone']): bad()
            if r.get('show_phone') and not r.get('contact_phone'): bad()

    def check_qr_photo(self, path, uid):             # disparador guard_qr
        if path is not None and (not re.match('^' + uid + r'/[A-Za-z0-9._-]{1,120}$', path) or '..' in path):
            raise Fail(400, '23514', 'La foto de la placa no es válida.')

    def check_insert(self, t, b, uid):
        if t == 'pets':
            if len(self.pets_of(uid)) >= 30: raise Fail(400, 'P0001', 'Alcanzaste el límite de mascotas por cuenta.')
            row = dict(id=b.get('id') or str(uuid.uuid4()), owner_id=uid, name=b.get('name'), photo_path=b.get('photo_path'), species=b.get('species'),
                       breed=b.get('breed'), sex=b.get('sex'), birth_date=b.get('birth_date'), weight_kg=b.get('weight_kg'),
                       description=b.get('description'), vet_info=b.get('vet_info'), created_at=datetime.datetime.utcnow().isoformat() + 'Z' + str(len(self.tables['pets'])).zfill(3))
            self.check_row(t, row); return row
        pet_id = b.get('pet_id')
        if self.owner_of(pet_id) != uid: raise Fail(403, '42501', 'new row violates row-level security policy for table "%s"' % t)
        plan = self.plan_of(uid)
        if t in CHILD:
            lim = plan['health_card_pet_limit']
            if lim == 0: raise Fail(400, 'P0001', 'Tu plan no incluye el carnet de salud digital. Consulta los planes Huellita Pro o VIP.')
            if lim is not None and not any(x['pet_id'] == pet_id for c in CHILD for x in self.tables[c]):
                with_card = {x['pet_id'] for c in CHILD for x in self.tables[c] if self.owner_of(x['pet_id']) == uid}
                if len(with_card) >= lim: raise Fail(400, 'P0001', 'Tu plan permite carnet de salud para %d mascota(s).' % lim)
            row = dict(id=str(uuid.uuid4()), created_at=datetime.datetime.utcnow().isoformat() + 'Z', **{k: b.get(k) for k in INSERT_COLS[t]})
            if t == 'pet_deworming' and row['kind'] is None: row['kind'] = 'interna'
            if t == 'pet_appointments':
                row['kind'] = row['kind'] or 'consulta'; row['status'] = row['status'] or 'programada'
            self.check_row(t, row); return row
        # pet_qr_profiles
        if not plan['qr_enabled']: raise Fail(400, 'P0001', 'Tu plan no incluye la placa QR. Está disponible en Huellita VIP.')
        if any(x['pet_id'] == pet_id for x in self.tables[t]): raise Fail(409, '23505', 'duplicate key value violates unique constraint "pet_qr_profiles_pet_id_key"')
        row = dict(id=str(uuid.uuid4()), pet_id=pet_id, public_token=uuid.uuid4().hex + uuid.uuid4().hex, is_active=b.get('is_active', True),
                   show_name=b.get('show_name', True), show_photo=b.get('show_photo', False), show_breed=b.get('show_breed', True),
                   public_message=b.get('public_message'), contact_name=b.get('contact_name'), contact_phone=b.get('contact_phone'),
                   show_phone=b.get('show_phone', False), qr_photo_path=b.get('qr_photo_path'))
        self.check_row(t, row); self.check_qr_photo(row['qr_photo_path'], uid); return row

    def public_profile(self, token):
        if not re.match(r'^[0-9a-f]{64}$', token or ''): return None
        q = next((r for r in self.tables['pet_qr_profiles'] if r['public_token'] == token and r['is_active']), None)
        if not q: return None
        p = next(x for x in self.tables['pets'] if x['id'] == q['pet_id'])
        return dict(name=p['name'] if q['show_name'] else None, species=p['species'], breed=p['breed'] if q['show_breed'] else None,
                    photo_path=q['qr_photo_path'] if q['show_photo'] else None, message=q['public_message'],
                    contact_name=q['contact_name'] if q['show_phone'] else None, contact_phone=q['contact_phone'] if q['show_phone'] else None)

    # ---------------- Storage ----------------
    def storage(self, method, path, query, h, body_text, raw):
        err = lambda s, e, m: (s, dict(statusCode=str(s), error=e, message=m))
        if self.storage_fail: return err(self.storage_fail, 'Internal', 'fallo simulado')
        rest = path[len('/storage/v1/'):]
        m = re.match(r'^object/public/([^/]+)/(.+)$', rest)
        if m and method == 'GET':                                    # lectura pública (solo buckets públicos)
            b, p = m.group(1), urllib.parse.unquote(m.group(2)); o = self.objects.get((b, p))
            if b not in PUBLIC_BUCKETS or not o: return err(404, 'not_found', 'Object not found')
            return 200, o['data'], o['type']
        m = re.match(r'^object/sign/([^/]+)/(.+)$', rest)
        if m and method == 'GET':                                    # descarga con URL firmada
            b, p = m.group(1), urllib.parse.unquote(m.group(2)); o = self.objects.get((b, p))
            if not o or 'token=' not in query: return err(400, 'InvalidJWT', 'invalid signature')
            return 200, o['data'], o['type']
        u = self.user_for(h)
        if not u: return err(400, 'InvalidJWT', 'Invalid Compact JWS')
        uid = u['id']; susp = self.profiles[uid]['is_suspended']
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        m = re.match(r'^object/sign/([^/]+)$', rest)
        if m and method == 'POST':
            b = m.group(1); out = []
            for p in (body or {}).get('paths', []):
                o = self.objects.get((b, p))
                if o and o['owner'] == uid and b in BUCKETS:
                    out.append(dict(path=p, signedURL='/object/sign/%s/%s?token=tok%d' % (b, urllib.parse.quote(p), len(out)), error=None))
                else: out.append(dict(path=p, signedURL=None, error='Either the object does not exist or you do not have access to it'))
            return 200, out
        m = re.match(r'^object/([^/]+)$', rest)
        if m and method == 'DELETE':
            b = m.group(1); gone = []
            for p in (body or {}).get('prefixes', []):
                o = self.objects.get((b, p))
                if o and o['owner'] == uid: del self.objects[(b, p)]; gone.append(dict(name=p, bucket_id=b))
            return 200, gone
        m = re.match(r'^object/([^/]+)/(.+)$', rest)
        if m and method == 'POST':
            b, p = m.group(1), urllib.parse.unquote(m.group(2))
            if b not in BUCKETS: return err(404, 'Bucket not found', 'Bucket not found')
            if p.split('/')[0] != uid or susp: return err(403, 'Unauthorized', 'new row violates row-level security policy')
            if b == 'qr-photos' and not self.plan_of(uid)['qr_enabled']: return err(403, 'Unauthorized', 'new row violates row-level security policy')
            if b == 'business-media' and self.profiles[uid]['account_type'] != 'business': return err(403, 'Unauthorized', 'new row violates row-level security policy')
            mine = [k for k, o in self.objects.items() if k[0] == b and o['owner'] == uid]
            if len(mine) >= BUCKETS[b]['room']: return err(403, 'Unauthorized', 'new row violates row-level security policy')
            ct, data = parse_multipart(h.get('content-type', ''), raw)
            if data is None: return err(400, 'InvalidRequest', 'sin archivo')
            if ct not in ('image/jpeg', 'image/png', 'image/webp'): return err(415, 'invalid_mime_type', 'mime type %s is not supported' % ct)
            if len(data) > BUCKETS[b]['limit']: return err(413, 'Payload too large', 'The object exceeded the maximum allowed size')
            if (b, p) in self.objects: return err(409, 'Duplicate', 'The resource already exists')
            self.objects[(b, p)] = dict(owner=uid, size=len(data), type=ct, data=data)
            return 200, dict(Key=b + '/' + p, Id=str(uuid.uuid4()))
        return err(404, 'not_found', 'Not found')
