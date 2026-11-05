"""
Simulador de la Etapa 8 SOLO para pruebas de interfaz de las notificaciones.

Qué es REAL aquí: la tabla notifications, las políticas RLS, los permisos por columna, el disparador que solo deja marcar «leída»,
las funciones generate_my_reminders / private.notify / private.notify_admins y la columna profiles.notification_prefs. Cada petición de la
página a /rest/v1/notifications, /rest/v1/rpc/generate_my_reminders y a /rest/v1/profiles con «notification_prefs» se TRADUCE a SQL y se
ejecuta en un PostgreSQL local con el esquema de database/00_instalar_todo.sql, como el rol «authenticated» y con el identificador de la
persona (igual que hace PostgREST). El chat (Etapa 7) sigue funcionando igual porque esta clase hereda de Backend7.

Qué es SIMULADO: PostgREST (solo entiende las consultas que usan js/pages/notificaciones.js y js/layout.js; cualquier otra devuelve un
error ruidoso para que la prueba falle y no se pierda un cambio) y Supabase Auth (mock_supabase.Backend).

Como PostgREST con la extensión de seguridad de Supabase, un DELETE o PATCH SIN filtro se rechaza.
"""
import json, re, urllib.parse
from mock_etapa7 import Backend7, UUID_RE

NCOLS = {'id', 'user_id', 'type', 'title', 'body', 'link', 'is_read', 'read_at', 'dedupe_key', 'email_status', 'created_at'}
CAST = {'id': 'uuid', 'user_id': 'uuid', 'is_read': 'boolean', 'created_at': 'timestamptz', 'read_at': 'timestamptz'}
PCOLS = {'id', 'display_name', 'account_type', 'avatar_path', 'phone', 'notification_prefs', 'email_reminders', 'is_suspended', 'created_at', 'updated_at'}


