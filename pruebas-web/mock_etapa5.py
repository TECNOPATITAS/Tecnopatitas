"""
Simulador de la Etapa 5 (aliados, promociones, estadísticas y directorio público), SOLO para pruebas de interfaz.
Imita las reglas de las políticas RLS, los disparadores y las funciones de database/*.sql (propiedad por dueño, límites de plan,
validaciones CHECK, lo que muestra el directorio según el plan) y las respuestas documentadas de PostgREST. No es Supabase.
Se apoya en Backend4 (mascotas, Storage, Auth).
"""
import datetime, json, re, urllib.parse, uuid
from zoneinfo import ZoneInfo
import mock_etapa4
from mock_etapa4 import Backend4, Fail

MX = ZoneInfo('America/Mexico_City')
mock_etapa4.PLANS.update({
    'basica': dict(mock_etapa4.PLANS['basica'], audience='owner'),
    'pro': dict(mock_etapa4.PLANS['pro'], audience='owner'),
    'vip': dict(mock_etapa4.PLANS['vip'], audience='owner'),
    'plata': dict(id='plata', name='Huellita de Plata', tagline='Plan Aliado Inicial', audience='business', max_promotions_per_month=1,
                  whatsapp_button=False, priority_listing=False, verified_badge_eligible=False),
    'oro': dict(id='oro', name='Huellita de Oro', tagline='Plan Aliado Premium', audience='business', max_promotions_per_month=None,
                whatsapp_button=True, priority_listing=True, verified_badge_eligible=True),
})
PLANS = mock_etapa4.PLANS

