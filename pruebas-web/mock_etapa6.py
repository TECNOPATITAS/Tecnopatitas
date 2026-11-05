"""
Simulador de la Etapa 6 SOLO para pruebas de interfaz: Supabase Auth con «CAPTCHA protection» activable.
(Las denuncias NO se simulan aquí: las pruebas de navegador usan la función segura REAL y la base de datos REAL mediante
pruebas-web/servidor_funcion.mjs; este simulador solo aporta la parte de Auth que necesitan registro, inicio de sesión y recuperar.)

Imita lo documentado de GoTrue: si la protección está activa, signup / token (contraseña) / recover exigen
gotrue_meta_security.captcha_token; el token de Turnstile solo sirve una vez; si falta o es inválido → 400 captcha_failed.
"""
import json, urllib.parse
from mock_supabase import Backend


class Backend6(Backend):
    def reset(self, **kw):
        super().reset(**kw)
        self.captcha_required = False
        self.captcha_used = set()
        self.captcha_seen = []        # tokens recibidos (para las pruebas)
        self.captcha_bodies = []      # cuerpos de las peticiones de Auth (para comprobar que no llevan nada de más)

    def handle(self, method, url, headers, body_text):
        p = urllib.parse.urlparse(url); q = urllib.parse.parse_qs(p.query)
        gated = (p.path == '/auth/v1/signup' and method == 'POST') or (p.path == '/auth/v1/recover' and method == 'POST') or \
                (p.path == '/auth/v1/token' and method == 'POST' and q.get('grant_type', [''])[0] == 'password')
        if gated:
            try: body = json.loads(body_text) if body_text else {}
            except Exception: body = {}
            sec = (body or {}).get('gotrue_meta_security') or {}
            tok = sec.get('captcha_token') if isinstance(sec, dict) else None
            self.captcha_bodies.append(body)
            if tok: self.captcha_seen.append(tok)
            if self.captcha_required:
                h = {k.lower(): v for k, v in headers.items()}
                if h.get('apikey') != self.key: return 401, dict(code=401, error_code='no_api_key', msg='No API key found in request')
                if not tok or not isinstance(tok, str) or not tok.startswith('ok.') or tok in self.captcha_used:
                    return 400, dict(code=400, error_code='captcha_failed', msg='captcha verification process failed')
                self.captcha_used.add(tok)
        return super().handle(method, url, headers, body_text)
