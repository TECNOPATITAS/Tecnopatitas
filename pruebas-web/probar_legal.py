"""
Pruebas de interfaz de la Etapa 11 (aviso de privacidad, términos, registro con aceptación, «Eliminar mi cuenta», 404 y revisión de
publicación) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP) y la base de datos:
            el disparador de alta (handle_new_user) que guarda la versión de términos aceptada y delete_my_account (frase, rol,
            archivos pendientes, borrado en cascada). PostgreSQL local con database/00_instalar_todo.sql (ver mock_etapa11.py).
  SIMULADO  Supabase Auth (mock_supabase.py), PostgREST (solo lo necesario), el listado/borrado de Storage y Cloudflare Turnstile.

Uso:  python3 pruebas-web/probar_legal.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), playwright + chromium.
Variables: TP_PORT (8775), TP_LEGAL_DB (tp_legal), TP_SITE (carpeta del sitio; las «pruebas de las pruebas» usan una copia saboteada), TP_ONLY (grupos).
"""
import datetime, http.server, json, os, re, socketserver, subprocess, sys, threading, time, urllib.parse
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa11 import Backend11

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8775)); DB = os.environ.get('TP_LEGAL_DB', 'tp_legal')
ORIGIN = f'http://localhost:{PORT}'
CONFIG_JS = open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", CONFIG_JS).group(1)
ONLY = os.environ.get('TP_ONLY', '')
HOSTILE = '<img src=x onerror="window.__pwn=1"> <b>negrita</b> & "comillas"'
SB_RE = re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')
def read(path): return open(os.path.join(ROOT, path), encoding='utf-8').read()
def read_real(path): return open(os.path.join(REAL_ROOT, path), encoding='utf-8').read()      # database/ no forma parte del sitio que se sabotea

# ------------------------------------------------------------------ base de datos
def prepare_db():
    env = dict(os.environ, PGOPTIONS='-c client_min_messages=warning')
    subprocess.run(['psql', '-X', '-q', '-d', 'postgres', '-c', f'drop database if exists {DB}', '-c', f'create database {DB}'], capture_output=True, text=True)
    for f in ('database/pruebas/shim_supabase.sql', 'database/00_instalar_todo.sql'):
        r = subprocess.run(['psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-d', DB, '-o', '/dev/null'], input=open(os.path.join(REAL_ROOT, f), encoding='utf-8').read(),
                           capture_output=True, text=True, env=env)
        if r.returncode: raise SystemExit('No se pudo preparar la base: ' + r.stderr[:400])

# ------------------------------------------------------------------ sitio estático con las cabeceras de _headers (y 404.html como Cloudflare Pages)
HEADERS = {}
for line in read('_headers').splitlines()[1:]:
    if line.startswith('/') or line.startswith('#') or not line.strip(): break
    if ':' in line: k, v = line.strip().split(':', 1); HEADERS[k.strip()] = v.strip()
HEADERS.pop('Strict-Transport-Security', None)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=ROOT, **kw)
    def end_headers(self):
        for k, v in HEADERS.items(): self.send_header(k, v)
        self.send_header('Cache-Control', 'no-store'); super().end_headers()
    def do_GET(self):
        p = self.translate_path(self.path)
        if not os.path.exists(p) and os.path.exists(os.path.join(ROOT, '404.html')):
            body = open(os.path.join(ROOT, '404.html'), 'rb').read()
            self.send_response(404); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body); return
        super().do_GET()
    def log_message(self, *a): pass
class Srv(socketserver.ThreadingTCPServer):
    def handle_error(self, request, client_address): pass
