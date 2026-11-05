"""
Pruebas de interfaz de la Etapa 7 (atención al cliente) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP) y la base de datos:
            tablas, RLS, permisos por columna, disparadores (límites, remitente fijado por el servidor), start_conversation
            (PostgreSQL local con database/00_instalar_todo.sql; ver mock_etapa7.py).
  SIMULADO  PostgREST (traduce solo las consultas del chat a SQL), Supabase Auth (mock_supabase.py) y el servidor de Supabase Realtime
            (un WebSocket falso que habla el protocolo documentado: unirse, latidos, cambios, cierre y rechazo).
            Los eventos que el «servidor» empuja salen de filas REALES de la base (como hace Realtime con el WAL).

Uso:  python3 pruebas-web/probar_chat.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), playwright + chromium.
Variables: TP_PORT (sitio, 8771), TP_CHAT_DB (base, tp_chat), TP_SITE (carpeta del sitio; las «pruebas de las pruebas» usan una copia saboteada).
"""
import http.server, json, os, re, socketserver, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa7 import Backend7
from playwright._impl import _network
def _close_page_tolerante(self, event):             # Playwright falla si el navegador cierra el WebSocket sin código (ws.close() sin argumentos)
    if self._on_page_close: self._on_page_close(event.get('code'), event.get('reason'))
    else: self._channel.send_may_fail('closeServer', None, event)
_network.WebSocketRoute._channel_close_page = _close_page_tolerante

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8771)); DB = os.environ.get('TP_CHAT_DB', 'tp_chat')
ORIGIN = f'http://localhost:{PORT}'
SUPA_HOST = 'mtkbxnhsjqqdbrjeaslo.supabase.co'
CONFIG_JS = open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", CONFIG_JS).group(1)
ONLY = os.environ.get('TP_ONLY', '')          # p. ej. TP_ONLY=9 ejecuta solo el grupo 9

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

# ------------------------------------------------------------------ base de datos
def prepare_db():
    env = dict(os.environ, PGOPTIONS='-c client_min_messages=warning')
    subprocess.run(['psql', '-X', '-q', '-d', 'postgres', '-c', f'drop database if exists {DB}', '-c', f'create database {DB}'], capture_output=True, text=True)
    for f in ('database/pruebas/shim_supabase.sql', 'database/00_instalar_todo.sql'):
        r = subprocess.run(['psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-d', DB, '-o', '/dev/null'], input=open(os.path.join(REAL_ROOT, f), encoding='utf-8').read(),
                           capture_output=True, text=True, env=env)
        if r.returncode: raise SystemExit('No se pudo preparar la base: ' + r.stderr[:400])

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
    def handle_error(self, request, client_address): pass
socketserver.TCPServer.allow_reuse_address = True
srv = Srv(('127.0.0.1', PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

# ------------------------------------------------------------------ servidor de Realtime simulado (protocolo Phoenix v2)
class Conn:
    def __init__(s, route):
        s.route = route; s.url = route.url; s.join = None; s.join_ref = None; s.topic = None; s.hb = 0; s.tokens = []; s.frames = []
        s.closed = False; s.left = False; s.t = time.time()
class RT:
    def __init__(s): s.reset()
    def reset(s):
        s.conns = []; s.mode = 'ok'; s.hb_reply = True; s.attempts = []; s.pending = []
    def handler(s, ws):
        c = Conn(ws); s.conns.append(c); s.attempts.append(time.time())
        ws.on_message(lambda m: s.on_msg(c, m))                     # siempre se registran los dos manejadores: sin ellos Playwright rebota el cierre en bucle
        ws.on_close(lambda code=None, reason=None: setattr(c, 'closed', True))
        if s.mode == 'refuse': c.closed = True; s.pending.append(ws)           # se cierra poco después, fuera del manejador (cerrar dentro del manejador cuelga Playwright)
    def send(s, c, frame):
        if not c.closed: c.route.send(json.dumps(frame))
    def on_msg(s, c, m):
        try: f = json.loads(m)
        except Exception: c.frames.append(('basura', m)); return
        c.frames.append(tuple(f))
        jr, ref, topic, ev, payload = f
        if ev == 'phx_join':
            c.join = payload; c.join_ref = jr; c.topic = topic
            if s.mode == 'silent': return
            if s.mode == 'joinerr': s.send(c, [jr, ref, topic, 'phx_reply', {'status': 'error', 'response': {'reason': 'Unauthorized'}}]); return
            pcs = (payload.get('config') or {}).get('postgres_changes') or []
            ids = [{'id': 1000 + i, **b} for i, b in enumerate(pcs)]
            if s.mode == 'badcount': ids = ids[:-1]
            s.send(c, [jr, ref, topic, 'phx_reply', {'status': 'ok', 'response': {'postgres_changes': ids}}])
            if s.mode == 'syserr': s.send(c, [None, None, topic, 'system', {'message': 'Error subscribing to realtime', 'status': 'error', 'extension': 'postgres_changes', 'channel': 'tp-chat'}])
            else: s.send(c, [None, None, topic, 'system', {'message': 'Subscribed to PostgreSQL', 'status': 'ok', 'extension': 'postgres_changes', 'channel': 'tp-chat'}])
        elif ev == 'heartbeat':
            c.hb += 1
            if s.hb_reply: s.send(c, [None, ref, 'phoenix', 'phx_reply', {'status': 'ok', 'response': {}}])
        elif ev == 'access_token':
            c.tokens.append((payload or {}).get('access_token'))
            s.send(c, [jr, ref, topic, 'phx_reply', {'status': 'ok', 'response': {}}])
        elif ev == 'phx_leave':
            c.left = True
    def pump(s):
        while s.pending: s.pending.pop().close(code=1011, reason='rechazado')
    def live(s):
        for c in reversed(s.conns):
            if c.join is not None and not c.closed: return c
        return None
    def open_count(s): return sum(1 for c in s.conns if not c.closed)
    def push(s, table, typ, record, old=None):
        c = s.live()
        if not c: return False
        s.send(c, [None, None, c.topic, 'postgres_changes', {'ids': [1000], 'data': {'schema': 'public', 'table': table, 'commit_timestamp': '2026-11-04T18:00:00Z',
                    'type': typ, 'record': record, 'old_record': old or {}, 'columns': [], 'errors': None}}])
        return True
    def drop(s):
        c = s.live()
        if c: c.closed = True; c.route.close(code=1006, reason='caída simulada')
rt = RT()

# ------------------------------------------------------------------ estado de la simulación
be = Backend7(KEY, DB)
CUR = [None]
def route_supa(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    status, data = be.handle(req.method, req.url, req.headers, req.post_data)
    if status == 'abort': route.abort(); return
    route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body='' if data is None else json.dumps(data))
WS_PATCH = """(() => { const N = window.WebSocket, all = []; window.__wsTimes = []; window.__wsOverlap = 0;
  window.WebSocket = class extends N { constructor(...a) { const live = all.filter(w => w.readyState < 2).length; window.__wsOverlap = Math.max(window.__wsOverlap, live);
    super(...a); all.push(this); window.__wsTimes.push(Date.now()); } }; })();"""
def new_ctx(br, w=1100, h=900, clock=False):
    ctx = br.new_context(viewport={'width': w, 'height': h})
    if clock: ctx.clock.install()
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), route_supa)
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    ctx.route_web_socket(re.compile(r'wss://mtkbxnhsjqqdbrjeaslo\.supabase\.co/realtime/v1/websocket.*'), rt.handler)
    ctx.add_init_script(WS_PATCH)            # DESPUÉS de route_web_socket: Playwright reemplaza window.WebSocket con su propio simulador y el parche debe envolverlo
    return ctx
def session_script(email, ttl=None):
    u = be.users[email]; s = be._session(u)
    if ttl is not None: s['expires_at'] = int(time.time()) + ttl
    sess = dict(access_token=s['access_token'], refresh_token=s['refresh_token'], expires_at=s['expires_at'],
                user=dict(id=u['id'], email=email, email_confirmed_at='2026-11-04T00:00:00Z'))
    return "try{if(!localStorage.getItem('tp-auth-v1'))localStorage.setItem('tp-auth-v1',%s)}catch(e){}" % json.dumps(json.dumps(sess)), sess
def open_chat(br, email, w=1100, h=900, clock=False, query='', ttl=None, wait=True, ctx=None):
    ctx = ctx or new_ctx(br, w, h, clock)
    if email:
        scr, sess = session_script(email, ttl); ctx.add_init_script(scr)
    log = []; pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/chat.html{query}')
    if wait:
        pg.wait_for_selector('body.tp-ok', timeout=8000)
        waitjs(pg, "document.getElementById('ch-loading').hidden === true")
    return ctx, pg, log

# ------------------------------------------------------------------ utilidades
def tick(pg, ms):
    try: pg.wait_for_timeout(ms)
    except Exception: time.sleep(ms / 1000)
    rt.pump()
def waitjs(pg, expr, timeout=8.0):
    t0 = time.time(); last = None
    while time.time() - t0 < timeout:
        try:
            if pg.evaluate(expr): return True
        except Exception as e: last = e
        tick(pg, 40)
    raise TimeoutError(f'Condición no cumplida en {timeout}s: {expr[:140]} {last or ""}')
