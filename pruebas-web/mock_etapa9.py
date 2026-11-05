"""
Simulador de la Etapa 9 SOLO para pruebas de interfaz de Suscripciones (planes y solicitudes, sin pagos).

Qué es REAL aquí: las tablas subscription_plans, subscriptions, subscription_events y plan_requests, las políticas RLS, los permisos
por columna y las funciones my_entitlements, request_plan, cancel_plan_request, cancel_my_subscription, private.resolve_plan_request,
private.assign_subscription y generate_my_reminders (avisos de vencimiento). Cada petición de la página a /rest/v1/plan_requests y a
/rest/v1/rpc/<función> se TRADUCE a SQL y se ejecuta en un PostgreSQL local con el esquema de database/00_instalar_todo.sql, como el rol
«authenticated» y con el identificador de la persona (igual que hace PostgREST). Las notificaciones y la campana (Etapa 8) siguen
funcionando igual porque esta clase hereda de Backend8.

Qué es SIMULADO: PostgREST (solo entiende las consultas que usa js/pages/planes.js; cualquier otra devuelve un error ruidoso para que
la prueba falle y no se pierda un cambio) y Supabase Auth (mock_supabase.Backend).

Una función que devuelve «void» responde 204 sin cuerpo, como PostgREST.
"""
import json, re, urllib.parse
from mock_etapa8 import Backend8
from mock_etapa7 import UUID_RE

RCOLS = {'id', 'user_id', 'plan_id', 'billing_period', 'status', 'user_note', 'admin_note', 'resolved_by', 'resolved_at', 'created_at'}
RCAST = {'id': 'uuid', 'user_id': 'uuid', 'resolved_by': 'uuid', 'resolved_at': 'timestamptz', 'created_at': 'timestamptz'}
RPC_ARGS = {'my_entitlements': set(), 'request_plan': {'p_plan', 'p_period', 'p_note'}, 'cancel_plan_request': {'p_request'},
            'cancel_my_subscription': set()}