socketserver.TCPServer.allow_reuse_address = True
srv = Srv(('127.0.0.1', PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

# ------------------------------------------------------------------ estado de la simulación
be = Backend11(KEY, DB)
CUR = [None]
SEQ = []                                                # (método, ruta) de todo lo que llega a Supabase, en orden
ST = dict(legal=None, site_key='')                      # config.js por contexto: datos legales y «site key» de Turnstile
TS_STUB = """(function(){
  var S = window.__ts = { widgets: [], tokens: 0, resets: 0, removed: 0 };
  window.turnstile = {
    render: function(el, o){
      var id = S.widgets.length, b = document.createElement('button');
      b.type = 'button'; b.className = 'ts-fake'; b.textContent = 'Verificación simulada'; b.addEventListener('click', function(){ S.solve(id); });
      el.appendChild(b); S.widgets.push({ el: el, opts: o, token: null }); return id;
    },
    reset: function(id){ var w = S.widgets[id]; if (w) { S.resets++; w.token = null; } },
    remove: function(id){ S.removed++; }
  };
  S.solve = function(id){ var w = S.widgets[id]; S.tokens++; w.token = 'ok.' + S.tokens; w.opts.callback(w.token); };
})();"""
def route_supa(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    SEQ.append((req.method, urllib.parse.urlparse(req.url).path))
    try: res = be.handle(req.method, req.url, req.headers, req.post_data)
    except Exception:
        import traceback; traceback.print_exc(); route.fulfill(status=500, headers=CORS, body='{"message":"error del simulador"}'); return
    if len(res) == 3: route.fulfill(status=res[0], headers={**CORS, 'content-type': res[2]}, body=res[1]); return
    status, data = res
    route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body='' if data is None else json.dumps(data))
def route_cfg(route):
    body = CONFIG_JS
    if ST['legal'] is not None:
        rep = 'LEGAL: Object.freeze(' + json.dumps(ST['legal']) + ')'
        body = re.sub(r"LEGAL:\s*Object\.freeze\(\{[^}]*\}\)", lambda m: rep, body)
    if ST['site_key']:
        rep2 = "TURNSTILE_SITE_KEY: '" + ST['site_key'] + "'"
        body = re.sub(r"TURNSTILE_SITE_KEY:\s*'[^']*'", lambda m: rep2, body)
    route.fulfill(status=200, headers={**HEADERS, 'content-type': 'application/javascript', 'cache-control': 'no-store'}, body=body)
def new_ctx(br, w=1100, h=900):
    ctx = br.new_context(viewport={'width': w, 'height': h})
    ctx.route(SB_RE, route_supa)
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    ctx.route(re.compile(r'https://challenges\.cloudflare\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'application/javascript'}, body=TS_STUB))
    ctx.route(re.compile(r'.*/js/config\.js(\?.*)?$'), route_cfg)
    return ctx
def session_script(email):
    u = be.users[email]; s = be._session(u)
    sess = dict(access_token=s['access_token'], refresh_token=s['refresh_token'], expires_at=s['expires_at'],
                user=dict(id=u['id'], email=email, email_confirmed_at='2026-11-04T00:00:00Z'))
    return "try{if(!localStorage.getItem('tp-auth-v1'))localStorage.setItem('tp-auth-v1',%s)}catch(e){}" % json.dumps(json.dumps(sess))
def tick(pg, ms):
    try: pg.wait_for_timeout(ms)
    except Exception: time.sleep(ms / 1000)
def waitjs(pg, expr, timeout=8.0):
    t0 = time.time(); last = None
    while time.time() - t0 < timeout:
        try:
            if pg.evaluate(expr): return True
        except Exception as e: last = e
        tick(pg, 40)
    try: seen = pg.inner_text('main')[:500].replace('\n', ' | ')
    except Exception: seen = '?'
    raise TimeoutError(f'Condición no cumplida en {timeout}s: {expr[:140]} {last or ""} · pantalla: {seen}')
def eventually(cond, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond(): return True
        except Exception: pass
        tick(CUR[0], 50)
    return False
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def txt(pg, sel): return pg.inner_text(sel) if pg.locator(sel).count() else ''
def vis(pg, sel): return pg.locator(sel).count() > 0 and pg.locator(sel).first.is_visible()
def open_page(br, email, page, w=1100, h=900, ctx=None, wait=True, qs=''):
    ctx = ctx or new_ctx(br, w, h)
    if email: ctx.add_init_script(session_script(email))
    log = []; pg = ctx.new_page(); CUR[0] = pg; pg.set_default_timeout(8000)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/{page}{qs}')
    if wait and page == 'perfil.html': waitjs(pg, "document.body.classList.contains('tp-ok') && document.getElementById('p-email').value !== ''")
    elif wait: pg.wait_for_load_state('load')
    return ctx, pg, log
def reset_state():
    be.sql("delete from auth.users where email like '%@l11.mx'")
    be.reset_db(); be.calls.clear(); be.rest_log.clear(); be.a_log.clear(); SEQ.clear()
    ST['legal'] = None; ST['site_key'] = ''
def mk(name, kind='owner', **kw):
    email = f'{name}@l11.mx'
    return be.add_user(email, 'ClaveSegura123', name=name.capitalize(), account_type=kind, **kw), email
def exists(uid, table='auth.users', col='id'):
    return be.sql(f"select exists (select 1 from {table} where {col} = '{uid}')") == 't'
def add_pet(uid, name='Firulais'):
    return be.sql(f"insert into public.pets (owner_id, name, species) values ('{uid}', '{name}', 'perro') returning id")
def group(n): return not ONLY or str(n) in ONLY.split(',')
def tokens_calls(): return [c for c in be.calls if c['path'] == '/auth/v1/token' and 'grant_type=password' in (c.get('query') or '')]
def auth_pw_calls(): return len(tokens_calls())

_adm = open(os.path.join(HERE, 'probar_admin.py'), encoding='utf-8').read()
A11Y_JS = re.search(r'A11Y_JS = r"""(.*?)"""', _adm, re.S).group(1)
AUDIT_JS = re.search(r'AUDIT_JS = r"""(.*?)"""', _adm, re.S).group(1)
VERSION = re.search(r"VERSION: '([0-9-]+)'", read('js/legal.js')).group(1)
FECHA = re.search(r"FECHA: '([^']+)'", read('js/legal.js')).group(1)
PHRASE = 'ELIMINAR MI CUENTA'

# ================================================================== GRUPOS
def g1(br):
    print('\n[1] Archivos, textos y coherencia con el sistema')
    priv, term = read('privacidad.html'), read('terminos.html')
    for nm, h in (('privacidad.html', priv), ('terminos.html', term)):
        ids = set(re.findall(r'<h2 id="([a-z-]+)"', h)); links = set(re.findall(r'<a href="#([a-z-]+)"', h))
        check(f'1.1 {nm}: tiene título, idioma es-MX, índice y cada enlace del índice apunta a una sección que existe',
              'lang="es-MX"' in h and '<h1>' in h and links and links <= ids and len(ids) >= 10, (sorted(links - ids), len(ids)))
        check(f'1.2 {nm}: sin scripts en línea, sin manejadores onclick y solo carga archivos del propio sitio (scripts)',
              not re.search(r'<script(?![^>]*\bsrc=)', h) and not re.search(r'\son[a-z]+=', h) and all(not s.startswith('http') for s in re.findall(r'<script[^>]*src="([^"]+)"', h)))
    check('1.3 Ambos textos usan los datos de config.js (responsable, domicilio, contacto) mediante data-lg, sin datos personales escritos a mano',
          all(f'data-lg="{k}"' in priv for k in ('responsable', 'domicilio', 'contacto', 'fecha', 'version')) and all(f'data-lg="{k}"' in term for k in ('responsable', 'domicilio', 'contacto', 'fecha', 'version')) and not re.search(r'[\w.]+@[\w.]+\.\w+', priv + term))
    csp = HEADERS['Content-Security-Policy']
    ext = set()
    for h in (read(f) for f in os.listdir(ROOT) if f.endswith('.html')):
        ext |= set(re.findall(r'(?:src|href)="(https://[^/"]+)', h))
    for f in ('js/tp-captcha.js', 'js/tp-client.js', 'js/layout.js'): ext |= set(re.findall(r"https://([a-z0-9.-]+\.[a-z]{2,})", read(f)))
    prov = {'google': 'fonts.googleapis.com' in ' '.join(ext) or any('googleapis' in e for e in ext), 'cloudflare': 'challenges.cloudflare.com' in csp, 'supabase': 'supabase.co' in csp}
    check('1.4 Todo proveedor externo que usa el sitio (según la CSP y los HTML) está nombrado en el aviso de privacidad',
          all(prov.values()) and all(x in priv for x in ('Supabase', 'Cloudflare', 'Google Fonts')), (prov, sorted(ext)))
    schema = read_real('database/01_esquema.sql')
    tables = set(re.findall(r'create table if not exists public\.(\w+)', schema))
    sec = {m.group(1): m.group(2) for m in re.finditer(r'<h2 id="([a-z-]+)">(.*?)(?=<h2 id=|</article>|\Z)', priv, re.S)}
    D_, E_ = sec['datos'], sec['eliminar']
    cover = {'profiles': ('correo electrónico', D_), 'admin_roles': None, 'subscription_plans': None, 'subscriptions': ('estado de tu plan', D_), 'subscription_events': None,
             'plan_requests': ('solicitudes de plan', D_), 'pets': ('Tus mascotas', D_), 'pet_vaccinations': ('vacunas', D_), 'pet_deworming': ('desparasitaciones', D_), 'pet_appointments': ('citas', D_),
             'pet_qr_profiles': ('Placa QR', D_), 'businesses': ('establecimiento', D_), 'business_promotions': ('promociones', D_), 'business_daily_stats': ('contadores del directorio', E_),
             'complaints': ('Reportes de maltrato', D_), 'conversations': ('Atención al cliente', D_), 'messages': ('chat', D_), 'notifications': ('Notificaciones', D_),
             'care_guides': None, 'admin_audit_log': ('bitácora', E_)}
    miss = sorted(t for t in tables if t not in cover); gaps = sorted(t for t, k in cover.items() if k and k[0] not in k[1])
    check('1.5 Cada tabla con datos de personas del esquema está cubierta por la sección correcta del aviso de privacidad (si se agrega una tabla nueva, esta prueba obliga a revisarlo)',
          not miss and not gaps and tables == set(cover), (miss, gaps, sorted(tables ^ set(cover))))
    check('1.6 El aviso no promete lo que el sistema no hace (nada de «descargar tus datos» ni de analítica/publicidad) y dice que no hay cobros ni tarjetas',
          'descargar' not in priv.lower() and 'No usamos tus datos para publicidad' in priv and 'No pedimos ni guardamos tarjetas' in priv and 'no se realizan cobros' in term.lower())
    check('1.7 Los términos aclaran: 18 años, orientación (no sustituye al veterinario), que el reporte no es denuncia oficial y que la contratación no está habilitada',
          '18 años' in term and 'No sustituyen la consulta' in term and 'No los presenta como denuncia' in term and 'no está habilitada' in term)
    check('1.8 Los derechos ARCO, la revocación, la autoridad (Secretaría Anticorrupción y Buen Gobierno) y la eliminación de cuenta están en el aviso',
          all(x in priv for x in ('Acceder', 'Rectificarlos', 'Cancelación', 'Oponerte', 'revocar tu consentimiento', 'Secretaría Anticorrupción y Buen Gobierno', 'Eliminar mi cuenta')))
    lg = read('js/legal.js')
    mon = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    y, m_, d = map(int, VERSION.split('-'))
    check('1.9 js/legal.js: VERSION es una fecha válida AAAA-MM-DD, FECHA dice lo mismo en español y el objeto está congelado',
          re.fullmatch(r'\d{4}-\d{2}-\d{2}', VERSION) and datetime.date(y, m_, d) and FECHA == f'{d} de {mon[m_ - 1]} de {y}' and 'Object.freeze' in lg, (VERSION, FECHA))
    cfg = re.search(r"LEGAL:\s*Object\.freeze\(\{([^}]*)\}\)", CONFIG_JS)
    check('1.10 config.js trae el bloque LEGAL congelado y VACÍO (no se publican datos personales por omisión)', cfg and not re.search(r":\s*'[^']+'", cfg.group(1)), cfg and cfg.group(1))
    lay = read('js/layout.js')
    check('1.11 El pie de todas las páginas enlaza el Aviso de privacidad y los Términos', 'href="privacidad.html"' in lay and 'href="terminos.html"' in lay)
    pub = ['index', 'guias', 'directorio', 'denuncias', 'planes', 'sobre-nosotros', 'privacidad', 'terminos']
    priv_pages = ['admin', 'carnet', 'chat', 'mascota', 'notificaciones', 'panel-aliado', 'perfil', 'qr', 'login', 'registro', 'recuperar', 'nueva-contrasena', '404']
    bad = [p for p in priv_pages if 'name="robots" content="noindex"' not in read(p + '.html')] + [p for p in pub if 'noindex' in read(p + '.html')]
    check('1.12 Páginas privadas, de acceso y 404 llevan noindex; las públicas (incluidas las legales) NO', not bad, bad)
    n404 = read('404.html')
    check('1.13 404.html usa <base href="/"> (funciona en cualquier ruta inexistente), está en español y no se indexa', '<base href="/">' in n404 and 'lang="es-MX"' in n404 and 'noindex' in n404)
    den = read('denuncias.html')
    check('1.14 Denuncias: ya no dice «Verificaremos estos datos»; enlaza a PROFEPA (gob.mx) con rel noopener y al aviso de privacidad',
          'Verificaremos' not in den and re.search(r'<a href="https://www\.gob\.mx/profepa"[^>]*rel="noopener noreferrer"', den) and 'href="privacidad.html"' in den)
    allf = {f: read(f) for f in ('js/legal.js', 'js/pages/legal.js', 'js/pages/perfil.js', 'js/pages/registro.js', 'js/pages/login.js')}
    bad = {f: re.findall(r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function', s) for f, s in allf.items()}
    check('1.15 Los archivos nuevos o tocados no usan innerHTML, eval ni document.write, y pasan la revisión de sintaxis',
          not any(bad.values()) and all(subprocess.run(['node', '--check', os.path.join(ROOT, f)], capture_output=True).returncode == 0 for f in allf), {k: v for k, v in bad.items() if v})
    check('1.16 La eliminación de cuenta usa SOLO funciones públicas del cliente y la función segura del servidor (nada de SQL, claves ni service_role)',
          "TP.rpc('delete_my_account'" in allf['js/pages/perfil.js'] and not re.search(r'service_role|sb_secret_|eyJhbGciOi', ''.join(allf.values())))
    sql = read_real('database/03_seguridad_rls.sql')
    check('1.17 delete_my_account: ejecución solo para «authenticated» y está en la lista del verificador', 'grant execute on function public.delete_my_account(text) to authenticated' in sql and "'delete_my_account'" in read_real('database/verificar_seguridad.sql'))

def g2(br):
    print('\n[2] Páginas legales en el navegador')
    reset_state()
    ctx = new_ctx(br); log = []; pg = ctx.new_page(); CUR[0] = pg; pg.set_default_timeout(8000)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None); pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    for p in ('privacidad', 'terminos'):
        pg.goto(f'{ORIGIN}/{p}.html'); pg.wait_for_load_state('load')
        check(f'2.1 {p}: sin errores de script ni violaciones de CSP, y NO consulta a Supabase (es una página pública sin sesión)', not csp_problems(log) and not [c for c in be.calls if c['path'] != '/auth/v1/logout'], (csp_problems(log)[:2], len(be.calls)))
        check(f'2.2 {p}: muestra la versión del texto ({FECHA})', FECHA in txt(pg, '.phead') and VERSION in txt(pg, 'article'), txt(pg, '.phead')[:120])
        warn = txt(pg, '#lg-falta')
        holes = pg.evaluate("['responsable', 'domicilio', 'contacto'].map(k => Array.from(document.querySelectorAll('[data-lg=' + k + ']')).map(e => e.textContent))")
        check(f'2.3 {p}: con config.js vacío avisa a quien administra qué datos faltan y CADA dato (responsable, domicilio, contacto) dice «(pendiente de completar)»',
              vis(pg, '#lg-falta') and all(x in warn for x in ('nombre', 'domicilio', 'medio de contacto')) and all(h and all(t == '(pendiente de completar)' for t in h) for h in holes), (warn, holes))
    # con los datos completos
    ST['legal'] = dict(RESPONSABLE='Ulises Romero', DOMICILIO='Calle Falsa 123, Guadalajara, Jalisco, México', CONTACTO='privacidad@ejemplo.mx')
    for p in ('privacidad', 'terminos'):
        pg.goto(f'{ORIGIN}/{p}.html'); pg.wait_for_load_state('load'); art = txt(pg, 'article')
        a = pg.locator('article a[href^="mailto:"]')
        check(f'2.4 {p}: con los datos completos desaparece el aviso, se escriben los datos y el contacto es un enlace mailto',
              not vis(pg, '#lg-falta') and 'Ulises Romero' in art and 'Calle Falsa 123' in art and '(pendiente' not in art and a.count() >= 1 and a.first.get_attribute('href') == 'mailto:privacidad@ejemplo.mx', (art[:200], a.count()))
    # hostil y demasiado largo
    ST['legal'] = dict(RESPONSABLE=HOSTILE, DOMICILIO='D' * 600, CONTACTO='<script>window.__pwn=1</script>')
    pg.goto(f'{ORIGIN}/privacidad.html'); pg.wait_for_load_state('load')
    art = txt(pg, 'article')
    check('2.5 Datos con HTML malicioso se muestran como TEXTO: no se ejecuta nada y no aparece ningún elemento nuevo (img/script)',
          pg.evaluate('window.__pwn') is None and pg.locator('article img, article script').count() == 0 and '<img src=x' in art and '<script>' in art)
    check('2.6 Un dato demasiado largo se recorta a 300 caracteres', 'D' * 300 in art and 'D' * 301 not in art)
    pg.set_viewport_size({'width': 390, 'height': 800}); tick(pg, 100)
    check('2.7 Aun con datos larguísimos, a 390 px no hay desborde horizontal', not pg.evaluate(A11Y_JS, {'touch': False}), pg.evaluate(A11Y_JS, {'touch': False}))
    ST['legal'] = None; pg.set_viewport_size({'width': 1100, 'height': 900})
    pg.goto(f'{ORIGIN}/privacidad.html#datos'); pg.wait_for_load_state('load')
    check('2.8 El índice funciona: la dirección con #datos deja visible la sección «Qué datos recabamos»', eventually(lambda: pg.evaluate("(() => { const r = document.getElementById('datos').getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; })()")))
    pg.goto(f'{ORIGIN}/index.html'); pg.wait_for_load_state('load')
    pg.click('footer a[href="privacidad.html"]'); pg.wait_for_url(re.compile(r'privacidad\.html')); ok1 = pg.locator('h1').inner_text() == 'Aviso de privacidad'
    pg.click('footer a[href="terminos.html"]'); pg.wait_for_url(re.compile(r'terminos\.html')); ok2 = pg.locator('h1').inner_text() == 'Términos y condiciones'
    check('2.9 Desde el pie de cualquier página se llega a los dos textos', ok1 and ok2)
    pg.goto(f'{ORIGIN}/privacidad.html#eliminar'); tick(pg, 100)
    check('2.10 El aviso enlaza a Perfil y a los términos; los términos enlazan al aviso y a Perfil', pg.locator('article a[href="perfil.html"]').count() >= 1 and pg.locator('article a[href="terminos.html"]').count() >= 1)
    for p, w in (('privacidad', 390), ('terminos', 390), ('privacidad', 1100)):
        pg.set_viewport_size({'width': w, 'height': 900}); pg.goto(f'{ORIGIN}/{p}.html'); pg.wait_for_load_state('load')
        a = pg.evaluate(A11Y_JS, {'touch': False}); c = pg.evaluate(AUDIT_JS)
        check(f'2.11 {p} a {w} px: sin desbordes, controles con nombre y contraste suficiente', not a and not c, (a, c[:2]))
    ctx.close()

def g3(br):
    print('\n[3] Registro con aceptación de términos')
    reset_state()
    ctx = new_ctx(br); log = []; pg = ctx.new_page(); CUR[0] = pg; pg.set_default_timeout(8000)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None); pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    be.confirm_on = False
    pg.goto(f'{ORIGIN}/registro.html'); pg.wait_for_load_state('load')
    links = pg.evaluate("Array.from(document.querySelectorAll('label.ck a')).map(a => [a.getAttribute('href'), a.target, a.rel])")
    check('3.1 La casilla enlaza al Aviso de privacidad y a los Términos en pestaña nueva con rel noopener', sorted(l[0] for l in links) == ['privacidad.html', 'terminos.html'] and all(l[1] == '_blank' and 'noopener' in l[2] for l in links), links)
    check('3.2 La casilla incluye la declaración de mayoría de edad (o autorización de tutor)', '18 años' in txt(pg, 'label.ck'))
    def fill(email, check_it=True):
        pg.fill('input[name=nombre]', 'Nuevo Usuario'); pg.fill('input[name=email]', email); pg.fill('input[name=pw]', 'MiClaveSegura1'); pg.fill('input[name=pw2]', 'MiClaveSegura1')
        pg.select_option('select[name=tipo]', 'owner'); pg.set_checked('input[name=consent]', check_it)
    fill('nuevo1@l11.mx', False); pg.click('button[type=submit]'); tick(pg, 200)
    check('3.3 Sin marcar la casilla: se explica que hay que aceptar el aviso y los términos y NO se llama al servidor', 'Aviso de privacidad' in txt(pg, '#msg') and 'Términos' in txt(pg, '#msg') and not be.signup_log, txt(pg, '#msg'))
    with ctx.expect_page() as newp:
        pg.click('label.ck a[href="privacidad.html"]')
    np_ = newp.value; np_.wait_for_load_state('load')
    check('3.4 El enlace abre el aviso en otra pestaña y el formulario conserva lo escrito', 'privacidad.html' in np_.url and pg.input_value('input[name=nombre]') == 'Nuevo Usuario' and pg.input_value('input[name=email]') == 'nuevo1@l11.mx')
    np_.close()
    pg.set_checked('input[name=consent]', True); pg.click('button[type=submit]')
    pg.wait_for_url(re.compile(r'(perfil|mascota|panel-aliado)\.html'), timeout=10000)
    sent = be.signup_log[-1] if be.signup_log else {}
    check('3.5 Al registrarse viaja la versión de los términos vigente (la de js/legal.js) en el metadato', (sent.get('data') or {}).get('terms_version') == VERSION, sent.get('data'))
    prof = be.profile_row(be.users['nuevo1@l11.mx']['id'])
    check('3.6 El disparador REAL de la base guardó la versión y la hora de aceptación en el perfil', prof and prof['terms_version'] == VERSION and prof['terms_accepted_at'], prof)
    # alterar el cliente
    ctx.close(); ctx = new_ctx(br); pg = ctx.new_page(); CUR[0] = pg                      # contexto nuevo: sin la sesión del alta anterior (así registro.html no redirige)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None); pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/registro.html'); pg.wait_for_load_state('load'); tick(pg, 200)
    r = pg.evaluate("""async () => { try { await TP.signUp({email:'nuevo2@l11.mx', password:'MiClaveSegura1', displayName:'X', accountType:'owner', redirectTo:location.href, termsVersion:"2026-01-01'; drop table x;--"}); return 'ok'; } catch (e) { return e.message; } }""")
    sent = be.signup_log[-1]
    check('3.7 Un valor de versión que no sea una fecha AAAA-MM-DD ni siquiera se envía (el cliente lo descarta)', 'terms_version' not in (sent.get('data') or {}), sent.get('data'))
    prof = be.profile_row(be.users['nuevo2@l11.mx']['id']) if 'nuevo2@l11.mx' in be.users else None
    check('3.8 …y la cuenta queda sin constancia de aceptación (no se inventa una)', prof and prof['terms_version'] is None and prof['terms_accepted_at'] is None, prof)
    check('3.9 Registro: sin errores de script ni de CSP', not csp_problems(log), csp_problems(log)[:2])
    be.confirm_on = True; ctx.close()
    ctx2 = new_ctx(br, 390, 800); pg2 = ctx2.new_page(); CUR[0] = pg2; pg2.goto(f'{ORIGIN}/registro.html'); pg2.wait_for_load_state('load')
    a = pg2.evaluate(A11Y_JS, {'touch': False}); c = pg2.evaluate(AUDIT_JS)
    check('3.10 Registro a 390 px: la casilla larga no desborda, hay contraste y todo tiene nombre', not a and not c, (a, c[:2]))
    box = pg2.evaluate("(() => { const i = document.querySelector('label.ck input').getBoundingClientRect(), l = document.querySelector('label.ck').getBoundingClientRect(); return [Math.round(i.width), Math.round(i.height), Math.round(i.top - l.top)]; })()")
    check('3.11 La casilla no se encoge por el texto largo y queda alineada con la primera línea', box[0] >= 13 and box[1] >= 13 and box[2] <= 8, box)
    ctx2.close()

def goto_delete(br, email, **kw):
    ctx, pg, log = open_page(br, email, 'perfil.html', **kw)
    return ctx, pg, log
def open_form(pg):
    pg.click('#del-abrir'); waitjs(pg, "!document.getElementById('f-borrar').hidden")
def submit_delete(pg, pw='ClaveSegura123', phrase=PHRASE):
    pg.fill('#del-pw', pw); pg.fill('#del-frase', phrase); pg.click('#del-ok')
def delmsg(pg): return txt(pg, '#msg-borrar') if vis(pg, '#msg-borrar') else ''
BUCKETS = ['avatars', 'pet-photos', 'qr-photos', 'business-media']

def g4(br):
    print('\n[4] Eliminar mi cuenta')
    reset_state()
    ana, ae = mk('ana'); bruno, be_ = mk('bruno')
    add_pet(ana); bp = add_pet(bruno, 'Rocky'); be.add_conv(ana); bc = be.add_conv(bruno)
    ctx, pg, log = goto_delete(br, ae)
    pg.goto(f'{ORIGIN}/index.html'); pg.wait_for_load_state('load')                 # historial: inicio → perfil, para probar «atrás» al final
    pg.goto(f'{ORIGIN}/perfil.html'); waitjs(pg, "document.body.classList.contains('tp-ok') && document.getElementById('p-email').value !== ''")
    check('4.1 Perfil de un dueño: la tarjeta «Eliminar mi cuenta» está visible, explica qué se borra y el formulario está oculto',
          vis(pg, '#card-borrar') and 'No se puede deshacer' in txt(pg, '#card-borrar') and not vis(pg, '#f-borrar') and pg.get_attribute('#del-abrir', 'aria-expanded') == 'false' and not vis(pg, '#del-admin'))
    open_form(pg)
    check('4.2 «Quiero eliminar mi cuenta…» abre el formulario, se oculta a sí mismo, avisa con aria-expanded y manda el foco a la contraseña',
          vis(pg, '#f-borrar') and not vis(pg, '#del-abrir') and pg.evaluate("document.activeElement.id") == 'del-pw' and pg.get_attribute('#del-abrir', 'aria-expanded') == 'true')
    pg.fill('#del-pw', 'algo'); pg.fill('#del-frase', 'ELIM'); pg.click('#del-cancelar'); tick(pg, 100)
    check('4.3 Cancelar cierra el formulario, borra lo escrito, devuelve el botón y no llama a nada', not vis(pg, '#f-borrar') and vis(pg, '#del-abrir') and pg.evaluate("document.activeElement.id") == 'del-abrir' and pg.input_value('#del-pw') == '' and pg.input_value('#del-frase') == '' and not be.del_calls and not be.store_log)
    open_form(pg); n0 = auth_pw_calls(); SEQ.clear()
    pg.fill('#del-frase', PHRASE); pg.click('#del-ok'); tick(pg, 150)
    check('4.4 Sin contraseña: se pide y no se llama a nadie', 'Escribe tu contraseña' in delmsg(pg) and auth_pw_calls() == n0 and not SEQ, delmsg(pg))
    submit_delete(pg, phrase='eliminar mi cuenta'); tick(pg, 150)
    check('4.5 Frase distinta (minúsculas): se rechaza en el navegador, sin tocar el servidor', 'exactamente' in delmsg(pg) and auth_pw_calls() == n0 and not SEQ, delmsg(pg))
    submit_delete(pg, pw='ClaveIncorrecta99'); waitjs(pg, "!document.getElementById('del-ok').disabled")
    check('4.6 Contraseña incorrecta: «La contraseña no es correcta», no se borra ningún archivo ni la cuenta, y el botón vuelve a funcionar',
          'La contraseña no es correcta' in delmsg(pg) and not be.store_log and not be.del_calls and exists(ana) and not pg.is_disabled('#del-cancelar'), (delmsg(pg), be.store_log))
    # fallo de Storage al borrar: no se pide borrar la cuenta
    for b in BUCKETS: be.seed_object(b, ana, 'a1.jpg')
    be.remove_fail = 500; SEQ.clear(); be.store_log.clear()
    submit_delete(pg); waitjs(pg, "!document.getElementById('del-ok').disabled")
    check('4.7 Si Storage falla al borrar un archivo: se muestra el error, NO se llama a delete_my_account y la cuenta y los archivos siguen ahí',
          delmsg(pg) and not be.del_calls and exists(ana) and any(k[1] == ana for k in [(a, n.split('/')[0]) for a, n in be.objects]) and ('POST', '/rest/v1/rpc/delete_my_account') not in SEQ, (delmsg(pg), be.del_calls))
    be.remove_fail = None; be.list_fail = 500; be.store_log.clear()
    submit_delete(pg); waitjs(pg, "!document.getElementById('del-ok').disabled")
    check('4.8 Si Storage falla al listar archivos: también se detiene todo y la cuenta sigue intacta', delmsg(pg) and not be.del_calls and exists(ana), (delmsg(pg), be.del_calls))
    # el servidor se niega si quedan archivos (segunda defensa), aunque el navegador no los vea
    be.list_fail = None; be.list_hidden = True; be.store_log.clear()
    submit_delete(pg); waitjs(pg, "!document.getElementById('del-ok').disabled")
    check('4.9 Si el listado no muestra archivos que SÍ existen, el SQL real se niega («Primero hay que borrar tus archivos») y la cuenta sigue intacta',
          'Primero hay que borrar tus archivos' in delmsg(pg) and len(be.del_calls) == 1 and exists(ana) and exists(ana, 'public.pets', 'owner_id'), (delmsg(pg), be.del_calls))
    # éxito
    be.list_hidden = False; be.del_calls.clear(); be.store_log.clear(); SEQ.clear()
    bfile = be.seed_object('avatars', bruno, 'b1.jpg'); n_obj = len(be.objects)
    for b in BUCKETS: be.seed_object(b, ana, 'a2.jpg')
    be.seed_object('pet-photos', ana, 'a3.jpg')
    submit_delete(pg); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    check('4.10 Éxito: vuelve a login.html con aviso de que la cuenta y los datos se eliminaron', 'eliminada=1' in pg.url and 'se eliminaron' in txt(pg, '#msg'), (pg.url, txt(pg, '#msg')))
    seq = [s for s in SEQ if s[1].startswith('/auth/v1/token') or '/storage/' in s[1] or s[1].endswith('delete_my_account') or s[1] == '/auth/v1/logout']
    i_tok = next(i for i, s in enumerate(seq) if s[1].startswith('/auth/v1/token') and s[0] == 'POST')
    i_rpc = max(i for i, s in enumerate(seq) if s[1].endswith('delete_my_account'))
    st_idx = [i for i, s in enumerate(seq) if '/storage/' in s[1]]
    i_out = max([i for i, s_ in enumerate(seq) if s_[1] == '/auth/v1/logout'] or [-1])
    check('4.11 El orden es: confirmar contraseña → listar y borrar archivos de los 4 depósitos → borrar la cuenta → cerrar la sesión (y nada de Storage después)',
          st_idx and i_tok < min(st_idx) and max(st_idx) < i_rpc < i_out, seq)
    listed = sorted(b for k, b, _ in be.store_log if k == 'LIST')
    check('4.12 Se listaron exactamente los 4 depósitos con archivos propios, usando como prefijo el identificador de la persona',
          listed == sorted(BUCKETS) and all(body.get('prefix') == ana for k, b, body in be.store_log if k == 'LIST'), be.store_log[:5])
    check('4.13 Se enviaron al servidor SOLO la frase y nada más (sin identificador: lo toma el servidor de la sesión)', be.del_calls == [{'p_confirm': PHRASE}], be.del_calls)
    check('4.14 La cuenta de Ana ya no existe en la base (auth, perfil, mascotas, conversaciones) ni sus archivos',
          not exists(ana) and not exists(ana, 'public.profiles') and not exists(ana, 'public.pets', 'owner_id') and not exists(ana, 'public.conversations', 'user_id')
          and not any(n.startswith(ana) for _, n in be.objects), None)
    check('4.15 Nada de otras personas se tocó: Bruno conserva cuenta, mascota, conversación y su archivo',
          exists(bruno) and exists(bruno, 'public.profiles') and exists(bruno, 'public.pets', 'owner_id') and exists(bruno, 'public.conversations', 'user_id') and ('avatars', bfile) in be.objects, None)
    check('4.16 La sesión local se borró y la persona ya no puede entrar con su contraseña (la cuenta no existe)', pg.evaluate("localStorage.getItem('tp-auth-v1')") is None, None)
    pg.fill('input[name=email]', ae); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.click('button[type=submit]'); tick(pg, 300)
    check('4.17 Intentar entrar con la cuenta eliminada falla con el mensaje normal de credenciales (y no entra)', 'login.html' in pg.url and pg.locator('#msg.err').count() == 1 and 'Correo o contraseña incorrectos' in txt(pg, '#msg') and auth_pw_calls() >= 1, (pg.url, txt(pg, '#msg')))
    pg.go_back(); tick(pg, 500)
    check('4.18 Con «atrás» solo se llega a la página anterior (el perfil fue reemplazado): sin sesión, cabecera de visitante y sin datos de la cuenta',
          pg.url == f'{ORIGIN}/index.html' and pg.locator('#acts a', has_text='Iniciar sesión').count() == 1 and pg.evaluate("localStorage.getItem('tp-auth-v1')") is None and 'ana@l11.mx' not in pg.content(), pg.url)
    check('4.19 Todo el flujo sin errores de script ni violaciones de CSP', not csp_problems(log), csp_problems(log)[:3])
    ctx.close()

def g5(br):
    print('\n[5] Eliminar cuenta: aliado, suspendida, administración y doble clic')
    reset_state()
    cris, ce = mk('cris', 'business'); susi, se = mk('susi', suspended=True); dani, de = mk('dani', admin=True); eli, ee = mk('eli', admin=True)
    biz = be.add_biz(cris, name='Veterinaria de Cris', status='approved'); be.add_promo(biz)
    be.seed_object('business-media', cris, 'logo.jpg'); be.seed_object('business-media', cris, 'f1.jpg')
    ctx, pg, log = goto_delete(br, ce); open_form(pg); submit_delete(pg); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    check('5.1 Aliado: se borran su negocio, sus promociones y sus archivos del directorio',
          not exists(cris) and not exists(biz, 'public.businesses') and be.sql(f"select count(*) from public.business_promotions where business_id = '{biz}'") == '0' and not any(n.startswith(cris) for _, n in be.objects), None)
    ctx.close()
    ctx, pg, log = goto_delete(br, se)
    check('5.2 Cuenta suspendida: sus formularios de datos y contraseña quedan bloqueados, pero la eliminación sigue disponible', pg.is_disabled('#p-nombre') and pg.is_disabled('#pw-actual') and vis(pg, '#del-abrir') and not pg.is_disabled('#del-abrir'))
    open_form(pg); submit_delete(pg); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    check('5.3 Cuenta suspendida: puede eliminar su cuenta', not exists(susi), None); ctx.close()
    ctx, pg, log = goto_delete(br, de)
    check('5.4 Administración: se explica que no se elimina desde aquí, no hay botón ni formulario', vis(pg, '#del-admin') and 'otra persona administradora' in txt(pg, '#del-admin') and not vis(pg, '#del-abrir') and not vis(pg, '#f-borrar'))
    r = pg.evaluate("""async () => { try { await TP.rpc('delete_my_account', {p_confirm: 'ELIMINAR MI CUENTA'}); return {ok: true}; } catch (e) { return {ok: false, code: e.code, msg: e.message}; } }""")
    check('5.5 Aunque alguien manipule la consola, el SERVIDOR rechaza borrar una cuenta de administración y la cuenta sigue', not r['ok'] and 'administración' in r['msg'] and exists(dani) and exists(dani, 'public.admin_roles', 'user_id'), r)
    ctx.close()
    # doble clic
    pe, pee = mk('pepe'); add_pet(pe)
    ctx, pg, log = goto_delete(br, pee); open_form(pg); be.del_calls.clear()
    pg.fill('#del-pw', 'ClaveSegura123'); pg.fill('#del-frase', PHRASE); pg.dblclick('#del-ok'); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    check('5.6 Doble clic en «Eliminar»: solo se pide una vez el borrado', len(be.del_calls) == 1 and not exists(pe), be.del_calls)
    ctx.close()
    # frase con espacios al inicio/fin se acepta (el servidor la recorta) pero no una distinta; el servidor también valida
    ana2, a2e = mk('ana2')
    ctx, pg, log = goto_delete(br, a2e)
    r = pg.evaluate("""async () => { try { await TP.rpc('delete_my_account', {p_confirm: 'eliminar mi cuenta'}); return {ok: true}; } catch (e) { return {ok: false, code: e.code, msg: e.message}; } }""")
    r2 = pg.evaluate("""async () => { try { await TP.rpc('delete_my_account', {}); return {ok: true}; } catch (e) { return {ok: false, code: e.code, msg: e.message}; } }""")
    check('5.7 Desde la consola, frase incorrecta o ausente: el servidor se niega y la cuenta sigue', not r['ok'] and not r2['ok'] and exists(ana2) and 'ELIMINAR MI CUENTA' in (r['msg'] or ''), (r, r2))
    ctx.close()
    # visitante sin sesión
    ctx = new_ctx(br); ctx.add_init_script("localStorage.clear()"); pg = ctx.new_page(); pg.goto(f'{ORIGIN}/index.html'); pg.wait_for_load_state('load')
    r = pg.evaluate("""async () => { try { await TP.rpc('delete_my_account', {p_confirm: 'ELIMINAR MI CUENTA'}); return {ok: true}; } catch (e) { return {ok: false, status: e.status, code: e.code}; } }""")
    check('5.8 Un visitante sin sesión no puede llamar a delete_my_account', not r['ok'], r); ctx.close()

def g6(br):
    print('\n[6] Anti-robots (Turnstile) al confirmar la contraseña en Perfil')
    reset_state(); ST['site_key'] = '0x4AAAAAAATESTKEY12345'
    ana, ae = mk('anat')
    ctx, pg, log = goto_delete(br, ae)
    try: waitjs(pg, "document.querySelectorAll('#pw-captcha .ts-fake').length === 1", 4)
    except TimeoutError: pass
    check('6.1 Con Turnstile activo, el formulario de cambiar contraseña muestra la verificación', pg.locator('#pw-captcha .ts-fake').count() == 1)
    pg.fill('#pw-actual', 'ClaveSegura123'); pg.fill('#pw-nueva', 'OtraClaveSegura456'); pg.fill('#pw-repetir', 'OtraClaveSegura456'); n0 = auth_pw_calls()
    pg.click('#f-pw button[type=submit]'); tick(pg, 200)
    check('6.2 Sin resolverla: se pide completar la verificación y NO se intenta confirmar la contraseña', 'verificación anti-robots' in txt(pg, '#msg-pw') and auth_pw_calls() == n0, txt(pg, '#msg-pw'))
    pg.click('#pw-captcha .ts-fake'); pg.click('#f-pw button[type=submit]'); waitjs(pg, "document.getElementById('msg-pw') && /actualizada/.test(document.getElementById('msg-pw').textContent)")
    tok = tokens_calls()[-1]['body']
    check('6.3 Resuelta: el token viaja en gotrue_meta_security.captcha_token (antes no se enviaba y Supabase lo rechazaría) y la contraseña cambia', (tok.get('gotrue_meta_security') or {}).get('captcha_token', '').startswith('ok.'), tok)
    check('6.4 …y la verificación se reinicia, porque cada token sirve una sola vez', pg.evaluate('window.__ts.resets') >= 1)
    check('6.5 El formulario de eliminar NO carga la verificación hasta que se abre', pg.locator('#del-captcha .ts-fake').count() == 0)
    open_form(pg); waitjs(pg, "document.querySelectorAll('#del-captcha .ts-fake').length === 1")
    pg.fill('#del-pw', 'OtraClaveSegura456'); pg.fill('#del-frase', PHRASE); n0 = auth_pw_calls(); pg.click('#del-ok'); tick(pg, 200)
    check('6.6 Eliminar sin resolver la verificación: se pide y no pasa nada más', 'verificación anti-robots' in delmsg(pg) and auth_pw_calls() == n0 and not be.del_calls, delmsg(pg))
    pg.fill('#del-pw', 'mala'); pg.click('#del-captcha .ts-fake'); pg.click('#del-ok'); waitjs(pg, "!document.getElementById('del-ok').disabled")
    r0 = pg.evaluate('window.__ts.resets')
    check('6.7 Con contraseña mala la verificación se reinicia (token gastado) y no se borró nada', 'no es correcta' in delmsg(pg) and not be.del_calls and exists(ana) and r0 >= 2, (delmsg(pg), r0))
    pg.fill('#del-pw', 'OtraClaveSegura456'); pg.click('#del-captcha .ts-fake'); pg.click('#del-ok'); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    tok = tokens_calls()[-1]['body']
    check('6.8 Con todo correcto, la confirmación lleva su token y la cuenta se elimina', (tok.get('gotrue_meta_security') or {}).get('captcha_token', '').startswith('ok.') and not exists(ana), tok)
    ctx.close()
    # cancelar destruye el widget
    bea, bee = mk('bea')
    ctx, pg, log = goto_delete(br, bee); open_form(pg); waitjs(pg, "document.querySelectorAll('#del-captcha .ts-fake').length === 1"); pg.click('#del-cancelar'); tick(pg, 150)
    check('6.9 Cancelar desmonta la verificación (no quedan widgets colgados)', pg.evaluate('window.__ts.removed') >= 1 and pg.locator('#del-captcha .ts-fake').count() == 0)
    ctx.close(); ST['site_key'] = ''
    # sin Turnstile configurado nada se muestra
    ctx, pg, log = goto_delete(br, bee)
    check('6.10 Sin «site key» no aparece ningún recuadro anti-robots en Perfil', pg.locator('.ts-fake').count() == 0 and pg.locator('#pw-captcha .captcha').count() == 0)
    ctx.close()

def g7(br):
    print('\n[7] 404, denuncias y vista en teléfono')
    reset_state()
    ctx = new_ctx(br); log = []; pg = ctx.new_page(); CUR[0] = pg; pg.set_default_timeout(8000)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None); pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    resp = pg.goto(f'{ORIGIN}/ruta/que/no/existe'); pg.wait_for_load_state('load')
    check('7.1 Una ruta inexistente (incluso anidada) muestra la página 404 con estado 404 y con estilos y cabecera', resp.status == 404 and 'Página no encontrada' in txt(pg, 'h1') and pg.locator('header.nav').count() == 1 and pg.evaluate("getComputedStyle(document.body).backgroundColor") != 'rgba(0, 0, 0, 0)', resp.status)
    check('7.2 La 404 no produce errores de script ni de CSP', not csp_problems(log), csp_problems(log)[:2])
    pg.click('#main a.btn >> text=Ir al inicio'); pg.wait_for_url(re.compile(r'/index\.html$'))
    check('7.3 Desde una 404 anidada, «Ir al inicio» llega a /index.html (gracias a <base href="/">)', pg.url == f'{ORIGIN}/index.html', pg.url)
    pg.goto(f'{ORIGIN}/denuncias.html'); pg.wait_for_load_state('load')
    card = pg.locator('.card:has(h3:text-is("Autoridades"))')
    lk = card.locator('a[href="https://www.gob.mx/profepa"]')
    check('7.4 Denuncias: la tarjeta de autoridades ya no tiene la leyenda provisional, enlaza a PROFEPA y al aviso de privacidad', 'Verificaremos' not in card.inner_text() and lk.count() == 1 and 'noopener' in lk.get_attribute('rel') and lk.get_attribute('target') == '_blank' and card.locator('a[href="privacidad.html"]').count() == 1)
    ctx.close()
    ana, ae = mk('mov')
    for w in (390, 360):
        ctx, pg, log = goto_delete(br, ae, w=w, h=800); open_form(pg); pg.fill('#del-pw', 'x' * 60); pg.fill('#del-frase', PHRASE); pg.evaluate("document.getElementById('msg-borrar').hidden=false;document.getElementById('msg-borrar').className='msg err';document.getElementById('msg-borrar').textContent='Un mensaje de error bastante largo para comprobar que no se desborda en el teléfono ' + 'palabra'.repeat(8)")
        a = pg.evaluate(A11Y_JS, {'touch': True}); c = pg.evaluate(AUDIT_JS)
        check(f'7.5 Perfil con el formulario de eliminar abierto a {w} px: sin desbordes, botones tocables (≥ 44 px) y contraste suficiente', not a and not c, (a, c[:2]))
        ctx.close()
    ctx, pg, log = goto_delete(br, ae)
    pg.keyboard.press('Tab')
    pg.focus('#del-abrir'); pg.keyboard.press('Enter'); tick(pg, 100)
    check('7.6 Con teclado: Enter en «Quiero eliminar…» abre el formulario y el foco queda en la contraseña', vis(pg, '#f-borrar') and pg.evaluate("document.activeElement.id") == 'del-pw')
    pg.fill('#del-pw', 'ClaveSegura123'); pg.fill('#del-frase', PHRASE); pg.keyboard.press('Enter'); pg.wait_for_url(re.compile(r'login\.html'), timeout=15000)
    check('7.7 Con teclado: Enter en el campo de la frase envía el formulario y elimina la cuenta', not exists(ana), None)
    ctx.close()

GROUPS = [g1, g2, g3, g4, g5, g6, g7]
if __name__ == '__main__':
    prepare_db()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for i, g in enumerate(GROUPS, 1):
            if group(i):
                try: g(br)
                except Exception as e:
                    import traceback; traceback.print_exc(); check(f'GRUPO {i}: terminó sin excepción', False, repr(e)[:300])
        br.close()
    bad = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(bad)}/{len(results)} comprobaciones superadas')
    for n, _, d in bad: print('  FALLA:', n, '->', d)
    sys.exit(1 if bad else 0)