def eventually(cond, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond(): return True
        except Exception: pass
        tick(CUR[0], 50)
    return False
def settle(pg, ms=250): tick(pg, ms)
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def txt(pg, sel): return pg.inner_text(sel) if pg.locator(sel).count() else ''
JUNK_RE = re.compile(r'\bnull\b|undefined|\[object|\bNaN\b|Invalid Date')
def junk(pg, sel): return JUNK_RE.findall(txt(pg, sel))
def items(pg):
    return pg.evaluate("""Array.from(document.querySelectorAll('#ch-list .chat-item')).map(b => ({id: b.dataset.id, subject: b.querySelector('b').textContent,
        badges: Array.from(b.querySelectorAll('.badge')).map(x => x.textContent), current: b.getAttribute('aria-current')}))""")
def bubbles(pg):
    return pg.evaluate("""Array.from(document.querySelectorAll('#th-log .bubble')).map(b => [b.querySelector('.who').textContent, b.querySelector('.txt').textContent])""")
def msg(pg): return txt(pg, '#ch-msg') if pg.locator('#ch-msg').is_visible() else ''
def live_text(pg): return txt(pg, '#ch-live').strip()
def rest_calls(table=None, method=None, since=0):
    return [r for r in be.rest_log[since:] if (table is None or r['path'].endswith('/' + table)) and (method is None or r['method'] == method)]
def new_conv(uid, subject='Duda de prueba', first='Hola, tengo una duda', status='abierta', ago_min=0):
    cid = be.sql(f"insert into public.conversations (user_id, subject, status) values ('{uid}', '{subject.replace(chr(39), chr(39)*2)}', '{status}') returning id")
    be.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{cid}', '{uid}', '{first.replace(chr(39), chr(39)*2)}')")
    if ago_min:
        be.sql(f"update public.messages set created_at = now() - interval '{ago_min} minutes' where conversation_id = '{cid}'; update public.conversations set last_message_at = now() - interval '{ago_min} minutes' where id = '{cid}'")
    return cid
def staff_say(cid, text, push=True):
    row = be.staff_reply(cid, ADMIN, text)
    if push:
        rt.push('messages', 'INSERT', row)
        rt.push('conversations', 'UPDATE', be.row('conversations', cid))
    return row
def open_thread(pg, cid):
    pg.click(f'#ch-list .chat-item[data-id="{cid}"]'); waitjs(pg, "!document.getElementById('ch-thread').hidden")
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length > 0")

def run():
    global ADMIN
    prepare_db()
    ANA = be.add_user('ana@ejemplo.mx', 'ClaveSegura123', name='Ana')
    BRUNO = be.add_user('bruno@ejemplo.mx', 'ClaveSegura123', name='Bruno')
    ADMIN = be.add_user('dani@ejemplo.mx', 'ClaveSegura123', name='Dani', admin=True)
    CRIS = be.add_user('cris@ejemplo.mx', 'ClaveSegura123', name='Cris', account_type='business')
    SUSI = be.add_user('susi@ejemplo.mx', 'ClaveSegura123', name='Susi', suspended=True)
    return dict(ANA=ANA, BRUNO=BRUNO, CRIS=CRIS, SUSI=SUSI)

def group(n): return not ONLY or ONLY == str(n)

def reset_state():
    be.reset_db(); be.rest_log.clear(); be.calls.clear(); be.fail_rest = None; rt.reset()

# ================================================================== PRUEBAS
U = run()
ANA, BRUNO, CRIS, SUSI = U['ANA'], U['BRUNO'], U['CRIS'], U['SUSI']
all_logs = []

def g1(br):
    print('\n[1] Estructura y seguridad de la página')
    html = open(os.path.join(ROOT, 'chat.html'), encoding='utf-8').read()
    check('1.1 chat.html ya no está marcado como «no conectado» (sin data-stage)', 'data-stage' not in html and 'se conecta en la Etapa 7' not in html)
    check('1.2 Los scripts cargan en orden: cliente, interfaz, guarda, tiempo real, página',
          re.search(r'tp-client\.js.*tp-ui\.js.*layout\.js.*guard\.js.*tp-realtime\.js.*pages/chat\.js', html) is not None)
    src = {f: open(os.path.join(ROOT, f), encoding='utf-8').read() for f in ('js/pages/chat.js', 'js/tp-realtime.js')}
    bad = [(f, m) for f, t in src.items() for m in re.findall(r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function', t)]
    check('1.3 Ni la página ni el cliente de tiempo real usan innerHTML, eval ni document.write', not bad, bad)
    csp = HEADERS.get('Content-Security-Policy', '')
    check('1.4 La CSP permite el WebSocket solo hacia tu proyecto de Supabase',
          f'wss://{SUPA_HOST}' in csp and 'wss://*' not in csp and re.search(r"connect-src 'self' https://%s wss://%s;" % (re.escape(SUPA_HOST), re.escape(SUPA_HOST)), csp), csp)
    reset_state()
    ctx, pg, log = open_chat(br, None, wait=False); all_logs.append(log)
    pg.wait_for_url(re.compile(r'login\.html\?next=chat\.html'), timeout=8000); settle(pg, 300)
    check('1.5 Sin sesión: manda a iniciar sesión y NO consulta chats ni abre la conexión en vivo',
          not rest_calls('conversations') and not rest_calls('messages') and not rt.attempts, (len(rest_calls()), len(rt.attempts)))
    ctx.close()
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('1.6 Con sesión la página carga sin errores de consola ni de CSP', not csp_problems(log), csp_problems(log))
    check('1.7 Se abre exactamente una conexión en vivo con la clave pública y el protocolo 2.0.0',
          eventually(lambda: rt.live() is not None) and len(rt.attempts) == 1 and f'apikey={KEY}' in rt.conns[0].url and 'vsn=2.0.0' in rt.conns[0].url and rt.conns[0].url.startswith(f'wss://{SUPA_HOST}/realtime/v1/websocket?'), [c.url for c in rt.conns])
    check('1.8 La clave secreta no aparece en la página ni en los archivos del chat',
          not re.search(r'sb_secret_[A-Za-z0-9_]{8,}', pg.content()) and all(not re.search(r'sb_secret_[A-Za-z0-9_]{8,}', t) and 'service_role' not in t for t in src.values()))
    ctx.close()

def g2(br):
    print('\n[2] Lista vacía y conversación nueva')
    reset_state()
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('2.1 Sin conversaciones se explica cómo empezar', 'Todavía no tienes conversaciones' in txt(pg, '#ch-empty') and pg.locator('#ch-empty').is_visible(), txt(pg, '#ch-empty'))
    check('2.2 «Nueva» está disponible, la lista no muestra restos y no hay textos «null/undefined»', pg.locator('#ch-new').is_enabled() and not items(pg) and not junk(pg, 'main'), junk(pg, 'main'))
    check('2.3 Se advierte que nunca se piden contraseñas ni datos de tarjeta', 'Nunca te pediremos contraseñas ni datos de tarjeta' in txt(pg, '#ch-intro'))
    check('2.4 No se promete respuesta inmediata ni se presenta como asistente automático', 'No es un asistente automático' in txt(pg, '#ch-intro') and 'puede tardar' in txt(pg, '#ch-intro'))
    q = rest_calls('conversations', 'GET')
    check('2.5 La lista se pide filtrada por la propia persona', q and f'user_id=eq.{ANA}' in q[0]['query'] and 'limit=100' in q[0]['query'], q[:1])
    check('2.6 Se muestra el marcador «Selecciona o crea una conversación»', pg.locator('#ch-placeholder').is_visible())
    pg.click('#ch-new')
    check('2.7 «Nueva» abre el formulario y el foco va al asunto', pg.locator('#f-new').is_visible() and pg.evaluate('document.activeElement.id') == 'n-asunto')
    n0 = len(be.rest_log)
    pg.fill('#n-asunto', 'ab'); pg.fill('#n-texto', 'Hola'); pg.click('#n-enviar'); settle(pg, 150)
    check('2.8 Asunto de 2 caracteres: aviso en español y NO se llama al servidor', 'entre 3 y 120' in msg(pg) and len(be.rest_log) == n0, msg(pg))
    pg.fill('#n-asunto', 'Asunto válido'); pg.fill('#n-texto', '   \n  '); pg.click('#n-enviar'); settle(pg, 150)
    check('2.9 Mensaje vacío (solo espacios): aviso y NO se llama al servidor', 'Escribe tu mensaje' in msg(pg) and len(be.rest_log) == n0, msg(pg))
    pg.fill('#n-texto', 'Hola 🐶🐶')
    check('2.10 El contador cuenta caracteres reales (un emoji cuenta 1)', txt(pg, '#n-cuenta') == '7 / 2,000', txt(pg, '#n-cuenta'))
    pg.fill('#n-texto', 'x' * 2001); settle(pg, 80)
    check('2.11 Pasarse de 2000 se marca en el contador y se rechaza sin llamar al servidor', pg.evaluate("document.getElementById('n-cuenta').classList.contains('over')") and (pg.click('#n-enviar') or True) and 'más de 2000' in msg(pg) and len(be.rest_log) == n0, msg(pg))
    pg.fill('#n-asunto', '  Duda sobre mi plan  '); pg.fill('#n-texto', '  Hola, quisiera saber cómo cambio mi plan.  ')
    pg.click('#n-enviar'); waitjs(pg, "!document.getElementById('ch-thread').hidden")
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 1")
    c = rest_calls('rpc/start_conversation', 'POST') if False else [r for r in be.rest_log if r['path'].endswith('/rpc/start_conversation')]
    check('2.12 Se llamó UNA vez a start_conversation con asunto y mensaje recortados', len(c) == 1 and c[0]['body'] == {'p_subject': 'Duda sobre mi plan', 'p_body': 'Hola, quisiera saber cómo cambio mi plan.'}, c)
    check('2.13 Se abre la conversación nueva: título, estado y mensaje propio', txt(pg, '#th-asunto') == 'Duda sobre mi plan' and txt(pg, '#th-estado') == 'Esperando respuesta' and bubbles(pg) == [['Tú', 'Hola, quisiera saber cómo cambio mi plan.']], (txt(pg, '#th-asunto'), bubbles(pg)))
    it = items(pg)
    check('2.14 Aparece en la lista, seleccionada y «Esperando respuesta»', len(it) == 1 and it[0]['current'] == 'true' and 'Esperando respuesta' in it[0]['badges'] and 'Nuevo' not in it[0]['badges'], it)
    check('2.15 La dirección guarda la conversación abierta (?c=)', f"c={it[0]['id']}" in pg.url, pg.url)
    db = be.sql("select count(*) || '|' || (select count(*) from public.messages) || '|' || (select string_agg(user_id::text || sender_role, ',') from public.conversations c join public.messages m on m.conversation_id = c.id) from public.conversations")
    check('2.16 En la base: 1 conversación, 1 mensaje, de Ana y como «user»', db == f'1|1|{ANA}user', db)
    check('2.17 El foco pasó al título de la conversación (accesibilidad)', pg.evaluate('document.activeElement.id') == 'th-asunto')
    check('2.18 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    # doble envío: dos envíos seguidos crean una sola conversación
    pg.click('#ch-new'); pg.fill('#n-asunto', 'Segunda consulta'); pg.fill('#n-texto', 'Mensaje de la segunda consulta')
    pg.evaluate("(() => { const f = document.getElementById('f-new'); f.requestSubmit(); f.requestSubmit(); })()")
    waitjs(pg, "document.querySelectorAll('#ch-list .chat-item').length === 2"); settle(pg, 300)
    n = int(be.sql("select count(*) from public.conversations where subject = 'Segunda consulta'"))
    check('2.19 Un doble envío crea una sola conversación', n == 1, n)
    # límite de conversaciones abiertas (disparador real)
    for i in range(8): new_conv(ANA, f'Relleno {i}')
    pg.click('#ch-new'); pg.fill('#n-asunto', 'Una más'); pg.fill('#n-texto', 'No debería entrar')
    pg.click('#n-enviar'); eventually(lambda: msg(pg), 4)
    check('2.20 Con 10 conversaciones abiertas, el aviso del servidor sale en español y el texto escrito se conserva',
          'demasiadas conversaciones abiertas' in msg(pg) and pg.input_value('#n-texto') == 'No debería entrar' and pg.locator('#f-new').is_visible(), msg(pg))
    check('2.21 El botón vuelve a estar disponible tras el error', pg.locator('#n-enviar').is_enabled() and txt(pg, '#n-enviar') == 'Enviar')
    ctx.close()

def g3(br):
    print('\n[3] Texto con código: se muestra como texto, nunca se ejecuta')
    reset_state()
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    XSS_S = '<img src=x onerror="window.__x=1">'; XSS_M = '<script>window.__x=2</script>\nlínea 2 & <b>negrita</b> "comillas"'
    pg.click('#ch-new'); pg.fill('#n-asunto', XSS_S); pg.fill('#n-texto', XSS_M); pg.click('#n-enviar')
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 1")
    check('3.1 El asunto con HTML se ve como texto (en título y en lista)', txt(pg, '#th-asunto') == XSS_S and items(pg)[0]['subject'] == XSS_S, txt(pg, '#th-asunto'))
    check('3.2 El mensaje con HTML se ve literal, con sus saltos de línea', bubbles(pg)[0][1] == XSS_M and 'línea 2' in pg.inner_text('#th-log .txt') and '\n' in pg.inner_text('#th-log .txt'), bubbles(pg))
    check('3.3 No se creó ningún elemento del texto del usuario (img, script, b)', pg.evaluate("document.querySelectorAll('#th-log img, #th-log script, #th-log b, #ch-list img, #th-asunto img').length") == 0)
    check('3.4 Nada se ejecutó', pg.evaluate('window.__x') is None)
    check('3.5 Los saltos de línea se conservan visualmente (white-space: pre-wrap)', pg.evaluate("getComputedStyle(document.querySelector('#th-log .txt')).whiteSpace") == 'pre-wrap')
    cid = items(pg)[0]['id']
    staff_say(cid, '<iframe src="https://example.com"></iframe> <a href="javascript:window.__x=3">clic</a>')
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 2")
    check('3.6 Una respuesta del equipo con HTML también se muestra como texto', pg.evaluate("document.querySelectorAll('#th-log iframe, #th-log a').length") == 0 and '<iframe' in bubbles(pg)[1][1], bubbles(pg))
    long = 'palabra' * 200
    pg.fill('#s-texto', long); pg.click('#s-enviar'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 3")
    w = pg.evaluate("(() => { const b = document.querySelector('#th-log .bubble:last-child'); return [b.scrollWidth, b.clientWidth, document.documentElement.scrollWidth, document.documentElement.clientWidth]; })()")
    check('3.7 Un texto larguísimo sin espacios no desborda la burbuja ni la página', w[0] <= w[1] + 1 and w[2] <= w[3], w)
    check('3.8 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g4(br):
    print('\n[4] Enviar mensajes y límites del servidor')
    reset_state()
    cid = new_conv(ANA, 'Consulta de envío', 'Primer mensaje')
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_thread(pg, cid)
    check('4.1 Al abrir: foco en el título, mensaje visible, hora en formato de México', pg.evaluate('document.activeElement.id') == 'th-asunto' and bubbles(pg) == [['Tú', 'Primer mensaje']] and re.search(r'\d{4}', txt(pg, '#th-log time')) and not junk(pg, '#th-log'), txt(pg, '#th-log time'))
    n0 = len(be.rest_log)
    pg.fill('#s-texto', '   '); pg.click('#s-enviar'); settle(pg, 150)
    check('4.2 Mensaje vacío: aviso y NO se llama al servidor', 'Escribe un mensaje' in msg(pg) and len(be.rest_log) == n0, msg(pg))
    pg.fill('#s-texto', 'Segundo mensaje'); pg.click('#s-enviar')
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 2")
    p = [r for r in be.rest_log[n0:] if r['method'] == 'POST']
    check('4.3 Se envía UNA petición y solo con conversation_id y body (el servidor fija remitente y rol)', len(p) == 1 and p[0]['body'] == {'conversation_id': cid, 'body': 'Segundo mensaje'}, p)
    check('4.4 Se limpia el cuadro, el contador vuelve a 0 y el foco regresa a escribir', pg.input_value('#s-texto') == '' and txt(pg, '#s-cuenta') == '0 / 2,000' and pg.evaluate('document.activeElement.id') == 's-texto')
    check('4.4b La página no tiene formularios «no conectados»: el aviso de etapa pendiente no aparece al enviar', pg.evaluate("document.querySelectorAll('form[data-stage]').length") == 0 and not pg.evaluate("document.getElementById('toast').classList.contains('on')"), pg.evaluate("document.getElementById('toast').textContent"))
    check('4.5 El mensaje queda guardado como del usuario (rol fijado por el servidor)', be.sql(f"select string_agg(sender_role, ',' order by created_at) from public.messages where conversation_id = '{cid}'") == 'user,user')
    pg.fill('#s-texto', 'Con atajo'); pg.press('#s-texto', 'Control+Enter'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 3")
    check('4.6 Ctrl+Enter envía el mensaje', bubbles(pg)[-1] == ['Tú', 'Con atajo'], bubbles(pg))
    pg.fill('#s-texto', 'Enter solo no envía'); pg.press('#s-texto', 'Enter'); settle(pg, 200)
    check('4.7 Enter solo agrega un salto de línea (no envía)', len(bubbles(pg)) == 3 and '\n' in pg.input_value('#s-texto'))
    pg.fill('#s-texto', 'Doble clic'); pg.evaluate("(() => { const f = document.getElementById('f-send'); f.requestSubmit(); f.requestSubmit(); })()")
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 4"); settle(pg, 300)
    check('4.8 Un doble envío guarda un solo mensaje', int(be.sql(f"select count(*) from public.messages where body = 'Doble clic'")) == 1)
    pg.fill('#s-texto', 'y' * 2000); pg.click('#s-enviar'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 5")
    check('4.9 Un mensaje de exactamente 2000 caracteres sí se envía', len(bubbles(pg)[-1][1]) == 2000)
    n1 = len(be.rest_log); pg.fill('#s-texto', 'z' * 2001); pg.click('#s-enviar'); settle(pg, 150)
    check('4.10 Con 2001 caracteres se rechaza en el navegador y no se llama al servidor', 'más de 2000' in msg(pg) and len(be.rest_log) == n1 and pg.input_value('#s-texto') == 'z' * 2001)
    # límite de 20 mensajes en 10 minutos (real)
    be.sql(f"insert into public.messages (conversation_id, sender_id, body) select '{cid}', '{ANA}', 'relleno ' || g from generate_series(1, 20) g")
    pg.fill('#s-texto', 'Mensaje de más'); pg.click('#s-enviar'); eventually(lambda: 'demasiados mensajes seguidos' in msg(pg), 4)
    check('4.11 Pasados 20 mensajes en 10 minutos: aviso del servidor en español, no se guarda y el texto se conserva',
          'demasiados mensajes seguidos' in msg(pg) and pg.input_value('#s-texto') == 'Mensaje de más' and int(be.sql("select count(*) from public.messages where body = 'Mensaje de más'")) == 0, msg(pg))
    check('4.12 El botón «Enviar» vuelve a estar activo tras el error', pg.locator('#s-enviar').is_enabled() and txt(pg, '#s-enviar') == 'Enviar')
    # límite diario (100 en 24 h) con mensajes más antiguos que 10 min
    be.sql(f"update public.messages set created_at = now() - interval '3 hours' - (random() * interval '10 hours') where conversation_id = '{cid}' and sender_id = '{ANA}' and body like 'relleno%'")
    be.sql(f"insert into public.messages (conversation_id, sender_id, body, created_at) select '{cid}', '{ANA}', 'antiguo ' || g, now() - interval '2 hours' - g * interval '1 minute' from generate_series(1, 90) g")
    pg.click('#s-enviar'); eventually(lambda: '100 mensajes en 24 horas' in msg(pg), 4)
    check('4.13 Con 100 mensajes en 24 horas: aviso del servidor en español', '100 mensajes en 24 horas' in msg(pg), msg(pg))
    check('4.14 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()


def g5(br):
    print('\n[5] Mensajes del equipo en vivo (Realtime)')
    reset_state()
    c1 = new_conv(ANA, 'Primera consulta', 'Hola uno', ago_min=30)
    c2 = new_conv(ANA, 'Segunda consulta', 'Hola dos', ago_min=20)
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    eventually(lambda: rt.live() is not None and 'En vivo' in live_text(pg) or True, 3); waitjs(pg, "true")
    cn = None
    eventually(lambda: rt.live() is not None, 5); cn = rt.live()
    tok = pg.evaluate("JSON.parse(localStorage.getItem('tp-auth-v1')).access_token")
    j = cn.join or {}
    check('5.1 Se une al canal con el tema, los dos enlaces de tablas y el token de la sesión',
          cn.topic == 'realtime:tp-chat' and (j.get('config') or {}).get('postgres_changes') == [{'event': 'INSERT', 'schema': 'public', 'table': 'messages'}, {'event': '*', 'schema': 'public', 'table': 'conversations'}]
          and j.get('access_token') == tok and (j.get('config') or {}).get('private') is False, (cn.topic, j))
    check('5.2 La lista llega ordenada: lo más reciente primero, con su estado', [i['subject'] for i in items(pg)] == ['Segunda consulta', 'Primera consulta'] and all('Esperando respuesta' in i['badges'] for i in items(pg)), items(pg))
    open_thread(pg, c1)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    check('5.3 Se muestra que el chat está «En vivo»', 'En vivo' in live_text(pg), live_text(pg))
    g0 = len(rest_calls('messages', 'GET')); l0 = len(rest_calls('conversations', 'GET'))
    staff_say(c1, 'Hola, con gusto te ayudamos')
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 2")
    check('5.4 La respuesta del equipo aparece sola, con «Equipo TECNOPATITAS»', bubbles(pg)[1] == ['Equipo TECNOPATITAS', 'Hola, con gusto te ayudamos'], bubbles(pg))
    settle(pg, 300)
    check('5.5 Llegó por el canal en vivo: no hizo falta consultar de nuevo al servidor', len(rest_calls('messages', 'GET')) == g0 and len(rest_calls('conversations', 'GET')) == l0, (g0, len(rest_calls('messages', 'GET'))))
    it = {i['subject']: i for i in items(pg)}
    check('5.6 La conversación pasa a «Respondida», sin «Nuevo» (ya la estás viendo) y sube al primer lugar',
          items(pg)[0]['subject'] == 'Primera consulta' and 'Respondida' in it['Primera consulta']['badges'] and 'Nuevo' not in it['Primera consulta']['badges'] and txt(pg, '#th-estado') == 'Respondida', items(pg))
    staff_say(c2, 'Respuesta para la segunda')
    waitjs(pg, "document.querySelectorAll('#ch-list .chat-item')[0].textContent.includes('Segunda consulta')")
    it = {i['subject']: i for i in items(pg)}
    check('5.7 Una respuesta en otra conversación la marca «Nuevo», sube al primer lugar y no cambia el hilo abierto',
          'Nuevo' in it['Segunda consulta']['badges'] and 'Respondida' in it['Segunda consulta']['badges'] and len(bubbles(pg)) == 2 and txt(pg, '#th-asunto') == 'Primera consulta', (items(pg), bubbles(pg)))
    open_thread(pg, c2)
    it = {i['subject']: i for i in items(pg)}
    check('5.8 Al abrirla, «Nuevo» desaparece y se ve la respuesta', 'Nuevo' not in it['Segunda consulta']['badges'] and bubbles(pg)[-1] == ['Equipo TECNOPATITAS', 'Respuesta para la segunda'], (items(pg), bubbles(pg)))
    pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('ch-loading').hidden === true")
    check('5.9 Tras recargar, lo ya leído no vuelve a salir como «Nuevo» (se recuerda solo en tu navegador)', all('Nuevo' not in i['badges'] for i in items(pg)) and f'c={c2}' in pg.url and txt(pg, '#th-asunto') == 'Segunda consulta', (items(pg), pg.url))
    eventually(lambda: rt.live() is not None and rt.live().join is not None, 5)
    staff_say(c1, 'Otra respuesta, ahora tras recargar')
    waitjs(pg, "document.querySelector('#ch-list .chat-item[data-id=\"%s\"]').textContent.includes('Nuevo')" % c1)
    check('5.10 Una respuesta posterior sí vuelve a marcar «Nuevo»', True)
    # La conversación que estás viendo nunca debe mostrar «Nuevo», ni un instante, cuando la respuesta llega por consulta (sin aviso en vivo)
    pg.evaluate("""(id => { window.__flash = 0; new MutationObserver(recs => { for (const r of recs) for (const n of r.addedNodes) { if (n.nodeType !== 1) continue;
      const it = n.closest('.chat-item[data-id="' + id + '"]') || n.querySelector('.chat-item[data-id="' + id + '"]'); if (it && it.textContent.includes('Nuevo')) window.__flash++; } })
      .observe(document.getElementById('ch-list'), {childList: true, subtree: true}); })(%r)""" % c2)
    nb = len(bubbles(pg))
    staff_say(c2, 'Llegó sin aviso en vivo', push=False)
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === %d" % (nb + 1)); settle(pg, 300)
    it = {i['subject']: i for i in items(pg)}
    check('5.10b Si la respuesta llega por consulta y no por el canal en vivo, la conversación abierta tampoco muestra «Nuevo» (ni un instante)',
          pg.evaluate('window.__flash') == 0 and 'Nuevo' not in it['Segunda consulta']['badges'] and bubbles(pg)[-1][1] == 'Llegó sin aviso en vivo', (pg.evaluate('window.__flash'), items(pg)))
    # repetidos y basura
    row = staff_say(c2, 'Mensaje que llega dos veces', push=False)
    rt.push('messages', 'INSERT', row); rt.push('messages', 'INSERT', row); settle(pg, 300)
    check('5.11 El mismo evento recibido dos veces no duplica el mensaje', [b[1] for b in bubbles(pg)].count('Mensaje que llega dos veces') == 1, bubbles(pg))
    n_b = len(bubbles(pg)); lst = items(pg); l0 = len(rest_calls('conversations', 'GET'))
    cn = rt.live()
    cn.route.send('esto no es JSON'); cn.route.send(json.dumps({'no': 'array'})); cn.route.send(json.dumps([1, 2]))
    cn.route.send(json.dumps([None, None, 'realtime:otro-canal', 'postgres_changes', {'data': {'table': 'messages', 'type': 'INSERT', 'record': {'id': 'cccccccc-0000-4000-8000-000000000009', 'conversation_id': c2, 'body': 'infiltrado por otro canal', 'sender_role': 'staff', 'created_at': '2026-11-04T10:00:00Z'}}}]))
    rt.push('messages', 'INSERT', {}); rt.push('messages', 'INSERT', {'conversation_id': 'no-es-uuid', 'id': 'x'})
    rt.push('messages', 'INSERT', {'conversation_id': c2, 'id': 'no-uuid', 'body': 'x', 'sender_role': 'staff', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('messages', 'INSERT', {'conversation_id': c2, 'id': 'aaaaaaaa-0000-4000-8000-000000000001', 'body': 12345, 'sender_role': 'staff', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('messages', 'DELETE', {'id': 'aaaaaaaa-0000-4000-8000-000000000002'})
    rt.push('conversations', 'UPDATE', {'id': c2, 'user_id': BRUNO, 'status': 'cerrada'})
    rt.push('conversations', 'UPDATE', {'id': c2, 'user_id': ANA, 'status': 'hackeada', 'last_sender': 'otro'})
    rt.push('tabla_rara', 'UPDATE', {'id': c2}); settle(pg, 400)
    check('5.12 Eventos rotos, ajenos o inventados se ignoran sin errores (nada cambia en pantalla)', len(bubbles(pg)) == n_b and items(pg) == lst and not csp_problems(log), (bubbles(pg)[-2:], csp_problems(log)))
    check('5.13 Un evento de la conversación de OTRA persona no abre ni muestra nada',
          not rt.push('messages', 'INSERT', {'conversation_id': new_conv(BRUNO, 'Secreto de Bruno'), 'id': 'bbbbbbbb-0000-4000-8000-000000000001', 'body': 'datos de Bruno', 'sender_role': 'staff', 'created_at': '2026-11-04T10:00:00Z'}) is False and 'Bruno' not in pg.inner_text('main'), pg.inner_text('main')[:200])
    settle(pg, 2200)
    check('5.14 …y la lista sigue mostrando solo las conversaciones de Ana', all(i['subject'] != 'Secreto de Bruno' for i in items(pg)), items(pg))
    # cierre y reapertura
    be.sql(f"update public.conversations set status = 'cerrada' where id = '{c2}'")
    rt.push('conversations', 'UPDATE', be.row('conversations', c2))
    waitjs(pg, "document.getElementById('f-send').hidden === true")
    check('5.15 Si el equipo cierra la conversación, el cuadro para escribir se oculta y se explica', 'está cerrada' in txt(pg, '#th-aviso') and 'Cerrada' in [b for i in items(pg) if i['id'] == c2 for b in i['badges']], (txt(pg, '#th-aviso'), items(pg)))
    staff_say(c2, 'Reabrimos tu caso')
    waitjs(pg, "document.getElementById('f-send').hidden === false")
    check('5.16 Si el equipo responde, la conversación se reabre y se puede escribir otra vez', pg.locator('#f-send').is_visible() and pg.locator('#th-aviso').is_hidden() and txt(pg, '#th-estado') == 'Respondida', txt(pg, '#th-estado'))
    pg.fill('#s-texto', 'Gracias, ahora te escribo yo'); pg.click('#s-enviar'); waitjs(pg, "document.querySelector('#th-log .bubble:last-child .txt').textContent === 'Gracias, ahora te escribo yo'")
    it = {i['id']: i for i in items(pg)}
    check('5.17 Al escribir tú después de una respuesta, la conversación vuelve a «Esperando respuesta» al instante', 'Esperando respuesta' in it[c2]['badges'] and txt(pg, '#th-estado') == 'Esperando respuesta', (it[c2], txt(pg, '#th-estado')))
    check('5.18 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g6(br):
    print('\n[6] Cerrar una conversación')
    reset_state()
    cid = new_conv(ANA, 'Para cerrar', 'Necesito ayuda')
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_thread(pg, cid)
    n0 = len(be.rest_log)
    pg.click('#th-cerrar'); settle(pg, 150)
    check('6.1 El primer clic pide confirmar (sin ventanas emergentes) y no cierra nada', txt(pg, '#th-cerrar') == 'Confirmar cierre' and '¿Cerrar esta conversación?' in msg(pg) and not [r for r in be.rest_log[n0:] if r['method'] == 'PATCH'])
    pg.click('#th-cerrar'); waitjs(pg, "document.getElementById('f-send').hidden === true")
    pt = [r for r in be.rest_log[n0:] if r['method'] == 'PATCH']
    check('6.2 El segundo clic cierra: una sola petición, solo con el estado', len(pt) == 1 and pt[0]['body'] == {'status': 'cerrada'} and pt[0]['query'] == f'id=eq.{cid}', pt)
    check('6.3 Queda «Cerrada» en la lista y el hilo; sin cuadro de escritura ni botón de cerrar; con explicación',
          txt(pg, '#th-estado') == 'Cerrada' and 'Cerrada' in items(pg)[0]['badges'] and pg.locator('#th-cerrar').is_hidden() and 'abre una nueva' in txt(pg, '#th-aviso') and 'Conversación cerrada' in msg(pg), (txt(pg, '#th-estado'), msg(pg)))
    check('6.4 En la base quedó cerrada', be.sql(f"select status from public.conversations where id = '{cid}'") == 'cerrada')
    pg.evaluate("(() => { document.getElementById('s-texto').value = 'escribo igual'; document.getElementById('f-send').requestSubmit(); })()")
    eventually(lambda: 'está cerrada' in msg(pg), 4)
    check('6.5 Aunque se fuerce el envío por código, el servidor lo rechaza en español y no guarda nada', 'La conversación está cerrada' in msg(pg) and int(be.sql("select count(*) from public.messages where body = 'escribo igual'")) == 0, msg(pg))
    r = pg.evaluate("""(async () => { try { await TP.rest('/conversations', {method: 'PATCH', query: 'id=eq.%s', body: {status: 'abierta'}, prefer: 'return=representation'}); return 'se reabrió'; } catch (e) { return TP.errorMessage(e); } })()""" % cid)
    check('6.6 La persona no puede reabrir una conversación cerrada (lo impide el servidor)', 'cerrada' in r and be.sql(f"select status from public.conversations where id = '{cid}'") == 'cerrada', r)
    # el primer clic de confirmación no cierra si se cambia de conversación
    c2 = new_conv(ANA, 'Otra para no cerrar', 'Hola')
    pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('ch-loading').hidden === true")
    open_thread(pg, c2); pg.click('#th-cerrar'); pg.click(f'#ch-list .chat-item[data-id="{cid}"]'); settle(pg, 200)
    open_thread(pg, c2)
    check('6.7 Al cambiar de conversación se cancela la confirmación pendiente', txt(pg, '#th-cerrar') == 'Cerrar conversación', txt(pg, '#th-cerrar'))
    ctx.close()

def g7(br):
    print('\n[7] Cada persona ve solo lo suyo')
    reset_state()
    mine = new_conv(ANA, 'Mi consulta', 'Mensaje de Ana')
    bru = new_conv(BRUNO, 'Secreto de Bruno', 'datos privados de Bruno')
    dani = new_conv(ADMIN, 'Consulta de Dani', 'Mensaje de la admin')
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('7.1 La lista de Ana solo tiene sus conversaciones', [i['subject'] for i in items(pg)] == ['Mi consulta'] and 'Bruno' not in pg.inner_text('main'), items(pg))
    r = pg.evaluate("""(async () => { const c = await TP.rest('/conversations', {query: 'select=id,subject'}); const m = await TP.rest('/messages', {query: 'select=id,body'}); return [c.length, m.length, c.map(x => x.subject).join('|'), m.map(x => x.body).join('|')]; })()""")
    check('7.2 Aunque se pida TODO sin filtro, la base solo entrega lo de Ana (RLS)', r[0] == 1 and r[1] == 1 and 'Bruno' not in r[2] + r[3] and 'admin' not in r[3], r)
    r = pg.evaluate("""(async () => { try { const x = await TP.rest('/messages', {method: 'POST', body: {conversation_id: '%s', body: 'intruso'}, prefer: 'return=representation'}); return 'entró ' + JSON.stringify(x); } catch (e) { return TP.errorMessage(e); } })()""" % bru)
    check('7.3 Ana no puede escribir en la conversación de Bruno', 'permiso' in r and int(be.sql("select count(*) from public.messages where body = 'intruso'")) == 0, r)
    for col, val in (('sender_role', 'staff'), ('sender_id', BRUNO)):
        r = pg.evaluate("""(async () => { try { const x = await TP.rest('/messages', {method: 'POST', body: {conversation_id: '%s', body: 'falso', %s: '%s'}, prefer: 'return=representation'}); return 'entró'; } catch (e) { return TP.errorMessage(e); } })()""" % (mine, col, val))
        check(f'7.4 Ana no puede falsificar «{col}» al escribir', 'permiso' in r and int(be.sql("select count(*) from public.messages where body = 'falso'")) == 0, r)
    r = pg.evaluate("""(async () => { try { const x = await TP.rest('/conversations', {method: 'PATCH', query: 'id=eq.%s', body: {status: 'cerrada'}, prefer: 'return=representation'}); return x.length; } catch (e) { return TP.errorMessage(e); } })()""" % bru)
    check('7.5 Ana no puede cerrar la conversación de Bruno (0 filas afectadas)', r == 0 and be.sql(f"select status from public.conversations where id = '{bru}'") == 'abierta', r)
    ctx.close()
    n0 = len(be.rest_log)
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', query=f'?c={bru}'); all_logs.append(log)
    check('7.6 ?c= con la conversación de otra persona se ignora: no abre nada ni pide sus mensajes',
          pg.locator('#ch-placeholder').is_visible() and pg.locator('#ch-thread').is_hidden() and not [r for r in be.rest_log[n0:] if bru in r['query']], pg.url)
    ctx.close()
    for bad in ('?c=no-es-uuid', "?c='%3E%3Cscript%3Ewindow.__x=1%3C/script%3E", '?c=' + 'a' * 500):
        ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', query=bad); all_logs.append(log)
        check(f'7.7 ?c= inválido ({bad[:24]}…) se ignora sin errores', pg.locator('#ch-placeholder').is_visible() and pg.evaluate('window.__x') is None and not csp_problems(log), csp_problems(log))
        ctx.close()
    ctx, pg, log = open_chat(br, 'dani@ejemplo.mx'); all_logs.append(log)
    check('7.8 Una administradora ve en esta página SOLO sus propias conversaciones', [i['subject'] for i in items(pg)] == ['Consulta de Dani'], items(pg))
    r = pg.evaluate("""(async () => (await TP.rest('/conversations', {query: 'select=id'})).length)()""")
    check('7.9 (contraste) la base sí le permite a la administradora ver todas: el filtro lo pone la página', r == 3, r)
    rt_ok = eventually(lambda: rt.live() is not None, 5)
    l0 = len(rest_calls('conversations', 'GET'))
    rt.push('messages', 'INSERT', {'conversation_id': bru, 'id': 'bbbbbbbb-0000-4000-8000-000000000002', 'body': 'x', 'sender_role': 'user', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('conversations', 'UPDATE', {'id': bru, 'user_id': BRUNO, 'status': 'cerrada'}); settle(pg, 2400)
    check('7.10 Los eventos de otras personas (que la administradora sí recibe) no cambian la lista ni provocan consultas', rt_ok and len(rest_calls('conversations', 'GET')) == l0 and len(items(pg)) == 1, (l0, len(rest_calls('conversations', 'GET'))))
    ctx.close()

def g8(br):
    print('\n[8] Conversaciones largas: paginación')
    reset_state()
    pcid = new_conv(ANA, 'Conversación larga', 'm001', ago_min=300)
    be.sql(f"""insert into public.messages (conversation_id, sender_id, body, created_at)
               select '{pcid}', case when g % 2 = 0 then '{ANA}'::uuid else '{ADMIN}'::uuid end, 'm' || lpad(g::text, 3, '0'), now() - ((121 - g) * interval '1 minute')
               from generate_series(2, 120) g""")
    be.sql(f"update public.conversations set last_message_at = now() where id = '{pcid}'")
    qcid = new_conv(ANA, 'Mismo instante', 'e000', ago_min=400)
    be.sql(f"insert into public.messages (conversation_id, sender_id, body) select '{qcid}', '{ADMIN}', 'e' || lpad(g::text, 3, '0') from generate_series(1, 130) g")
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_thread(pg, pcid)
    bodies = lambda: [b[1] for b in bubbles(pg)]
    check('8.1 Se cargan los 50 mensajes más recientes, en orden', len(bodies()) == 50 and bodies()[0] == 'm071' and bodies()[-1] == 'm120', (len(bodies()), bodies()[:1], bodies()[-1:]))
    check('8.2 Aparece «Cargar mensajes anteriores» y la vista queda al final', pg.locator('#th-mas-wrap').is_visible() and pg.evaluate("(() => { const l = document.getElementById('th-log'); return l.scrollHeight - l.scrollTop - l.clientHeight < 4; })()"))
    top0 = pg.evaluate("(() => { const l = document.getElementById('th-log'); const b = l.querySelector('.bubble'); return b.getBoundingClientRect().top - l.getBoundingClientRect().top; })()")
    pg.evaluate("document.getElementById('th-log').scrollTop = 0")
    first_before = pg.evaluate("(() => { const l = document.getElementById('th-log'); const b = l.querySelector('.bubble'); return b.getBoundingClientRect().top - l.getBoundingClientRect().top; })()")
    pg.click('#th-mas'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 100")
    pos = pg.evaluate("(() => { const l = document.getElementById('th-log'); const bs = Array.from(l.querySelectorAll('.bubble')); const b = bs.find(x => x.querySelector('.txt').textContent === 'm071'); return b.getBoundingClientRect().top - l.getBoundingClientRect().top; })()")
    check('8.3 Al cargar anteriores, lo que leías no se mueve de lugar', abs(pos - first_before) < 3, (pos, first_before))
    check('8.4 Se agregan los 50 anteriores y el botón sigue disponible', bodies()[0] == 'm021' and pg.locator('#th-mas-wrap').is_visible(), bodies()[:1])
    pg.click('#th-mas'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 120"); settle(pg, 100)
    check('8.5 Al llegar al inicio el botón desaparece y están los 120 mensajes exactamente una vez y en orden',
          pg.locator('#th-mas-wrap').is_hidden() and bodies() == [f'm{g:03d}' for g in range(1, 121)], (len(bodies()), bodies()[:3]))
    check('8.6 Los mensajes alternan correctamente entre «Tú» y el equipo', all(b[0] == ('Tú' if int(b[1][1:]) % 2 == 0 or b[1] == 'm001' else 'Equipo TECNOPATITAS') for b in bubbles(pg)))
    open_thread(pg, qcid)
    check('8.7 Con 130 mensajes del mismo instante: se cargan 50', len(bodies()) == 50, len(bodies()))
    pg.click('#th-mas'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 100")
    pg.click('#th-mas'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 131"); settle(pg, 100)
    got = bodies()
    check('8.8 …y con la misma hora ninguno se pierde ni se repite (131 distintos)', len(got) == 131 and len(set(got)) == 131 and set(got) == {f'e{g:03d}' for g in range(0, 131)}, (len(got), len(set(got))))
    # mensajes nuevos con la vista arriba o abajo
    open_thread(pg, pcid)
    pg.evaluate("document.getElementById('th-log').scrollTop = 0"); settle(pg, 80)
    staff_say(pcid, 'nuevo-1'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 51")
    st = pg.evaluate("document.getElementById('th-log').scrollTop")
    check('8.9 Si estás leyendo mensajes viejos, uno nuevo no te mueve de lugar', st < 5, st)
    pg.evaluate("(() => { const l = document.getElementById('th-log'); l.scrollTop = l.scrollHeight; })()"); settle(pg, 80)
    staff_say(pcid, 'nuevo-2'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 52"); settle(pg, 80)
    check('8.10 Si estás al final, el mensaje nuevo se muestra de inmediato', pg.evaluate("(() => { const l = document.getElementById('th-log'); return l.scrollHeight - l.scrollTop - l.clientHeight < 4; })()"))
    check('8.11 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()


def advance(pg, ms, step=None):
    """Avanza el reloj de la página (tiempo virtual) y deja que se procesen los mensajes pendientes."""
    if step:
        done = 0
        while done < ms:
            d = min(step, ms - done); pg.clock.run_for(d); done += d; tick(pg, 35)
            if os.environ.get('TP_DEBUG') and done % 1000 == 0: print('   … avanzado', done, 'ms; conexiones', len(rt.conns), flush=True)
    else:
        pg.clock.run_for(ms); tick(pg, 120)
def with_thread(br, email='ana@ejemplo.mx', ttl=None, query='', subject='Hilo con reloj'):
    cid = new_conv(ANA if email.startswith('ana') else BRUNO, subject, 'Hola desde el reloj')
    ctx, pg, log = open_chat(br, email, clock=True, ttl=ttl, query=query); all_logs.append(log)
    open_thread(pg, cid)
    eventually(lambda: rt.live() is not None, 5)
    return ctx, pg, log, cid
def live_ok(pg): return 'En vivo' in live_text(pg)
def times(pg): return pg.evaluate('window.__wsTimes')

def g9(br):
    print('\n[9] Conexión en vivo: latidos, reconexión, respaldo y sesión (reloj virtual)')
    # --- latidos
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    cn = rt.live(); check('9.1 Al conectar no se envía ningún latido todavía', cn.hb == 0)
    advance(pg, 25000); eventually(lambda: cn.hb >= 1, 3)
    hb = [f for f in cn.frames if f[3] == 'heartbeat']
    check('9.2 A los 25 s se manda un latido en el formato del protocolo', cn.hb == 1 and hb[0][0] is None and hb[0][2] == 'phoenix' and hb[0][4] == {}, hb)
    advance(pg, 25000); eventually(lambda: cn.hb >= 2, 3)
    check('9.3 Sigue mandando uno cada 25 s y la conexión sigue siendo la misma', cn.hb == 2 and len(rt.conns) == 1 and live_ok(pg), (cn.hb, len(rt.conns)))
    ctx.close()
    # --- latido sin respuesta: la conexión se da por muerta
    reset_state(); rt.hb_reply = False
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    c0 = rt.live()
    advance(pg, 25000); advance(pg, 25000)
    check('9.4 Si el servidor no contesta el latido, se detecta la conexión muerta y se avisa «Sin conexión en vivo»', eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 3) and c0.closed is True, live_text(pg))
    rt.hb_reply = True; advance(pg, 1500, 100)
    check('9.5 Se reconecta solo con una conexión nueva y vuelve a «En vivo»', eventually(lambda: len(rt.conns) == 2 and live_ok(pg), 4) and rt.open_count() == 1, (len(rt.conns), live_text(pg)))
    ctx.close()
    # --- caída del servidor: reconexión + respaldo por consultas + recuperar lo perdido
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    rt.drop()
    check('9.6 Si el servidor corta la conexión, la página lo avisa', eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 3), live_text(pg))
    be.staff_reply(cid, ADMIN, 'Se escribió mientras no había conexión')
    g0 = len(rest_calls('conversations', 'GET'))
    advance(pg, 1400, 100)
    check('9.7 Al reconectar recupera por consulta lo que se perdió (sin recargar la página)',
          eventually(lambda: live_ok(pg) and len(rt.conns) == 2, 4) and eventually(lambda: bubbles(pg)[-1:] == [['Equipo TECNOPATITAS', 'Se escribió mientras no había conexión']], 4), bubbles(pg)[-2:])
    check('9.8 La página manda de nuevo su token y pide unirse al mismo canal', rt.live().join is not None and rt.live().topic == 'realtime:tp-chat')
    g1_ = len(rest_calls('conversations', 'GET')); advance(pg, 46000, 5000)
    check('9.8b Cuando vuelve la conexión en vivo ya no consulta cada 15 s (solo latidos)', len(rest_calls('conversations', 'GET')) == g1_, len(rest_calls('conversations', 'GET')) - g1_)
    ctx.close()
    # --- retroceso exponencial
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    rt.mode = 'refuse'; rt.drop()
    advance(pg, 22000, 100)
    t = times(pg); gaps = [t[i + 1] - t[i] for i in range(1, len(t) - 1)]
    check('9.9 Con el servidor rechazando, las esperas crecen: ~2 s, ~4 s, ~8 s… (cada una con hasta 30 % de azar)',
          len(gaps) >= 3 and 1900 <= gaps[0] <= 2900 and 3900 <= gaps[1] <= 5500 and 7900 <= gaps[2] <= 10900, gaps)
    rt.mode = 'ok'
    advance(pg, 12000, 200)
    check('9.10 Cuando el servidor vuelve, se conecta y queda «En vivo»', eventually(lambda: live_ok(pg), 4) and rt.live() is not None, live_text(pg))
    check('9.11 En ningún momento hubo dos conexiones abiertas a la vez', pg.evaluate('window.__wsOverlap') == 0, pg.evaluate('window.__wsOverlap'))
    ctx.close()
    # --- el botón de «recuperar red» salta la espera
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    rt.mode = 'refuse'; rt.drop(); advance(pg, 6000, 200)
    n = len(rt.conns); rt.mode = 'ok'; pg.evaluate("window.dispatchEvent(new Event('online'))")
    check('9.12 Al volver la red («online») reconecta de inmediato, sin esperar el retroceso', eventually(lambda: live_ok(pg) and len(rt.conns) == n + 1, 3), (n, len(rt.conns), live_text(pg)))
    rt.drop(); eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 3); n = len(rt.conns)
    pg.evaluate("(() => { for (let i = 0; i < 3; i++) window.dispatchEvent(new Event('online')); document.dispatchEvent(new Event('visibilitychange')); })()")
    eventually(lambda: live_ok(pg), 3); advance(pg, 3000, 500)
    check('9.12b Varios avisos a la vez (online ×3 y visibilitychange) abren UNA sola conexión nueva', len(rt.conns) == n + 1 and rt.open_count() == 1 and pg.evaluate('window.__wsOverlap') == 0, (n, len(rt.conns), rt.open_count(), pg.evaluate('window.__wsOverlap')))
    ctx.close()
    # --- respaldo: sin conexión en vivo desde el principio
    reset_state(); rt.mode = 'refuse'
    ctx, pg, log, cid = with_thread(br)
    eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 4)
    check('9.13 Sin conexión en vivo desde el inicio la página funciona y lo avisa', 'Sin conexión en vivo' in live_text(pg) and bubbles(pg) == [['Tú', 'Hola desde el reloj']], live_text(pg))
    be.staff_reply(cid, ADMIN, 'Respuesta que llega solo por consulta periódica')
    g0 = len(rest_calls('conversations', 'GET')); advance(pg, 60000, 5000)
    n = len(rest_calls('conversations', 'GET')) - g0
    check('9.14 Consulta cada ~15 s (unas 4 veces por minuto), no más seguido', 3 <= n <= 5, n)
    check('9.15 A los 15 s la respuesta aparece por la consulta periódica', eventually(lambda: bubbles(pg)[-1:] == [['Equipo TECNOPATITAS', 'Respuesta que llega solo por consulta periódica']], 4), bubbles(pg))
    pg.fill('#s-texto', 'Escribo sin conexión en vivo'); pg.click('#s-enviar')
    check('9.16 También se puede escribir sin conexión en vivo', eventually(lambda: bubbles(pg)[-1:] == [['Tú', 'Escribo sin conexión en vivo']], 4), bubbles(pg))
    ctx.close()
    # --- unión rechazada / recuento distinto / error del sistema
    for mode, label in (('joinerr', '9.17 Si el servidor rechaza la unión (token no válido)'), ('badcount', '9.18 Si el servidor devuelve otros enlaces de los pedidos'), ('silent', '9.19 Si el servidor nunca responde a la unión')):
        reset_state(); rt.mode = mode
        ctx, pg, log, cid = with_thread(br)
        eventually(lambda: len(rt.conns) >= 1, 3); advance(pg, 16000, 4000)
        ok = (eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 3) if mode != 'silent'
              else ('En vivo' not in live_text(pg) and len(rt.conns) >= 2))            # sin respuesta a la unión: pasa de «conectando» a «sin conexión» a los 10 s y reintenta
        be.staff_reply(cid, ADMIN, 'por respaldo'); advance(pg, 16000, 4000)
        check(label + ': no queda «En vivo», reintenta y el chat sigue funcionando por consulta', ok and eventually(lambda: bubbles(pg)[-1:] == [['Equipo TECNOPATITAS', 'por respaldo']], 4), (live_text(pg), bubbles(pg)[-1:]))
        ctx.close()
    reset_state(); rt.mode = 'syserr'
    ctx, pg, log, cid = with_thread(br)
    advance(pg, 14000, 250)
    t = times(pg); gaps = [t[i + 1] - t[i] for i in range(0, len(t) - 1)]
    check('9.20 Si el canal avisa un error tras unirse, reconecta con esperas CRECIENTES (no en bucle)', len(gaps) >= 3 and gaps[1] > gaps[0] * 1.5 and gaps[2] > gaps[1] * 1.5, gaps)
    ctx.close()
    # --- renovación del token de sesión
    reset_state()
    ctx, pg, log, cid = with_thread(br, ttl=100)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    cn = rt.live(); t0 = cn.join['access_token']; r0 = len([c for c in be.calls if 'refresh_token' in c['query']])
    advance(pg, 56000, 5000)
    ok = eventually(lambda: len(cn.tokens) >= 1, 5)
    now_tok = pg.evaluate("JSON.parse(localStorage.getItem('tp-auth-v1')).access_token")
    check('9.21 Antes de que venza la sesión se renueva y se manda el token nuevo al canal (sin reconectar)',
          ok and cn.tokens[-1] == now_tok and now_tok != t0 and len([c for c in be.calls if 'refresh_token' in c['query']]) == r0 + 1 and len(rt.conns) == 1 and live_ok(pg), (ok, cn.tokens, len(rt.conns)))
    ctx.close()
    # --- cerrar sesión cierra la conexión
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    cn = rt.live(); pg.evaluate("TP.signOut()"); settle(pg, 300)
    check('9.22 Al cerrar sesión se avisa al servidor (phx_leave) y se cierra la conexión, sin reconectar (aunque la página siga abierta)', cn.left and cn.closed and eventually(lambda: rt.live() is None, 2) and len(rt.conns) == 1, (cn.left, cn.closed, len(rt.conns)))
    ctx.close()
    # --- salir de la página
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    cn = rt.live(); pg.goto(f'{ORIGIN}/index.html'); settle(pg, 300)
    check('9.23 Al salir de la página se cierra la conexión y no se abre otra (no se acumulan conexiones del plan gratuito)', cn.closed and len(rt.conns) == 1, (cn.closed, len(rt.conns)))
    ctx.close()
    # --- pestaña oculta
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    waitjs(pg, "document.getElementById('ch-live').textContent.includes('En vivo')")
    cn = rt.live(); g0 = len(rest_calls())
    pg.evaluate("(() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange')); })()")
    advance(pg, 240000, 10000)
    check('9.24 Con la pestaña oculta menos de 5 minutos, la conexión se mantiene', not cn.closed)
    advance(pg, 70000, 10000)
    check('9.25 Tras 5 minutos oculta se cierra la conexión (ahorra el límite de conexiones) y no consulta nada', eventually(lambda: cn.closed, 3) and len(rest_calls()) == g0, (cn.closed, len(rest_calls()) - g0))
    be.staff_reply(cid, ADMIN, 'llegó con la pestaña oculta')
    pg.evaluate("(() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange')); })()")
    check('9.26 Al volver a la pestaña reconecta y recupera lo que llegó', eventually(lambda: live_ok(pg) and len(rt.conns) == 2, 5) and eventually(lambda: bubbles(pg)[-1:] == [['Equipo TECNOPATITAS', 'llegó con la pestaña oculta']], 5), (live_text(pg), bubbles(pg)[-1:]))
    ctx.close()
    # --- confirmación de cierre caduca
    reset_state()
    ctx, pg, log, cid = with_thread(br)
    pg.click('#th-cerrar'); check('9.27 (reloj) El primer clic de «Cerrar» pide confirmar', txt(pg, '#th-cerrar') == 'Confirmar cierre')
    advance(pg, 6500); check('9.28 …y a los 6 s la confirmación caduca sola', txt(pg, '#th-cerrar') == 'Cerrar conversación' and not msg(pg), (txt(pg, '#th-cerrar'), msg(pg)))
    check('9.29 Sin errores de consola ni CSP', not any(csp_problems(l) for l in all_logs[-12:]), [csp_problems(l) for l in all_logs[-12:]])
    ctx.close()


SHOTS = os.environ.get('TP_SHOTS', '/tmp/claude-0/-home-claude/08c201bf-1a83-5894-b8bd-b81b4fba75f3/scratchpad/chat-shots')
os.makedirs(SHOTS, exist_ok=True)

def g10(br):
    print('\n[10] Cuenta suspendida: puede leer, no escribir')
    reset_state(); be.set_suspended(SUSI, False)
    cid = new_conv(SUSI, 'Mi caso antes de la suspensión', 'Mensaje previo')
    be.set_suspended(SUSI, True)
    ctx, pg, log = open_chat(br, 'susi@ejemplo.mx'); all_logs.append(log)
    check('10.1 Se ve el aviso de cuenta suspendida y la lista sigue visible', 'suspendida' in pg.inner_text('main') and [i['subject'] for i in items(pg)] == ['Mi caso antes de la suspensión'], pg.inner_text('main')[:120])
    check('10.2 «Nueva» está desactivado', pg.locator('#ch-new').is_disabled())
    open_thread(pg, cid)
    check('10.3 Puede leer sus mensajes, pero no escribir: cuadro y botón desactivados, sin botón de cerrar, con explicación',
          bubbles(pg) == [['Tú', 'Mensaje previo']] and pg.locator('#s-texto').is_disabled() and pg.locator('#s-enviar').is_disabled() and pg.locator('#th-cerrar').is_hidden() and 'suspendida' in txt(pg, '#th-aviso'), txt(pg, '#th-aviso'))
    n0 = len(be.rest_log)
    pg.evaluate("""(() => {
      document.getElementById('s-texto').value = 'texto forzado por código';
      document.getElementById('n-asunto').value = 'Asunto forzado por código'; document.getElementById('n-texto').value = 'Mensaje forzado por código';
      document.getElementById('f-send').requestSubmit(); document.getElementById('f-new').requestSubmit();
    })()"""); settle(pg, 200)
    check('10.4 Aunque se fuerce el envío por código, la página no manda nada', not [r for r in be.rest_log[n0:] if r['method'] in ('POST', 'PATCH')], be.rest_log[n0:])
    r = pg.evaluate("""(async () => { try { await TP.rest('/messages', {method: 'POST', body: {conversation_id: '%s', body: 'forzado'}, prefer: 'return=representation'}); return 'entró'; } catch (e) { return TP.errorMessage(e); } })()""" % cid)
    check('10.5 Y si alguien lo intenta saltándose la página, la base lo rechaza con un mensaje claro', 'suspendida' in r and int(be.sql("select count(*) from public.messages where body = 'forzado'")) == 0, r)
    r = pg.evaluate("""(async () => { try { await TP.rpc('start_conversation', {p_subject: 'Forzada', p_body: 'x'}); return 'entró'; } catch (e) { return TP.errorMessage(e); } })()""")
    check('10.6 Tampoco puede abrir conversaciones nuevas por la función del servidor', 'suspendida' in r and int(be.sql("select count(*) from public.conversations where subject = 'Forzada'")) == 0, r)
    check('10.7 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    be.set_suspended(SUSI, False)
    ctx, pg, log = open_chat(br, 'susi@ejemplo.mx'); all_logs.append(log)
    open_thread(pg, cid)
    check('10.8 Al reactivar la cuenta, todo vuelve a funcionar', pg.locator('#ch-new').is_enabled() and pg.locator('#s-texto').is_enabled() and pg.locator('#s-enviar').is_enabled() and pg.locator('#th-aviso').is_hidden())
    ctx.close()

def g11(br):
    print('\n[11] Teléfono (390 px): una columna a la vez')
    reset_state()
    a = new_conv(ANA, 'Primera para el móvil', 'Hola, tengo una duda larga sobre mi plan de suscripción y mis mascotas', ago_min=10)
    new_conv(ANA, 'Asunto larguísimo ' + 'palabra ' * 12, 'Otra', ago_min=5)
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', w=390, h=800); all_logs.append(log)
    ov = lambda: pg.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    vis = lambda sel: pg.locator(sel).is_visible()
    check('11.1 Al entrar solo se ve la lista de conversaciones', vis('#ch-list') and not vis('.chat-thread') and ov() <= 0, ov())
    pg.screenshot(path=f'{SHOTS}/mov-lista.png', full_page=True)
    pg.click(f'#ch-list .chat-item[data-id="{a}"]'); waitjs(pg, "!document.getElementById('ch-thread').hidden")
    check('11.2 Al abrir una conversación solo se ve el hilo, con botón «← Conversaciones»', vis('#ch-thread') and not vis('.chat-list') and vis('#ch-thread .chat-back') and ov() <= 0, ov())
    pg.screenshot(path=f'{SHOTS}/mov-hilo.png', full_page=True)
    sizes = pg.evaluate("Array.from(document.querySelectorAll('.chat .btn, .chat-item')).filter(b => b.offsetParent !== null).map(b => [b.textContent.trim().slice(0, 24), Math.round(b.getBoundingClientRect().height)])")
    check('11.3 Todos los botones del hilo miden al menos 44 px de alto', all(h >= 44 for _, h in sizes), sizes)
    pg.click('#ch-thread .chat-back'); settle(pg, 150)
    check('11.4 «← Conversaciones» regresa a la lista', vis('.chat-list') and not vis('.chat-thread'))
    sizes = pg.evaluate("Array.from(document.querySelectorAll('.chat .btn, .chat-item')).filter(b => b.offsetParent !== null).map(b => [b.textContent.trim().slice(0, 24), Math.round(b.getBoundingClientRect().height)])")
    check('11.5 En la lista también: botones y conversaciones de al menos 44 px', all(h >= 44 for _, h in sizes), sizes)
    pg.click('#ch-new'); settle(pg, 150)
    check('11.6 «Nueva» muestra el formulario a pantalla completa, con botón de volver', vis('#f-new') and not vis('.chat-list') and vis('#f-new .chat-back') and ov() <= 0, ov())
    pg.fill('#n-asunto', 'Asunto de prueba en el teléfono'); pg.fill('#n-texto', 'Mensaje en el teléfono')
    pg.screenshot(path=f'{SHOTS}/mov-nueva.png', full_page=True)
    pg.click('#n-cancelar'); settle(pg, 150)
    check('11.7 «Cancelar» vuelve a la lista', vis('.chat-list') and not vis('#f-new'))
    ctx.close()
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', w=1100, h=800); all_logs.append(log)
    open_thread(pg, a)
    check('11.8 En escritorio se ven lista e hilo a la vez y no hay botón de volver', vis('.chat-list') and vis('#ch-thread') and not vis('#ch-thread .chat-back'))
    staff_say(a, 'Con gusto te ayudamos con tu plan.')
    waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 2")
    pg.screenshot(path=f'{SHOTS}/esc-hilo.png', full_page=True)
    ctx.close()

def g12(br):
    print('\n[12] Accesibilidad')
    reset_state()
    a = new_conv(ANA, 'Consulta accesible', 'Hola')
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('12.1 Hay un solo título de nivel 1 y el idioma es español de México', pg.locator('h1').count() == 1 and pg.get_attribute('html', 'lang') == 'es-MX')
    nm = pg.evaluate("Array.from(document.querySelectorAll('#ch-list .chat-item')).map(b => b.textContent)")
    check('12.2 Cada conversación es un botón con nombre claro (asunto, estado y fecha)', len(nm) == 1 and 'Consulta accesible' in nm[0] and 'Esperando respuesta' in nm[0], nm)
    pg.focus('#ch-list .chat-item'); pg.keyboard.press('Enter'); waitjs(pg, "!document.getElementById('ch-thread').hidden")
    check('12.3 Con el teclado (Enter) se abre la conversación y el foco pasa al título', pg.evaluate('document.activeElement.id') == 'th-asunto')
    check('12.4 La conversación abierta se marca con aria-current', pg.get_attribute('#ch-list .chat-item', 'aria-current') == 'true')
    lg = pg.evaluate("(() => { const l = document.getElementById('th-log'); return [l.getAttribute('role'), l.getAttribute('aria-live'), l.getAttribute('aria-label'), l.tabIndex]; })()")
    check('12.5 Los mensajes están en una región role=log, anunciada con cortesía, con nombre y alcanzable con teclado', lg == ['log', 'polite', 'Mensajes de la conversación', 0], lg)
    lab = pg.evaluate("(() => { const t = document.getElementById('s-texto'); const l = document.querySelector('label[for=s-texto]'); return [!!l, l && l.textContent.trim(), t.labels.length]; })()")
    check('12.6 El cuadro de mensaje tiene etiqueta (oculta visualmente pero leída por lectores de pantalla)', lab[0] and lab[1] and lab[2] == 1, lab)
    pg.fill('#s-texto', ''); pg.click('#s-enviar'); settle(pg, 100)
    ro = pg.evaluate("(() => { const m = document.getElementById('ch-msg'); return [m.getAttribute('role'), m.hidden]; })()")
    check('12.7 Los errores se anuncian (role=alert)', ro == ['alert', False], ro)
    pg.keyboard.press('Tab'); 
    seq = []
    pg.focus('#th-asunto')
    for _ in range(8):
        pg.keyboard.press('Tab'); seq.append(pg.evaluate("document.activeElement.id || document.activeElement.textContent.trim().slice(0, 20)"))
    check('12.8 Con Tab se llega, en orden lógico, a cerrar, al registro de mensajes, al cuadro y a «Enviar»', 'th-cerrar' in seq and 'th-log' in seq and 's-texto' in seq and 's-enviar' in seq and seq.index('th-cerrar') < seq.index('th-log') < seq.index('s-texto') < seq.index('s-enviar'), seq)
    bad = pg.evaluate("Array.from(document.querySelectorAll('.chat button, .chat input, .chat textarea')).filter(e => !e.hidden && e.offsetParent !== null && !(e.textContent.trim() || (e.labels && e.labels.length) || e.getAttribute('aria-label'))).map(e => e.id)")
    check('12.9 Ningún control visible queda sin nombre accesible', not bad, bad)
    tm = pg.evaluate("Array.from(document.querySelectorAll('#th-log time')).every(t => /^\\d{4}-/.test(t.getAttribute('datetime')))")
    check('12.10 Las horas llevan su valor máquina (datetime)', tm)
    ctx.close()

def g13(br):
    print('\n[13] Fallos de red y del servidor')
    reset_state()
    cid = new_conv(ANA, 'Consulta con fallos', 'Hola')
    # carga inicial fallida → se avisa y se recupera sola
    state = {'fail': True}
    be.fail_rest = lambda path, method: ('abort', None) if state['fail'] and path.endswith('/conversations') else None
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', clock=True, wait=False); all_logs.append(log)
    pg.wait_for_selector('body.tp-ok', timeout=8000); eventually(lambda: msg(pg), 4)
    check('13.1 Si falla la primera carga se avisa en español, sin textos raros', 'No se pudo conectar' in msg(pg) and not junk(pg, 'main') and not items(pg), msg(pg))
    state['fail'] = False; advance(pg, 16000, 4000)
    check('13.2 …y la página se recupera sola cuando vuelve la conexión (sin recargar)', eventually(lambda: [i['subject'] for i in items(pg)] == ['Consulta con fallos'] and not msg(pg), 5), (items(pg), msg(pg)))
    ctx.close()
    # envío fallido
    be.fail_rest = None
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_thread(pg, cid)
    be.fail_rest = lambda path, method: ('abort', None) if method == 'POST' and path.endswith('/messages') else None
    pg.fill('#s-texto', 'Mensaje que no sale'); pg.click('#s-enviar'); eventually(lambda: msg(pg), 4)
    check('13.3 Si falla el envío: aviso claro, el texto NO se pierde y el botón vuelve a funcionar',
          'No se pudo conectar' in msg(pg) and pg.input_value('#s-texto') == 'Mensaje que no sale' and pg.locator('#s-enviar').is_enabled() and len(bubbles(pg)) == 1, (msg(pg), pg.input_value('#s-texto')))
    be.fail_rest = None; pg.click('#s-enviar'); waitjs(pg, "document.querySelectorAll('#th-log .bubble').length === 2")
    check('13.4 Al reintentar, el mensaje se envía una sola vez', int(be.sql("select count(*) from public.messages where body = 'Mensaje que no sale'")) == 1 and not msg(pg), msg(pg))
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if method == 'POST' and path.endswith('/messages') else None
    pg.fill('#s-texto', 'Error 500'); pg.click('#s-enviar'); eventually(lambda: msg(pg), 4)
    check('13.5 Un error 500 del servidor no muestra su texto interno (mensaje genérico en español)', 'error inesperado' in msg(pg) and 'boom' not in msg(pg) and 'XX000' not in msg(pg), msg(pg))
    # sesión vencida
    be.fail_rest = lambda path, method: (401, dict(code='PGRST301', message='JWT expired', details=None, hint=None)) if method == 'POST' and path.endswith('/messages') else None
    pg.click('#s-enviar')
    try: pg.wait_for_url(re.compile(r'login\.html\?next=chat\.html'), timeout=6000); ok = True
    except Exception: ok = False
    check('13.6 Si la sesión venció al enviar, se pide iniciar sesión y se vuelve al chat después', ok, pg.url)
    ctx.close()
    # consultas periódicas con el servidor caído: no se borra nada
    be.fail_rest = None; reset_state(); rt.mode = 'refuse'
    cid2 = new_conv(ANA, 'Sigue visible', 'Hola')
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx', clock=True); all_logs.append(log)
    open_thread(pg, cid2); eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 4)
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='caído', details=None, hint=None))
    advance(pg, 31000, 5000)
    check('13.7 Con el servidor fallando durante las consultas periódicas, la pantalla no se borra ni muestra errores', len(items(pg)) == 1 and len(bubbles(pg)) == 1 and not msg(pg), (items(pg), msg(pg)))
    be.fail_rest = None; be.staff_reply(cid2, ADMIN, 'Ya volvió el servidor'); advance(pg, 16000, 4000)
    check('13.8 Cuando el servidor vuelve, se pone al día solo', eventually(lambda: bubbles(pg)[-1:] == [['Equipo TECNOPATITAS', 'Ya volvió el servidor']], 5), bubbles(pg))
    check('13.9 Sin errores de consola ni CSP (salvo los fallos de red provocados a propósito)', not [m for m in csp_problems(log) if 'PAGEERROR' in m or 'Content Security' in m], csp_problems(log))
    ctx.close()

def g14(br):
    print('\n[14] El resto del sitio sigue igual')
    reset_state()
    ctx, pg, log = open_chat(br, 'ana@ejemplo.mx'); all_logs.append(log)
    pg.evaluate("(() => { document.getElementById('f-new').hidden = false; })()")
    pg.fill('#n-asunto', 'Prueba'); pg.fill('#n-texto', 'x'); pg.press('#n-texto', 'Control+Enter'); settle(pg, 300)
    check('14.1 En el chat ya no sale el aviso «todavía no está conectado» (el formulario es real)', not pg.evaluate("document.getElementById('toast').classList.contains('on')") and 'no está conectado' not in pg.inner_text('#toast'))
    ctx.close()
    n_rt = len(rt.attempts)
    scr, sess = session_script('ana@ejemplo.mx')
    ctx = new_ctx(br); ctx.add_init_script(scr); pg = ctx.new_page(); log = []; all_logs.append(log)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None); pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_selector('body.tp-ok')
    f = pg.locator('form[data-stage]')
    if f.count():
        pg.evaluate("document.querySelector('form[data-stage]').requestSubmit()"); settle(pg, 200)
        check('14.2 Las secciones que aún no se conectan (notificaciones, Etapa 8) conservan su aviso honesto', pg.evaluate("document.getElementById('toast').classList.contains('on')") and 'Etapa 8' in pg.inner_text('#toast'), pg.inner_text('#toast'))
    else:
        check('14.2 (notificaciones.html ya no tiene formulario pendiente)', True)
    check('14.3 Las páginas que no son el chat ni Notificaciones (aquí, Perfil) no abren conexión en vivo', len(rt.attempts) == n_rt, len(rt.attempts) - n_rt)
    ctx.close()

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for n, f in ((1, g1), (2, g2), (3, g3), (4, g4), (5, g5), (6, g6), (7, g7), (8, g8), (9, g9), (10, g10), (11, g11), (12, g12), (13, g13), (14, g14)):
        if group(n):
            try: f(br)
            except Exception as e:
                import traceback; traceback.print_exc(); check(f'GRUPO {n} terminó sin excepciones', False, repr(e)[:300])
    br.close()

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)} de {len(results)} comprobaciones correctas")
if bad:
    print('FALLARON:'); [print(' -', n, '->', d[:200]) for n, _, d in bad]
sys.exit(1 if bad else 0)