class Backend9(Backend8):
    def __init__(self, key, db, psql_env=None):
        self.p_log = []                                       # peticiones a plan_requests / funciones de suscripción
        super().__init__(key, db, psql_env)

    # ---------- datos de prueba (como superusuario: igual que lo haría el equipo desde el editor SQL) ----------
    def reset_db(self):
        super().reset_db()
        self.sql("truncate public.plan_requests, public.subscription_events, public.subscriptions restart identity cascade; "
                 "truncate public.admin_audit_log restart identity")

    def assign(self, uid, plan, period='monthly', days=None, ends_sql=None, starts_ago_days=0):
        """Asigna un plan. days=None → vigencia normal (1 mes / 1 año); days=N → vence en N días; days=0 → sin vencimiento."""
        ends = 'null' if days == 0 else (f"now() + interval '{days} days'" if days is not None else ends_sql or 'null')
        if days is None and ends_sql is None:
            return self.sql(f"select private.assign_subscription('{uid}', '{plan}', '{period}')")
        starts = f"now() - interval '{starts_ago_days} days'"
        self.sql(f"update public.subscriptions set status = 'replaced' where user_id = '{uid}' and status = 'active'")
        return self.sql(f"insert into public.subscriptions (user_id, plan_id, billing_period, starts_at, ends_at) values ('{uid}', '{plan}', '{period}', {starts}, {ends}) returning id")

    def sub(self, uid, status='active'):
        out = self.sql(f"select to_jsonb(s) from public.subscriptions s where user_id = '{uid}' and status = '{status}' order by created_at desc limit 1")
        return json.loads(out) if out else None

    def reqs(self, uid=None, status=None):
        w = ' and '.join(x for x in ([f"user_id = '{uid}'"] if uid else []) + ([f"status = '{status}'"] if status else [])) or 'true'
        return json.loads(self.sql(f"select coalesce(json_agg(to_jsonb(r) order by created_at, id), '[]'::json) from public.plan_requests r where {w}"))

    def make_request(self, uid, plan='pro', period='monthly', note=None, status='pending', admin_note=None, ago_min=0):
        """Inserta una solicitud directamente (para probar el historial)."""
        q = lambda v: 'null' if v is None else "'" + str(v).replace("'", "''") + "'"
        res = '' if status == 'pending' else f", resolved_at = now() - interval '{max(ago_min - 1, 0)} minutes'"
        rid = self.sql(f"insert into public.plan_requests (user_id, plan_id, billing_period, user_note, created_at) values ('{uid}', '{plan}', '{period}', {q(note)}, now() - interval '{int(ago_min)} minutes') returning id")
        if status != 'pending':
            self.sql(f"update public.plan_requests set status = '{status}', admin_note = {q(admin_note)}{res} where id = '{rid}'")
        return rid

    def resolve(self, req_id, approve, note=None, ends=None):
        q = lambda v: 'null' if v is None else "'" + str(v).replace("'", "''") + "'"
        return self.sql(f"select private.resolve_plan_request('{req_id}', {'true' if approve else 'false'}, {q(note)}, null, {q(ends)})")

    # ---------- traducción mínima de PostgREST ----------
    def _rcols(self, q):
        sel = q.get('select', ['*'])[0]
        if sel == '*': return '*'
        cols = sel.split(',')
        if not all(c in RCOLS for c in cols): raise ValueError('select no soportado: ' + sel)
        return ','.join(cols)

    def _rwhere(self, q, variables):
        conds = []
        for k, vals in q.items():
            if k in ('select', 'order', 'limit'): continue
            m = re.fullmatch(r'eq\.(.+)', vals[0])
            if k not in RCOLS or not m: raise ValueError('filtro no soportado: %s=%s' % (k, vals[0]))
            variables['f_' + k] = m.group(1); conds.append(f"{k} = :'f_{k}'::{RCAST.get(k, 'text')}")
        return (' where ' + ' and '.join(conds)) if conds else ''

    def _rorder(self, q):
        o = q.get('order', [''])[0]
        if not o: return ''
        parts = []
        for it in o.split(','):
            m = re.fullmatch(r'([a-z_]+)\.(asc|desc)', it)
            if not m or m.group(1) not in RCOLS: raise ValueError('order no soportado: ' + o)
            parts.append(f'{m.group(1)} {m.group(2)}')
        return ' order by ' + ', '.join(parts)

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); path = p.path
        h = {k.lower(): v for k, v in headers.items()}
        fn = path[len('/rest/v1/rpc/'):] if path.startswith('/rest/v1/rpc/') else None
        mine = path == '/rest/v1/plan_requests' or fn in RPC_ARGS
        if not mine or h.get('apikey') != self.key:
            return super().handle(method, url, headers, body_text)
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
        rec = dict(method=method, path=path, query=p.query, body=body)
        self.rest_log.append(rec); self.p_log.append(rec)
        if self.fail_rest:
            r = self.fail_rest(path, method)
            if r: return r
        u = self.user_for(h)
        if 'authorization' in h and not u:
            return 401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)
        if not u:                                            # sin sesión: el rol «anon» no tiene permiso para nada de esto
            return 401, dict(code='42501', message='permission denied for ' + (fn or 'plan_requests'), details=None, hint=None)
        uid = u['id']; q = urllib.parse.parse_qs(p.query); variables = {}
        try:
            if fn:
                if method != 'POST' or not (body is None or isinstance(body, dict)) or set(body or {}) - RPC_ARGS[fn]:
                    return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
                b = body or {}
                if fn == 'my_entitlements': script = 'select to_json(public.my_entitlements());'
                elif fn == 'cancel_my_subscription': script = 'select to_json(public.cancel_my_subscription());'
                elif fn == 'cancel_plan_request':
                    if not isinstance(b.get('p_request'), str) or not UUID_RE.match(b['p_request']):
                        return 400, dict(code='22P02', message='invalid input syntax for type uuid', details=None, hint=None)
                    variables['r'] = b['p_request']; script = "select public.cancel_plan_request(:'r'::uuid);"
                else:
                    if 'p_plan' not in b: return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
                    variables['pl'] = b['p_plan']; args = ["p_plan => :'pl'"]
                    for key, var in (('p_period', 'pe'), ('p_note', 'no')):
                        if key in b:
                            if b[key] is None: args.append(f'{key} => null')
                            else: variables[var] = b[key]; args.append(f"{key} => :'{var}'")
                    script = 'select to_json(public.request_plan(' + ', '.join(args) + '));'
                ok, out = self.psql(script, variables, uid)
                if not ok: return self._pg_error(out)
                if fn == 'cancel_plan_request': return 204, None
                return 200, json.loads(out) if out else None
            # ---- plan_requests (solo lectura: se escribe únicamente con funciones) ----
            if method != 'GET':
                return 405, dict(code='42501', message='permission denied for table plan_requests', details=None, hint=None)
            cols = self._rcols(q); where = self._rwhere(q, variables)
            lim = q.get('limit', [''])[0]; limit = f' limit {int(lim)}' if lim.isdigit() else ''
            script = f"select coalesce(json_agg(to_jsonb(t)), '[]'::json) from (select {cols} from public.plan_requests{where}{self._rorder(q)}{limit}) t;"
            self.sql_log.append(('GET', path, script))
            ok, out = self.psql(script, variables, uid)
            if not ok: return self._pg_error(out)
            return 200, json.loads(out)
        except ValueError as e:
            return 400, dict(code='MOCK_UNSUPPORTED', message=str(e), details=None, hint=None)
