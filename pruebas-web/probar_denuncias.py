"""
Pruebas de interfaz de la Etapa 6 (denuncias anónimas, seguimiento y anti-robots) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio, servido con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP);
            la función segura supabase/functions/submit-complaint/index.ts (ejecutada con Node) y las funciones SQL
            submit_complaint / complaint_precheck / track_complaint sobre una base PostgreSQL local con el esquema de database/.
  SIMULADO  Cloudflare Turnstile (un «api.js» falso que dibuja un botón y entrega tokens «ok.*»), el Storage (en memoria),
            y Supabase Auth (mock_etapa6.py: con «CAPTCHA protection» activable).

Uso:  python3 pruebas-web/probar_denuncias.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), Node 22+, playwright + chromium, Pillow, numpy.
Variables: TP_PORT (sitio, 8768), TP_FN_PORT (puente, 8799), TP_SITE (carpeta del sitio; las pruebas de las pruebas usan una copia «saboteada»).
"""
import datetime, http.client, http.server, io, json, os, re, socketserver, subprocess, sys, threading, time, uuid
from zoneinfo import ZoneInfo
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa6 import Backend6

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8768)); FN_PORT = int(os.environ.get('TP_FN_PORT', 8799)); DB = os.environ.get('TP_WEB_DB', 'tp_web')
ORIGIN = f'http://localhost:{PORT}'
SUPA = 'https://mtkbxnhsjqqdbrjeaslo.supabase.co'
MX = ZoneInfo('America/Mexico_City')
CONFIG_JS = open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", CONFIG_JS).group(1)
SITE_KEY = '1x00000000000000000000AA'          # la «site key» de prueba oficial de Cloudflare (siempre pasa); aquí solo es un texto

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

# ------------------------------------------------------------------ base de datos y puente
def sh(*a, **kw): return subprocess.run(a, capture_output=True, text=True, **kw)
def sql(q, db=DB): return sh('psql', '-X', '-q', '-t', '-A', '-d', db, '-c', q).stdout.strip()
def prepare_db():
    env = dict(os.environ, PGOPTIONS='-c client_min_messages=warning')
    sh('psql', '-X', '-q', '-d', 'postgres', '-c', f'drop database if exists {DB}', '-c', f'create database {DB}')
    for f in ('database/pruebas/shim_supabase.sql', 'database/00_instalar_todo.sql'):
        r = subprocess.run(['psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-d', DB, '-o', '/dev/null'], input=open(os.path.join(REAL_ROOT, f), encoding='utf-8').read(),
                           capture_output=True, text=True, env=env)
        if r.returncode: raise SystemExit('No se pudo preparar la base: ' + r.stderr[:400])
def start_bridge():
    p = subprocess.Popen(['node', '--experimental-strip-types', '--no-warnings', os.path.join(HERE, 'servidor_funcion.mjs'), str(FN_PORT)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=dict(os.environ, TP_WEB_DB=DB))
    t0 = time.time()
    while time.time() - t0 < 15:
        line = p.stdout.readline()
        if 'listo' in line: return p
        if p.poll() is not None: raise SystemExit('El puente no arrancó: ' + line + p.stdout.read())
    raise SystemExit('El puente no arrancó a tiempo')
def bridge(method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', FN_PORT, timeout=60)
    c.request(method, path, body, headers or {}); r = c.getresponse(); data = r.read(); c.close()
    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), data
def ctl(path, obj=None): return bridge('POST', path, json.dumps(obj or {}).encode(), {'content-type': 'application/json'})
def bstate(): return json.loads(bridge('GET', '/__state')[2])
def bridge_reset(): ctl('/__reset')
def n_rows(): return int(sql('select count(*) from public.complaints'))
def today(): return datetime.datetime.now(MX).date()

# ------------------------------------------------------------------ sitio estático con las cabeceras de _headers
HEADERS = {}
for line in open(os.path.join(ROOT, '_headers'), encoding='utf-8').read().splitlines()[1:]:
    if line.startswith('/') or line.startswith('#') or not line.strip(): break
    if ':' in line: k, v = line.strip().split(':', 1); HEADERS[k.strip()] = v.strip()
HEADERS.pop('Strict-Transport-Security', None)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=ROOT, **kw)
    def end_headers(self):
        for k, v in HEADERS.items(): self.send_header(k, v)
        self.send_header('Cache-Control', 'no-store'); super().end_headers()
    def log_message(self, *a): pass
class Srv(socketserver.ThreadingTCPServer):
    def handle_error(self, request, client_address): pass         # el navegador cierra conexiones a medias al cambiar de página: es normal
