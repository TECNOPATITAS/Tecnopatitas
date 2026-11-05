"""
Simulador de la Etapa 10 SOLO para pruebas de interfaz del panel de administración (admin.html) y de las guías públicas (guias.html).

Qué es REAL aquí: TODAS las funciones admin_* (usuarios, aliados, denuncias, guías, suscripciones, solicitudes de plan, atención al cliente
y bitácora), private.require_admin, la bitácora, los disparadores, las políticas RLS y los permisos. Cada llamada a
/rest/v1/rpc/admin_<función> se TRADUCE a SQL y se ejecuta en un PostgreSQL local con el esquema de database/00_instalar_todo.sql, con el
rol «authenticated» y el identificador de la persona (igual que hace PostgREST); por eso una cuenta que no es administradora recibe el
MISMO error 42501 «No autorizado.» que daría el servidor real. Las guías públicas se leen como el rol «anon» (la política solo deja ver las
publicadas). Las notificaciones y la campana (Etapa 8), el chat (7) y los planes (9) siguen funcionando porque esta clase hereda de Backend9.

Qué es SIMULADO: PostgREST (solo entiende estas funciones y la lectura de care_guides; cualquier otra cosa devuelve un error ruidoso para que
la prueba falle y no se pierda un cambio), Supabase Auth (mock_supabase.Backend) y Storage (las fotos de evidencia de una denuncia solo se
firman para quien sea administrador).
"""
import json, re, subprocess, urllib.parse
from mock_etapa9 import Backend9
from mock_etapa7 import UUID_RE