class Backend8(Backend7):
    def __init__(self, key, db, psql_env=None):
        self.n_log = []                                       # peticiones a notifications / generate_my_reminders / profiles(prefs)
        super().__init__(key, db, psql_env)

    # ---------- datos de prueba (como superusuario: igual que lo haría el servidor) ----------
    def notify(self, uid, typ='aviso', title='Aviso de prueba', body=None, link=None, read=False, ago_min=0, dedupe=None):
        q = lambda v: 'null' if v is None else "'" + str(v).replace("'", "''") + "'"
        return self.sql(
            "insert into public.notifications (user_id, type, title, body, link, is_read, read_at, dedupe_key, created_at) values "
            f"('{uid}', '{typ}', {q(title)}, {q(body)}, {q(link)}, {'true' if read else 'false'}, {'now()' if read else 'null'}, {q(dedupe)}, now() - interval '{int(ago_min)} minutes') returning id")

    def notify_many(self, uid, n, prefix='Notificación', read=False, start_ago=1):
        self.sql(f"insert into public.notifications (user_id, type, title, is_read, read_at, created_at) "
                 f"select '{uid}', 'aviso', '{prefix} ' || g, {'true' if read else 'false'}, {'now()' if read else 'null'}, now() - ((g + {start_ago}) || ' minutes')::interval from generate_series(1, {n}) g")

    def notif(self, id_):
        out = self.sql(f"select to_jsonb(t) from public.notifications t where id = '{id_}'")
        return json.loads(out) if out else None

    def count(self, where='true'):
        return int(self.sql(f'select count(*) from public.notifications where {where}'))

    def prefs(self, uid):
        return json.loads(self.sql(f"select notification_prefs from public.profiles where id = '{uid}'"))

    def set_prefs(self, uid, **kw):
        cur = self.prefs(uid); cur.update(kw)
        self.sql(f"update public.profiles set notification_prefs = '{json.dumps(cur)}'::jsonb where id = '{uid}'")

    def add_pet(self, uid, name='Nube', species='perro'):
        return self.sql(f"insert into public.pets (owner_id, name, species) values ('{uid}', '{name}', '{species}') returning id")

    def reset_db(self):
        self.sql("truncate public.messages, public.conversations, public.notifications, public.pets restart identity cascade; "
                 "truncate private.reminder_log, private.rate_limits; "
                 "update public.profiles set notification_prefs = jsonb_build_object('vacuna', true, 'desparasitacion', true, 'cita', true, 'promocion', true, 'suscripcion', true, 'mensaje', true, 'aviso', true)")

    # ---------- traducción mínima de PostgREST ----------
    def _ncols(self, q, table_cols):
        sel = q.get('select', ['*'])[0]
        if sel == '*':
            return '*'
        cols = sel.split(',')
        if not all(c in table_cols for c in cols):
            raise ValueError('select no soportado: ' + sel)
        return ','.join(cols)

    def _nwhere(self, q, variables):
        conds = []
        for k, vals in q.items():
            if k in ('select', 'order', 'limit', 'offset'):
                continue
            v = vals[0]
            if k == 'or':
                m = re.fullmatch(r'\(created_at\.lt\.(.+),and\(created_at\.eq\.(.+),id\.lt\.([0-9a-f-]{36})\)\)', v)
                if not m or m.group(1) != m.group(2) or not UUID_RE.match(m.group(3)):
                    raise ValueError('or= no soportado: ' + v)
                variables['ts'] = m.group(1); variables['lid'] = m.group(3)
                conds.append("(created_at < :'ts'::timestamptz or (created_at = :'ts'::timestamptz and id < :'lid'::uuid))")
            elif k in NCOLS:
                m = re.fullmatch(r'(eq|lt|gt)\.(.+)', v)
                if not m:
                    raise ValueError('filtro no soportado: %s=%s' % (k, v))
                op = {'eq': '=', 'lt': '<', 'gt': '>'}[m.group(1)]
                nm = 'f_' + k
                variables[nm] = m.group(2)
                conds.append(f"{k} {op} :'{nm}'::{CAST.get(k, 'text')}")
            else:
                raise ValueError('columna/parámetro no soportado: ' + k)
        return (' where ' + ' and '.join(conds)) if conds else ''

    def _norder(self, q):
        o = q.get('order', [''])[0]
        if not o:
            return ''
        parts = []
        for it in o.split(','):
            m = re.fullmatch(r'([a-z_]+)\.(asc|desc)', it)
            if not m or m.group(1) not in NCOLS:
                raise ValueError('order no soportado: ' + o)
            parts.append(f'{m.group(1)} {m.group(2)}')
        return ' order by ' + ', '.join(parts)

    @staticmethod
    def _prefs_request(method, query, body):
        q = urllib.parse.parse_qs(query)
        if method == 'GET':
            return 'notification_prefs' in q.get('select', [''])[0]
        return isinstance(body, dict) and 'notification_prefs' in body

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); path = p.path
        h = {k.lower(): v for k, v in headers.items()}
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        mine = (path in ('/rest/v1/notifications', '/rest/v1/rpc/generate_my_reminders')
                or (path == '/rest/v1/profiles' and self._prefs_request(method, p.query, body)))
        if not mine or h.get('apikey') != self.key:
            return super().handle(method, url, headers, body_text)
        self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
        rec = dict(method=method, path=path, query=p.query, body=body)
        self.rest_log.append(rec); self.n_log.append(rec)
        if self.fail_rest:
            r = self.fail_rest(path, method)
            if r: return r
        u = self.user_for(h)
        if 'authorization' in h and not u:
            return 401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)
        q = urllib.parse.parse_qs(p.query)
        uid = u['id'] if u else None
        variables = {}
        want_rep = 'return=representation' in h.get('prefer', '')
        try:
            if path == '/rest/v1/rpc/generate_my_reminders':
                if method != 'POST' or body not in ({}, None):
                    return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
                ok, out = self.psql('select to_json(public.generate_my_reminders());', variables, uid)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            if path == '/rest/v1/profiles':
                where = self._pwhere(q, variables)
                if method == 'GET':
                    cols = self._ncols(q, PCOLS)
                    script = f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from (select {cols} from public.profiles{where}) t;"
                    ok, out = self.psql(script, variables, uid)
                    if not ok: return self._pg_error(out)
                    rows = json.loads(out)
                    if 'pgrst.object' in h.get('accept', ''):
                        return (200, rows[0]) if len(rows) == 1 else (406, dict(code='PGRST116', message='JSON object requested, multiple (or no) rows returned', details=None, hint=None))
                    return 200, rows
                if method == 'PATCH':
                    if not where: return 400, dict(code='21000', message='UPDATE requires a WHERE clause', details=None, hint=None)
                    sets = []
                    for i, (k, v) in enumerate(body.items()):
                        if k not in PCOLS: return 400, dict(code='PGRST204', message='Could not find a column in the schema cache', details=None, hint=None)
                        variables[f'v{i}'] = json.dumps(v) if isinstance(v, (dict, list)) else str(v).lower() if isinstance(v, bool) else v
                        sets.append(f"{k} = :'v{i}'" + ('::jsonb' if k == 'notification_prefs' else '::boolean' if isinstance(v, bool) else ''))
                    script = f"with u as (update public.profiles set {', '.join(sets)}{where} returning *) select coalesce(json_agg(to_jsonb(u)), '[]'::json) from u;"
                    ok, out = self.psql(script, variables, uid)
                    if not ok: return self._pg_error(out)
                    return 200, json.loads(out)
                return 405, dict(code='PGRST000', message='MOCK_UNSUPPORTED %s %s' % (method, path), details=None, hint=None)
            # ---- notifications ----
            where = self._nwhere(q, variables)
            if method == 'GET':
                cols = self._ncols(q, NCOLS)
                lim = q.get('limit', [''])[0]
                limit = f' limit {int(lim)}' if lim.isdigit() else ''
                script = f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from (select {cols} from public.notifications{where}{self._norder(q)}{limit}) t;"
                self.sql_log.append(('GET', path, script))
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            if method in ('PATCH', 'DELETE') and not where:
                return 400, dict(code='21000', message=f'{"UPDATE" if method == "PATCH" else "DELETE"} requires a WHERE clause', details=None, hint=None)
            cols = self._ncols(q, NCOLS)
            if method == 'PATCH':
                if not isinstance(body, dict) or not body or any(k not in NCOLS for k in body):
                    return 400, dict(code='PGRST102', message='bad body', details=None, hint=None)
                sets = []
                for i, (k, v) in enumerate(body.items()):
                    variables[f'v{i}'] = str(v).lower() if isinstance(v, bool) else v
                    sets.append(f"{k} = :'v{i}'::{CAST.get(k, 'text')}")
                script = f"with u as (update public.notifications set {', '.join(sets)}{where} returning {cols}) select coalesce(json_agg(to_jsonb(u)), '[]'::json) from u;"
            elif method == 'DELETE':
                script = f"with d as (delete from public.notifications{where} returning {cols}) select coalesce(json_agg(to_jsonb(d)), '[]'::json) from d;"
            else:
                return 405, dict(code='PGRST000', message='MOCK_UNSUPPORTED %s %s' % (method, path), details=None, hint=None)
            ok, out = self.psql(script, variables, uid)
            if not ok: return self._pg_error(out)
            rows = json.loads(out)
            return (200, rows) if want_rep else (204, None)
        except ValueError as e:
            return 400, dict(code='MOCK_UNSUPPORTED', message=str(e), details=None, hint=None)

    def _pwhere(self, q, variables):
        conds = []
        for k, vals in q.items():
            if k == 'select':
                continue
            m = re.fullmatch(r'eq\.(.+)', vals[0])
            if k != 'id' or not m or not UUID_RE.match(m.group(1)):
                raise ValueError('filtro de profiles no soportado: %s=%s' % (k, vals[0]))
            variables['pid'] = m.group(1); conds.append("id = :'pid'::uuid")
        return (' where ' + ' and '.join(conds)) if conds else ''
