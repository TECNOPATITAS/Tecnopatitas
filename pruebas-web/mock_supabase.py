"""
Simulador MÍNIMO de Supabase Auth + PostgREST, SOLO para pruebas locales de la interfaz (Etapa 3).
No es Supabase: imita las respuestas documentadas de GoTrue y PostgREST que usa js/tp-client.js,
con los mismos permisos que dejan las políticas de la Etapa 2 (perfil propio, columnas protegidas, etc.).
"""
import json, re, time, urllib.parse, uuid

CORS = {
    'access-control-allow-origin': '*',
    'access-control-allow-headers': 'apikey, authorization, content-type, prefer, accept, x-client-info',
    'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
}

class Backend:
    def __init__(self, publishable_key):
        self.key = publishable_key
        self.reset()

    def reset(self, confirm_on=True, smtp_authorized=None):
        self.confirm_on = confirm_on
        self.smtp_authorized = smtp_authorized          # None = cualquiera; lista = solo esos correos
        self.users = {}                                 # email -> dict
        self.profiles = {}                              # id -> dict
        self.access = {}                                # token -> uid
        self.refresh = {}                               # token -> uid (válido)
        self.calls = []
        self.access_ttl = 3600
        self.rate_limited = False

    # --- utilidades de prueba ---
    def add_user(self, email, password, account_type='owner', name='Usuario', admin=False, confirmed=True, suspended=False, phone=None):
        uid = str(uuid.uuid4())
        self.users[email] = dict(id=uid, email=email, password=password, confirmed=confirmed, admin=admin)
        self.profiles[uid] = dict(id=uid, display_name=name, account_type=account_type, phone=phone,
                                  is_suspended=suspended, avatar_path=None, created_at='2026-11-04T00:00:00Z')
        return uid

    def _session(self, u):
        n = len(self.access) + 1
        at, rt = f'at.{u["id"]}.{n}', f'rt.{u["id"]}.{n}'
        self.access[at] = u['id']; self.refresh[rt] = u['id']
        return dict(access_token=at, token_type='bearer', expires_in=self.access_ttl, expires_at=int(time.time()) + self.access_ttl,
                    refresh_token=rt, user=self._user(u))

    def _user(self, u):
        return dict(id=u['id'], aud='authenticated', role='authenticated', email=u['email'],
                    email_confirmed_at='2026-11-04T00:00:00Z' if u['confirmed'] else None, user_metadata={})

    def expire_access(self, token):
        self.access.pop(token, None)

    def user_for(self, headers):
        auth = headers.get('authorization', '')
        if not auth.startswith('Bearer '):
            return None
        uid = self.access.get(auth[7:])
        return next((u for u in self.users.values() if u['id'] == uid), None) if uid else None

    # --- manejador de peticiones ---
    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(p.query); path = p.path
        try: body = json.loads(body_text) if body_text else None
        except Exception: body = None
        h = {k.lower(): v for k, v in headers.items()}
        self.calls.append(dict(method=method, path=path, query=p.query, headers=h, body=body))
        def ok(data, status=200): return status, data
        def err(status, code, msg): return status, dict(code=status, error_code=code, msg=msg)

        if h.get('apikey') != self.key:
            return err(401, 'no_api_key', 'No API key found in request')
        if self.rate_limited and path.startswith('/auth/v1/') and path != '/auth/v1/logout':
            return err(429, 'over_request_rate_limit', 'Too many requests')

        # ---------- Auth ----------
        if path == '/auth/v1/signup' and method == 'POST':
            email = (body or {}).get('email', ''); pw = (body or {}).get('password', '')
            if len(pw) < 6: return err(422, 'weak_password', 'Password should be at least 6 characters.')
            if self.confirm_on and self.smtp_authorized is not None and email not in self.smtp_authorized:
                return err(422, 'email_address_not_authorized', 'Email address not authorized')
            if email in self.users:
                if self.confirm_on:                      # respuesta ofuscada: no revela que el correo existe
                    return ok(dict(id=str(uuid.uuid4()), email=email, identities=[]))
                return err(422, 'user_already_exists', 'User already registered')
            meta = (body or {}).get('data') or {}
            at = 'business' if meta.get('account_type') == 'business' else 'owner'   # igual que el disparador handle_new_user
            uid = self.add_user(email, pw, account_type=at, name=str(meta.get('display_name', ''))[:80], confirmed=not self.confirm_on)
            u = self.users[email]
            return ok(self._session(u)) if not self.confirm_on else ok(self._user(u))
        if path == '/auth/v1/token' and method == 'POST':
            gt = q.get('grant_type', [''])[0]
            if gt == 'password':
                u = self.users.get((body or {}).get('email'))
                if not u or u['password'] != (body or {}).get('password'):
                    return err(400, 'invalid_credentials', 'Invalid login credentials')
                if not u['confirmed']:
                    return err(400, 'email_not_confirmed', 'Email not confirmed')
                return ok(self._session(u))
            if gt == 'refresh_token':
                uid = self.refresh.pop((body or {}).get('refresh_token'), None)
                u = next((x for x in self.users.values() if x['id'] == uid), None) if uid else None
                if not u: return err(400, 'refresh_token_not_found', 'Invalid Refresh Token: Refresh Token Not Found')
                return ok(self._session(u))
        if path == '/auth/v1/user':
            u = self.user_for(h)
            if not u: return err(401, 'bad_jwt', 'invalid JWT')
            if method == 'GET': return ok(self._user(u))
            if method == 'PUT':
                pw = (body or {}).get('password')
                if pw is not None:
                    if len(pw) < 6: return err(422, 'weak_password', 'Password should be at least 6 characters.')
                    if pw == u['password']: return err(422, 'same_password', 'New password should be different from the old password.')
                    u['password'] = pw
                return ok(self._user(u))
        if path == '/auth/v1/logout' and method == 'POST':
            return 204, None
        if path == '/auth/v1/recover' and method == 'POST':
            return ok({})

        # ---------- PostgREST ----------
        if path.startswith('/rest/v1/'):
            u = self.user_for(h)                          # sin Authorization: rol anon
            if path == '/rest/v1/rpc/is_admin':
                if not u: return err(401, 'PGRST301', 'JWT required') if 'authorization' in h else ok(False)
                return ok(bool(u['admin']))
            if path == '/rest/v1/rpc/my_entitlements':
                if not u: return ok(None)
                return ok(dict(plan=None if u['email'].startswith('sinplan') or self.profiles[u['id']]['account_type'] == 'business'
                               else dict(id='basica', name='Huellita Básica', tagline='Plan Comunidad'), subscription=None))
            if path == '/rest/v1/notifications' and method == 'GET':        # Etapa 8: la campana de la cabecera cuenta las no leídas (aquí: ninguna)
                if 'authorization' in h and not u: return err(401, 'PGRST301', 'JWT expired')
                return ok([]) if u else err(401, 'PGRST301', 'JWT required')
            if path == '/rest/v1/rpc/generate_my_reminders' and method == 'POST':
                if 'authorization' in h and not u: return err(401, 'PGRST301', 'JWT expired')
                return ok(0) if u else err(401, 'PGRST301', 'JWT required')
            if path == '/rest/v1/profiles':
                if 'authorization' in h and not u: return err(401, 'PGRST301', 'JWT expired')
                if not u: return ok([])
                flt = q.get('id', [''])[0]
                target = flt[3:] if flt.startswith('eq.') else None
                if method == 'GET':
                    row = self.profiles.get(u['id']) if target == u['id'] else None   # RLS: solo el propio
                    if 'pgrst.object' in h.get('accept', ''):
                        return ok(row) if row else (406, dict(code='PGRST116', message='JSON object requested, multiple (or no) rows returned'))
                    return ok([row] if row else [])
                if method == 'PATCH':
                    if any(k in (body or {}) for k in ('account_type', 'is_suspended', 'id')):
                        return err(403, '42501', 'permission denied for table profiles')
                    row = self.profiles.get(u['id'])
                    if target != u['id'] or row is None or row['is_suspended']:
                        return ok([])                     # RLS: 0 filas afectadas
                    row.update({k: v for k, v in (body or {}).items() if k in ('display_name', 'phone', 'avatar_path')})
                    return ok([row])
        return err(404, 'not_found', 'Not found: ' + path)