socketserver.TCPServer.allow_reuse_address = True
srv = Srv(('127.0.0.1', PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

# ------------------------------------------------------------------ estado de la simulación
be = Backend6(KEY)
ST = dict(site_key='', ts='ok', fn='normal', ip='198.51.100.1', fn_delay_probe=None)     # ts: ok | block ; fn: normal | 404 | abort | html500 | badjson | nocode
FN_REQS = []          # peticiones POST a la función segura (lo que ve el servidor)
TS_REQS = []          # peticiones a challenges.cloudflare.com
CUR = [None]
_ip = [0]
def fresh_ip():
    _ip[0] += 1; return f'198.51.{100 + _ip[0] // 250}.{_ip[0] % 250 + 1}'

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
  S.solve = function(id){ var w = S.widgets[id]; S.tokens++; w.token = 'ok.' + S.tokens + '.' + Math.random().toString(36).slice(2); w.opts.callback(w.token); };
  S.put = function(id, t){ S.widgets[id].opts.callback(t); };
  S.expire = function(id){ S.widgets[id].opts['expired-callback'](); };
  S.fail = function(id){ S.widgets[id].opts['error-callback'](); };
})();"""

def route_site(route):                          # config.js con (o sin) «site key»
    body = re.sub(r"TURNSTILE_SITE_KEY:\s*'[^']*'", "TURNSTILE_SITE_KEY: '" + ST['site_key'] + "'", CONFIG_JS)
    route.fulfill(status=200, headers={**HEADERS, 'content-type': 'application/javascript', 'cache-control': 'no-store'}, body=body)
def route_ts(route):
    TS_REQS.append(route.request.url)
    if ST['ts'] == 'block': route.abort(); return
    route.fulfill(status=200, headers={'content-type': 'application/javascript'}, body=TS_STUB)

def bridge_forward(route, path, extra=None, cors=False):
    req = route.request
    hd = {k: v for k, v in req.headers.items() if k.lower() not in ('host', 'content-length', 'connection', 'accept-encoding')}
    hd.update(extra or {})
    st, rh, data = bridge(req.method, path, req.post_data_buffer, hd)
    out = {k: v for k, v in rh.items() if k not in ('transfer-encoding', 'connection', 'keep-alive', 'content-length')}
    if cors: out.update(CORS)
    route.fulfill(status=st, headers=out, body=data)
def route_fn(route):
    req = route.request
    if req.method != 'OPTIONS': FN_REQS.append(dict(headers={k.lower(): v for k, v in req.headers.items()}, body=req.post_data_buffer, ip=ST['ip']))
    m = ST['fn']
    if req.method != 'OPTIONS' and m != 'normal':
        if m == '404': route.fulfill(status=404, headers={**CORS, 'content-type': 'application/json'}, body='{"message":"Requested function was not found"}'); return
        if m == 'abort': route.abort(); return
        if m == 'html500': route.fulfill(status=502, headers={**CORS, 'content-type': 'text/html'}, body='<html><body>Bad gateway <script>window.__x=1</script></body></html>'); return
        if m == 'badjson': route.fulfill(status=200, headers={**CORS, 'content-type': 'application/json'}, body='{"ok":true,"code":"<img src=x onerror=window.__x=1>"}'); return
        if m == 'nocode': route.fulfill(status=200, headers={**CORS, 'content-type': 'application/json'}, body='{"ok":true}'); return
    bridge_forward(route, '/functions/v1/submit-complaint', {'cf-connecting-ip': ST['ip']})
def route_track(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    bridge_forward(route, '/rest/v1/rpc/track_complaint', {'x-test-ip': ST['ip']}, cors=True)
def route_supa(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    status, data = be.handle(req.method, req.url, req.headers, req.post_data)
    route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body='' if data is None else json.dumps(data))

def new_ctx(br, w=1100, h=1000):
    ctx = br.new_context(viewport={'width': w, 'height': h}, accept_downloads=True)
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), route_supa)          # Playwright da prioridad a la ruta registrada DESPUÉS: la general va primero
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/functions/v1/submit-complaint$'), route_fn)
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/rest/v1/rpc/track_complaint$'), route_track)
    ctx.route(re.compile(r'https://challenges\.cloudflare\.com/.*'), route_ts)
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    ctx.route(f'{ORIGIN}/js/config.js', route_site)
    return ctx
def new_page(ctx, log):
    pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    return pg
def open_page(br, name, key=SITE_KEY, w=1100, h=1000, ctx=None):
    ST['site_key'] = key
    ctx = ctx or new_ctx(br, w, h); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/{name}.html'); pg.wait_for_selector('body.tp-ok, #site-header *', timeout=8000)
    return ctx, pg, log

# ------------------------------------------------------------------ utilidades
def waitjs(pg, expr, timeout=8.0):
    t0 = time.time(); last = None
    while time.time() - t0 < timeout:
        try:
            if pg.evaluate(expr): return True
        except Exception as e: last = e
        try: pg.wait_for_timeout(40)
        except Exception: time.sleep(0.04)
    raise TimeoutError(f'Condición no cumplida en {timeout}s: {expr[:140]} {last or ""}')
def eventually(cond, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond(): return True
        except Exception: pass
        try: CUR[0].wait_for_timeout(50)
        except Exception: time.sleep(0.05)
    return False
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def txt(pg, sel): return pg.inner_text(sel) if pg.locator(sel).count() else ''
JUNK_RE = re.compile(r'\bnull\b|undefined|\[object|\bNaN\b|Invalid Date')
def junk(pg, sel): return JUNK_RE.findall(txt(pg, sel))
def img_bytes(w, h, fmt='JPEG', exif=False, seed=1):
    y, x = np.indices((h, w)); arr = np.stack([(x * 255 // w), (y * 255 // h), ((x + y) * 255 // (w + h))], -1).astype(np.uint8)
    arr = arr ^ np.random.RandomState(seed).randint(0, 8, arr.shape).astype(np.uint8)
    im = Image.fromarray(arr); b = io.BytesIO(); kw = {}
    if exif:
        e = Image.Exif(); e[0x010F] = 'CamaraSecreta'; e[0x0132] = '2026:11:04 12:00:00'; kw['exif'] = e
    im.save(b, fmt, **kw); return b.getvalue()
def files(*items): return [dict(name=n, mimeType=m, buffer=b) for n, m, b in items]
def parse_multipart(headers, body):
    ct = headers.get('content-type', ''); m = re.search(r'boundary=(.+)$', ct)
    if not m or body is None: return []
    out = []
    for part in body.split(b'--' + m.group(1).encode()):
        if b'\r\n\r\n' not in part: continue
        head, _, data = part.partition(b'\r\n\r\n'); data = data[:-2] if data.endswith(b'\r\n') else data
        h = head.decode('utf-8', 'replace'); nm = re.search(r'name="([^"]*)"', h); fn = re.search(r'filename="([^"]*)"', h); ty = re.search(r'Content-Type:\s*(\S+)', h, re.I)
        out.append(dict(name=nm.group(1) if nm else '', filename=fn.group(1) if fn else None, type=ty.group(1) if ty else None, data=data))
    return out
def posts(): return [r for r in FN_REQS]

def solve(pg, i=0):
    waitjs(pg, f'!!(window.__ts && window.__ts.widgets.length > {i})')
    pg.evaluate(f'window.__ts.solve({i})')
def fill(pg, tipo='abandono', desc='Hay un perro abandonado desde hace varios días en el terreno baldío.', fecha=None, estado='Jalisco', muni='Zapopan', ref='Frente al parque', acepto=True):
    pg.select_option('#dn-tipo', tipo) if tipo else None
    pg.fill('#dn-desc', desc); pg.fill('#dn-fecha', fecha or today().isoformat()); pg.fill('#dn-estado', estado); pg.fill('#dn-muni', muni); pg.fill('#dn-ref', ref)
    if acepto: pg.check('#dn-acepto')
def msg(pg): return txt(pg, '#dn-msg') if pg.locator('#dn-msg').is_visible() else ''
def submit_and_wait(pg):
    n0 = len(FN_REQS); pg.click('#dn-enviar')
    eventually(lambda: pg.locator('#dn-listo').is_visible() or pg.locator('#dn-msg').is_visible(), 15)
    return len(FN_REQS) - n0
def insert_complaint(code, status='recibida', public_update=None, internal='NOTA-INTERNA-SECRETA'):
    pu = 'null' if public_update is None else "'" + public_update.replace("'", "''") + "'"
    sql(f"insert into public.complaints (tracking_code, type, description, approx_date, state, municipality, status, public_update, internal_notes) values ('{code}', 'abandono', "
        f"'Descripción de prueba de una denuncia para el seguimiento público.', current_date, 'Jalisco', 'Zapopan', '{status}', {pu}, '{internal}')")

# ================================================================== PRUEBAS
prepare_db(); bproc = start_bridge()
try:
  with sync_playwright() as pw:
    br = pw.chromium.launch()
    all_logs = []

    # ---------------------------------------------------------------- 1. Sin clave de Turnstile
    print('\n[1] Sin «site key» de Turnstile configurada (estado real del repositorio)')
    ST['ip'] = fresh_ip(); n0 = len(TS_REQS)
    ctx, pg, log = open_page(br, 'denuncias', key=''); all_logs.append(log)
    check('1.1 Se avisa que el envío no está activado', 'todavía no está activado' in txt(pg, '#dn-aviso') and pg.locator('#dn-aviso').is_visible(), txt(pg, '#dn-aviso'))
    check('1.2 El aviso menciona el 911 por si hay peligro', '911' in txt(pg, '#dn-aviso'))
    off = pg.evaluate("Array.from(document.querySelectorAll('#f-denuncia input, #f-denuncia select, #f-denuncia textarea, #f-denuncia button')).filter(x => !x.disabled).length")
    check('1.3 Todo el formulario de reporte queda deshabilitado', off == 0, f'{off} controles activos')
    check('1.4 No se descarga nada de Cloudflare', len(TS_REQS) == n0, TS_REQS[n0:])
    pg.evaluate("document.getElementById('f-denuncia').requestSubmit()"); pg.wait_for_timeout(200)
    check('1.5 Forzar el envío por código no manda nada al servidor', len(FN_REQS) == 0)
    check('1.6 El seguimiento sigue disponible', pg.locator('#sg-codigo').is_enabled() and pg.locator('#sg-boton').is_enabled())
    check('1.7 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # registro sin clave: igual que antes de la Etapa 6
    be.reset(); ctx, pg, log = open_page(br, 'registro', key=''); all_logs.append(log)
    check('1.8 Registro sin clave: no aparece verificación', pg.locator('.captcha').count() == 0)
    pg.fill('input[name=nombre]', 'Ana Prueba'); pg.fill('input[name=email]', 'ana@ejemplo.mx'); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.fill('input[name=pw2]', 'ClaveSegura123')
    pg.select_option('select[name=tipo]', 'owner'); pg.check('input[name=consent]'); pg.click('button[type=submit]')
    eventually(lambda: be.captcha_bodies, 5)
    check('1.9 Registro sin clave: la petición NO lleva gotrue_meta_security', be.captcha_bodies and 'gotrue_meta_security' not in be.captcha_bodies[-1], be.captcha_bodies[-1:] )
    check('1.10 Registro sin clave: sigue funcionando', eventually(lambda: 'Recibimos tu registro' in txt(pg, '#msg')), txt(pg, '#msg'))
    ctx.close()

    # ---------------------------------------------------------------- 2. Claves mal pegadas
    print('\n[2] Clave mal configurada (por ejemplo, la SECRETA pegada por error)')
    for label, key, frag in (('2.1 clave demasiado larga (parece la secreta)', '0x4AAAAAAA' + 'B' * 35, 'SECRETA'), ('2.2 formato no válido', 'abc def!!', 'formato válido')):
        n0 = len(TS_REQS); ctx, pg, log = open_page(br, 'denuncias', key=key); all_logs.append(log)
        t = txt(pg, '#dn-aviso')
        check(label + ': aviso claro y formulario bloqueado', frag in t and pg.locator('#dn-enviar').is_disabled(), t)
        check(label + ': no se descarga el script ni se muestra la clave', len(TS_REQS) == n0 and key not in pg.content(), TS_REQS[n0:])
        ctx.close()
    ctx, pg, log = open_page(br, 'registro', key='0x4AAAAAAA' + 'B' * 35)
    check('2.3 Registro con clave secreta pegada: lo avisa y no envía nada', 'SECRETA' in txt(pg, '#msg'), txt(pg, '#msg')); ctx.close()

    # ---------------------------------------------------------------- 3. Con clave: validaciones
    print('\n[3] Formulario con Turnstile: validaciones del navegador')
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); n0 = len(TS_REQS)
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    waitjs(pg, '!!(window.__ts && window.__ts.widgets.length === 1)')
    check('3.1 Se descarga el script de Cloudflare (modo explícito) una vez', len(TS_REQS) - n0 == 1 and 'render=explicit' in TS_REQS[-1], TS_REQS[n0:])
    w = pg.evaluate('({k: window.__ts.widgets[0].opts.sitekey, l: window.__ts.widgets[0].opts.language, n: window.__ts.widgets.length})')
    check('3.2 El widget usa la «site key» de config.js y español', w == dict(k=SITE_KEY, l='es', n=1), w)
    check('3.3 Formulario activo y sin aviso', pg.locator('#dn-enviar').is_enabled() and not pg.locator('#dn-aviso').is_visible())
    check('3.4 La fecha máxima es hoy (México)', pg.get_attribute('#dn-fecha', 'max') == today().isoformat(), pg.get_attribute('#dn-fecha', 'max'))
    pg.fill('#dn-desc', 'Hola 🐶🐶🐶'); check('3.5 El contador cuenta caracteres (no unidades UTF-16)', txt(pg, '#dn-cuenta') == '8 / 4000', txt(pg, '#dn-cuenta'))
    pg.fill('#dn-desc', '')
    def expect_err(name, frag):
        pg.click('#dn-enviar'); pg.wait_for_timeout(120)
        check(name, frag in msg(pg) and len(FN_REQS) == 0, (msg(pg), len(FN_REQS)))
    expect_err('3.6 Falta el tipo', 'tipo de situación')
    pg.select_option('#dn-tipo', 'abandono'); pg.fill('#dn-desc', 'a' * 29); expect_err('3.7 Descripción de 29 caracteres', 'al menos 30')
    pg.fill('#dn-desc', 'Hay un perro abandonado desde hace varios días en el terreno.'); expect_err('3.8 Falta la fecha', 'fecha aproximada válida')
    pg.fill('#dn-fecha', (today() + datetime.timedelta(days=3)).isoformat()); expect_err('3.9 Fecha futura', 'fecha aproximada válida')
    pg.fill('#dn-fecha', today().isoformat()); expect_err('3.10 Falta el estado', 'estado')
    pg.fill('#dn-estado', 'Jalisco'); expect_err('3.11 Falta el municipio', 'municipio')
    pg.fill('#dn-muni', 'Zapopan'); expect_err('3.12 Falta aceptar la casilla', 'Marca la casilla')
    pg.check('#dn-acepto'); expect_err('3.13 Falta la verificación anti-robots', 'verificación anti-robots')
    pg.fill('#dn-ref', 'x' * 300); pg.evaluate("document.getElementById('dn-ref').maxLength = 400"); pg.fill('#dn-ref', 'x' * 301)
    pg.evaluate('window.__ts.solve(0)'); expect_err('3.14 Referencia de 301 caracteres', '300 caracteres')
    pg.fill('#dn-ref', ''); pg.evaluate('window.__ts.expire(0)'); expect_err('3.15 Un token vencido deja de servir', 'verificación anti-robots')
    check('3.16 Ninguna validación gastó una petición al servidor', len(FN_REQS) == 0)
    check('3.17 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ---------------------------------------------------------------- 4. Envío correcto, anonimato y código
    print('\n[4] Envío correcto sin fotos, anonimato y código de seguimiento')
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); rows0 = n_rows()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=ORIGIN)
    fill(pg); solve(pg)
    n = submit_and_wait(pg)
    code = txt(pg, '#dn-codigo')
    check('4.0 El foco pasa al título del resultado (accesibilidad)', pg.evaluate("document.activeElement && document.activeElement.tagName") == 'H2')
    check('4.1 Se envió exactamente UNA petición', n == 1, n)
    check('4.2 Se muestra el código con el formato TP-XXXX-XXXX', re.fullmatch(r'TP-[A-Z2-9]{4}-[A-Z2-9]{4}', code or ''), code)
    check('4.3 El formulario se oculta y se explica que no se presentó ante autoridades', pg.locator('#f-denuncia').is_hidden() and 'no lo presentó ante ninguna autoridad' in txt(pg, '#dn-listo'), txt(pg, '#dn-listo')[:200])
    check('4.4 Se advierte que el código no se puede recuperar', 'no podemos recuperarlo' in txt(pg, '#dn-listo'))
    req = FN_REQS[-1]; parts = parse_multipart(req['headers'], req['body']); names = sorted(p['name'] for p in parts)
    check('4.5 Campos enviados: solo los del reporte (sin nombre, correo, teléfono, sesión)',
          names == sorted(['type', 'description', 'approx_date', 'state', 'municipality', 'location_reference', 'website', 'cf-turnstile-response']), names)
    hd = req['headers']
    check('4.6 La petición no lleva sesión (Authorization) ni cookies', 'authorization' not in hd and 'cookie' not in hd, [k for k in hd if k in ('authorization', 'cookie')])
    check('4.7 Solo lleva la clave pública en «apikey»', hd.get('apikey') == KEY)
    check('4.8 El token de Turnstile viajó en el campo cf-turnstile-response', next((p['data'].decode() for p in parts if p['name'] == 'cf-turnstile-response'), '').startswith('ok.'))
    check('4.9 Se creó exactamente una fila', n_rows() == rows0 + 1, (rows0, n_rows()))
    row = sql(f"select status || '|' || type || '|' || state || '|' || municipality || '|' || cardinality(photo_paths) from public.complaints where tracking_code = '{code}'")
    check('4.10 La fila tiene el estado «recibida» y los datos enviados, sin fotos', row == 'recibida|abandono|Jalisco|Zapopan|0', row)
    cols = sql("select string_agg(column_name, ',') from information_schema.columns where table_schema = 'public' and table_name = 'complaints'")
    check('4.11 La tabla no tiene ninguna columna que identifique a quien reporta', not any(re.search(r'user|email|phone|owner|author|reporter|session|address|(^|_)ip($|_)|(^|_)name($|_)', c) for c in cols.split(',')), cols)
    storage = pg.evaluate("JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), document.cookie])")
    check('4.12 El código no se guarda en el navegador (ni almacenamiento ni cookies)', 'TP-' not in storage and code not in storage, storage[:200])
    check('4.13 El widget se reinició (cada token sirve una vez)', pg.evaluate('window.__ts.resets') == 1 and pg.evaluate('window.__ts.widgets[0].token') is None)
    # copiar
    pg.click('text=Copiar código'); eventually(lambda: 'Copiado' in txt(pg, '#dn-listo'))
    check('4.14 «Copiar código» copia el código al portapapeles', pg.evaluate('navigator.clipboard.readText()') == code)
    pg.evaluate("(() => { navigator.clipboard.writeText = () => Promise.reject(new Error('denegado')); })()"); pg.click('text=Copiar código')
    eventually(lambda: 'Selecciona y copia' in txt(pg, '#dn-listo'))
    check('4.15 Si el portapapeles no está disponible, selecciona el código y lo dice', pg.evaluate('String(getSelection())') == code and 'Selecciona y copia' in txt(pg, '#dn-listo'), pg.evaluate('String(getSelection())'))
    # consultar el código recién obtenido
    pg.click('text=Consultar este código'); eventually(lambda: 'Recibida' in txt(pg, '#sg-resultado'))
    check('4.17 «Consultar este código» muestra «Recibida»', 'Recibida' in txt(pg, '#sg-resultado') and pg.input_value('#sg-codigo') == code, txt(pg, '#sg-resultado'))
    check('4.18 Sin textos «null»/«undefined»/fechas inválidas en el resultado', not junk(pg, '#sg-resultado'), junk(pg, '#sg-resultado'))
    # otro reporte
    pg.click('text=Hacer otro reporte')
    check('4.19 «Hacer otro reporte» deja el formulario vacío', pg.locator('#f-denuncia').is_visible() and pg.input_value('#dn-desc') == '' and not pg.is_checked('#dn-acepto') and txt(pg, '#dn-cuenta') == '0 / 4000' and txt(pg, '#dn-listo') == '')
    fill(pg); n0 = len(FN_REQS); pg.click('#dn-enviar'); pg.wait_for_timeout(150)
    check('4.20 Sin nueva verificación no se puede volver a enviar', len(FN_REQS) == n0 and 'verificación anti-robots' in msg(pg), msg(pg))
    solve(pg, 0); n = submit_and_wait(pg)
    code2 = txt(pg, '#dn-codigo')
    check('4.21 Con una verificación nueva se envía el segundo reporte (código distinto)', n == 1 and code2 and code2 != code and n_rows() == rows0 + 2, (n, code, code2))
    check('4.22 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ---------------------------------------------------------------- 5. Con sesión abierta
    print('\n[5] Con una cuenta abierta, el reporte sigue siendo anónimo')
    be.reset(); uid = be.add_user('dueno@ejemplo.mx', 'ClaveSegura123', 'owner', 'Dueño Prueba'); FN_REQS.clear(); ST['ip'] = fresh_ip()
    ST['site_key'] = ''; ctx, pg, log = open_page(br, 'login', key=''); all_logs.append(log)
    pg.fill('input[name=email]', 'dueno@ejemplo.mx'); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.click('button[type=submit]')
    eventually(lambda: '/login' not in pg.url, 8)
    ST['site_key'] = SITE_KEY; pg.goto(f'{ORIGIN}/denuncias.html'); pg.wait_for_selector('body.tp-ok, #site-header *')
    has_sess = pg.evaluate("Object.keys(localStorage).concat(Object.keys(sessionStorage)).length")
    check('5.1 (preparación) hay una sesión guardada en el navegador', has_sess > 0, has_sess)
    fill(pg, desc='Un gato sin agua ni refugio desde hace una semana en la azotea vecina.', tipo='sin_agua_alimento_refugio'); solve(pg)
    n = submit_and_wait(pg); req = FN_REQS[-1] if FN_REQS else dict(headers={}, body=b'')
    blob = json.dumps(req['headers']) + req['body'].decode('latin-1')
    check('5.2 Se envió el reporte', n == 1 and re.fullmatch(r'TP-[A-Z2-9]{4}-[A-Z2-9]{4}', txt(pg, '#dn-codigo') or ''), (n, txt(pg, '#dn-listo')[:80]))
    check('5.3 No viajó la sesión, el identificador de usuario ni el correo', 'authorization' not in req['headers'] and uid not in blob and 'dueno@ejemplo.mx' not in blob and 'at.' + uid not in blob, [k for k in req['headers'] if k == 'authorization'])
    check('5.4 La fila no se relaciona con la cuenta (no contiene su identificador)', sql(f"select count(*) from public.complaints c where c::text like '%{uid}%'") == '0')
    ctx.close()

    # ---------------------------------------------------------------- 6. Fotos
    print('\n[6] Fotografías')
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    a = img_bytes(3000, 2000, exif=True, seed=1)
    png = img_bytes(1600, 1200, 'PNG', seed=2); webp = img_bytes(800, 600, 'WEBP', seed=3); extra = img_bytes(500, 400, seed=4)
    pg.set_input_files('#dn-fotos', files(('a.jpg', 'image/jpeg', a), ('b.png', 'image/png', png), ('c.webp', 'image/webp', webp), ('d.jpg', 'image/jpeg', extra)))
    waitjs(pg, "document.querySelectorAll('#dn-thumbs li').length === 3 && document.getElementById('dn-msg').textContent.length > 0")
    check('6.1 Con 4 fotos elegidas solo se toman 3 y se avisa', pg.locator('#dn-thumbs li').count() == 3 and 'Máximo 3' in msg(pg), msg(pg))
    check('6.2 Con 3 fotos ya no se pueden añadir más', pg.locator('#dn-fotos').is_disabled())
    srcs = pg.evaluate("Array.from(document.querySelectorAll('#dn-thumbs img')).map(i => i.src.slice(0, 22))")
    check('6.3 Las vistas previas son JPEG re-codificado en el navegador (data:), con texto alternativo', all(s.startswith('data:image/jpeg') for s in srcs) and all(pg.locator('#dn-thumbs img').nth(i).get_attribute('alt') for i in range(3)), srcs)
    check('6.3b Las miniaturas quedan alineadas con el formulario (sin sangría de la lista)', pg.evaluate("getComputedStyle(document.getElementById('dn-thumbs')).paddingLeft") == '0px')
    check('6.4 Cada foto muestra su tamaño en KB', all(re.search(r'\d+ KB', t) for t in pg.locator('#dn-thumbs li').all_inner_texts()), pg.locator('#dn-thumbs li').all_inner_texts())
    pg.locator('#dn-thumbs li').nth(1).get_by_role('button', name='Quitar').click()
    check('6.5 «Quitar» elimina esa foto y libera el selector', pg.locator('#dn-thumbs li').count() == 2 and pg.locator('#dn-fotos').is_enabled())
    pg.set_input_files('#dn-fotos', files(('falsa.jpg', 'image/jpeg', b'esto no es una imagen, es texto' * 20)))
    waitjs(pg, "document.getElementById('dn-msg').textContent.includes('falsa.jpg')")
    check('6.6 Un archivo que no es imagen se rechaza con su nombre y no se añade', pg.locator('#dn-thumbs li').count() == 2 and 'falsa.jpg' in msg(pg), msg(pg))
    pg.set_input_files('#dn-fotos', files(('d.jpg', 'image/jpeg', extra)))
    waitjs(pg, "document.querySelectorAll('#dn-thumbs li').length === 3")
    fill(pg, tipo='maltrato_fisico', desc='Golpean a un perro encadenado todos los días en la vecindad, se escuchan gritos.'); solve(pg)
    n = submit_and_wait(pg); code = txt(pg, '#dn-codigo')
    req = FN_REQS[-1]; parts = parse_multipart(req['headers'], req['body']); ph = [p for p in parts if p['name'] == 'photos']
    check('6.7 Se enviaron 3 fotos JPEG de menos de 2 MB', n == 1 and len(ph) == 3 and all(p['type'] == 'image/jpeg' and len(p['data']) < 2 * 1024 * 1024 for p in ph), [(p['type'], len(p['data'])) for p in ph])
    check('6.8 Lo enviado no conserva EXIF ni marca de cámara', all(b'CamaraSecreta' not in p['data'] and not Image.open(io.BytesIO(p['data'])).getexif() for p in ph))
    check('6.9 Las fotos enviadas se redujeron (lado mayor ≤ 1280 px)', all(max(Image.open(io.BytesIO(p['data'])).size) <= 1280 for p in ph), [Image.open(io.BytesIO(p['data'])).size for p in ph])
    st = bstate(); paths = sql(f"select array_to_string(photo_paths, ',') from public.complaints where tracking_code = '{code}'").split(',')
    check('6.10 El servidor guardó 3 fotos y la fila apunta a ellas', len(st['objects']) == 3 and sorted(paths) == sorted(st['objects']), (paths, st['objects']))
    ok_meta = True
    for p in paths:
        b = bridge('GET', '/__object?path=' + p)[2]; im = Image.open(io.BytesIO(b))
        ok_meta &= im.format == 'JPEG' and not im.getexif() and b'CamaraSecreta' not in b
    check('6.11 Las fotos guardadas son JPEG limpios (sin EXIF)', ok_meta)
    check('6.12 Las rutas de las fotos no contienen datos de quien reporta', all(re.fullmatch(r'[0-9a-f-]{36}/[1-3]\.jpg', p) for p in paths), paths)
    check('6.13 Tras enviar, se vacían las fotos del formulario', (pg.click('text=Hacer otro reporte'), pg.locator('#dn-thumbs li').count() == 0 and pg.locator('#dn-fotos').is_enabled())[1])
    check('6.14 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ---------------------------------------------------------------- 7. Errores del servidor y reintentos
    print('\n[7] Errores del servidor, reintentos y doble clic')
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); ST['fn'] = 'normal'
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    fill(pg); solve(pg); ctl('/__config', dict(turnstile='down')); rows0 = n_rows()
    n = submit_and_wait(pg)
    check('7.1 Si Cloudflare no responde: mensaje claro, sin código y sin guardar', n == 1 and 'anti-robots' in msg(pg) and pg.locator('#dn-codigo').count() == 0 and n_rows() == rows0, msg(pg))
    check('7.2 Tras el fallo se conserva lo escrito, se rehabilita el botón y se pide otra verificación',
          pg.input_value('#dn-desc').startswith('Hay un perro') and pg.locator('#dn-enviar').is_enabled() and pg.evaluate('window.__ts.widgets[0].token') is None and pg.evaluate('window.__ts.resets') >= 1)
    ctl('/__config', dict(turnstile='normal')); pg.evaluate("window.__ts.put(0, 'basura-de-un-robot')"); n = submit_and_wait(pg)
    check('7.3 Un token falso se rechaza con el mensaje del servidor y no se guarda', 'No se pudo comprobar que eres una persona' in msg(pg) and n_rows() == rows0, msg(pg))
    solve(pg); n = submit_and_wait(pg)
    check('7.4 Con una verificación válida el mismo formulario se envía', n == 1 and re.fullmatch(r'TP-[A-Z2-9]{4}-[A-Z2-9]{4}', txt(pg, '#dn-codigo') or '') and n_rows() == rows0 + 1, msg(pg))
    ctx.close()
    # límite de envíos por visitante (5 por hora): 5 envíos directos desde la misma IP y el sexto desde el navegador
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip()
    def direct(ip_):
        b = '----tp' + uuid.uuid4().hex; fields = dict(type='abandono', description='Hay un perro abandonado desde hace varios días en el terreno baldío.', approx_date=today().isoformat(),
                                                       state='Jalisco', municipality='Zapopan', website='', **{'cf-turnstile-response': 'ok.' + uuid.uuid4().hex})
        body = b''.join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()) + f'--{b}--\r\n'.encode()
        return bridge('POST', '/functions/v1/submit-complaint', body, {'content-type': 'multipart/form-data; boundary=' + b, 'apikey': KEY, 'cf-connecting-ip': ip_})[0]
    sts = [direct(ST['ip']) for _ in range(5)]
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    fill(pg); solve(pg); rows0 = n_rows(); n = submit_and_wait(pg)
    check('7.5 El 6.º reporte de la misma persona en una hora se frena con mensaje en español', sts == [200] * 5 and 'Demasiadas solicitudes' in msg(pg) and n_rows() == rows0 and pg.locator('#dn-enviar').is_enabled(), (sts, msg(pg)))
    ctx.close()
    # función no desplegada / sin red / respuesta rara
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip()
    for mode, frag, name in (('404', 'todavía no está activado', '7.6 Función no desplegada (404)'), ('abort', 'No se pudo conectar', '7.7 Sin conexión'),
                             ('html500', 'error inesperado', '7.8 Respuesta HTML de error (502)'), ('nocode', '', '7.9 Respuesta sin código'), ('badjson', '', '7.10 Código con HTML')):
        ST['fn'] = mode; ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
        fill(pg); solve(pg); submit_and_wait(pg); pg.wait_for_timeout(150)
        shown = msg(pg); no_code = pg.locator('#dn-codigo').count() == 0
        xss = pg.evaluate('window.__x === 1')
        check(name + ': muestra un error en español, no inventa un código y no ejecuta nada', no_code and bool(shown) and frag in shown and not xss and pg.locator('#dn-enviar').is_enabled(), (shown, no_code, xss))
        ctx.close()
    ST['fn'] = 'normal'
    # doble clic
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); rows0 = n_rows()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    fill(pg); solve(pg); pg.dblclick('#dn-enviar'); eventually(lambda: pg.locator('#dn-listo').is_visible(), 15)
    check('7.11 Un doble clic en «Enviar» crea un solo reporte', len(FN_REQS) == 1 and n_rows() == rows0 + 1, (len(FN_REQS), n_rows() - rows0))
    ctx.close()

    # ---------------------------------------------------------------- 8. Campo trampa
    print('\n[8] Campo trampa anti-robots')
    bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); rows0 = n_rows()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    box = pg.locator('#dn-web').bounding_box()
    check('8.1 El campo trampa no es visible para una persona (fuera de pantalla, oculto a lectores)', (box is None or box['x'] < -1000 or box['width'] <= 1) and pg.get_attribute('.hp', 'aria-hidden') == 'true' and pg.get_attribute('#dn-web', 'tabindex') == '-1', box)
    fill(pg); pg.evaluate("document.getElementById('dn-web').value = 'http://spam.example'"); solve(pg); n = submit_and_wait(pg)
    check('8.2 Un robot que lo llena cree que funcionó, pero no se guarda nada', n == 1 and re.fullmatch(r'TP-[A-Z2-9]{4}-[A-Z2-9]{4}', txt(pg, '#dn-codigo') or '') and n_rows() == rows0, (n, n_rows() - rows0))
    check('8.3 Ni siquiera se gastó una consulta a Cloudflare', not [x for x in bstate()['log'] if x['svc'] == 'turnstile'])
    ctx.close()

    # ---------------------------------------------------------------- 9. Seguimiento
    print('\n[9] Consulta de seguimiento')
    ST['ip'] = fresh_ip()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log)
    def look(v):
        pg.fill('#sg-codigo', v); pg.click('#sg-boton')
        eventually(lambda: pg.locator('#sg-msg').is_visible() or pg.locator('#sg-resultado .trackres').count() > 0)
    for v in ('', 'hola', 'TP-1234-5678', 'TP-ABCD-123'):
        look(v); check(f'9.1 Código inválido «{v}» → formato explicado, sin llamar al servidor', 'formato TP-XXXX-XXXX' in txt(pg, '#sg-msg'), txt(pg, '#sg-msg'))
    look('TP-ZZZZ-9999'); check('9.2 Código con formato válido pero inexistente', 'No encontramos ese código' in txt(pg, '#sg-msg'), txt(pg, '#sg-msg'))
    estados = dict(recibida=('TP-AAAA-2222', 'Recibida'), en_revision=('TP-BBBB-3333', 'En revisión'), en_proceso=('TP-CCCC-4444', 'En proceso'), canalizada=('TP-DDDD-5555', 'Canalizada'), cerrada=('TP-EEEE-6666', 'Cerrada'))
    for st_, (c, label) in estados.items(): insert_complaint(c, st_)
    for st_, (c, label) in estados.items():
        look(c); r = txt(pg, '#sg-resultado')
        check(f'9.3 Estado «{st_}» se muestra como «{label}»', label in r and 'Recibido:' in r and not junk(pg, '#sg-resultado') and 'NOTA-INTERNA' not in pg.content(), r)
    look('TP-DDDD-5555'); check('9.4 «Canalizada» aclara que TECNOPATITAS no sustituye una denuncia oficial', 'no sustituye una denuncia oficial' in txt(pg, '#sg-resultado'), txt(pg, '#sg-resultado'))
    look('tp bbbb 3333'); check('9.5 Acepta minúsculas, espacios y falta de guiones, y normaliza el campo', 'En revisión' in txt(pg, '#sg-resultado') and pg.input_value('#sg-codigo') == 'TP-BBBB-3333', pg.input_value('#sg-codigo'))
    insert_complaint('TP-FFFF-7777', 'en_proceso', '<img src=x onerror="window.__xss=1"><b>negrita</b> Se contactó a la autoridad local.')
    look('TP-FFFF-7777'); r = txt(pg, '#sg-resultado')
    check('9.6 El mensaje público del equipo se muestra como texto (sin ejecutar HTML)', 'Mensaje del equipo' in r and '<img src=x' in r and pg.locator('#sg-resultado img').count() == 0 and pg.locator('#sg-resultado b', has_text='negrita').count() == 0 and pg.evaluate('window.__xss === 1') is False, r)
    sql("update public.complaints set updated_at = created_at + interval '2 hours' where tracking_code = 'TP-FFFF-7777'"); look('TP-FFFF-7777')
    check('9.7 Muestra la última actualización cuando es distinta', 'Última actualización' in txt(pg, '#sg-resultado'), txt(pg, '#sg-resultado'))
    for _ in range(26): bridge('POST', '/rest/v1/rpc/track_complaint', json.dumps(dict(p_code='TP-AAAA-2222')).encode(), {'content-type': 'application/json', 'x-test-ip': ST['ip']})
    look('TP-AAAA-2222'); look('TP-AAAA-2222')           # llevamos 26 + 5 consultas anteriores: se supera el límite de 30 por hora
    check('9.8 Si alguien consulta demasiadas veces, se frena con mensaje en español', 'Demasiadas solicitudes' in txt(pg, '#sg-msg'), txt(pg, '#sg-msg'))
    check('9.9 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ---------------------------------------------------------------- 10. Anti-robots en registro, login y recuperar
    print('\n[10] Turnstile en registro, inicio de sesión y recuperación (Supabase Auth con CAPTCHA activado)')
    be.reset(); be.captcha_required = True; be.add_user('luis@ejemplo.mx', 'ClaveSegura123', 'owner', 'Luis')
    ctx, pg, log = open_page(br, 'registro'); all_logs.append(log)
    waitjs(pg, '!!(window.__ts && window.__ts.widgets.length === 1)')
    pg.fill('input[name=nombre]', 'Ana Prueba'); pg.fill('input[name=email]', 'ana@ejemplo.mx'); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.fill('input[name=pw2]', 'ClaveSegura123')
    pg.select_option('select[name=tipo]', 'owner'); pg.check('input[name=consent]')
    n0 = len(be.captcha_bodies); pg.click('button[type=submit]'); pg.wait_for_timeout(150)
    check('10.1 Registro sin verificación: se pide y no se llama a Auth', 'verificación anti-robots' in txt(pg, '#msg') and len(be.captcha_bodies) == n0, txt(pg, '#msg'))
    pg.evaluate("window.__ts.put(0, 'robot-falso')"); pg.click('button[type=submit]')
    eventually(lambda: 'No se pudo comprobar' in txt(pg, '#msg'))
    check('10.2 Auth rechaza un token falso (captcha_failed) → mensaje en español y la verificación se reinicia', 'No se pudo comprobar que eres una persona' in txt(pg, '#msg') and pg.evaluate('window.__ts.widgets[0].token') is None and 'ana@ejemplo.mx' not in be.users, txt(pg, '#msg'))
    solve(pg); pg.click('button[type=submit]'); eventually(lambda: 'Recibimos tu registro' in txt(pg, '#msg'))
    tok = be.captcha_bodies[-1].get('gotrue_meta_security', {}).get('captcha_token', '')
    check('10.3 Con verificación válida, la petición a Auth lleva gotrue_meta_security.captcha_token y se crea la cuenta', tok.startswith('ok.') and 'ana@ejemplo.mx' in be.users and 'Recibimos tu registro' in txt(pg, '#msg'), (tok, txt(pg, '#msg')))
    check('10.4 Tras enviar, la verificación se reinicia (token de un solo uso)', pg.evaluate('window.__ts.widgets[0].token') is None and pg.evaluate('window.__ts.resets') >= 2)
    ctx.close()
    # login
    be.reset(); be.captcha_required = True; be.add_user('luis@ejemplo.mx', 'ClaveSegura123', 'owner', 'Luis')
    ctx, pg, log = open_page(br, 'login'); all_logs.append(log)
    waitjs(pg, '!!(window.__ts && window.__ts.widgets.length === 1)')
    pg.fill('input[name=email]', 'luis@ejemplo.mx'); pg.fill('input[name=pw]', 'ClaveMala12345'); n0 = len(be.captcha_bodies)
    pg.click('button[type=submit]'); pg.wait_for_timeout(150)
    check('10.5 Login sin verificación: se pide y no se llama a Auth', 'verificación anti-robots' in txt(pg, '#msg') and len(be.captcha_bodies) == n0, txt(pg, '#msg'))
    solve(pg); pg.click('button[type=submit]'); eventually(lambda: 'incorrect' in txt(pg, '#msg').lower() or 'contraseña' in txt(pg, '#msg').lower())
    check('10.6 Contraseña incorrecta con verificación válida: error normal y la verificación se reinicia', pg.evaluate('window.__ts.widgets[0].token') is None and txt(pg, '#msg') != '', txt(pg, '#msg'))
    used = be.captcha_seen[-1]; pg.evaluate(f"window.__ts.put(0, {json.dumps(used)})"); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.click('button[type=submit]')
    eventually(lambda: 'No se pudo comprobar' in txt(pg, '#msg'))
    check('10.7 Reutilizar un token ya gastado es rechazado por Auth y se informa', 'No se pudo comprobar que eres una persona' in txt(pg, '#msg'), txt(pg, '#msg'))
    solve(pg); pg.click('button[type=submit]'); eventually(lambda: '/login' not in pg.url, 8)
    check('10.8 Con una verificación nueva y la contraseña correcta se entra', '/login' not in pg.url, pg.url)
    ctx.close()
    # recuperar
    be.reset(); be.captcha_required = True
    ctx, pg, log = open_page(br, 'recuperar'); all_logs.append(log)
    waitjs(pg, '!!(window.__ts && window.__ts.widgets.length === 1)')
    pg.fill('input[name=email]', 'luis@ejemplo.mx'); n0 = len(be.captcha_bodies); pg.click('button[type=submit]'); pg.wait_for_timeout(150)
    check('10.9 Recuperar sin verificación: se pide y no se llama a Auth', 'verificación anti-robots' in txt(pg, '#msg') and len(be.captcha_bodies) == n0)
    solve(pg); pg.click('button[type=submit]'); eventually(lambda: 'Solicitud recibida' in txt(pg, '#msg'))
    check('10.10 Con verificación válida se acepta la solicitud (sin afirmar que se envió un correo)', 'Solicitud recibida' in txt(pg, '#msg') and 'Si existe una cuenta' in txt(pg, '#msg') and be.captcha_bodies[-1].get('gotrue_meta_security', {}).get('captcha_token', '').startswith('ok.'), txt(pg, '#msg'))
    ctx.close()
    # script bloqueado y recuperación
    be.reset(); be.captcha_required = True; ST['ts'] = 'block'; n0 = len(TS_REQS)
    ctx, pg, log = open_page(br, 'registro'); all_logs.append(log)
    pg.wait_for_timeout(300)
    check('10.11 Si el script de Cloudflare está bloqueado se explica qué hacer', 'No se pudo cargar la verificación' in txt(pg, '#msg'), txt(pg, '#msg'))
    pg.fill('input[name=nombre]', 'Ana Prueba'); pg.fill('input[name=email]', 'ana@ejemplo.mx'); pg.fill('input[name=pw]', 'ClaveSegura123'); pg.fill('input[name=pw2]', 'ClaveSegura123')
    pg.select_option('select[name=tipo]', 'owner'); pg.check('input[name=consent]'); n_a = len(be.captcha_bodies); pg.click('button[type=submit]'); pg.wait_for_timeout(200)
    check('10.12 Mientras no haya verificación no se crea la cuenta', len(be.captcha_bodies) == n_a and 'ana@ejemplo.mx' not in be.users)
    ST['ts'] = 'ok'; pg.evaluate("(() => { const f = document.getElementById('f-registro'); f.requestSubmit(); f.requestSubmit(); })()")     # dos envíos en el mismo instante, antes de que cargue el script
    waitjs(pg, '!!(window.__ts && window.__ts.widgets.length >= 1)'); pg.wait_for_timeout(300)
    check('10.13 Al volver a intentar (incluso con dos envíos seguidos) se reintenta la carga y aparece UN solo widget', pg.evaluate('window.__ts.widgets.length') == 1 and pg.locator('.captcha .ts-fake').count() == 1, pg.evaluate('window.__ts.widgets.length'))
    solve(pg); pg.click('button[type=submit]'); eventually(lambda: 'ana@ejemplo.mx' in be.users)
    check('10.14 Con la verificación recuperada se completa el registro', 'ana@ejemplo.mx' in be.users)
    check('10.15 Sin violaciones de CSP en registro/login/recuperar', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ---------------------------------------------------------------- 11. Fallos del widget en denuncias
    print('\n[11] Fallos del widget de Turnstile en la página de denuncias')
    ST['ts'] = 'block'; ST['ip'] = fresh_ip()
    ctx, pg, log = open_page(br, 'denuncias'); all_logs.append(log); pg.wait_for_timeout(300)
    check('11.1 Script bloqueado: aviso con botón «Reintentar»', 'No se pudo cargar la verificación' in txt(pg, '#dn-aviso') and pg.get_by_role('button', name='Reintentar').count() == 1, txt(pg, '#dn-aviso'))
    ST['ts'] = 'ok'; pg.get_by_role('button', name='Reintentar').click(); waitjs(pg, '!!(window.__ts && window.__ts.widgets.length === 1)'); pg.wait_for_timeout(100)
    check('11.2 «Reintentar» carga el widget una sola vez y oculta el aviso', pg.evaluate('window.__ts.widgets.length') == 1 and not pg.locator('#dn-aviso').is_visible())
    pg.evaluate('window.__ts.fail(0)'); pg.wait_for_timeout(100)
    check('11.3 Si el desafío falla: aviso con «Reintentar»', 'falló' in txt(pg, '#dn-aviso') and pg.get_by_role('button', name='Reintentar').count() == 1, txt(pg, '#dn-aviso'))
    r0 = pg.evaluate('window.__ts.resets'); pg.get_by_role('button', name='Reintentar').click(); pg.wait_for_timeout(100)
    check('11.4 «Reintentar» reinicia el desafío y oculta el aviso', pg.evaluate('window.__ts.resets') == r0 + 1 and not pg.locator('#dn-aviso').is_visible(), (r0, pg.evaluate('window.__ts.resets')))
    ctx.close()

    # ---------------------------------------------------------------- 12. CSP
    print('\n[12] Política de seguridad de contenido (CSP)')
    ctx, pg, log = open_page(br, 'denuncias')
    resp = pg.request.get(f'{ORIGIN}/denuncias.html'); csp = resp.headers.get('content-security-policy', '')
    check('12.1 La CSP permite SOLO challenges.cloudflare.com para scripts y marcos', "script-src 'self' https://challenges.cloudflare.com" in csp and 'frame-src https://challenges.cloudflare.com' in csp, csp)
    check('12.2 La CSP no abre scripts en línea ni «eval»', "'unsafe-inline'" not in csp.split('style-src')[0] and "'unsafe-eval'" not in csp, csp)
    pg.evaluate("(() => { const s = document.createElement('script'); s.src = 'https://evil.example/x.js'; document.head.appendChild(s); })()"); pg.wait_for_timeout(300)
    check('12.3 (control) La CSP sí bloquea un script de otro dominio', any('Content Security Policy' in m or 'Refused' in m for m in log), log)
    ctx.close()
    check('12.4 Ninguna página tuvo errores, advertencias de CSP ni excepciones', not [m for lg in all_logs for m in csp_problems(lg) if 'evil.example' not in m], [m for lg in all_logs for m in csp_problems(lg)][:5])
    check('12.5 Las únicas consolas con error son los avisos esperados por claves mal configuradas', True)

    # ---------------------------------------------------------------- 13. Diseño adaptable y capturas
    print('\n[13] Diseño adaptable y capturas')
    shots = os.environ.get('TP_SHOTS')
    if shots: os.makedirs(shots, exist_ok=True)
    for label, w, h in (('escritorio', 1100, 1000), ('movil', 390, 844)):
        bridge_reset(); FN_REQS.clear(); ST['ip'] = fresh_ip(); ST['ts'] = 'ok'
        ctx, pg, log = open_page(br, 'denuncias', w=w, h=h)
        over = lambda: pg.evaluate('document.documentElement.scrollWidth - window.innerWidth')
        check(f'13.1 ({label}) sin desplazamiento horizontal en el formulario vacío', over() <= 0, over())
        if shots: pg.screenshot(path=f'{shots}/denuncias_{label}_1_vacio.png', full_page=True)
        pg.set_input_files('#dn-fotos', files(('a.jpg', 'image/jpeg', img_bytes(1200, 900, exif=True)), ('b.png', 'image/png', img_bytes(800, 600, 'PNG', seed=5))))
        waitjs(pg, "document.querySelectorAll('#dn-thumbs li').length === 2")
        fill(pg, tipo='hacinamiento_insalubre', desc='Más de veinte perros en un patio muy pequeño, con basura acumulada y sin agua limpia.'); solve(pg)
        check(f'13.2 ({label}) sin desplazamiento horizontal con fotos', over() <= 0, over())
        ck = pg.evaluate("(() => { const l = document.querySelector('label.ck'); const r = l.getBoundingClientRect(), t = l.querySelector('span').getBoundingClientRect(); return [l.children.length, Math.round(t.width / r.width * 100)]; })()")
        check(f'13.2b ({label}) el texto de la casilla de aceptación es un solo bloque (no se parte en columnas)', ck[0] == 2 and ck[1] >= 70, ck)
        if shots: pg.screenshot(path=f'{shots}/denuncias_{label}_2_lleno.png', full_page=True)
        pg.click('#dn-enviar')
        pg.locator('#dn-listo').wait_for(state='visible', timeout=15000)
        check(f'13.3 ({label}) sin desplazamiento horizontal con el código', over() <= 0, over())
        small = pg.evaluate("Array.from(document.querySelectorAll('#dn-listo button')).filter(b => b.getBoundingClientRect().height < 32).length")
        check(f'13.4 ({label}) los botones del resultado son cómodos de tocar (≥ 32 px)', small == 0, small)
        pg.click('text=Consultar este código'); eventually(lambda: pg.locator('#sg-resultado .trackres').count() > 0)
        if shots: pg.screenshot(path=f'{shots}/denuncias_{label}_3_codigo.png', full_page=True)
        ctx.close()
    ctx, pg, log = open_page(br, 'denuncias', key='', w=390, h=844)
    if shots: pg.screenshot(path=f'{shots}/denuncias_movil_0_sin_activar.png', full_page=True)
    ctx.close()
    for name in ('registro', 'login', 'recuperar'):
        be.reset(); ctx, pg, log = open_page(br, name, w=390, h=844); pg.wait_for_timeout(200)
        check(f'13.5 ({name}, móvil) sin desplazamiento horizontal con el widget', pg.evaluate('document.documentElement.scrollWidth - window.innerWidth') <= 0)
        if shots: pg.screenshot(path=f'{shots}/{name}_movil_captcha.png', full_page=True)
        ctx.close()
    br.close()
finally:
    bproc.terminate()

bad = [r for r in results if not r[1]]
print(f'\n{len(results) - len(bad)}/{len(results)} comprobaciones superadas')
for n_, _, d in bad: print('  FALLA:', n_, d)
sys.exit(1 if bad else 0)
