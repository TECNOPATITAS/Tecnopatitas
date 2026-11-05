"""
Pruebas de interfaz de la Etapa 8 (notificaciones y campana) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP) y la base de datos:
            tablas, RLS, permisos por columna, disparador de «solo marcar leída», private.notify, generate_my_reminders y los avisos
            al equipo (PostgreSQL local con database/00_instalar_todo.sql; ver mock_etapa8.py).
  SIMULADO  PostgREST (traduce solo las consultas de las notificaciones a SQL), Supabase Auth (mock_supabase.py) y el servidor de
            Supabase Realtime (un WebSocket falso que habla el protocolo documentado). Los eventos que el «servidor» empuja salen de
            filas REALES de la base (como hace Realtime con el WAL).

Uso:  python3 pruebas-web/probar_notificaciones.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), playwright + chromium.
Variables: TP_PORT (sitio, 8772), TP_NOTIF_DB (base, tp_notif), TP_SITE (carpeta del sitio; las «pruebas de las pruebas» usan una copia saboteada),
           TP_ONLY (ejecuta solo un grupo, p. ej. TP_ONLY=9).
"""
import http.server, json, os, re, socketserver, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa8 import Backend8
from playwright._impl import _network
def _close_page_tolerante(self, event):             # Playwright falla si el navegador cierra el WebSocket sin código (ws.close() sin argumentos)
    if self._on_page_close: self._on_page_close(event.get('code'), event.get('reason'))
    else: self._channel.send_may_fail('closeServer', None, event)
_network.WebSocketRoute._channel_close_page = _close_page_tolerante

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8772)); DB = os.environ.get('TP_NOTIF_DB', 'tp_notif')
ORIGIN = f'http://localhost:{PORT}'
SUPA_HOST = 'mtkbxnhsjqqdbrjeaslo.supabase.co'
CONFIG_JS = open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", CONFIG_JS).group(1)
ONLY = os.environ.get('TP_ONLY', '')

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
        ws.on_message(lambda m: s.on_msg(c, m))
        ws.on_close(lambda code=None, reason=None: setattr(c, 'closed', True))
        if s.mode == 'refuse': c.closed = True; s.pending.append(ws)
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
            pcs = (payload.get('config') or {}).get('postgres_changes') or []
            ids = [{'id': 1000 + i, **b} for i, b in enumerate(pcs)]
            s.send(c, [jr, ref, topic, 'phx_reply', {'status': 'ok', 'response': {'postgres_changes': ids}}])
            s.send(c, [None, None, topic, 'system', {'message': 'Subscribed to PostgreSQL', 'status': 'ok', 'extension': 'postgres_changes', 'channel': 'tp-notifs'}])
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
be = Backend8(KEY, DB)
CUR = [None]
def route_supa(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    status, data = be.handle(req.method, req.url, req.headers, req.post_data)
    if status == 'abort': route.abort(); return
    route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body='' if data is None else json.dumps(data))
def new_ctx(br, w=1100, h=900, clock=False):
    ctx = br.new_context(viewport={'width': w, 'height': h})
    if clock: ctx.clock.install()
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), route_supa)
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    ctx.route_web_socket(re.compile(r'wss://mtkbxnhsjqqdbrjeaslo\.supabase\.co/realtime/v1/websocket.*'), rt.handler)
    return ctx
def session_script(email, ttl=None):
    u = be.users[email]; s = be._session(u)
    if ttl is not None: s['expires_at'] = int(time.time()) + ttl
    sess = dict(access_token=s['access_token'], refresh_token=s['refresh_token'], expires_at=s['expires_at'],
                user=dict(id=u['id'], email=email, email_confirmed_at='2026-11-04T00:00:00Z'))
    return "try{if(!localStorage.getItem('tp-auth-v1'))localStorage.setItem('tp-auth-v1',%s)}catch(e){}" % json.dumps(json.dumps(sess)), sess
def open_page(br, email, page='notificaciones.html', w=1100, h=900, clock=False, query='', wait=True, ctx=None):
    ctx = ctx or new_ctx(br, w, h, clock)
    if email:
        scr, sess = session_script(email); ctx.add_init_script(scr)
    log = []; pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/{page}{query}')
    if wait:
        pg.wait_for_selector('body.tp-ok', timeout=8000)
        if page == 'notificaciones.html': waitjs(pg, "document.getElementById('nt-loading').hidden === true")
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
def advance(pg, ms, step=None):
    """Avanza el reloj de la página (tiempo virtual) y deja que se procesen las peticiones pendientes."""
    if step:
        done = 0
        while done < ms:
            d = min(step, ms - done); pg.clock.run_for(d); done += d; tick(pg, 35)
    else:
        pg.clock.run_for(ms); tick(pg, 120)
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def txt(pg, sel): return pg.inner_text(sel) if pg.locator(sel).count() else ''
JUNK_RE = re.compile(r'\bnull\b|undefined|\[object|\bNaN\b|Invalid Date')
def junk(pg, sel): return JUNK_RE.findall(txt(pg, sel))
def nitems(pg):
    return pg.evaluate("""Array.from(document.querySelectorAll('#nt-list > li')).map(li => { const a = li.querySelector('a.btn');
        return {id: li.dataset.id, title: li.querySelector('.nt-title').textContent, body: li.querySelector('.nt-txt') ? li.querySelector('.nt-txt').textContent : null,
        unread: li.classList.contains('unread'), badges: Array.from(li.querySelectorAll('.badge')).map(b => b.textContent), link: a ? a.getAttribute('href') : null,
        toggle: li.querySelector('[data-act=toggle]').textContent, busy: li.getAttribute('aria-busy')}; })""")
def titles(pg): return [i['title'] for i in nitems(pg)]
def bell(pg):
    return pg.evaluate("""(() => { const b = document.getElementById('bell'), n = document.getElementById('bell-n');
        return {hidden: b.hidden, n: n.hidden ? '' : n.textContent, label: b.getAttribute('aria-label'), href: b.getAttribute('href'), has: b.classList.contains('has')}; })()""")
def msg(pg, sel='#nt-msg'): return txt(pg, sel) if pg.locator(sel).is_visible() else ''
def rest_calls(path=None, method=None, since=0):
    return [r for r in be.n_log[since:] if (path is None or r['path'].endswith(path)) and (method is None or r['method'] == method)]
def focus_info(pg):
    return pg.evaluate("""(() => { const a = document.activeElement; if (!a) return null; const li = a.closest && a.closest('li');
        return {id: a.id, act: a.dataset && a.dataset.act, li: li ? li.dataset.id : null, tag: a.tagName}; })()""")
def api(pg, method, path, body=None, prefer=None):
    """Llama al servidor desde la página (con su sesión), como lo haría alguien que manipula la consola del navegador."""
    return pg.evaluate("""async ([m, p, b, pr]) => { try { const r = await TP.rest(p, {method: m, body: b, prefer: pr}); return {ok: true, r}; }
        catch (e) { return {ok: false, status: e.status, code: e.code, msg: e.message}; } }""", [method, path, body, prefer])
def reset_state():
    be.reset_db(); be.rest_log.clear(); be.n_log.clear(); be.calls.clear(); be.fail_rest = None; rt.reset()
def group(n): return not ONLY or ONLY == str(n)
def ids_of(rows): return [r['id'] for r in rows]

def setup_users():
    prepare_db()
    return dict(ANA=be.add_user('ana@ejemplo.mx', 'ClaveSegura123', name='Ana'),
                BRUNO=be.add_user('bruno@ejemplo.mx', 'ClaveSegura123', name='Bruno'),
                ADMIN=be.add_user('dani@ejemplo.mx', 'ClaveSegura123', name='Dani', admin=True),
                CRIS=be.add_user('cris@ejemplo.mx', 'ClaveSegura123', name='Cris', account_type='business'),
                ELI=be.add_user('eli@ejemplo.mx', 'ClaveSegura123', name='Eli'))

# ================================================================== PRUEBAS
U = setup_users()
ANA, BRUNO, ADMIN, CRIS, ELI = U['ANA'], U['BRUNO'], U['ADMIN'], U['CRIS'], U['ELI']
all_logs = []

def seed_basic():
    a1 = be.notify(ANA, 'vacuna', 'Vacuna próxima: Rabia (Nube)', 'Fecha recomendada: 7 nov 2026. Consulta a tu veterinario y actualiza el carnet cuando la apliques.', 'carnet.html', ago_min=5)
    a2 = be.notify(ANA, 'mensaje', 'Nueva respuesta de atención al cliente', 'Hola Ana, ya revisamos tu duda.', 'chat.html', read=True, ago_min=60)
    a3 = be.notify(ANA, 'promocion', 'Promoción en el directorio', None, None, ago_min=120)
    b1 = be.notify(BRUNO, 'aviso', 'Aviso SOLO de Bruno', 'Esto no lo debe ver Ana', None, ago_min=1)
    b2 = be.notify(BRUNO, 'cita', 'Cita de Bruno secreta', None, 'carnet.html', ago_min=2)
    return a1, a2, a3, b1, b2

