"""
Simulador de la Etapa 7 SOLO para pruebas de interfaz del chat.

Qué es REAL aquí: las tablas conversations / messages, las políticas RLS, los permisos por columna, los disparadores (límites,
remitente fijado por el servidor, notificaciones) y la función start_conversation. Cada petición de la página a
/rest/v1/conversations, /rest/v1/messages y /rest/v1/rpc/start_conversation se TRADUCE a SQL y se ejecuta en un PostgreSQL local con el
esquema de database/00_instalar_todo.sql, como el rol «authenticated» y con el identificador de la persona (igual que hace PostgREST).

Qué es SIMULADO: PostgREST (solo entiende las consultas que usa js/pages/chat.js; cualquier otra devuelve un error ruidoso para que
la prueba falle y no se pierda un cambio) y Supabase Auth (mock_supabase.Backend).

Los errores de PostgreSQL se devuelven con el mismo formato y estado HTTP que PostgREST: {"code","details","hint","message"}.
"""
import json, re, subprocess, urllib.parse
from mock_supabase import Backend

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
COLS = {'conversations': {'id', 'user_id', 'subject', 'status', 'last_sender', 'last_message_at', 'created_at'},
        'messages': {'id', 'conversation_id', 'sender_id', 'sender_role', 'body', 'created_at'}}
HTTP_FOR = {'P0001': 400, '23514': 400, '23502': 400, '22P02': 400, '42501': 403, '23503': 409, '23505': 409}


