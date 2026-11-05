"""
Simulador de la Etapa 11 SOLO para pruebas de interfaz de: registro con aceptación de términos, páginas legales y «Eliminar mi cuenta» (perfil).

Qué es REAL aquí: la base de datos (PostgreSQL local con database/00_instalar_todo.sql). El alta de una cuenta pasa por el disparador REAL
handle_new_user (guarda terms_version / terms_accepted_at solo si vienen en el metadato de registro) y delete_my_account se TRADUCE a SQL y
corre con el rol «authenticated» y la identidad de la persona (igual que PostgREST): comprueba frase, rol de administración, que no queden
archivos y borra la cuenta en cascada. Si no se cumple algo, el error 42501 / P0001 es el mismo que daría el servidor.

Qué es SIMULADO: Supabase Auth (mock_supabase.py) y Storage. Del Storage se simulan solo POST /object/list/{bucket} y DELETE /object/{bucket}:
solo ven y borran los objetos de su dueño (como las políticas RLS reales). Antes de llamar a delete_my_account se copian los objetos del
simulador a storage.objects, para que la comprobación «no quedan archivos» del SQL real tenga con qué trabajar.
"""
import json, re, urllib.parse
from mock_etapa10 import Backend10
from mock_etapa7 import Backend7

LIST_RE = re.compile(r'^/storage/v1/object/list/([a-z-]+)$')
DEL_RE = re.compile(r'^/storage/v1/object/([a-z-]+)$')


def q(v):
    return 'null' if v is None else "'" + str(v).replace("'", "''") + "'"