# función -> (tipo de resultado, {argumento: tipo})
ADMIN_RPC = {
    'admin_dashboard_stats': ('jsonb', {}),
    'admin_list_users': ('table', {'p_search': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_get_user': ('jsonb', {'p_user': 'uuid'}),
    'admin_set_user_suspended': ('void', {'p_user': 'uuid', 'p_suspended': 'boolean', 'p_reason': 'text'}),
    'admin_list_businesses': ('table', {'p_status': 'text', 'p_search': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_get_business': ('jsonb', {'p_id': 'uuid'}),
    'admin_set_business_status': ('void', {'p_business': 'uuid', 'p_status': 'text'}),
    'admin_set_business_verified': ('void', {'p_business': 'uuid', 'p_verified': 'boolean'}),
    'admin_delete_promotion': ('void', {'p_promo': 'uuid', 'p_reason': 'text'}),
    'admin_list_complaints': ('table', {'p_status': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_get_complaint': ('jsonb', {'p_id': 'uuid'}),
    'admin_update_complaint': ('void', {'p_id': 'uuid', 'p_status': 'text', 'p_priority': 'text', 'p_attended': 'boolean',
                                        'p_public_update': 'text', 'p_internal_notes': 'text'}),
    'admin_list_guides': ('table', {'p_search': 'text', 'p_state': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_get_guide': ('jsonb', {'p_id': 'uuid'}),
    'admin_save_guide': ('scalar', {'p_id': 'uuid', 'p_slug': 'text', 'p_title': 'text', 'p_summary': 'text', 'p_content': 'text',
                                    'p_category': 'text', 'p_author_source': 'text', 'p_publish': 'boolean'}),
    'admin_delete_guide': ('void', {'p_id': 'uuid'}),
    'admin_list_plan_requests': ('table', {'p_status': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_resolve_plan_request': ('scalar', {'p_request': 'uuid', 'p_approve': 'boolean', 'p_note': 'text', 'p_ends': 'timestamptz'}),
    'admin_list_subscriptions': ('table', {'p_status': 'text', 'p_search': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_assign_subscription': ('scalar', {'p_user': 'uuid', 'p_plan': 'text', 'p_period': 'text', 'p_starts': 'timestamptz',
                                             'p_ends': 'timestamptz', 'p_note': 'text'}),
    'admin_cancel_subscription': ('void', {'p_user': 'uuid', 'p_note': 'text'}),
    'admin_renew_subscription': ('scalar', {'p_subscription': 'uuid', 'p_note': 'text'}),
    'admin_set_subscription_dates': ('void', {'p_subscription': 'uuid', 'p_starts': 'timestamptz', 'p_ends': 'timestamptz'}),
    'admin_list_conversations': ('table', {'p_filter': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
    'admin_get_conversation': ('jsonb', {'p_id': 'uuid'}),
    'admin_reply_conversation': ('scalar', {'p_conversation': 'uuid', 'p_body': 'text'}),
    'admin_set_conversation_status': ('void', {'p_conversation': 'uuid', 'p_status': 'text'}),
    'admin_list_audit': ('table', {'p_prefix': 'text', 'p_limit': 'integer', 'p_offset': 'integer'}),
}
GCOLS = {'slug', 'title', 'summary', 'category', 'author_source', 'published_at', 'content', 'is_published', 'id'}
GCAST = {'is_published': 'boolean', 'id': 'uuid', 'published_at': 'timestamptz'}
SIGN_RE = re.compile(r'^/storage/v1/object/sign/complaint-evidence$')


def q(v):
    return 'null' if v is None else "'" + str(v).replace("'", "''") + "'"


class Backend10(Backend9):
    def __init__(self, key, db, psql_env=None):
        self.a_log = []                                       # llamadas admin_* y lecturas de guías
        self.sign_log = []                                    # firmas de fotos de evidencia
        super().__init__(key, db, psql_env)
        self.storage_fail = None                              # p. ej. 500 para simular un fallo de Storage
        self.objects = {}                                     # (bucket, ruta) -> dict(owner, size, type, data)

    # ---------- datos de prueba (como superusuario: igual que lo haría el equipo desde el editor SQL) ----------
    def reset_db(self):
        super().reset_db()
        self.sql("truncate public.business_promotions, public.businesses, public.complaints, public.care_guides, public.admin_audit_log "
                 "restart identity cascade")
        self.objects = {}
        # cuentas de prueba como al inicio (los grupos anteriores pudieron suspenderlas)
        susp = ', '.join("'%s'" % uid for uid, p in self.profiles.items() if p.get('is_suspended')) or "'00000000-0000-0000-0000-000000000000'"
        self.sql(f"update public.profiles set is_suspended = (id::text in ({susp}))")

    def psql_anon(self, script, variables=None):
        """Como PostgREST sin sesión: rol «anon»."""
        args = ['psql', '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', '-d', self.db]
        for k, v in (variables or {}).items(): args += ['-v', f'{k}={v}']
        r = subprocess.run(args, input='begin;\nset local role anon;\n' + script + '\ncommit;\n', capture_output=True, text=True)
        return (False, r.stderr) if r.returncode else (True, r.stdout.strip())

    def add_biz(self, owner, name='Veterinaria Patitas', category='veterinaria', status='pending', demo=False, **kw):
        cols = dict(name=name, category=category, status=status, description='Atendemos mascotas con cariño.', address='Calle 5 #10',
                    state='Jalisco', municipality='Zapopan', phone='3312345678', is_demo=demo)
        cols.update(kw)
        if owner: cols['owner_id'] = owner
        keys = list(cols)
        vals = ', '.join('true' if cols[k] is True else 'false' if cols[k] is False else q(cols[k]) for k in keys)
        bid = self.sql(f"insert into public.businesses ({', '.join(keys)}) values ({vals}) returning id")
        if status == 'approved' and kw.get('verified'):
            self.sql(f"update public.businesses set verified_at = now() where id = '{bid}'")
        return bid

    def add_promo(self, biz, title='2x1 en baños', description='Válida entre semana', days=10, active=True):
        return self.sql("insert into public.business_promotions (business_id, title, description, starts_on, ends_on, is_active) values "
                        f"('{biz}', {q(title)}, {q(description)}, (now() at time zone 'America/Mexico_City')::date, (now() at time zone 'America/Mexico_City')::date + {int(days)}, {'true' if active else 'false'}) returning id")

    def add_complaint(self, code='TP-ABCD-EFGH', type_='abandono', status='recibida', description='Un perro lleva días sin agua ni comida en un patio.',
                      state='Jalisco', municipality='Zapopan', photos=0, ago_min=0, priority=None, extra=None, ref='Frente a la tienda azul'):
        paths = []
        folder = self.sql('select gen_random_uuid()')
        for i in range(photos):
            p = f'{folder}/{i + 1}.jpg'; paths.append(p)
            self.objects[('complaint-evidence', p)] = dict(owner=None, size=4, type='image/jpeg', data=b'\xff\xd8\xff\xd9')
        arr = "array[" + ', '.join(q(p) for p in paths) + "]::text[]" if paths else "'{}'::text[]"
        return self.sql("insert into public.complaints (tracking_code, type, description, approx_date, state, municipality, location_reference, extra_info, photo_paths, status, priority, created_at) "
                        f"values ({q(code)}, {q(type_)}, {q(description)}, current_date - 2, {q(state)}, {q(municipality)}, {q(ref)}, {q(extra)}, {arr}, {q(status)}, {q(priority)}, now() - interval '{int(ago_min)} minutes') returning id")

    def add_guide(self, slug='cuidados-del-gato', title='Cuidados del gato', category='gatos', published=True, content='Primer párrafo.\n\nSegundo párrafo.',
                  summary='Resumen de la guía', source='Contenido general de ejemplo', ago_min=0):
        return self.sql("insert into public.care_guides (slug, title, summary, content, category, author_source, is_published, published_at, updated_at) values "
                        f"({q(slug)}, {q(title)}, {q(summary)}, {q(content)}, {q(category)}, {q(source)}, {'true' if published else 'false'}, "
                        f"{('now() - interval ' + q(str(int(ago_min)) + ' minutes')) if published else 'null'}, now() - interval '{int(ago_min)} minutes') returning id")

    def add_conv(self, user, subject='Duda sobre mi plan', body='Hola, tengo una pregunta', status='abierta', ago_min=0):
        cid = self.sql(f"insert into public.conversations (user_id, subject) values ('{user}', {q(subject)}) returning id")
        self.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{cid}', '{user}', {q(body)})")
        if ago_min: self.sql(f"update public.conversations set last_message_at = now() - interval '{int(ago_min)} minutes' where id = '{cid}'")
        if status == 'cerrada': self.sql(f"update public.conversations set status = 'cerrada' where id = '{cid}'")
        return cid

    def staff_reply(self, cid, admin, body='Con gusto te ayudamos'):
        self.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{cid}', '{admin}', {q(body)})")

    def audit_rows(self, action=None):
        w = f"where action = {q(action)}" if action else ''
        return json.loads(self.sql(f"select coalesce(json_agg(to_jsonb(a) order by id), '[]'::json) from public.admin_audit_log a {w}"))

    def one(self, table, id_):
        out = self.sql(f"select to_jsonb(t) from public.{table} t where id = '{id_}'")
        return json.loads(out) if out else None

    # ---------- traducción de PostgREST ----------
    def _guides_get(self, p, uid):
        qs = urllib.parse.parse_qs(p.query); variables = {}
        sel = qs.get('select', ['*'])[0]
        cols = sorted(GCOLS) if sel == '*' else sel.split(',')
        if not all(c in GCOLS for c in cols): raise ValueError('select no soportado: ' + sel)
        conds = []
        for k, vals in qs.items():
            if k in ('select', 'order', 'limit'): continue
            m = re.fullmatch(r'eq\.(.+)', vals[0])
            if k not in GCOLS or not m: raise ValueError('filtro no soportado: %s=%s' % (k, vals[0]))
            variables['f_' + k] = m.group(1); conds.append(f"{k} = :'f_{k}'::{GCAST.get(k, 'text')}")
        order = ''
        if qs.get('order'):
            parts = []
            for it in qs['order'][0].split(','):
                m = re.fullmatch(r'([a-z_]+)\.(asc|desc)', it)
                if not m or m.group(1) not in GCOLS: raise ValueError('order no soportado: ' + qs['order'][0])
                parts.append(f'{m.group(1)} {m.group(2)}')
            order = ' order by ' + ', '.join(parts)
        lim = qs.get('limit', [''])[0]
        script = (f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from (select {','.join(cols)} from public.care_guides"
                  f"{(' where ' + ' and '.join(conds)) if conds else ''}{order}{(' limit ' + str(int(lim))) if lim.isdigit() else ''}) t;")
        self.sql_log.append(('GET', p.path, script))
        return self.psql(script, variables, uid) if uid else self.psql_anon(script, variables)

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); path = p.path
        h = {k.lower(): v for k, v in headers.items()}
        if path.startswith('/storage/v1/'):
            return self.storage(method, path, p.query, h, body_text)
        fn = path[len('/rest/v1/rpc/'):] if path.startswith('/rest/v1/rpc/') else None
        mine = (fn in ADMIN_RPC) or path == '/rest/v1/care_guides' or (fn or '').startswith('admin_')
        if not mine or h.get('apikey') != self.key:
            return super().handle(method, url, headers, body_text)
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
        rec = dict(method=method, path=path, query=p.query, body=body, auth='authorization' in h)
        self.rest_log.append(rec); self.a_log.append(rec)
        if self.fail_rest:
            r = self.fail_rest(path, method)
            if r: return r
        u = self.user_for(h)
        if 'authorization' in h and not u:
            return 401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)
        try:
            if path == '/rest/v1/care_guides':
                if method != 'GET': return 405, dict(code='42501', message='permission denied for table care_guides', details=None, hint=None)
                ok, out = self._guides_get(p, u['id'] if u else None)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            if fn not in ADMIN_RPC:
                return 404, dict(code='PGRST202', message='Could not find the function public.%s' % fn, details=None, hint=None)
            if not u:                                         # sin sesión: el rol «anon» no tiene permiso
                return 401, dict(code='42501', message='permission denied for function ' + fn, details=None, hint=None)
            kind, types = ADMIN_RPC[fn]
            if method != 'POST' or not (body is None or isinstance(body, dict)) or set(body or {}) - set(types):
                return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
            variables, args = {}, []
            for i, (k, v) in enumerate((body or {}).items()):
                if v is None: args.append(f'{k} => null'); continue
                variables[f'a{i}'] = ('true' if v else 'false') if isinstance(v, bool) else str(v)
                args.append(f"{k} => :'a{i}'::{types[k]}")
            call = f"public.{fn}({', '.join(args)})"
            if kind == 'table': script = f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from {call} t;"
            elif kind == 'void': script = f"select {call};"
            else: script = f"select to_json({call});"
            self.sql_log.append(('POST', path, script))
            ok, out = self.psql(script, variables, u['id'])
            if not ok: return self._pg_error(out)
            if kind == 'void': return 204, None
            return 200, json.loads(out) if out else None
        except ValueError as e:
            return 400, dict(code='MOCK_UNSUPPORTED', message=str(e), details=None, hint=None)

    # ---------- Storage: la evidencia de las denuncias solo se firma para administradores ----------
    def storage(self, method, path, query, h, body_text):
        err = lambda st, e, m: (st, dict(statusCode=str(st), error=e, message=m))
        if SIGN_RE.match(path) and method == 'POST':
            if self.storage_fail: return err(self.storage_fail, 'Internal', 'fallo simulado')
            u = self.user_for(h)
            if not u: return err(400, 'InvalidJWT', 'Invalid Compact JWS')
            try: body = json.loads(body_text) if body_text else {}
            except Exception: body = {}
            self.sign_log.append(dict(uid=u['id'], paths=list(body.get('paths', [])), expiresIn=body.get('expiresIn')))
            is_admin = self.sql(f"select exists (select 1 from public.admin_roles where user_id = '{u['id']}')") == 't'
            out = []
            for i, pth in enumerate(body.get('paths', [])):
                if is_admin and ('complaint-evidence', pth) in self.objects:
                    out.append(dict(path=pth, signedURL='/object/sign/complaint-evidence/%s?token=tok%d' % (urllib.parse.quote(pth), i), error=None))
                else:
                    out.append(dict(path=pth, signedURL=None, error='Either the object does not exist or you do not have access to it'))
            return 200, out
        m = re.match(r'^/storage/v1/object/sign/complaint-evidence/(.+)$', path)
        if m and method == 'GET':                              # descarga con enlace firmado
            o = self.objects.get(('complaint-evidence', urllib.parse.unquote(m.group(1))))
            if not o or 'token=' not in query: return err(400, 'InvalidJWT', 'invalid signature')
            return 200, o['data'], o['type']
        return err(404, 'not_found', 'Not found')