B5_TABLES = ('businesses', 'business_promotions', 'business_daily_stats')
B5_RPCS = ('rpc/directory_search', 'rpc/directory_get', 'rpc/directory_track', 'rpc/my_entitlements')
CATEGORIES = ('veterinaria', 'estetica_canina', 'estetica_felina', 'tienda', 'adiestramiento', 'otro')
BIZ_INSERT = {'id', 'owner_id', 'name', 'category', 'description', 'address', 'state', 'municipality', 'phone', 'whatsapp_url', 'maps_query', 'logo_path', 'photo_paths', 'hours'}
BIZ_UPDATE = BIZ_INSERT - {'id', 'owner_id'}
PROMO_INSERT = {'business_id', 'title', 'description', 'starts_on', 'ends_on', 'is_active'}
PROMO_UPDATE = PROMO_INSERT - {'business_id'}
PHONE_RE = re.compile(r'^[0-9+() .-]{7,20}$')
WA_RE = re.compile(r'^https://wa\.me/[0-9]{8,15}(\?text=[A-Za-z0-9%._~+-]{1,255})?$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def today_mx(): return datetime.datetime.now(MX).date()
def month_start_utc(): return datetime.datetime.now(MX).replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc)
def now_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Backend5(Backend4):
    def reset(self, **kw):
        super().reset(**kw)
        for t in B5_TABLES: self.tables[t] = []
        self.track_seen = {}                 # (visitante, evento, negocio) -> veces hoy
        self.client_ip = '203.0.113.7'       # «huella» del visitante; los tests la cambian para simular otra persona
        self.fail_patch = False              # True: las modificaciones de establecimientos fallan con 500 (prueba de limpieza de archivos)
        self.fail_dir = None                 # p. ej. 500: el directorio falla (para probar el aviso de error)

    # ---------------- utilidades de prueba ----------------
    def eff_plan(self, uid):
        """Igual que private.plan_for: suscripción vigente; las cuentas de dueño sin suscripción tienen la Básica; las de aliado, ninguna."""
        pid = self.user_plan.get(uid)
        if pid: return PLANS[pid]
        prof = self.profiles.get(uid)
        return PLANS['basica'] if prof and prof['account_type'] == 'owner' else None

    def add_business(self, owner, name, category='veterinaria', status='approved', demo=False, **kw):
        uid = None if demo else (self.users[owner]['id'] if owner in self.users else owner)
        row = dict(id=str(uuid.uuid4()), owner_id=uid, is_demo=demo, name=name, category=category, description=None, address=None, state=None,
                   municipality=None, phone=None, whatsapp_url=None, maps_query=None, logo_path=None, photo_paths=[], hours={}, status=status,
                   verified=False, verified_at=None, created_at=now_iso(), updated_at=now_iso())
        row.update(kw); self.tables['businesses'].append(row); return row

    def add_promo(self, biz, title, days_from=0, days_to=30, active=True, **kw):
        t = today_mx()
        row = dict(id=str(uuid.uuid4()), business_id=biz['id'], title=title, description=None, starts_on=(t + datetime.timedelta(days=days_from)).isoformat(),
                   ends_on=(t + datetime.timedelta(days=days_to)).isoformat(), is_active=active, created_at=now_iso(), updated_at=now_iso())
        row.update(kw); self.tables['business_promotions'].append(row); return row

    def add_stat(self, biz, days_ago, views, clicks):
        d = (today_mx() - datetime.timedelta(days=days_ago)).isoformat()
        self.tables['business_daily_stats'].append(dict(business_id=biz['id'], day=d, views=views, map_clicks=clicks))

    def biz_by_id(self, i): return next((b for b in self.tables['businesses'] if b['id'] == i), None)
    def biz_owner(self, i): b = self.biz_by_id(i); return b['owner_id'] if b else None
    def stats_for(self, biz): return [s for s in self.tables['business_daily_stats'] if s['business_id'] == biz['id']]

    # ---------------- enrutado ----------------
    def handle(self, method, url, headers, body_text, raw=None):
        p = urllib.parse.urlparse(url)
        if p.path.startswith('/rest/v1/'):
            name = p.path[len('/rest/v1/'):]
            if name in B5_TABLES or name in B5_RPCS:
                h = {k.lower(): v for k, v in headers.items()}
                try: body = json.loads(body_text) if body_text else None
                except Exception: body = None
                self.calls.append(dict(method=method, path=p.path, query=p.query, headers=h, body=body))
                if h.get('apikey') != self.key: return 401, dict(code=401, error_code='no_api_key', msg='No API key found in request')
                try: return self.rest5(method, name, urllib.parse.parse_qs(p.query), h, body)
                except Fail as f: return f.status, dict(code=f.code, details=None, hint=None, message=f.msg)
        return super().handle(method, url, headers, body_text, raw)

    def rest5(self, method, name, q, h, body):
        u = self.user_for(h)
        if 'authorization' in h and not u: raise Fail(401, 'PGRST301', 'JWT expired')
        if name.startswith('rpc/directory') and self.fail_dir: raise Fail(self.fail_dir, 'XX000', 'fallo simulado')
        if name == 'rpc/directory_search': return 200, self.dir_search(body or {})
        if name == 'rpc/directory_get': return 200, self.dir_get((body or {}).get('p_id'))
        if name == 'rpc/directory_track': self.dir_track(u, body or {}); return 204, None
        if not u: raise Fail(401, '42501', 'permission denied for table ' + name.replace('rpc/', ''))
        uid = u['id']; susp = self.profiles[uid]['is_suspended']
        if name == 'rpc/my_entitlements': return 200, dict(plan=self.eff_plan(uid), subscription=None)
        t = name
        mine = (lambda r: r['owner_id'] == uid) if t == 'businesses' else (lambda r: self.biz_owner(r['business_id']) == uid)
        rows = self.filtered([r for r in self.tables[t] if mine(r)], q)
        rep = 'return=representation' in h.get('prefer', '')
        if method == 'GET':
            for spec in reversed((q.get('order', [''])[0]).split(',')):
                if not spec: continue
                col, _, d = spec.partition('.')
                rows.sort(key=lambda r: (r.get(col) is None, str(r.get(col) or '')), reverse=(d == 'desc'))
            if 'limit' in q: rows = rows[:int(q['limit'][0])]
            sel = q.get('select', ['*'])[0]
            if sel != '*': cols = sel.split(','); rows = [{c: r.get(c) for c in cols} for r in rows]
            return 200, json.loads(json.dumps(rows))
        if t == 'business_daily_stats': raise Fail(403, '42501', 'permission denied for table business_daily_stats')
        if method == 'POST':
            b = dict(body or {})
            if set(b) - (BIZ_INSERT if t == 'businesses' else PROMO_INSERT): raise Fail(403, '42501', 'permission denied for table ' + t)
            row = self.new_biz(b, uid, susp) if t == 'businesses' else self.new_promo(b, uid, susp)
            self.tables[t].append(row)
            return (201, [json.loads(json.dumps(row))]) if rep else (201, None)
        if method == 'PATCH':
            b = dict(body or {})
            if set(b) - (BIZ_UPDATE if t == 'businesses' else PROMO_UPDATE): raise Fail(403, '42501', 'permission denied for table ' + t)
            if self.fail_patch and t == 'businesses': raise Fail(500, 'XX000', 'fallo simulado')
            if susp: return (200, []) if rep else (204, None)
            for r in rows:
                new = {**r, **b}
                if t == 'businesses': self.check_biz(new, r)
                else: self.check_promo(new)
                r.update(b); r['updated_at'] = now_iso()
            return (200, json.loads(json.dumps(rows))) if rep else (204, None)
        if method == 'DELETE':
            if susp: return (200, []) if rep else (204, None)
            for r in rows:
                self.tables[t].remove(r)
                if t == 'businesses':
                    for c in ('business_promotions', 'business_daily_stats'): self.tables[c] = [x for x in self.tables[c] if x['business_id'] != r['id']]
            return (200, json.loads(json.dumps(rows))) if rep else (204, None)
        raise Fail(405, 'PGRST000', 'method not allowed')

    def filtered(self, rows, q):
        for k, v in q.items():
            if k in ('select', 'order', 'limit') or not v: continue
            op, _, val = v[0].partition('.')
            if op == 'eq': rows = [r for r in rows if str(r.get(k)) == val]
            elif op == 'gte':
                if k == 'created_at':
                    lim = datetime.datetime.fromisoformat(val)
                    rows = [r for r in rows if datetime.datetime.fromisoformat(r[k]) >= lim]
                else: rows = [r for r in rows if str(r.get(k)) >= val]
        return rows

    # ---------------- establecimientos ----------------
    def new_biz(self, b, uid, susp):
        if susp: raise Fail(403, '42501', 'new row violates row-level security policy for table "businesses"')
        if self.profiles[uid]['account_type'] != 'business': raise Fail(403, '42501', 'Solo las cuentas de aliado comercial pueden registrar un establecimiento.')
        if sum(1 for x in self.tables['businesses'] if x['owner_id'] == uid) >= 5: raise Fail(400, 'P0001', 'Alcanzaste el límite de establecimientos por cuenta.')
        row = dict(id=b.get('id') or str(uuid.uuid4()), owner_id=uid, is_demo=False, name=b.get('name'), category=b.get('category'), description=b.get('description'),
                   address=b.get('address'), state=b.get('state'), municipality=b.get('municipality'), phone=b.get('phone'), whatsapp_url=b.get('whatsapp_url'),
                   maps_query=b.get('maps_query'), logo_path=b.get('logo_path'), photo_paths=b.get('photo_paths') or [], hours=b.get('hours') or {},
                   status='pending', verified=False, verified_at=None, created_at=now_iso(), updated_at=now_iso())
        self.check_biz(row, None); return row

    def check_biz(self, r, old):
        def bad(msg='new row for relation "businesses" violates check constraint'): raise Fail(400, '23514', msg)
        if not (2 <= len((r.get('name') or '').strip()) <= 100) or r.get('category') not in CATEGORIES: bad()
        for col, mx in (('description', 1000), ('address', 200), ('state', 80), ('municipality', 80), ('maps_query', 200), ('logo_path', 300)):
            if r.get(col) is not None and len(r[col]) > mx: bad()
        if r.get('phone') is not None and not PHONE_RE.match(r['phone']): bad()
        if r.get('whatsapp_url') is not None and not WA_RE.match(r['whatsapp_url']): bad()
        if not isinstance(r.get('photo_paths'), list) or len(r['photo_paths']) > 6: bad()
        if not isinstance(r.get('hours'), dict): bad()
        own = r['owner_id']; pat = re.compile('^' + re.escape(own) + r'/[A-Za-z0-9._-]{1,120}$')
        okp = lambda x: bool(pat.match(x)) and '..' not in x
        if (old is None or r.get('logo_path') != old.get('logo_path')) and r.get('logo_path') is not None and not okp(r['logo_path']): bad('El logotipo no es válido.')
        if (old is None or r.get('photo_paths') != old.get('photo_paths')) and not all(okp(x) for x in r['photo_paths']): bad('Una de las fotos no es válida.')
        if old is None or r['hours'] != old.get('hours'):
            if len(r['hours']) > 10 or any(not isinstance(v, str) or len(k) > 20 or len(v) > 60 for k, v in r['hours'].items()): bad('El horario no es válido.')
        if r.get('whatsapp_url') is not None and (old is None or r['whatsapp_url'] != old.get('whatsapp_url')):
            pl = self.eff_plan(own)
            if not pl or not pl.get('whatsapp_button'): raise Fail(400, 'P0001', 'Tu plan no incluye el botón directo a WhatsApp.')

    # ---------------- promociones ----------------
    def new_promo(self, b, uid, susp):
        if susp or self.biz_owner(b.get('business_id')) != uid: raise Fail(403, '42501', 'new row violates row-level security policy for table "business_promotions"')
        pl = self.eff_plan(uid)
        if not pl: raise Fail(400, 'P0001', 'Necesitas un plan de aliado para publicar promociones.')
        lim = pl.get('max_promotions_per_month')
        if lim is not None:
            ms = month_start_utc()
            used = sum(1 for x in self.tables['business_promotions'] if self.biz_owner(x['business_id']) == uid and datetime.datetime.fromisoformat(x['created_at']) >= ms)
            if used >= lim: raise Fail(400, 'P0001', 'Tu plan permite %d promoción(es) al mes y ya las usaste.' % lim)
        row = dict(id=str(uuid.uuid4()), business_id=b['business_id'], title=b.get('title'), description=b.get('description'),
                   starts_on=b.get('starts_on') or today_mx().isoformat(), ends_on=b.get('ends_on'), is_active=b.get('is_active', True),
                   created_at=now_iso(), updated_at=now_iso())
        self.check_promo(row); return row

    def check_promo(self, r):
        def bad(): raise Fail(400, '23514', 'new row for relation "business_promotions" violates check constraint')
        if not (3 <= len((r.get('title') or '').strip()) <= 100): bad()
        if r.get('description') is not None and len(r['description']) > 500: bad()
        if not (r.get('starts_on') and r.get('ends_on') and DATE_RE.match(r['starts_on']) and DATE_RE.match(r['ends_on'])): bad()
        s = datetime.date.fromisoformat(r['starts_on']); e = datetime.date.fromisoformat(r['ends_on'])
        if e < s or e > s + datetime.timedelta(days=366): bad()

    # ---------------- directorio público ----------------
    def promo_live(self, b):
        t = today_mx().isoformat()
        return [p for p in self.tables['business_promotions'] if p['business_id'] == b['id'] and p['is_active'] and p['starts_on'] <= t <= p['ends_on']]

    def dir_search(self, a):
        cat = a.get('p_category')
        if cat is not None and cat not in CATEGORIES: raise Fail(400, '22023', 'Categoría no válida.')
        order = a.get('p_order') or 'priority'
        if order not in ('priority', 'name', 'recent'): raise Fail(400, '22023', 'Orden no válido.')
        qq = (a.get('p_query') or '').strip().lower()
        lim = min(max(a.get('p_limit') or 24, 1), 50); off = max(a.get('p_offset') or 0, 0)
        rows = [b for b in self.tables['businesses'] if b['status'] == 'approved' and (cat is None or b['category'] == cat)
                and (not qq or qq in b['name'].lower() or qq in (b['description'] or '').lower() or qq in (b['municipality'] or '').lower())]
        pl = lambda b: self.eff_plan(b['owner_id']) if b['owner_id'] else None
        rows.sort(key=lambda b: (b['name'].lower(), b['id']))
        if order == 'recent': rows.sort(key=lambda b: b['created_at'], reverse=True)
        if order == 'priority': rows.sort(key=lambda b: 0 if (pl(b) or {}).get('priority_listing') else 1)
        total = len(rows); out = []
        for b in rows[off:off + lim]:
            p = pl(b) or {}; full = p.get('audience') == 'business'
            out.append(dict(id=b['id'], name=b['name'], category=b['category'], description=b['description'], address=b['address'], state=b['state'],
                            municipality=b['municipality'], phone=b['phone'] if full else None, whatsapp_url=b['whatsapp_url'] if p.get('whatsapp_button') else None,
                            maps_query=b['maps_query'], logo_path=b['logo_path'] if full else None, hours=b['hours'] if full else {},
                            verified=bool(b['verified'] and p.get('verified_badge_eligible')), is_demo=b['is_demo'], is_priority=bool(p.get('priority_listing')),
                            full_listing=full, has_promotion=bool(full and self.promo_live(b)), total_count=total))
        return out

    def dir_get(self, i):
        b = self.biz_by_id(i)
        if not b or b['status'] != 'approved': return None
        p = (self.eff_plan(b['owner_id']) if b['owner_id'] else None) or {}; full = p.get('audience') == 'business'
        return dict(id=b['id'], name=b['name'], category=b['category'], description=b['description'], address=b['address'], state=b['state'], municipality=b['municipality'],
                    full_listing=full, phone=b['phone'] if full else None, whatsapp_url=b['whatsapp_url'] if p.get('whatsapp_button') else None, maps_query=b['maps_query'],
                    logo_path=b['logo_path'] if full else None, photo_paths=list(b['photo_paths']) if full else [], hours=b['hours'] if full else {},
                    verified=bool(b['verified'] and p.get('verified_badge_eligible')), is_demo=b['is_demo'],
                    promotions=[dict(id=x['id'], title=x['title'], description=x['description'], starts_on=x['starts_on'], ends_on=x['ends_on'])
                                for x in sorted(self.promo_live(b), key=lambda x: x['ends_on'])] if full else [])

    def dir_track(self, u, a):
        i, ev = a.get('p_id'), a.get('p_event')
        if not i or ev not in ('view', 'map'): return
        b = self.biz_by_id(i)
        if not b or b['status'] != 'approved' or b['is_demo']: return
        if b['owner_id'] and u and b['owner_id'] == u['id']: return
        key = (self.client_ip, ev, i, today_mx().isoformat())
        if self.track_seen.get(key, 0) >= (1 if ev == 'view' else 3): return
        self.track_seen[key] = self.track_seen.get(key, 0) + 1
        d = today_mx().isoformat()
        row = next((s for s in self.tables['business_daily_stats'] if s['business_id'] == i and s['day'] == d), None)
        if not row: row = dict(business_id=i, day=d, views=0, map_clicks=0); self.tables['business_daily_stats'].append(row)
        if ev == 'view': row['views'] += 1
        else: row['map_clicks'] += 1