class Backend11(Backend10):
    def __init__(self, key, db, psql_env=None):
        super().__init__(key, db, psql_env)
        self.pending_meta = None
        self.signup_log = []                                  # cuerpos de /auth/v1/signup
        self.store_log = []                                   # (método, bucket, cuerpo) de listados y borrados de Storage
        self.del_calls = []                                   # cuerpos de rpc/delete_my_account
        self.list_hidden = False                              # el listado no devuelve nada (prueba de la 2.ª defensa: el SQL se niega)
        self.list_fail = None                                 # estado HTTP de fallo para el listado
        self.remove_fail = None                               # estado HTTP de fallo para el borrado

    def reset_db(self):
        super().reset_db()
        self.sql("truncate storage.objects")
        self.store_log.clear(); self.del_calls.clear(); self.signup_log.clear()
        self.list_hidden = False; self.list_fail = None; self.remove_fail = None

    # El alta por el formulario manda su metadato tal cual (display_name, account_type, terms_version…) a auth.users, donde actúa el disparador real.
    def add_user(self, email, password, account_type='owner', name='Usuario', admin=False, confirmed=True, suspended=False, phone=None):
        if self.pending_meta is None:
            return super().add_user(email, password, account_type, name, admin, confirmed, suspended, phone)
        uid = super(Backend7, self).add_user(email, password, account_type=account_type, name=name, admin=admin, confirmed=confirmed, suspended=suspended, phone=phone)
        meta = json.dumps(self.pending_meta).replace("'", "''")
        self.sql(f"insert into auth.users (id, email, raw_user_meta_data) values ('{uid}', '{email}', '{meta}')")
        return uid

    def profile_row(self, uid):
        out = self.sql(f"select to_jsonb(p) from public.profiles p where id = '{uid}'")
        return json.loads(out) if out else None

    def seed_object(self, bucket, uid, name, data=b'\xff\xd8\xff\xd9'):
        self.objects[(bucket, f'{uid}/{name}')] = dict(owner=uid, size=len(data), type='image/jpeg', data=data)
        return f'{uid}/{name}'

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); path = p.path
        h = {k.lower(): v for k, v in headers.items()}
        if path == '/auth/v1/signup' and method == 'POST':
            try: b = json.loads(body_text) if body_text else None
            except Exception: b = None
            self.signup_log.append(b)
            self.pending_meta = (b or {}).get('data') or {}
            try: return super().handle(method, url, headers, body_text)
            finally: self.pending_meta = None
        if path == '/rest/v1/rpc/delete_my_account' and h.get('apikey') == self.key:
            return self._delete_account(method, h, body_text)
        return super().handle(method, url, headers, body_text)

    def _delete_account(self, method, h, body_text):
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        self.del_calls.append(body)
        rec = dict(method=method, path='/rest/v1/rpc/delete_my_account', query='', body=body, auth='authorization' in h)
        self.rest_log.append(rec); self.a_log.append(rec)
        u = self.user_for(h)
        if 'authorization' in h and not u:
            return 401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)
        if not u:
            return 401, dict(code='42501', message='permission denied for function delete_my_account', details=None, hint=None)
        if method != 'POST' or not isinstance(body, dict) or set(body) - {'p_confirm'}:
            return 400, dict(code='PGRST202', message='Could not find the function with those arguments', details=None, hint=None)
        uid = u['id']
        # espejo de los archivos del simulador en storage.objects (carpeta de esta persona)
        self.sql(f"delete from storage.objects where (storage.foldername(name))[1] = '{uid}'")
        for (bucket, name), o in list(self.objects.items()):
            if name.startswith(uid + '/'):
                self.sql(f"insert into storage.objects (bucket_id, name, owner) values ({q(bucket)}, {q(name)}, '{uid}')")
        script = "select public.delete_my_account(p_confirm => :'a0'::text);" if body.get('p_confirm') is not None else "select public.delete_my_account(p_confirm => null);"
        ok, out = self.psql(script, {'a0': str(body.get('p_confirm'))} if body.get('p_confirm') is not None else {}, uid)
        self.sql(f"delete from storage.objects where (storage.foldername(name))[1] = '{uid}'")
        if not ok:
            return self._pg_error(out)
        # la cuenta ya no existe: tampoco para el simulador de Auth
        for email, usr in list(self.users.items()):
            if usr['id'] == uid: self.users.pop(email)
        self.profiles.pop(uid, None)
        for tok in [t for t, x in self.access.items() if x == uid]: self.access.pop(tok)
        for tok in [t for t, x in self.refresh.items() if x == uid]: self.refresh.pop(tok)
        return 204, None

    # ---------- Storage ----------
    def storage(self, method, path, query, h, body_text):
        err = lambda st, e, m: (st, dict(statusCode=str(st), error=e, message=m))
        m = LIST_RE.match(path)
        if m and method == 'POST':
            bucket = m.group(1)
            try: body = json.loads(body_text) if body_text else {}
            except Exception: body = {}
            self.store_log.append(('LIST', bucket, body))
            if self.list_fail: return err(self.list_fail, 'Internal', 'fallo simulado')
            u = self.user_for(h)
            if not u: return err(400, 'InvalidJWT', 'Invalid Compact JWS')
            prefix = str(body.get('prefix', '')); off = int(body.get('offset', 0)); lim = int(body.get('limit', 100))
            names = [] if self.list_hidden else sorted(k[1] for k, o in self.objects.items() if k[0] == bucket and o.get('owner') == u['id'] and k[1].startswith(prefix + '/'))
            return 200, [dict(name=n[len(prefix) + 1:], id='obj-' + n, bucket_id=bucket, metadata={'size': 4}) for n in names[off:off + lim]]
        m = DEL_RE.match(path)
        if m and method == 'DELETE':
            bucket = m.group(1)
            try: body = json.loads(body_text) if body_text else {}
            except Exception: body = {}
            self.store_log.append(('REMOVE', bucket, body))
            if self.remove_fail: return err(self.remove_fail, 'Internal', 'fallo simulado')
            u = self.user_for(h)
            if not u: return err(400, 'InvalidJWT', 'Invalid Compact JWS')
            gone = []
            for p in body.get('prefixes', []):
                o = self.objects.get((bucket, p))
                if o and o.get('owner') == u['id']: del self.objects[(bucket, p)]; gone.append(dict(name=p, bucket_id=bucket))
            return 200, gone
        return super().storage(method, path, query, h, body_text)