class Backend7(Backend):
    def __init__(self, key, db, psql_env=None):
        self.db = db
        self.sql_log = []                                     # (método, ruta, consulta) de lo que llegó a la base
        self.rest_log = []                                    # peticiones REST a conversations / messages / rpc
        self.fail_rest = None                                 # función(path, method) -> (status, data) | None  (para simular caídas)
        super().__init__(key)

    # ---------- base de datos real ----------
    def psql(self, script, variables=None, uid=None):
        """Ejecuta SQL como 'authenticated' (si hay uid) o como superusuario. Devuelve (ok, texto de salida o error)."""
        pre = ''
        if uid:
            pre = ("\\o /dev/null\nbegin;\nselect set_config('request.jwt.claims', json_build_object('sub', :'uid'::text, 'role', 'authenticated')::text, true);\n"
                   "set local role authenticated;\n\\o\n")
        post = 'commit;\n' if uid else ''
        args = ['psql', '-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', '-d', self.db]
        for k, v in dict(variables or {}, **({'uid': uid} if uid else {})).items():
            args += ['-v', f'{k}={v}']
        r = subprocess.run(args, input=pre + script + '\n' + post, capture_output=True, text=True)
        if r.returncode:
            return False, r.stderr
        return True, r.stdout.strip()

    def sql(self, q):
        ok, out = self.psql(q)
        if not ok:
            raise RuntimeError(out)
        return out

    def add_user(self, email, password, account_type='owner', name='Usuario', admin=False, confirmed=True, suspended=False, phone=None):
        uid = super().add_user(email, password, account_type=account_type, name=name, admin=admin, confirmed=confirmed, suspended=suspended, phone=phone)
        meta = json.dumps({'display_name': name, 'account_type': account_type}).replace("'", "''")
        self.sql(f"insert into auth.users (id, email, raw_user_meta_data) values ('{uid}', '{email}', '{meta}')")
        if admin:
            self.sql(f"insert into public.admin_roles (user_id, note) values ('{uid}', 'admin de pruebas')")
        if suspended:
            self.sql(f"update public.profiles set is_suspended = true where id = '{uid}'")
        return uid

    def set_suspended(self, uid, on):
        self.sql(f"update public.profiles set is_suspended = {'true' if on else 'false'} where id = '{uid}'")
        self.profiles[uid]['is_suspended'] = on

    def staff_reply(self, conv_id, admin_uid, body):
        """Respuesta del equipo (como si se hiciera desde el editor SQL de Supabase). Devuelve la fila del mensaje."""
        b = body.replace("'", "''")
        return json.loads(self.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{conv_id}', '{admin_uid}', '{b}') returning to_jsonb(messages)"))

    def row(self, table, id_):
        out = self.sql(f"select to_jsonb(t) from public.{table} t where id = '{id_}'")
        return json.loads(out) if out else None

    def reset_db(self):
        self.sql("truncate public.messages, public.conversations, public.notifications restart identity cascade")

    # ---------- traducción mínima de PostgREST ----------
    def _cols(self, table, q):
        sel = q.get('select', ['*'])[0]
        if sel == '*':
            return '*'
        cols = sel.split(',')
        if not all(c in COLS[table] for c in cols):
            raise ValueError('select no soportado: ' + sel)
        return ','.join(cols)

    def _where(self, table, q, variables):
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
            elif k in COLS[table]:
                m = re.fullmatch(r'(eq|lt|gt)\.(.+)', v)
                if not m:
                    raise ValueError('filtro no soportado: %s=%s' % (k, v))
                op = {'eq': '=', 'lt': '<', 'gt': '>'}[m.group(1)]
                nm = 'f_' + k
                variables[nm] = m.group(2)
                cast = {'id': 'uuid', 'user_id': 'uuid', 'conversation_id': 'uuid', 'sender_id': 'uuid', 'created_at': 'timestamptz', 'last_message_at': 'timestamptz'}.get(k, 'text')
                conds.append(f"{k} {op} :'{nm}'::{cast}")
            else:
                raise ValueError('columna/parámetro no soportado: ' + k)
        return (' where ' + ' and '.join(conds)) if conds else ''

    def _order(self, table, q):
        o = q.get('order', [''])[0]
        if not o:
            return ''
        parts = []
        for it in o.split(','):
            m = re.fullmatch(r'([a-z_]+)\.(asc|desc)', it)
            if not m or m.group(1) not in COLS[table]:
                raise ValueError('order no soportado: ' + o)
            parts.append(f'{m.group(1)} {m.group(2)}')
        return ' order by ' + ', '.join(parts)

    def _pg_error(self, stderr):
        m = re.search(r'ERROR:\s+([0-9A-Z]{5}):\s*(.*)', stderr)
        code, msg = (m.group(1), m.group(2).strip()) if m else ('XX000', stderr[:200])
        return HTTP_FOR.get(code, 400), dict(code=code, details=None, hint=None, message=msg)

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); path = p.path
        h = {k.lower(): v for k, v in headers.items()}
        mine = re.fullmatch(r'/rest/v1/(conversations|messages)', path) or path == '/rest/v1/rpc/start_conversation'
        if not mine or h.get('apikey') != self.key:
            return super().handle(method, url, headers, body_text)
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
        self.rest_log.append(dict(method=method, path=path, query=p.query, body=body))
        if self.fail_rest:
            r = self.fail_rest(path, method)
            if r: return r
        u = self.user_for(h)
        if 'authorization' in h and not u:
            return 401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)
        q = urllib.parse.parse_qs(p.query)
        uid = u['id'] if u else None
        variables = {}
        try:
            if path == '/rest/v1/rpc/start_conversation':
                if method != 'POST' or not isinstance(body, dict) or set(body) - {'p_subject', 'p_body'}:
                    return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
                variables = {'s': body.get('p_subject') if body.get('p_subject') is not None else '', 'b': body.get('p_body') if body.get('p_body') is not None else ''}
                script = "select to_json(public.start_conversation(:'s', :'b'));"
                if body.get('p_subject') is None: script = "select to_json(public.start_conversation(null, :'b'));"
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            table = path.rsplit('/', 1)[1]
            if method == 'GET':
                cols = self._cols(table, q)
                where = self._where(table, q, variables)
                order = self._order(table, q)
                lim = q.get('limit', [''])[0]
                limit = f' limit {int(lim)}' if lim.isdigit() else ''
                script = f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from (select {cols} from public.{table}{where}{order}{limit}) t;"
                self.sql_log.append(('GET', path, script))
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            if method == 'POST' and table == 'messages':
                if not isinstance(body, dict) or not body or any(k not in COLS['messages'] for k in body):
                    return 400, dict(code='PGRST204', message='Could not find a column in the schema cache', details=None, hint=None)
                cols = list(body)
                for i, k in enumerate(cols): variables[f'v{i}'] = body[k] if isinstance(body[k], str) else json.dumps(body[k])
                script = ("with i as (insert into public.messages (%s) values (%s) returning *) select coalesce(json_agg(to_jsonb(i)), '[]'::json) from i;"
                          % (', '.join(cols), ', '.join(f":'v{i}'" for i in range(len(cols)))))
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                return 201, json.loads(out)
            if method == 'PATCH' and table == 'conversations':
                if not isinstance(body, dict) or not body or any(k not in COLS['conversations'] for k in body):
                    return 400, dict(code='PGRST102', message='bad body', details=None, hint=None)
                sets = []
                for i, (k, v) in enumerate(body.items()):
                    variables[f'v{i}'] = v; sets.append(f"{k} = :'v{i}'")
                where = self._where(table, q, variables)
                script = f"with u as (update public.conversations set {', '.join(sets)}{where} returning *) select coalesce(json_agg(to_jsonb(u)), '[]'::json) from u;"
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                return 200, json.loads(out)
            return 405, dict(code='PGRST000', message='MOCK_UNSUPPORTED %s %s' % (method, path), details=None, hint=None)
        except ValueError as e:
            return 400, dict(code='MOCK_UNSUPPORTED', message=str(e), details=None, hint=None)