def g1(br):
    print('\n[1] Estructura y seguridad de la página')
    html = open(os.path.join(ROOT, 'notificaciones.html'), encoding='utf-8').read()
    check('1.1 notificaciones.html ya no está marcado como «no conectado» ni menciona Resend', 'data-stage' not in html and 'Resend' not in html and 'se conecta en la Etapa 8' not in html)
    check('1.2 Los scripts cargan en orden: cliente, interfaz, diseño, guarda, tiempo real, página',
          re.search(r'tp-client\.js.*tp-ui\.js.*layout\.js.*guard\.js.*tp-realtime\.js.*pages/notificaciones\.js', html) is not None)
    src = {f: open(os.path.join(ROOT, f), encoding='utf-8').read() for f in ('js/pages/notificaciones.js',)}
    bad = [(f, m) for f, t in src.items() for m in re.findall(r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function', t)]
    check('1.3 La página no usa innerHTML, eval ni document.write', not bad, bad)
    reset_state()
    ctx, pg, log = open_page(br, None, wait=False); all_logs.append(log)
    pg.wait_for_url(re.compile(r'login\.html\?next=notificaciones\.html'), timeout=8000); settle(pg, 300)
    check('1.4 Sin sesión: manda a iniciar sesión y NO consulta notificaciones ni abre la conexión en vivo', not rest_calls('notifications') and not rt.attempts, (len(rest_calls()), len(rt.attempts)))
    ctx.close()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('1.5 Con sesión la página carga sin errores de consola ni de CSP', not csp_problems(log), csp_problems(log))
    check('1.6 Se abre exactamente una conexión en vivo con la clave pública y el protocolo 2.0.0',
          eventually(lambda: rt.live() is not None) and len(rt.attempts) == 1 and f'apikey={KEY}' in rt.conns[0].url and 'vsn=2.0.0' in rt.conns[0].url, [c.url[:90] for c in rt.conns])
    pcs = ((rt.live().join or {}).get('config') or {}).get('postgres_changes') or [] if rt.live() else []
    check('1.7 Solo escucha INSERT y UPDATE de notifications, filtrado a la propia persona (user_id=eq.<su id>); nunca DELETE',
          sorted((c['event'], c['table'], c.get('filter')) for c in pcs) == sorted([('INSERT', 'notifications', f'user_id=eq.{ANA}'), ('UPDATE', 'notifications', f'user_id=eq.{ANA}')]), pcs)
    check('1.8 La clave secreta no aparece en la página ni en sus archivos', not re.search(r'sb_secret_[A-Za-z0-9_]{8,}', pg.content()) and all('service_role' not in t and not re.search(r'sb_secret_', t) for t in src.values()))
    check('1.11 Los avisos para lectores de pantalla tienen una región educada (role=status, aria-live=polite) y la lista tiene nombre',
          pg.evaluate("(() => { const a = document.getElementById('nt-announce'); return a.getAttribute('role') === 'status' && a.getAttribute('aria-live') === 'polite' && !!document.getElementById('nt-list').getAttribute('aria-label'); })()"))
    check('1.9 El menú lateral marca «Notificaciones» como página actual', pg.evaluate("document.querySelector('.side a[aria-current]').textContent.includes('Notificaciones')"))
    ctx.close()
    # la campana: invitados no la ven
    n0 = len(be.n_log)
    ctx = new_ctx(br)
    # registra si la campana llegó a verse en algún momento (un parpadeo ya sería un fallo para un invitado)
    ctx.add_init_script("""window.__bellSeen = false;
      new MutationObserver(() => { const b = document.getElementById('bell'); if (b && !b.hidden) window.__bellSeen = true; })
        .observe(document, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden']});""")
    ctx, pg, log = open_page(br, None, page='index.html', wait=False, ctx=ctx); all_logs.append(log)
    pg.wait_for_selector('#bell', state='attached'); settle(pg, 400)
    check('1.10 Un invitado no ve la campana en ninguna página pública y no consulta nada', bell(pg)['hidden'] is True and not rest_calls(None, None, n0), bell(pg))
    check('1.10b Y la campana no llega a verse ni un instante para un invitado (sin parpadeo mientras carga)', pg.evaluate('window.__bellSeen') is False, pg.evaluate('window.__bellSeen'))
    ctx.close()

def g2(br):
    print('\n[2] Lista de notificaciones y privacidad entre cuentas')
    reset_state()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('2.1 Sin notificaciones se explica qué verás aquí; no hay contador ni textos «null/undefined»',
          pg.locator('#nt-empty').is_visible() and 'No tienes notificaciones' in txt(pg, '#nt-empty-h') and not pg.locator('#nt-count').is_visible() and not junk(pg, 'main'), junk(pg, 'main'))
    check('2.2 Con la lista vacía «Marcar todas» y «Borrar las leídas» están desactivados', pg.locator('#nt-readall').is_disabled() and pg.locator('#nt-delread').is_disabled())
    check('2.3 Se aclara que por ahora no se envían correos', 'no enviamos correos' in txt(pg, '#nt-intro'))
    ctx.close()
    a1, a2, a3, b1, b2 = seed_basic()
    n0 = len(be.n_log)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    it = nitems(pg)
    check('2.4 Se ven solo las 3 notificaciones de Ana, la más nueva primero', ids_of(it) == [a1, a2, a3], ids_of(it))
    check('2.5 Las de Bruno (aviso y cita) no aparecen en ninguna parte de la página', 'Bruno' not in pg.inner_text('main') and 'secreta' not in pg.inner_text('main') and 'SOLO' not in pg.inner_text('main'))
    q = [r for r in rest_calls('notifications', 'GET', n0) if 'order=' in r['query']]
    check('2.6 La lista se pide ordenada (más nueva primero), con 50 por página y solo las columnas necesarias',
          q and 'limit=50' in q[0]['query'] and 'order=created_at.desc,id.desc' in q[0]['query'] and 'select=id,type,title,body,link,is_read,read_at,created_at' in q[0]['query'], q[:1])
    check('2.7 Las no leídas llevan «Nueva» y estilo destacado; las leídas no', it[0]['unread'] and 'Nueva' in it[0]['badges'] and it[2]['unread'] and not it[1]['unread'] and 'Nueva' not in it[1]['badges'], it)
    check('2.8 Cada una muestra su tipo en texto (no solo icono)', it[0]['badges'][-1] == 'Vacuna' and it[1]['badges'][-1] == 'Mensaje' and it[2]['badges'][-1] == 'Promoción', [i['badges'] for i in it])
    check('2.9 Título y detalle se muestran; la que no tiene detalle no deja un hueco vacío', it[0]['body'].startswith('Fecha recomendada: 7 nov 2026') and it[2]['body'] is None, it)
    check('2.10 «Ver» solo aparece donde hay enlace seguro y apunta a su página', it[0]['link'] == 'carnet.html' and it[1]['link'] == 'chat.html' and it[2]['link'] is None, [i['link'] for i in it])
    check('2.11 El contador dice «2 sin leer · 3 notificaciones»', txt(pg, '#nt-count') == '2 sin leer · 3 notificaciones', txt(pg, '#nt-count'))
    check('2.12 La fecha y hora salen en español de México (hora de México), sin «Invalid Date»',
          all(re.fullmatch(r'\d{1,2} \w+\.? \d{4},? \d{1,2}:\d{2}.*', t.strip()) for t in pg.locator('#nt-list time.when').all_inner_texts()) and pg.locator('#nt-list time.when').count() == 3 and not junk(pg, '#nt-list'), pg.locator('#nt-list time.when').all_inner_texts())
    check('2.13 Los botones de cada fila dicen a qué notificación se refieren (lectores de pantalla)',
          pg.evaluate("Array.from(document.querySelectorAll('#nt-list [data-act]')).every(b => (b.getAttribute('aria-label') || '').includes(':'))"))
    check('2.14 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    check('2.15 «Marcar todas» está activo (hay sin leer) y «Borrar las leídas» también (hay una leída)', pg.locator('#nt-readall').is_enabled() and pg.locator('#nt-delread').is_enabled())
    ctx.close()
    # la cuenta de Bruno ve solo lo suyo
    ctx, pg, log = open_page(br, 'bruno@ejemplo.mx'); all_logs.append(log)
    check('2.16 Bruno ve solo sus 2 notificaciones', sorted(titles(pg)) == sorted(['Aviso SOLO de Bruno', 'Cita de Bruno secreta']), titles(pg))
    ctx.close()

def g3(br):
    print('\n[3] Marcar como leída / no leída')
    reset_state()
    a1, a2, a3, b1, b2 = seed_basic()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    waitjs(pg, "document.getElementById('bell-n') && !document.getElementById('bell-n').hidden")
    check('3.0 La campana muestra 2 sin leer al abrir', bell(pg)['n'] == '2' and 'Notificaciones: 2 sin leer' == bell(pg)['label'], bell(pg))
    n0 = len(be.n_log)
    btn = f'#nt-list li[data-id="{a1}"] [data-act=toggle]'
    pg.focus(btn); pg.click(btn)
    waitjs(pg, f"!document.querySelector('#nt-list li[data-id=\"{a1}\"]').classList.contains('unread')")
    p = rest_calls('notifications', 'PATCH', n0)
    check('3.1 Se manda UNA petición PATCH solo con {is_read: true} para ese id', len(p) == 1 and p[0]['body'] == {'is_read': True} and f'id=eq.{a1}' in p[0]['query'], p)
    row = be.notif(a1)
    check('3.2 En la base queda leída y con fecha de lectura', row['is_read'] is True and row['read_at'] is not None, row)
    check('3.3 La fila pierde «Nueva», el botón cambia de texto y el contador baja a «1 sin leer»',
          'Nueva' not in nitems(pg)[0]['badges'] and nitems(pg)[0]['toggle'] == 'Marcar como no leída' and txt(pg, '#nt-count') == '1 sin leer · 3 notificaciones', (nitems(pg)[0], txt(pg, '#nt-count')))
    fi = focus_info(pg)
    check('3.4 El foco se queda en el mismo botón (no se pierde al actualizar)', fi and fi['li'] == a1 and fi['act'] == 'toggle', fi)
    check('3.5 La campana baja a 1 enseguida (sin esperar al minuto)', eventually(lambda: bell(pg)['n'] == '1', 4), bell(pg))
    pg.click(btn)
    waitjs(pg, f"document.querySelector('#nt-list li[data-id=\"{a1}\"]').classList.contains('unread')")
    row = be.notif(a1)
    check('3.6 Volver a «no leída» limpia la fecha de lectura en la base', row['is_read'] is False and row['read_at'] is None, row)
    check('3.7 La campana vuelve a 2', eventually(lambda: bell(pg)['n'] == '2', 4), bell(pg))
    # doble clic
    n0 = len(be.n_log)
    pg.evaluate(f"(() => {{ const b = document.querySelector('#nt-list li[data-id=\"{a1}\"] [data-act=toggle]'); b.click(); b.click(); }})()")
    settle(pg, 500)
    check('3.8 Un doble clic rápido manda una sola petición', len(rest_calls('notifications', 'PATCH', n0)) == 1, len(rest_calls('notifications', 'PATCH', n0)))
    # manipulación desde la consola: lo ajeno y lo prohibido
    r = api(pg, 'PATCH', f'/notifications?id=eq.{b1}&select=id', {'is_read': True}, 'return=representation')
    check('3.9 Alguien que manipula la consola NO puede marcar como leída una notificación de Bruno (0 filas)', r['ok'] and r['r'] == [] and be.notif(b1)['is_read'] is False, r)
    r = api(pg, 'DELETE', f'/notifications?id=eq.{b1}&select=id', None, 'return=representation')
    check('3.10 ...ni borrarla (0 filas) y sigue existiendo', r['ok'] and r['r'] == [] and be.notif(b1) is not None, r)
    r = api(pg, 'PATCH', f'/notifications?id=eq.{a1}&select=id', {'title': 'Hackeado'}, 'return=representation')
    check('3.11 ...ni cambiar el título de la suya (permiso denegado)', not r['ok'] and be.notif(a1)['title'] == 'Vacuna próxima: Rabia (Nube)', r)
    r = api(pg, 'PATCH', f'/notifications?id=eq.{a1}&select=id', {'user_id': BRUNO}, 'return=representation')
    check('3.12 ...ni pasársela a otra persona', not r['ok'] and be.notif(a1)['user_id'] == ANA, r)
    r = api(pg, 'POST', '/notifications', {'user_id': ANA, 'type': 'aviso', 'title': 'Falsa'}, 'return=representation')
    check('3.13 ...ni crear notificaciones desde el navegador (solo las crea el servidor)', not r['ok'] and be.count("title = 'Falsa'") == 0, r)
    # ya borrada en otra pestaña
    be.sql(f"delete from public.notifications where id = '{a3}'")
    pg.click(f'#nt-list li[data-id="{a3}"] [data-act=toggle]'); settle(pg, 400)
    check('3.14 Si la notificación ya no existe, se avisa con calma y desaparece de la lista', 'ya no existe' in msg(pg) and a3 not in ids_of(nitems(pg)), (msg(pg), ids_of(nitems(pg))))
    # marcar todas
    be.notify(ANA, 'aviso', 'Otra sin leer', ago_min=1)
    be.notify(ANA, 'cita', 'Y otra más', ago_min=2)
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    # ahora sincroniza por la conexión viva solo con eventos; forzamos con 'online'
    pg.evaluate("window.dispatchEvent(new Event('online'))")
    waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 4")
    n0 = len(be.n_log)
    pg.click('#nt-readall'); waitjs(pg, "document.querySelectorAll('#nt-list > li.unread').length === 0")
    p = rest_calls('notifications', 'PATCH', n0)
    check('3.15 «Marcar todas» manda una sola petición, solo para las no leídas', len(p) == 1 and 'is_read=eq.false' in p[0]['query'] and p[0]['body'] == {'is_read': True}, p)
    check('3.16 En la base todas las de Ana quedan leídas y las de Bruno siguen sin leer', be.count(f"user_id = '{ANA}' and not is_read") == 0 and be.count(f"user_id = '{BRUNO}' and not is_read") == 2)
    check('3.17 Sale el mensaje «Listo: 2 notificaciones marcadas como leídas.» (la tercera ya se había leído) y la campana queda en cero',
          msg(pg) == 'Listo: 2 notificaciones marcadas como leídas.' and eventually(lambda: bell(pg)['n'] == '' and not bell(pg)['has'], 4), (msg(pg), bell(pg)))
    check('3.18 Y el contador dice «Todo al día»', txt(pg, '#nt-count').startswith('Todo al día'), txt(pg, '#nt-count'))
    check('3.19 «Marcar todas» queda desactivado (ya no hay sin leer)', pg.locator('#nt-readall').is_disabled())
    check('3.20 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # la campana no abre consultas en paralelo aunque se pida actualizarla muchas veces seguidas (red lenta)
    be.notify(ANA, 'aviso', 'Para contar consultas de la campana')
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page='perfil.html'); all_logs.append(log)
    waitjs(pg, "document.getElementById('bell-n') && !document.getElementById('bell-n').hidden")
    pg.evaluate("""(() => { const f = window.fetch.bind(window); window.__bellGets = 0; window.__bellMax = 0; let live = 0;
        window.fetch = async (...a) => { const u = String(a[0] && a[0].url || a[0]);
          if (u.includes('/notifications') && u.includes('select=id') && u.includes('is_read=eq.false')) {
            window.__bellGets++; live++; window.__bellMax = Math.max(window.__bellMax, live);
            await new Promise(r => setTimeout(r, 1200)); try { return await f(...a); } finally { live--; } }
          return f(...a); }; })()""")
    pg.evaluate("for (let i = 0; i < 6; i++) window.dispatchEvent(new Event('tp-notifs'))")
    eventually(lambda: pg.evaluate('window.__bellGets') >= 2, 6); settle(pg, 1800)
    got = pg.evaluate('[window.__bellGets, window.__bellMax]')
    check('3.21 Pedir actualizar la campana 6 veces seguidas con red lenta hace 1 consulta en curso más 1 pendiente (nunca consultas en paralelo)', got[1] == 1 and got[0] == 2, got)
    check('3.22 Sin errores de consola ni CSP en esa página', not csp_problems(log), csp_problems(log))
    ctx.close()

def g4(br):
    print('\n[4] Borrar')
    reset_state()
    ids = [be.notify(ANA, 'aviso', f'Aviso {i}', None, None, read=(i % 2 == 0), ago_min=i) for i in range(1, 7)]   # 1,3,5 sin leer; 2,4,6 leídas
    be.notify(BRUNO, 'aviso', 'De Bruno leída', read=True)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', clock=True); all_logs.append(log)
    check('4.0 Se ven 6 notificaciones', len(nitems(pg)) == 6)
    n0 = len(be.n_log)
    pg.focus(f'#nt-list li[data-id="{ids[1]}"] [data-act=del]'); pg.click(f'#nt-list li[data-id="{ids[1]}"] [data-act=del]')
    waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 5")
    d = rest_calls('notifications', 'DELETE', n0)
    check('4.1 Borrar una manda UN DELETE con el id de esa notificación', len(d) == 1 and f'id=eq.{ids[1]}' in d[0]['query'], d)
    check('4.2 En la base ya no existe, y las demás siguen', be.notif(ids[1]) is None and be.count(f"user_id = '{ANA}'") == 5)
    fi = focus_info(pg)
    check('4.3 El foco pasa a la fila siguiente (no se pierde en la página)', fi and fi['li'] == ids[2], fi)
    check('4.4 Se anuncia «Notificación borrada.» para lectores de pantalla', 'Notificación borrada' in txt(pg, '#nt-announce'), txt(pg, '#nt-announce'))
    # borrar leídas (confirmación en dos pasos)
    n0 = len(be.n_log)
    pg.click('#nt-delread'); settle(pg, 200)
    check('4.5 «Borrar las leídas» primero pide confirmar y NO borra nada todavía', 'Confirmar' in txt(pg, '#nt-delread') and 'No se puede deshacer' in msg(pg) and not rest_calls('notifications', 'DELETE', n0) and len(nitems(pg)) == 5, (txt(pg, '#nt-delread'), msg(pg)))
    advance(pg, 6500, 500)
    check('4.6 Si no se confirma, a los 6 segundos se cancela solo', txt(pg, '#nt-delread') == 'Borrar las leídas' and not msg(pg), (txt(pg, '#nt-delread'), msg(pg)))
    pg.click('#nt-delread'); pg.click('#nt-delread'); waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 3")
    d = rest_calls('notifications', 'DELETE', n0)
    check('4.7 Al confirmar sale UN DELETE solo de las leídas', len(d) == 1 and 'is_read=eq.true' in d[0]['query'], d)
    check('4.8 Quedan las 3 sin leer; la leída de Bruno sigue en la base', be.count(f"user_id = '{ANA}'") == 3 and be.count(f"user_id = '{ANA}' and is_read") == 0 and be.count(f"user_id = '{BRUNO}'") == 1)
    check('4.9 Mensaje «Listo: 2 notificaciones borradas.»', msg(pg) == 'Listo: 2 notificaciones borradas.', msg(pg))
    check('4.10 La campana sigue en 3', eventually(lambda: bell(pg)['n'] == '3', 4), bell(pg))
    # borrar todo
    for i in ids_of(nitems(pg)):
        pg.click(f'#nt-list li[data-id="{i}"] [data-act=del]'); waitjs(pg, f"!document.querySelector('#nt-list li[data-id=\"{i}\"]')")
    check('4.11 Al borrar la última aparece el mensaje de lista vacía y el foco no se pierde (va al título)',
          pg.locator('#nt-empty').is_visible() and focus_info(pg) and focus_info(pg)['id'] == 'nt-h', focus_info(pg))
    check('4.12 La campana queda en cero', eventually(lambda: bell(pg)['n'] == '', 4), bell(pg))
    check('4.13 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g5(br):
    print('\n[5] Filtro «Sin leer»')
    reset_state()
    ids = [be.notify(ANA, 'aviso', f'Aviso {i}', read=(i > 2), ago_min=i) for i in range(1, 5)]    # 1,2 sin leer; 3,4 leídas
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    settle(pg, 600)   # que terminen las consultas de arranque (campana, recordatorios) antes de contar
    n0 = len(be.n_log)
    pg.click('#nt-f-unread'); settle(pg, 150)
    check('5.1 «Sin leer» muestra solo las 2 sin leer y marca el botón como activo (aria-pressed)',
          titles(pg) == ['Aviso 1', 'Aviso 2'] and pg.get_attribute('#nt-f-unread', 'aria-pressed') == 'true' and pg.get_attribute('#nt-f-all', 'aria-pressed') == 'false', (titles(pg)))
    extra = [r for r in be.n_log[n0:] if not (r['path'].endswith('/generate_my_reminders') or ('is_read=eq.false' in r.get('query', '') and 'select=id' in r.get('query', '')))]   # la campana puede consultar por su cuenta
    check('5.2 Cambiar de filtro no llama al servidor para pedir la lista', not extra, extra)
    pg.click(f'#nt-list li[data-id="{ids[0]}"] [data-act=toggle]'); waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 1")
    fi = focus_info(pg)
    check('5.3 Al marcar una como leída desaparece de «Sin leer» y el foco pasa a la otra fila', titles(pg) == ['Aviso 2'] and fi and fi['li'] == ids[1], (titles(pg), fi))
    pg.click('#nt-readall'); waitjs(pg, "document.getElementById('nt-empty').hidden === false")
    check('5.4 Sin ninguna sin leer: «Estás al día» (no «no tienes notificaciones»)', 'No tienes notificaciones sin leer' == txt(pg, '#nt-empty-h') and 'Estás al día' in txt(pg, '#nt-empty-p'), (txt(pg, '#nt-empty-h'), txt(pg, '#nt-empty-p')))
    pg.click('#nt-f-all'); settle(pg, 150)
    check('5.5 «Todas» vuelve a mostrar las 4', len(nitems(pg)) == 4 and not pg.locator('#nt-empty').is_visible())
    ctx.close()

def g6(br):
    print('\n[6] Muchas notificaciones: paginación')
    reset_state()
    be.notify_many(ANA, 120, 'Aviso', read=False)
    be.notify(BRUNO, 'aviso', 'De Bruno')
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('6.1 Se cargan 50 y se ofrece «Mostrar más»', len(nitems(pg)) == 50 and pg.locator('#nt-more').is_visible(), len(nitems(pg)))
    check('6.2 El contador avisa que hay más antiguas', '50 notificaciones cargadas (hay más antiguas)' in txt(pg, '#nt-count'), txt(pg, '#nt-count'))
    check('6.3 La campana llega a «99+» con más de 99 sin leer', eventually(lambda: bell(pg)['n'] == '99+', 4) and 'más de 99' in bell(pg)['label'], bell(pg))
    n0 = len(be.n_log)
    pg.click('#nt-more'); waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 100")
    q = rest_calls('notifications', 'GET', n0)
    check('6.4 «Mostrar más» pide por clave (created_at, id), no por desplazamiento', len(q) == 1 and 'or=(created_at.lt.' in q[0]['query'] and 'offset' not in q[0]['query'], q)
    pg.click('#nt-more'); waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 120")
    it = nitems(pg)
    check('6.5 Tras la tercera página están las 120, sin repetidas, de la más nueva a la más antigua y sin las de Bruno',
          len(set(ids_of(it))) == 120 and titles(pg) == [f'Aviso {i}' for i in range(1, 121)] and 'De Bruno' not in titles(pg), titles(pg)[:3])
    check('6.6 «Mostrar más» desaparece y el contador ya no dice «cargadas»', not pg.locator('#nt-more').is_visible() and txt(pg, '#nt-count') == '120 sin leer · 120 notificaciones', txt(pg, '#nt-count'))
    pg.click('#nt-readall'); waitjs(pg, "document.querySelectorAll('#nt-list > li.unread').length === 0")
    check('6.7 «Marcar todas» alcanza también a las que no se habían cargado en pantalla', be.count(f"user_id = '{ANA}' and not is_read") == 0 and msg(pg) == 'Listo: 120 notificaciones marcadas como leídas.', msg(pg))
    ctx.close()
    # con más páginas por cargar, «Marcar todas» y «Borrar las leídas» siguen activos
    reset_state(); be.notify_many(ANA, 60, 'Aviso', read=True)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('6.8 Si hay más por cargar, «Borrar las leídas» sigue activo aunque lo visible ya sea todo leído; «Marcar todas» también (puede haber sin leer más abajo)',
          pg.locator('#nt-delread').is_enabled() and pg.locator('#nt-readall').is_enabled())
    pg.click('#nt-delread'); pg.click('#nt-delread'); waitjs(pg, "document.getElementById('nt-empty').hidden === false")
    check('6.9 Borrar las leídas borra las 60 (también las que no se veían) y refresca la lista', be.count(f"user_id = '{ANA}'") == 0 and msg(pg) == 'Listo: 60 notificaciones borradas.', msg(pg))
    ctx.close()


def seed_pet_reminders(uid, name='Nube'):
    pid = be.add_pet(uid, name)
    be.sql(f"""select (now() at time zone 'America/Mexico_City')::date as hoy \\gset
insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on, next_due_on) values
  ('{pid}', 'Rabia', :'hoy'::date - 360, :'hoy'::date + 3),
  ('{pid}', 'Parvovirus', :'hoy'::date - 400, :'hoy'::date - 20);
insert into public.pet_appointments (pet_id, kind, scheduled_at, status, clinic) values ('{pid}', 'vacunacion', now() + interval '20 hours', 'programada', 'Clínica Patitas');""")
    return pid
def today_mx(): return be.sql("select (now() at time zone 'America/Mexico_City')::date")
def ls(pg, key): return pg.evaluate("k => localStorage.getItem(k)", key)
def live_text(pg): return txt(pg, '#nt-live').strip()
def wait_live(pg): return eventually(lambda: rt.live() is not None and 'En vivo' in live_text(pg), 6)

def g7(br):
    print('\n[7] Texto con código y enlaces peligrosos: se muestran como texto o no se muestran')
    reset_state()
    XSS_T = '<img src=x onerror="window.__x=1">'; XSS_B = '<script>window.__x=2</script>\nlínea 2 & <b>negrita</b> "comillas"'
    n_xss = be.notify(ANA, 'aviso', XSS_T, XSS_B, 'carnet.html', ago_min=1)
    n_ext = be.notify(ANA, 'aviso', 'Enlace externo', None, '//evil.example.com/x', ago_min=2)
    n_dot = be.notify(ANA, 'aviso', 'Enlace con puntos', None, '../admin.html', ago_min=3)
    n_unk = be.notify(ANA, 'aviso', 'Página desconocida', None, 'evil.html', ago_min=4)
    n_qry = be.notify(ANA, 'aviso', 'Con consulta', None, 'chat.html?c=abc#fin', ago_min=5)
    n_sl = be.notify(ANA, 'aviso', 'Con barra', None, 'carnet.html/../../x', ago_min=6)
    n_lng = be.notify(ANA, 'aviso', 'palabra' * 17, 'x' * 480, None, ago_min=7)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    it = {i['id']: i for i in nitems(pg)}
    check('7.1 Un título con HTML se ve como texto', it[n_xss]['title'] == XSS_T, it[n_xss]['title'])
    check('7.2 Un detalle con HTML se ve literal, con sus saltos de línea', it[n_xss]['body'] == XSS_B and pg.evaluate("getComputedStyle(document.querySelector('.nt-txt')).whiteSpace") == 'pre-wrap', it[n_xss]['body'])
    check('7.3 No se creó ningún elemento del texto (img, script, b) y no se ejecutó nada',
          pg.evaluate("document.querySelectorAll('#nt-list img, #nt-list script, #nt-list b:not(.nt-title)').length") == 0 and pg.evaluate('window.__x') is None)
    check('7.4 «//otro-sitio» (protocolo relativo), «../» y páginas fuera de la lista NO generan botón «Ver»',
          it[n_ext]['link'] is None and it[n_dot]['link'] is None and it[n_unk]['link'] is None and it[n_sl]['link'] is None, [it[i]['link'] for i in (n_ext, n_dot, n_unk, n_sl)])
    check('7.5 Un enlace interno con consulta y ancla sí funciona', it[n_qry]['link'] == 'chat.html?c=abc#fin', it[n_qry]['link'])
    check('7.6 En toda la página no hay ningún enlace hacia «evil»', pg.evaluate("Array.from(document.querySelectorAll('a')).filter(a => a.href.includes('evil')).length") == 0)
    w = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth, Math.max(...Array.from(document.querySelectorAll('#nt-list li')).map(l => l.scrollWidth - l.clientWidth))]")
    check('7.7 Un título y un detalle larguísimos sin espacios no desbordan la fila ni la página', w[0] <= w[1] and w[2] <= 1, w)
    ctx.close()
    # lo mismo si llega en vivo
    reset_state()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    wait_live(pg); settle(pg, 300)
    nid = be.notify(ANA, 'cita', XSS_T, XSS_B, '//evil.example.com')
    rt.push('notifications', 'INSERT', be.notif(nid))
    waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 1")
    check('7.8 Lo que llega en vivo también es texto y su enlace peligroso se ignora', titles(pg) == [XSS_T] and nitems(pg)[0]['link'] is None and pg.evaluate('window.__x') is None, nitems(pg))
    check('7.9 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g8(br):
    print('\n[8] Botón «Ver»')
    reset_state()
    u1 = be.notify(ANA, 'mensaje', 'Con respuesta', None, 'chat.html', ago_min=1)
    u2 = be.notify(ANA, 'vacuna', 'Para el carnet', None, 'carnet.html', ago_min=2)
    r1 = be.notify(ANA, 'cita', 'Ya leída', None, 'carnet.html', read=True, ago_min=3)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    n0 = len(be.n_log)
    pg.click(f'#nt-list li[data-id="{u1}"] a.btn')
    pg.wait_for_url(re.compile(r'/chat\.html$'), timeout=8000)
    p = rest_calls('notifications', 'PATCH', n0)
    check('8.1 «Ver» en una no leída la marca como leída ANTES de abrir la página', len(p) == 1 and be.notif(u1)['is_read'] is True and pg.url.endswith('/chat.html'), (p, pg.url))
    ctx.close()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    n0 = len(be.n_log)
    pg.click(f'#nt-list li[data-id="{r1}"] a.btn'); pg.wait_for_url(re.compile(r'/carnet\.html$'), timeout=8000)
    check('8.2 «Ver» en una ya leída abre la página sin llamar al servidor', not rest_calls('notifications', 'PATCH', n0), rest_calls('notifications', 'PATCH', n0))
    ctx.close()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    n0 = len(be.n_log); before = len(ctx.pages)
    with ctx.expect_page() as newp:
        pg.click(f'#nt-list li[data-id="{u2}"] a.btn', modifiers=['Control'])
    np_ = newp.value; settle(pg, 300)
    check('8.3 Ctrl+clic en «Ver» abre en otra pestaña sin interferir (queda sin leer: el clic normal es el que marca)', not rest_calls('notifications', 'PATCH', n0) and be.notif(u2)['is_read'] is False and pg.url.endswith('notificaciones.html'), pg.url)
    np_.close(); ctx.close()
    # servidor lento: no se queda esperando
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    def slow(path, method):
        if method == 'PATCH' and path.endswith('/notifications'): time.sleep(3.2)
        return None
    be.fail_rest = slow
    pg.evaluate("sessionStorage.setItem('t0', String(Date.now()))")
    pg.click(f'#nt-list li[data-id="{u2}"] a.btn'); pg.wait_for_url(re.compile(r'/carnet\.html$'), timeout=10000)
    dt = pg.evaluate("performance.timeOrigin - Number(sessionStorage.getItem('t0'))")
    check('8.4 Si el servidor tarda, «Ver» no se queda esperando más de ~1.5 s antes de abrir la página', 1000 < dt < 2900, dt)
    be.fail_rest = None; ctx.close()
    # error al marcar: igual abre
    be.sql(f"update public.notifications set is_read = false, read_at = null where id = '{u2}'")
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if method == 'PATCH' else None
    pg.click(f'#nt-list li[data-id="{u2}"] a.btn'); pg.wait_for_url(re.compile(r'/carnet\.html$'), timeout=8000)
    check('8.5 Si falla marcarla como leída, «Ver» abre la página de todos modos', pg.url.endswith('/carnet.html'), pg.url)
    be.fail_rest = None; ctx.close()

def g9(br):
    print('\n[9] Tiempo real')
    reset_state()
    old = be.notify(ANA, 'aviso', 'Ya estaba', None, None, ago_min=30)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('9.1 Aparece el indicador «En vivo»', wait_live(pg), live_text(pg))
    settle(pg, 500)
    n0 = len(be.n_log)
    nid = be.notify(ANA, 'vacuna', 'Vacuna nueva en vivo', 'Detalle', 'carnet.html')
    rt.push('notifications', 'INSERT', be.notif(nid))
    waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 2")
    lst = [r for r in rest_calls('notifications', 'GET', n0) if 'order=' in r['query']]
    check('9.2 Una notificación nueva aparece arriba al instante, sin volver a pedir la lista', titles(pg) == ['Vacuna nueva en vivo', 'Ya estaba'] and not lst, (titles(pg), lst))
    check('9.3 Se anuncia a lectores de pantalla («Nueva notificación: …»)', 'Nueva notificación: Vacuna nueva en vivo' in txt(pg, '#nt-announce'), txt(pg, '#nt-announce'))
    check('9.4 La campana sube a 2 sin esperar al minuto', eventually(lambda: bell(pg)['n'] == '2', 4), bell(pg))
    stale = be.notif(nid)
    pg.evaluate("document.getElementById('nt-announce').textContent = ''")
    rt.push('notifications', 'INSERT', stale); settle(pg, 400)
    check('9.5 El mismo evento repetido no duplica la fila ni vuelve a anunciarse a lectores de pantalla', len(nitems(pg)) == 2 and txt(pg, '#nt-announce') == '', (titles(pg), txt(pg, '#nt-announce')))
    be.sql(f"update public.notifications set is_read = true, read_at = now() where id = '{nid}'")
    rt.push('notifications', 'UPDATE', be.notif(nid), {'id': nid})
    waitjs(pg, f"!document.querySelector('#nt-list li[data-id=\"{nid}\"]').classList.contains('unread')")
    check('9.6 Marcarla como leída desde otra pestaña (evento UPDATE) actualiza la fila y el contador', txt(pg, '#nt-count') == '1 sin leer · 2 notificaciones' and eventually(lambda: bell(pg)['n'] == '1', 4), (txt(pg, '#nt-count'), bell(pg)))
    rt.push('notifications', 'INSERT', stale); settle(pg, 300)
    check('9.6b Un evento viejo repetido (sin leer) NO deshace lo que ya se marcó como leído', not nitems(pg)[0]['unread'] and txt(pg, '#nt-count') == '1 sin leer · 2 notificaciones', (nitems(pg)[0], txt(pg, '#nt-count')))
    foreign = be.notify(BRUNO, 'aviso', 'Para Bruno')
    n1 = len(nitems(pg))
    rt.push('notifications', 'INSERT', be.notif(foreign)); settle(pg, 300)
    check('9.7 Un evento de OTRA persona se ignora aunque llegara por error', len(nitems(pg)) == n1 and 'Para Bruno' not in pg.inner_text('main'), titles(pg))
    rt.push('notifications', 'INSERT', {'id': 'no-es-uuid', 'user_id': ANA, 'type': 'aviso', 'title': 'Roto', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('notifications', 'INSERT', {'id': '11111111-1111-4111-8111-111111111111', 'user_id': ANA, 'type': 'hackeo', 'title': 'Tipo raro', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('notifications', 'INSERT', {'id': '22222222-2222-4222-8222-222222222222', 'user_id': ANA, 'type': 'aviso', 'title': '', 'created_at': '2026-11-04T10:00:00Z'})
    rt.push('notifications', 'INSERT', {'id': '33333333-3333-4333-8333-333333333333', 'user_id': ANA, 'type': 'aviso', 'title': 'Sin fecha'})
    settle(pg, 400)
    check('9.8 Eventos mal formados (id, tipo, título vacío, sin fecha) se descartan sin romper la página', len(nitems(pg)) == n1 and not csp_problems(log), (titles(pg), csp_problems(log)))
    ok_id = be.notify(ANA, 'aviso', 'Válida después de los eventos rotos')
    rt.push('notifications', 'INSERT', be.notif(ok_id))
    check('9.8b Tras los eventos mal formados, uno válido se sigue dibujando (la lista no quedó rota)', eventually(lambda: titles(pg)[:1] == ['Válida después de los eventos rotos'], 4) and len(nitems(pg)) == n1 + 1, titles(pg))
    n1 = len(nitems(pg))
    # evento UPDATE de una antigua que no está cargada: se sincroniza sin romper
    n0 = len(be.n_log)
    rt.push('notifications', 'UPDATE', {'id': '44444444-4444-4444-8444-444444444444', 'user_id': ANA, 'type': 'aviso', 'title': 'Antigua', 'is_read': True, 'created_at': '2026-01-01T10:00:00Z'})
    settle(pg, 600)
    check('9.9 Un UPDATE de una que no estaba cargada solo provoca una sincronización', len(rest_calls('notifications', 'GET', n0)) >= 1 and len(nitems(pg)) == n1 and 'Antigua' not in titles(pg), (len(rest_calls('notifications', 'GET', n0)), titles(pg)))
    # caída y recuperación
    rt.drop()
    check('9.10 Al caerse la conexión se avisa «Sin conexión en vivo»', eventually(lambda: 'Sin conexión en vivo' in live_text(pg), 5), live_text(pg))
    missed = be.notify(ANA, 'cita', 'Llegó mientras no había conexión')
    check('9.11 Al reconectar se pone al día solo (aparece lo que llegó durante la caída)', eventually(lambda: 'Llegó mientras no había conexión' in titles(pg), 12) and 'En vivo' in live_text(pg), (titles(pg), live_text(pg)))
    check('9.12 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g9b(br):
    print('\n[9b] Con la conexión en vivo activa no se consulta por su cuenta')
    reset_state()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', clock=True); all_logs.append(log)
    check('9.13 La conexión en vivo se establece', wait_live(pg), live_text(pg))
    advance(pg, 1500, 500)
    be.notify(ANA, 'aviso', 'No se empujó por la conexión'); n0 = len(be.n_log)
    advance(pg, 45000, 5000)
    lst = [r for r in rest_calls('notifications', 'GET', n0) if 'order=' in r['query']]
    check('9.14 Mientras la conexión en vivo funciona NO se consulta cada 20 s (ahorra peticiones)', not lst and 'No se empujó por la conexión' not in titles(pg), (len(lst), titles(pg)))
    check('9.15 La conexión sigue viva tras los latidos', 'En vivo' in live_text(pg), live_text(pg))
    ctx.close()

def g10(br):
    print('\n[10] Sin conexión en vivo: consulta cada 20 s')
    reset_state()
    rt.mode = 'refuse'
    k1 = be.notify(ANA, 'aviso', 'Se queda', ago_min=10)
    k2 = be.notify(ANA, 'aviso', 'Se borrará en otra pestaña', ago_min=11)
    k3 = be.notify(ANA, 'aviso', 'Se leerá en otra pestaña', ago_min=12)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', clock=True); all_logs.append(log)
    check('10.1 Con la conexión en vivo rechazada se avisa que se revisa cada 20 segundos', eventually(lambda: 'cada 20 segundos' in live_text(pg), 6), live_text(pg))
    n0 = len(be.n_log)
    be.notify(ANA, 'cita', 'Nueva por consulta', ago_min=0)
    be.sql(f"delete from public.notifications where id = '{k2}'")
    be.sql(f"update public.notifications set is_read = true, read_at = now() where id = '{k3}'")
    advance(pg, 10000, 2500)
    check('10.2 A los 10 s todavía no ha consultado', not [r for r in rest_calls('notifications', 'GET', n0) if 'order=' in r['query']], len(rest_calls('notifications', 'GET', n0)))
    advance(pg, 12000, 2500)
    check('10.3 Pasados 20 s aparece lo nuevo, desaparece lo borrado en otra pestaña y se actualiza lo leído',
          eventually(lambda: titles(pg) == ['Nueva por consulta', 'Se queda', 'Se leerá en otra pestaña'], 4) and [i['unread'] for i in nitems(pg)] == [True, True, False], (titles(pg), [i['unread'] for i in nitems(pg)]))
    # pestaña oculta: no consulta
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true})")
    n0 = len(be.n_log); be.notify(ANA, 'aviso', 'Mientras estaba oculta')
    advance(pg, 65000, 5000)
    check('10.4 Con la pestaña oculta no consulta (ahorra batería y límites del plan gratuito)', not rest_calls('notifications', None, n0), len(rest_calls('notifications', None, n0)))
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
    check('10.5 Al volver a la pestaña se pone al día de inmediato', eventually(lambda: 'Mientras estaba oculta' in titles(pg), 5), titles(pg))
    # servidor caído durante las consultas periódicas
    before = titles(pg)
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='caído', details=None, hint=None))
    advance(pg, 41000, 5000)
    check('10.6 Con el servidor fallando la lista no se borra ni aparece un error', titles(pg) == before and not msg(pg), (titles(pg), msg(pg)))
    be.fail_rest = None; be.notify(ANA, 'aviso', 'Tras la caída'); advance(pg, 21000, 5000)
    check('10.7 Cuando el servidor vuelve, se pone al día solo', eventually(lambda: 'Tras la caída' in titles(pg), 5), titles(pg))
    check('10.8 Sin errores de página ni de CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # fallo al cargar al abrir
    reset_state(); rt.mode = 'refuse'
    be.notify(ANA, 'aviso', 'Existe')
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if path.endswith('/notifications') else None
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', clock=True, wait=False); all_logs.append(log)
    pg.wait_for_selector('body.tp-ok', timeout=8000)
    check('10.9 Si la primera carga falla se explica (sin mostrar «boom») y no se queda «Cargando…» mudo', eventually(lambda: 'error inesperado' in msg(pg) and 'No pudimos cargar' in txt(pg, '#nt-loading'), 6) and 'boom' not in msg(pg), (msg(pg), txt(pg, '#nt-loading')))
    be.fail_rest = None; advance(pg, 21000, 5000)
    check('10.10 Y se recupera sola cuando el servidor vuelve (desaparece el error y aparece la lista)', eventually(lambda: titles(pg) == ['Existe'] and not msg(pg), 6), (titles(pg), msg(pg)))
    ctx.close()

def g11(br):
    print('\n[11] Preferencias')
    reset_state()
    be.set_prefs(ANA, vacuna=False, promocion=False)
    pid = seed_pet_reminders(ANA)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    waitjs(pg, "!document.getElementById('p-set').disabled")
    st = pg.evaluate("Object.fromEntries(Array.from(document.querySelectorAll('#f-prefs [name]')).map(i => [i.name, i.checked]))")
    check('11.1 El formulario refleja lo guardado: vacunas y promociones apagadas, lo demás encendido',
          st == {'vacuna': False, 'desparasitacion': True, 'cita': True, 'promocion': False, 'suscripcion': True, 'mensaje': True}, st)
    check('11.2 Los avisos importantes aparecen encendidos y NO se pueden apagar', pg.evaluate("(() => { const i = Array.from(document.querySelectorAll('#f-prefs input')).find(x => !x.name && x.id !== 'p-email'); return i.checked && i.disabled; })()"))
    check('11.3 El correo aparece apagado, bloqueado y se aclara que todavía no existe', pg.evaluate("(() => { const e = document.getElementById('p-email'); return !e.checked && e.disabled; })()") and 'todavía no disponible' in txt(pg, '#f-prefs'))
    g = [r for r in rest_calls('profiles', 'GET')]
    check('11.4 Las preferencias se piden solo de la propia persona (id=eq.<su id>) y solo esa columna', g and f'id=eq.{ANA}' in g[0]['query'] and 'select=notification_prefs' in g[0]['query'], g[:1])
    # al abrir, con «vacunas» apagadas, no se genera ese recordatorio (pero sí la cita)
    check('11.5 Con «vacunas» apagado no aparecen recordatorios de vacunas (sí el de la cita)', titles(pg) == ['Cita próxima de Nube'], titles(pg))
    n0 = len(be.n_log)
    pg.check('#f-prefs [name=vacuna]'); pg.uncheck('#f-prefs [name=cita]'); pg.click('#p-save')
    waitjs(pg, "document.getElementById('p-msg').textContent.includes('guardadas')")
    p = rest_calls('profiles', 'PATCH', n0)
    want = {'aviso': True, 'vacuna': True, 'desparasitacion': True, 'cita': False, 'promocion': False, 'suscripcion': True, 'mensaje': True}
    check('11.6 Se guarda con UNA petición y el objeto completo (siete claves; «aviso» siempre true)', len(p) == 1 and p[0]['body'] == {'notification_prefs': want}, p)
    check('11.7 En la base queda exactamente eso y el correo sigue apagado', be.prefs(ANA) == want and be.sql(f"select email_reminders from public.profiles where id = '{ANA}'") == 'f', be.prefs(ANA))
    check('11.8 Al reactivar «vacunas» aparecen de inmediato los recordatorios que estaban pendientes', eventually(lambda: sorted(titles(pg)) == sorted(['Cita próxima de Nube', 'Vacuna próxima: Rabia (Nube)', 'Vacuna vencida: Parvovirus (Nube)']), 6), titles(pg))
    check('11.9 Se llamó a generar recordatorios al reactivar (no antes)', len(rest_calls('generate_my_reminders', 'POST', n0)) == 1, len(rest_calls('generate_my_reminders', 'POST', n0)))
    # intentar apagar los avisos manipulando el formulario
    pg.evaluate("(() => { const i = Array.from(document.querySelectorAll('#f-prefs input')).find(x => !x.name && x.id !== 'p-email'); i.disabled = false; i.checked = false; })()")
    n0 = len(be.n_log); pg.click('#p-save'); waitjs(pg, "document.getElementById('p-save').textContent === 'Guardar preferencias'"); settle(pg, 300)
    p = rest_calls('profiles', 'PATCH', n0)
    check('11.10 Aunque se manipule el formulario, el cliente siempre manda «aviso: true»', p and p[-1]['body']['notification_prefs']['aviso'] is True and be.prefs(ANA)['aviso'] is True, p)
    # error del servidor al guardar
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if method == 'PATCH' and path.endswith('/profiles') else None
    pg.uncheck('#f-prefs [name=mensaje]'); pg.click('#p-save'); eventually(lambda: pg.locator('#p-msg').is_visible() and 'error' in txt(pg, '#p-msg').lower(), 4)
    check('11.11 Si falla al guardar: mensaje en español sin detalles internos, el botón vuelve a estar disponible y no dice «guardadas»',
          'error inesperado' in txt(pg, '#p-msg') and 'boom' not in txt(pg, '#p-msg') and pg.locator('#p-save').is_enabled() and txt(pg, '#p-save') == 'Guardar preferencias', txt(pg, '#p-msg'))
    check('11.12 ...y lo guardado en la base no cambió', be.prefs(ANA)['mensaje'] is True)
    be.fail_rest = None
    # datos inválidos desde la consola: la base los rechaza
    r = api(pg, 'PATCH', f'/profiles?id=eq.{ANA}', {'notification_prefs': ['x']}, 'return=representation')
    check('11.13 Alguien que manipula la consola no puede guardar preferencias que no sean un objeto (la base lo rechaza)', not r['ok'] and isinstance(be.prefs(ANA), dict), r)
    r = api(pg, 'PATCH', f'/profiles?id=eq.{BRUNO}', {'notification_prefs': {'vacuna': False}}, 'return=representation')
    check('11.14 ...ni cambiar las preferencias de otra persona', r['ok'] and r['r'] == [] and be.prefs(BRUNO).get('vacuna') is True, r)
    ctx.close()
    # error al cargar las preferencias
    reset_state()
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if method == 'GET' and path.endswith('/profiles') else None
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    settle(pg, 400)
    check('11.15 Si no cargan las preferencias se avisa y el formulario queda bloqueado (no se guardan valores a ciegas)', 'No pudimos cargar tus preferencias' in txt(pg, '#p-msg') and pg.locator('#p-save').is_disabled() and pg.evaluate("document.getElementById('p-set').disabled"), txt(pg, '#p-msg'))
    be.fail_rest = None; ctx.close()

def g12(br):
    print('\n[12] Recordatorios de vacunas, desparasitaciones y citas')
    reset_state()
    seed_pet_reminders(ANA)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    eventually(lambda: len(nitems(pg)) == 3, 6)
    check('12.1 Al abrir la pantalla se generan los recordatorios (vacuna próxima, vacuna vencida y cita)', sorted(titles(pg)) == sorted(['Vacuna próxima: Rabia (Nube)', 'Vacuna vencida: Parvovirus (Nube)', 'Cita próxima de Nube']), titles(pg))
    check('12.2 Solo se llamó UNA vez al servidor para generarlos (la cabecera no lo repite en esta pantalla)', len(rest_calls('generate_my_reminders', 'POST')) == 1, len(rest_calls('generate_my_reminders', 'POST')))
    it = {i['title']: i for i in nitems(pg)}
    check('12.3 Los textos son claros y llevan al carnet', 'Consulta a tu veterinario' in it['Vacuna vencida: Parvovirus (Nube)']['body'] and it['Vacuna próxima: Rabia (Nube)']['link'] == 'carnet.html' and 'hora de México' in it['Cita próxima de Nube']['body'], it)
    check('12.4 Quedan marcados los tipos «Vacuna» y «Cita»', it['Cita próxima de Nube']['badges'][-1] == 'Cita' and it['Vacuna próxima: Rabia (Nube)']['badges'][-1] == 'Vacuna')
    check('12.5 El navegador recuerda que hoy ya se pidieron (clave por cuenta, fecha de México)', ls(pg, f'tp-rem-v1:{ANA}') == today_mx(), ls(pg, f'tp-rem-v1:{ANA}'))
    check('12.6 La campana cuenta los 3 recordatorios', eventually(lambda: bell(pg)['n'] == '3', 4), bell(pg))
    # borrar uno: no vuelve
    vid = [i['id'] for i in nitems(pg) if i['title'].startswith('Vacuna vencida')][0]
    pg.click(f'#nt-list li[data-id="{vid}"] [data-act=del]'); waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 2")
    ctx.close()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    settle(pg, 700)
    check('12.7 Un recordatorio borrado NO vuelve a aparecer al reabrir; tampoco se duplican los demás', len(nitems(pg)) == 2 and not any(t.startswith('Vacuna vencida') for t in titles(pg)), titles(pg))
    ctx.close()
    # cuenta de aliado: también pide la generación (avisos de vencimiento del plan)
    reset_state(); n0 = len(be.n_log)
    ctx, pg, log = open_page(br, 'cris@ejemplo.mx'); all_logs.append(log)
    settle(pg, 500)
    check('12.8 Una cuenta de aliado también pide la generación (una vez): sirve para sus avisos de vencimiento del plan', len(rest_calls('generate_my_reminders', 'POST', n0)) == 1, rest_calls('generate_my_reminders', None, n0))
    ctx.close()
    # fallo del servidor al generar: la lista funciona igual y sin mensajes
    reset_state(); seed_pet_reminders(ELI, 'Pelusa'); be.notify(ELI, 'aviso', 'Ya había una')
    be.fail_rest = lambda path, method: (400, dict(code='P0001', message='Demasiadas solicitudes. Espera un momento.', details=None, hint=None)) if path.endswith('/generate_my_reminders') else None
    ctx, pg, log = open_page(br, 'eli@ejemplo.mx'); all_logs.append(log); settle(pg, 500)
    check('12.9 Si generar recordatorios falla (p. ej. límite por hora), la lista sigue y no se muestra ningún error', titles(pg) == ['Ya había una'] and not msg(pg), (titles(pg), msg(pg)))
    check('12.10 ...y no se marca el día como hecho (se reintenta después)', ls(pg, f'tp-rem-v1:{ELI}') is None, ls(pg, f'tp-rem-v1:{ELI}'))
    be.fail_rest = None; ctx.close()
    # recordatorios diarios desde cualquier otra página (los pide la cabecera, una vez al día por navegador)
    reset_state(); seed_pet_reminders(ANA)
    key = f'tp-rem-v1:{ANA}'
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page='perfil.html', wait=False); all_logs.append(log)
    eventually(lambda: bell(pg)['n'] == '3', 6)
    check('12.11 En cualquier otra página la primera visita del día genera los recordatorios y la campana los cuenta (3)', len(rest_calls('generate_my_reminders', 'POST')) == 1 and bell(pg)['n'] == '3', (len(rest_calls('generate_my_reminders', 'POST')), bell(pg)))
    check('12.12 ...y el navegador recuerda el día (clave por cuenta)', ls(pg, key) == today_mx(), ls(pg, key))
    n0 = len(be.n_log); pg.reload(); pg.wait_for_selector('#bell:not([hidden])'); settle(pg, 700)
    check('12.13 Recargar la página el mismo día NO vuelve a pedirlos', not rest_calls('generate_my_reminders', None, n0), rest_calls('generate_my_reminders', None, n0))
    pg.evaluate("k => localStorage.setItem(k, '2020-01-01')", key); n0 = len(be.n_log); pg.reload(); pg.wait_for_selector('#bell:not([hidden])'); settle(pg, 700)
    check('12.14 Con otra fecha guardada (otro día) se piden otra vez, sin duplicar nada', len(rest_calls('generate_my_reminders', 'POST', n0)) == 1 and be.count(f"user_id = '{ANA}'") == 3 and ls(pg, key) == today_mx(), (len(rest_calls('generate_my_reminders', 'POST', n0)), be.count(f"user_id = '{ANA}'")))
    ctx.close()
    n0 = len(be.n_log)
    ctx, pg, log = open_page(br, 'cris@ejemplo.mx', page='perfil.html', wait=False); all_logs.append(log)
    pg.wait_for_selector('#bell:not([hidden])'); settle(pg, 700)
    check('12.15 La cabecera de una cuenta de aliado pide la generación una sola vez al día', len(rest_calls('generate_my_reminders', 'POST', n0)) == 1, rest_calls('generate_my_reminders', None, n0))
    check('12.16 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g13(br):
    print('\n[13] Campana de la cabecera')
    reset_state()
    for i in range(3): be.notify(ANA, 'aviso', f'Sin leer {i}', ago_min=i + 1)
    be.notify(ANA, 'aviso', 'Leída', read=True)
    be.notify(BRUNO, 'aviso', 'Ajena 1'); be.notify(BRUNO, 'aviso', 'Ajena 2')
    n_rt0 = len(rt.attempts)
    for page in ('index.html', 'perfil.html', 'directorio.html', 'planes.html'):
        n0 = len(be.n_log)
        ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page=page, wait=False); all_logs.append(log)
        pg.wait_for_selector('#bell', state='attached'); eventually(lambda: bell(pg)['n'] == '3', 5)
        b = bell(pg)
        q = [r for r in rest_calls('notifications', 'GET', n0)]
        check(f'13.1 {page}: la campana muestra 3 (solo las suyas), enlaza a Notificaciones y su etiqueta lo dice',
              not b['hidden'] and b['n'] == '3' and b['href'] == 'notificaciones.html' and b['label'] == 'Notificaciones: 3 sin leer' and b['has'], b)
        check(f'13.2 {page}: la consulta de la campana es ligera (solo ids, sin leer, máximo 100)', q and q[0]['query'] == 'select=id&is_read=eq.false&limit=100', q[:1])
        ctx.close()
    check('13.3 Ninguna de esas páginas abre conexión en vivo (cada pestaña no gasta una de las ~200 conexiones del plan gratuito)', len(rt.attempts) == n_rt0, len(rt.attempts) - n_rt0)
    # consulta cada 60 s
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page='perfil.html', clock=True, wait=False); all_logs.append(log)
    eventually(lambda: bell(pg)['n'] == '3', 5)
    n0 = len(be.n_log); be.notify(ANA, 'aviso', 'Nueva sin leer')
    advance(pg, 30000, 5000)
    check('13.4 A los 30 s todavía no ha vuelto a consultar', not rest_calls('notifications', None, n0), len(rest_calls('notifications', None, n0)))
    advance(pg, 32000, 5000)
    check('13.5 Pasado el minuto actualiza el número (4)', eventually(lambda: bell(pg)['n'] == '4', 4), bell(pg))
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true})")
    n0 = len(be.n_log); advance(pg, 130000, 10000)
    check('13.6 Con la pestaña oculta no consulta', not rest_calls('notifications', None, n0), len(rest_calls('notifications', None, n0)))
    be.notify(ANA, 'aviso', 'Otra más')
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
    check('13.7 Al volver a la pestaña actualiza enseguida (5)', eventually(lambda: bell(pg)['n'] == '5', 4), bell(pg))
    be.fail_rest = lambda path, method: (500, dict(code='XX000', message='boom', details=None, hint=None)) if path.endswith('/notifications') else None
    advance(pg, 62000, 5000)
    check('13.8 Si el servidor falla, la campana conserva el último número (no se pone en cero ni muestra error)', bell(pg)['n'] == '5' and not csp_problems(log), (bell(pg), csp_problems(log)))
    be.fail_rest = None
    pg.click('#bell'); pg.wait_for_url(re.compile(r'/notificaciones\.html$'), timeout=8000)
    check('13.9 Al pulsar la campana se abre la pantalla de Notificaciones', pg.url.endswith('/notificaciones.html'), pg.url)
    ctx.close()
    # sin notificaciones
    reset_state()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page='perfil.html', wait=False); all_logs.append(log)
    pg.wait_for_selector('#bell:not([hidden])', timeout=6000); settle(pg, 500)
    b = bell(pg)
    check('13.10 Sin notificaciones sin leer: no hay globo y la etiqueta dice «ninguna sin leer»', b['n'] == '' and b['label'] == 'Notificaciones: ninguna sin leer' and not b['has'], b)
    ctx.close()
    # cerrar sesión: la campana desaparece y deja de consultar (se prueba sin navegar: el simulador vuelve a inyectar la sesión al cambiar de página)
    be.notify(ANA, 'aviso', 'Para el cierre de sesión')
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', page='perfil.html', clock=True, wait=False); all_logs.append(log)
    eventually(lambda: bell(pg)['n'] == '1', 5)
    pg.evaluate("TP.signOut()")
    check('13.11 Al cerrar sesión la campana desaparece y los botones vuelven a «Iniciar sesión»', eventually(lambda: bell(pg)['hidden'] is True and 'Iniciar sesión' in txt(pg, '#acts'), 5), (bell(pg), txt(pg, '#acts')))
    n0 = len(be.n_log); advance(pg, 130000, 10000)
    check('13.12 ...y deja de consultar notificaciones', not rest_calls('notifications', None, n0), len(rest_calls('notifications', None, n0)))
    ctx.close()

def g14(br):
    print('\n[14] Teléfono (390 px)')
    reset_state()
    for i in range(6): be.notify(ANA, ['vacuna', 'cita', 'mensaje', 'aviso', 'promocion', 'desparasitacion'][i], f'Notificación número {i + 1} con un título bastante largo para probar el ajuste', 'Texto de ayuda de la notificación ' * 3, 'carnet.html', read=(i % 2 == 1), ago_min=i + 1)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx', w=390, h=800); all_logs.append(log)
    pg.wait_for_selector('#bell:not([hidden])', timeout=6000); settle(pg, 400)
    w = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    check('14.1 No hay desplazamiento horizontal en la página', w[0] <= w[1], w)
    small = pg.evaluate("""Array.from(document.querySelectorAll('.nt-card .btn, .nt-card .ck, #bell')).filter(e => e.offsetParent !== null).map(e => [e.id || e.className, Math.round(e.getBoundingClientRect().height)]).filter(x => x[1] < 44)""")
    check('14.2 Botones, casillas y campana miden al menos 44 px de alto', not small, small)
    bb = pg.evaluate("(() => { const r = document.getElementById('bell').getBoundingClientRect(), m = document.getElementById('mbtn').getBoundingClientRect(); return {bell: [r.left, r.right, r.top, r.bottom], mbtn: [m.left, m.right], vw: innerWidth}; })()")
    check('14.3 La campana se ve en la barra (fuera del menú de hamburguesa), junto al botón del menú y dentro de la pantalla',
          bb['bell'][0] >= 0 and bb['bell'][1] <= bb['vw'] - 4 and bb['bell'][1] <= bb['mbtn'][0] + 1 and bb['bell'][3] <= 70, bb)
    bd = pg.evaluate("(() => { const r = document.getElementById('bell-n').getBoundingClientRect(); return [r.left, r.right, r.top, innerWidth]; })()")
    check('14.4 El globo con el número no queda cortado por el borde', bd[0] >= 0 and bd[1] <= bd[3] and bd[2] >= 0, bd)
    gl = pg.evaluate("(() => { const n = document.getElementById('bell-n').getBoundingClientRect(), b = document.getElementById('bell').getBoundingClientRect(), m = document.getElementById('mbtn').getBoundingClientRect(); return {n: [n.left, n.right, n.top, n.bottom], b: [b.left, b.right, b.top, b.bottom], m: [m.left, m.right]}; })()")
    print('      (globo/campana/menú:', gl, ')')
    check('14.4b El globo cuelga de la esquina superior derecha de la campana (no se despega de ella) y no tapa el botón del menú',
          gl['n'][0] >= gl['b'][0] and gl['n'][1] <= gl['b'][1] + 12 and gl['n'][3] <= gl['b'][3] and gl['n'][1] <= gl['m'][0] + 4, gl)
    pg.click('#mbtn'); settle(pg, 150)
    check('14.5 El menú de hamburguesa sigue funcionando junto a la campana', pg.evaluate("document.getElementById('mp').classList.contains('open')") and pg.get_attribute('#mbtn', 'aria-expanded') == 'true')
    pg.click('#mbtn')
    ov = pg.evaluate("Array.from(document.querySelectorAll('.nt-item')).filter(e => e.scrollWidth > e.clientWidth + 1).length")
    check('14.6 Ninguna fila se sale de la pantalla', ov == 0, ov)
    os.makedirs(os.path.join(os.environ.get('TP_SHOTS', '/tmp'), 'notif-shots'), exist_ok=True)
    pg.screenshot(path=os.path.join(os.environ.get('TP_SHOTS', '/tmp'), 'notif-shots', 'movil.png'), full_page=True)
    check('14.7 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # escritorio: la cabecera no se parte en dos líneas con la campana
    for w_ in (1100, 1280):
        ctx, pg, log = open_page(br, 'ana@ejemplo.mx', w=w_, h=800); all_logs.append(log)
        pg.wait_for_selector('#bell:not([hidden])', timeout=6000); settle(pg, 300)
        hh = pg.evaluate("document.querySelector('header.nav').getBoundingClientRect().height")
        check(f'14.8 A {w_} px la cabecera con campana sigue en una sola línea', hh < 80, hh)
        if w_ == 1100: pg.screenshot(path=os.path.join(os.environ.get('TP_SHOTS', '/tmp'), 'notif-shots', 'escritorio.png'), full_page=True)
        ctx.close()

def g15(br):
    print('\n[15] Cuentas distintas y avisos reales del servidor')
    reset_state()
    # aliado
    be.notify(CRIS, 'aviso', 'Aviso para el aliado')
    ctx, pg, log = open_page(br, 'cris@ejemplo.mx'); all_logs.append(log)
    vis = pg.evaluate("Array.from(document.querySelectorAll('.side a')).filter(a => !a.hidden).map(a => a.getAttribute('href'))")
    check('15.1 Un aliado ve sus notificaciones y el menú lateral correcto (sin mascotas/carnet, con panel de aliado)', titles(pg) == ['Aviso para el aliado'] and 'panel-aliado.html' in vis and 'mascota.html' not in vis and 'admin.html' not in vis, (titles(pg), vis))
    ctx.close()
    # aviso de denuncia a todo el equipo (función real)
    be.sql("select private.notify_admins('aviso', 'Nueva denuncia recibida', 'Código TP-ABCD-EFGH · abandono · Jalisco', 'admin.html', 'denuncia-prueba')")
    ctx, pg, log = open_page(br, 'dani@ejemplo.mx'); all_logs.append(log)
    it = nitems(pg)
    check('15.2 El administrador recibe el aviso de denuncia con su botón «Ver» hacia la administración', len(it) == 1 and it[0]['title'] == 'Nueva denuncia recibida' and it[0]['link'] == 'admin.html' and 'TP-ABCD-EFGH' in it[0]['body'], it)
    check('15.3 El menú lateral del administrador incluye «Administración»', pg.evaluate("Array.from(document.querySelectorAll('.side a')).some(a => !a.hidden && a.getAttribute('href') === 'admin.html')"))
    ctx.close()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('15.4 Una persona que no es del equipo no recibe ese aviso', titles(pg) == [], titles(pg))
    # respuesta del equipo en el chat: llega como notificación real
    wait_live(pg); settle(pg, 400)
    cid = be.sql(f"insert into public.conversations (user_id, subject) values ('{ANA}', 'Duda de prueba') returning id")
    be.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{cid}', '{ANA}', 'Hola, tengo una duda')")
    be.staff_reply(cid, U['ADMIN'], 'Con gusto te ayudamos')
    row = json.loads(be.sql(f"select to_jsonb(n) from public.notifications n where user_id = '{ANA}' and type = 'mensaje'"))
    rt.push('notifications', 'INSERT', row)
    waitjs(pg, "document.querySelectorAll('#nt-list > li').length === 1")
    it = nitems(pg)
    check('15.5 La respuesta del equipo en el chat llega como notificación con enlace a «Atención al cliente»', it[0]['title'] == 'Nueva respuesta de atención al cliente' and it[0]['link'] == 'chat.html' and it[0]['badges'][-1] == 'Mensaje', it)
    check('15.6 La notificación solo trae un adelanto de la respuesta (máx. 140 caracteres), propio de esa conversación y de nadie más',
          it[0]['body'] == 'Con gusto te ayudamos' and be.count("type = 'mensaje' and title = 'Nueva respuesta de atención al cliente' and user_id <> '%s'" % ANA) == 0, it)
    long_reply = 'y' * 300
    be.staff_reply(cid, U['ADMIN'], long_reply)
    row2 = json.loads(be.sql(f"select to_jsonb(n) from public.notifications n where user_id = '{ANA}' and type = 'mensaje' order by created_at desc limit 1"))
    check('15.6b Una respuesta larga se recorta a 140 caracteres en la notificación', len(row2['body']) == 140, len(row2['body']))
    check('15.7 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()


# Contraste de texto (WCAG AA: 4.5:1; 3:1 para texto grande) sobre los fondos reales de la paleta. Los controles desactivados están exentos.
AUDIT_JS = r"""
() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(x => parseFloat(x)); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}; };
  const lin = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
  const L = c => 0.2126*lin(c.r)+0.7152*lin(c.g)+0.0722*lin(c.b);
  const over = (f,b) => ({r:f.r*f.a+b.r*(1-f.a), g:f.g*f.a+b.g*(1-f.a), b:f.b*f.a+b.b*(1-f.a), a:1});
  const bgOf = el => { let stack=[]; for (let e=el; e; e=e.parentElement) { const cs=getComputedStyle(e); const c=parse(cs.backgroundColor); if (cs.backgroundImage!=='none') stack.push({img:true}); if (c && c.a>0) { stack.push(c); if (c.a===1) break; } }
    let base={r:255,g:255,b:255,a:1}; for (let i=stack.length-1;i>=0;i--) { if (stack[i].img) continue; base = over(stack[i], base); } return base; };
  const out=[]; const seen=new Set();
  const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const t=w.currentNode; if (!t.textContent.trim()) continue; const el=t.parentElement; if (!el) continue;
    const cs=getComputedStyle(el); if (cs.visibility==='hidden'||cs.display==='none') continue;
    const r=el.getBoundingClientRect(); if (r.width===0||r.height===0) continue;
    if (el.closest('[hidden],script,style,noscript,button:disabled,[aria-disabled="true"]')) continue;
    let fg=parse(cs.color); let bg=bgOf(el); fg=over({...fg,a:fg.a*parseFloat(cs.opacity||1)},bg);
    const l1=L(fg), l2=L(bg); const ratio=(Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    const size=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight)>=700; const large = size>=24 || (size>=18.66 && bold);
    const need = large?3:4.5;
    if (ratio<need) { const k=el.tagName+'.'+el.className+'|'+cs.color+'|'+JSON.stringify(bg); if (!seen.has(k)) { seen.add(k); out.push({tag:el.tagName,cls:el.className,id:el.id,txt:t.textContent.trim().slice(0,40),ratio:Math.round(ratio*100)/100,fg:cs.color,bg:`rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`}); } }
  }
  return out;
}
"""

def g16(br):
    print('\n[16] Contraste de colores (accesibilidad, paleta fija)')
    reset_state()
    tipos = ['vacuna', 'desparasitacion', 'cita', 'mensaje', 'promocion', 'suscripcion', 'aviso']
    for i, t in enumerate(tipos):
        be.notify(ANA, t, f'Notificación de tipo {t}', 'Texto de apoyo de la notificación para medir el contraste.' if i % 2 == 0 else None, 'carnet.html' if i % 3 == 0 else None, read=(i % 2 == 1), ago_min=i + 1)
    for w_, h_, tag in ((1100, 900, 'escritorio'), (390, 900, 'teléfono')):
        ctx, pg, log = open_page(br, 'ana@ejemplo.mx', w=w_, h=h_); all_logs.append(log)
        pg.wait_for_selector('#bell:not([hidden])', timeout=6000); settle(pg, 300)
        bad = pg.evaluate(AUDIT_JS)
        check(f'16.1 ({tag}) Todo el texto de la lista, la campana y la cabecera cumple el contraste AA', not bad, bad[:3])
        pg.click('#nt-delread'); settle(pg, 150)
        bad = pg.evaluate(AUDIT_JS)
        check(f'16.2 ({tag}) El botón en modo «confirmar» también cumple el contraste', not bad and pg.get_attribute('#nt-delread', 'data-confirm') == '1', [bad[:3], pg.get_attribute('#nt-delread', 'data-confirm')])
        ctx.close()
    # estado vacío y mensajes de aviso
    reset_state()
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    bad = pg.evaluate(AUDIT_JS)
    check('16.3 La pantalla vacía cumple el contraste', not bad, bad[:3])
    check('16.4 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # control: la propia comprobación detecta un texto de bajo contraste (si no, 16.1–16.3 no probarían nada)
    be.notify(ANA, 'aviso', 'Título de control', 'Detalle de control', None)
    ctx, pg, log = open_page(br, 'ana@ejemplo.mx'); all_logs.append(log)
    pg.evaluate("document.querySelectorAll('.nt-title, .nt-txt').forEach(e => e.style.setProperty('color', '#c9d3e8', 'important'))")
    bad = pg.evaluate(AUDIT_JS)
    check('16.5 Control: un texto claro sobre fondo claro SÍ es detectado por la comprobación de contraste', len(bad) >= 1, bad[:2])
    ctx.close()

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for n, f in ((1, g1), (2, g2), (3, g3), (4, g4), (5, g5), (6, g6), (7, g7), (8, g8), (9, g9), ('9b', g9b), (10, g10), (11, g11), (12, g12), (13, g13), (14, g14), (15, g15), (16, g16)):
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
