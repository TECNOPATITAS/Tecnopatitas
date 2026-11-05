"""
Pruebas de interfaz de la Etapa 9 (Suscripciones: planes, solicitudes sin pagos, historial y cancelación) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP) y la base de datos:
            planes, suscripciones, solicitudes, RLS, permisos, request_plan / cancel_plan_request / cancel_my_subscription /
            my_entitlements / resolve_plan_request y los avisos de vencimiento (PostgreSQL local con database/00_instalar_todo.sql;
            ver mock_etapa9.py).
  SIMULADO  PostgREST (traduce solo las consultas de Suscripciones a SQL) y Supabase Auth (mock_supabase.py).

Uso:  python3 pruebas-web/probar_planes.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), playwright + chromium.
Variables: TP_PORT (sitio, 8773), TP_PLANES_DB (base, tp_planes), TP_SITE (carpeta del sitio; las «pruebas de las pruebas» usan una copia saboteada),
           TP_ONLY (ejecuta solo un grupo, p. ej. TP_ONLY=5).
"""
import datetime, http.server, json, os, re, socketserver, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa9 import Backend9

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8773)); DB = os.environ.get('TP_PLANES_DB', 'tp_planes')
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


# ------------------------------------------------------------------ estado de la simulación
be = Backend9(KEY, DB)
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
    return ctx
def session_script(email, ttl=None, valid_refresh=True):
    u = be.users[email]; s = be._session(u)
    if ttl is not None: s['expires_at'] = int(time.time()) + ttl
    if not valid_refresh: be.refresh.pop(s['refresh_token'], None)
    sess = dict(access_token=s['access_token'], refresh_token=s['refresh_token'], expires_at=s['expires_at'],
                user=dict(id=u['id'], email=email, email_confirmed_at='2026-11-04T00:00:00Z'))
    return "try{if(!localStorage.getItem('tp-auth-v1'))localStorage.setItem('tp-auth-v1',%s)}catch(e){}" % json.dumps(json.dumps(sess)), sess

MINE_READY = """(() => { const m = document.getElementById('mine'); if (!m) return false; if (m.hidden) return document.querySelectorAll('#pu .card, #pb .card').length === 5;
    const b = document.getElementById('mine-body'); return !!b && !!b.querySelector('.mine-card') && !/Cargando/.test(b.textContent) && !Array.from(document.querySelectorAll('#pu button, #pb button')).some(x => x.textContent === 'Cargando…'); })()"""
def open_planes(br, email, w=1100, h=900, clock=False, ttl=None, valid_refresh=True, ctx=None, wait=True, page='planes.html', query=''):
    ctx = ctx or new_ctx(br, w, h, clock)
    if email:
        scr, sess = session_script(email, ttl, valid_refresh); ctx.add_init_script(scr)
    log = []; pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/{page}{query}')
    if wait: waitjs(pg, MINE_READY if page == 'planes.html' else "document.body.classList.contains('tp-ok')")
    return ctx, pg, log

# ------------------------------------------------------------------ utilidades
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
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
def fecha_es(iso):
    y, m, d = iso[:10].split('-'); return f'{int(d)} {MESES[int(m) - 1]} {y}'
def mx_date_of(ts_sql):
    """Fecha (hora de Ciudad de México) de un instante SQL, escrita como la escribe la interfaz."""
    return fecha_es(be.sql(f"select to_char(({ts_sql}) at time zone 'America/Mexico_City', 'YYYY-MM-DD')"))
def plan_calls(path=None, since=0):
    return [r for r in be.p_log[since:] if path is None or r['path'].endswith(path)]
def bell_calls(since=0):
    return [r for r in be.n_log[since:]]
def bell(pg):
    return pg.evaluate("""(() => { const b = document.getElementById('bell'), n = document.getElementById('bell-n');
        return {hidden: b.hidden, n: n.hidden ? '' : n.textContent, label: b.getAttribute('aria-label')}; })()""")
def cards(pg):
    return pg.evaluate("""Object.fromEntries(Array.from(document.querySelectorAll('[data-plan]')).map(c => [c.dataset.plan, {
        name: c.querySelector('h3').textContent, price: c.querySelector('.price').textContent, pop: !!c.querySelector('.tag.pk') && c.querySelector('.tag.pk').textContent === 'Más popular',
        tags: Array.from(c.querySelectorAll('.tag')).map(t => t.textContent).filter(t => t !== 'Más popular'), small: Array.from(c.querySelectorAll('small')).map(t => t.textContent),
        buttons: Array.from(c.querySelectorAll('button')).map(b => ({text: b.textContent, disabled: b.disabled, aria: b.getAttribute('aria-label'), type: b.type})),
        links: Array.from(c.querySelectorAll('a')).map(a => ({text: a.textContent, href: a.getAttribute('href')})), form: !!c.querySelector('form'),
        benefits: Array.from(c.querySelectorAll('li')).map(l => l.textContent)}]))""")
def mine(pg):
    return pg.evaluate("""(() => { const b = document.getElementById('mine-body'); if (!b) return null;
        const plan = b.querySelector('.mine-plan'); const ps = Array.from(b.querySelectorAll('.mine-card:not(.rq-pend) > p'));
        return {plan: plan ? plan.querySelector('b').textContent : null, planFull: plan ? plan.textContent : null, vig: ps[1] ? ps[1].textContent : null,
          buttons: Array.from(b.querySelectorAll('button')).map(x => ({text: x.textContent, disabled: x.disabled, fx: x.dataset.fx || null})),
          pending: b.querySelector('.rq-pend') ? b.querySelector('.rq-pend').innerText : null,
          confirm: b.querySelector('.rq-confirm') ? b.querySelector('.rq-confirm').innerText : null,
          hist: Array.from(b.querySelectorAll('.rq-item')).map(li => ({name: li.querySelector('.rq-top b').textContent, st: li.querySelector('.rq-st').textContent, cls: li.querySelector('.rq-st').className, status: li.dataset.status, text: li.innerText})),
          text: b.innerText}; })()""")
def say(pg):
    return pg.evaluate("(() => { const m = document.getElementById('mine-msg'); return m && !m.hidden ? {cls: m.className, role: m.getAttribute('role'), text: m.textContent} : null; })()")
def focus_info(pg):
    return pg.evaluate("""(() => { const a = document.activeElement; if (!a) return null; return {id: a.id, fx: a.dataset && a.dataset.fx, tag: a.tagName, name: a.name || null, text: (a.textContent || '').slice(0, 40)}; })()""")
def api(pg, method, path, body=None, prefer=None):
    """Llama al servidor desde la página (con su sesión), como lo haría alguien que manipula la consola del navegador."""
    return pg.evaluate("""async ([m, p, b, pr]) => { try { const r = await TP.rest(p, {method: m, body: b, prefer: pr}); return {ok: true, r}; }
        catch (e) { return {ok: false, status: e.status, code: e.code, msg: e.message}; } }""", [method, path, body, prefer])
def rpc(pg, fn, args=None):
    return pg.evaluate("""async ([f, a]) => { try { const r = await TP.rpc(f, a); return {ok: true, r}; }
        catch (e) { return {ok: false, status: e.status, code: e.code, msg: e.message}; } }""", [fn, args or {}])
def reset_state():
    be.reset_db(); be.rest_log.clear(); be.n_log.clear(); be.p_log.clear(); be.calls.clear(); be.fail_rest = None
def group(n): return not ONLY or ONLY == str(n)
def open_form(pg, plan):
    pg.click(f'[data-plan={plan}] button[data-fx=open-{plan}]'); waitjs(pg, f"!!document.querySelector('[data-plan={plan}] form')")
def submit_form(pg, plan, period=None, note=None, wait=True):
    if period: pg.check(f'[data-plan={plan}] input[value={period}]')
    if note is not None: pg.fill(f'[data-plan={plan}] textarea', note)
    pg.click(f'[data-plan={plan}] button[type=submit]')
    if wait: waitjs(pg, "!document.querySelector('form.rq-form') || (document.getElementById('mine-msg') && !document.getElementById('mine-msg').hidden)")
    settle(pg, 250)
def pending_row(uid): return (be.reqs(uid, 'pending') or [None])[0]

def setup_users():
    prepare_db()
    return dict(ANA=be.add_user('ana@ejemplo.mx', 'ClaveSegura123', name='Ana'),
                BRUNO=be.add_user('bruno@ejemplo.mx', 'ClaveSegura123', name='Bruno'),
                ADMIN=be.add_user('dani@ejemplo.mx', 'ClaveSegura123', name='Dani', admin=True),
                CRIS=be.add_user('cris@ejemplo.mx', 'ClaveSegura123', name='Cris', account_type='business'),
                SUSI=be.add_user('susi@ejemplo.mx', 'ClaveSegura123', name='Susi', suspended=True))

# ================================================================== PRUEBAS
U = setup_users()
ANA, BRUNO, ADMIN, CRIS, SUSI = U['ANA'], U['BRUNO'], U['ADMIN'], U['CRIS'], U['SUSI']
all_logs = []
PLANS_JS = open(os.path.join(ROOT, 'js/plans.js'), encoding='utf-8').read()
PLANES_JS = open(os.path.join(ROOT, 'js/pages/planes.js'), encoding='utf-8').read()

def g1(br):
    print('\n[1] Estructura y seguridad de la página')
    html = open(os.path.join(ROOT, 'planes.html'), encoding='utf-8').read()
    check('1.1 Los scripts cargan en orden: cliente, interfaz, diseño, catálogo y la pantalla con sesión',
          re.search(r'tp-client\.js.*tp-ui\.js.*layout\.js.*plans\.js.*pages/planes\.js', html) is not None)
    check('1.2 La página tiene el panel #mine (oculto de inicio) y la nota #stage-note', re.search(r'id="mine"[^>]*hidden', html) is not None and 'id="stage-note"' in html)
    check('1.3 planes.js no usa innerHTML, eval ni document.write', not re.findall(r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function', PLANES_JS))
    inner = re.findall(r'.*innerHTML.*', PLANS_JS)
    check('1.4 plans.js no usa innerHTML (Etapa 11): las tarjetas de ejemplo de la portada (#plans-mini) y las de planes se arman con elementos de TPUI.el',
          not inner and 'plans-mini' in PLANS_JS and 'replaceChildren' in PLANS_JS and 'TPUI' in PLANS_JS, inner)
    check('1.5 Ningún archivo de la página contiene claves secretas ni service_role', all(not re.search(r'sb_secret_|service_role', t) for t in (html, PLANS_JS, PLANES_JS)))
    check('1.6 El texto de la página aclara que NO hay cobros ni datos de pago', 'no están habilitados' in html and 'no se piden tarjetas ni datos bancarios' in html)
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('1.7 Con sesión la página carga sin errores de consola ni de CSP', not csp_problems(log), csp_problems(log))
    check('1.8 El panel «Tu plan» tiene un h2 con foco programático (tabindex=-1) y una región de avisos', pg.evaluate("(() => { const h = document.getElementById('mine-h'); return h.tagName === 'H2' && h.getAttribute('tabindex') === '-1' && !!document.getElementById('mine-msg'); })()"))
    check('1.9 Las escrituras van SOLO por funciones del servidor (request_plan, cancel_plan_request, cancel_my_subscription): nunca se escribe directo en una tabla',
          all(r['method'] == 'GET' or '/rpc/' in r['path'] for r in plan_calls()), [(r['method'], r['path']) for r in plan_calls()])
    ctx.close()

def g2(br):
    print('\n[2] Visitante sin sesión: la página queda igual que antes y no hace peticiones')
    reset_state()
    ctx, pg, log = open_planes(br, None); all_logs.append(log)
    settle(pg, 500)
    c = cards(pg)
    check('2.1 Se ven las 5 tarjetas: 3 de dueños y 2 de aliados', list(c) == ['basica', 'pro', 'vip', 'plata', 'oro'] and pg.locator('#pu .card').count() == 3 and pg.locator('#pb .card').count() == 2, list(c))
    check('2.2 Los botones son enlaces a registro con el plan elegido (los aliados, con tipo=aliado)',
          [c[k]['links'][0]['href'] for k in c] == ['registro.html?plan=basica', 'registro.html?plan=pro', 'registro.html?plan=vip', 'registro.html?tipo=aliado&plan=plata', 'registro.html?tipo=aliado&plan=oro'],
          [c[k]['links'] for k in c])
    check('2.3 Textos de los botones del catálogo', [c[k]['links'][0]['text'] for k in c] == ['Comenzar gratis', 'Elegir Huellita Pro', 'Elegir Huellita VIP', 'Registrar mi negocio', 'Elegir plan Premium'], [c[k]['links'][0]['text'] for k in c])
    check('2.4 Solo «Huellita Pro» lleva la etiqueta «Más popular»', [k for k in c if c[k]['pop']] == ['pro'], [k for k in c if c[k]['pop']])
    check('2.5 Precios mensuales', [c[k]['price'] for k in c] == ['$0 MXN · gratis', '$29 MXN /mes', '$59 MXN /mes', '$149 MXN /mes', '$299 MXN /mes'], [c[k]['price'] for k in c])
    check('2.6 El panel «Tu plan» está oculto y la nota original sigue intacta',
          pg.evaluate("document.getElementById('mine').hidden") and 'Elegir un plan te llevará al registro' in txt(pg, '#stage-note'), txt(pg, '#stage-note'))
    pg.click('[data-bill=y]'); settle(pg, 100)
    c = cards(pg)
    check('2.7 Al elegir «Anual» cambian los precios y aparece el ahorro frente a 12 pagos mensuales',
          [c[k]['price'] for k in c] == ['$0 MXN · gratis', '$290 MXN /año', '$590 MXN /año', '$1,490 MXN /año', '$2,990 MXN /año'] and 'ahorras $58 MXN' in ' '.join(c['pro']['small']), ([c[k]['price'] for k in c], c['pro']['small']))
    check('2.8 El botón «Anual» queda marcado (aria-pressed) y «Mensual» no', pg.get_attribute('[data-bill=y]', 'aria-pressed') == 'true' and pg.get_attribute('[data-bill=m]', 'aria-pressed') == 'false')
    pg.click('[data-bill=m]'); settle(pg, 100)
    check('2.9 Volver a «Mensual» restaura los precios', cards(pg)['pro']['price'] == '$29 MXN /mes')
    check('2.10 El visitante NO hizo ninguna petición a Supabase (ni campana, ni planes, ni solicitudes)', not be.calls, [(x['method'], x['path']) for x in be.calls])
    check('2.11 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    check('2.12 No aparece «null», «undefined» ni «[object» en las tarjetas', not junk(pg, 'main'), junk(pg, 'main'))
    ctx.close()
    # con una sesión guardada pero vencida e irrecuperable: vuelve a verse como visitante
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', ttl=-100, valid_refresh=False, wait=False); all_logs.append(log)
    waitjs(pg, "document.getElementById('mine').hidden && document.querySelectorAll('[data-plan] a.btn').length === 5")
    c = cards(pg)
    check('2.13 Con la sesión vencida la página se ve como la de un visitante (enlaces de registro, sin panel)',
          pg.evaluate("document.getElementById('mine').hidden") and c['pro']['links'][0]['href'] == 'registro.html?plan=pro' and not any(c[k]['buttons'] for k in c), [pg.evaluate("document.getElementById('mine').hidden"), c['pro']])
    check('2.14 La nota original NO se reemplazó (no hubo sesión válida)', 'Elegir un plan te llevará al registro' in txt(pg, '#stage-note'), txt(pg, '#stage-note'))
    ctx.close()
    # Etapa 11: las tarjetas de ejemplo de la portada ya no se arman con innerHTML sino con TPUI.el: se comprueba que se ven igual
    reset_state()
    ctx = new_ctx(br); log = []; all_logs.append(log); pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/index.html'); waitjs(pg, "document.querySelectorAll('#plans-mini .card').length === 5")
    mini = pg.evaluate("Array.from(document.querySelectorAll('#plans-mini .card')).map(a => ({tag: a.tagName, href: a.getAttribute('href'), h3: a.querySelector('h3').textContent, who: a.querySelector('small').textContent, price: a.querySelector('.price').textContent, kids: a.children.length}))")
    check('2.15 La portada muestra las 5 tarjetas de ejemplo (enlaces a planes.html) con nombre, a quién va dirigido y precio',
          len(mini) == 5 and all(m['tag'] == 'A' and m['href'] == 'planes.html' and m['kids'] == 3 for m in mini)
          and [m['who'] for m in mini] == ['Dueños de mascotas'] * 3 + ['Aliados comerciales'] * 2
          and [m['price'] for m in mini] == ['$0 MXN · gratis', '$29 MXN /mes', '$59 MXN /mes', '$149 MXN /mes', '$299 MXN /mes'] and all(m['h3'].strip() for m in mini), mini)
    check('2.16 Esas tarjetas llevan los mismos nombres que el catálogo de la página de planes', [m['h3'] for m in mini] == [c[k]['name'] for k in c], ([m['h3'] for m in mini], [c[k]['name'] for k in c]))
    check('2.17 La portada carga sin errores de consola ni de CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g3(br):
    print('\n[3] El catálogo de la página coincide con la tabla subscription_plans de la base')
    reset_state()
    ctx, pg, log = open_planes(br, None); all_logs.append(log)
    cat = pg.evaluate("TPPlans.PLANS")
    db = json.loads(be.sql("select coalesce(json_agg(to_jsonb(p) order by sort_order), '[]'::json) from public.subscription_plans p where is_active"))
    check('3.1 Los mismos planes, en el mismo orden', [p['id'] for p in cat] == [p['id'] for p in db], ([p['id'] for p in cat], [p['id'] for p in db]))
    for p in cat:
        d = next((x for x in db if x['id'] == p['id']), None)
        if not d: check(f'3.2 {p["id"]} existe en la base', False); continue
        check(f'3.2 {p["id"]}: nombre, lema, público y precios mensual y anual coinciden',
              (p['n'], p['s'], 'business' if p['g'] else 'owner', p['m'], p['a']) == (d['name'], d['tagline'], d['audience'], d['price_monthly_mxn'], d['price_yearly_mxn']),
              ((p['n'], p['s'], p['g'], p['m'], p['a']), (d['name'], d['tagline'], d['audience'], d['price_monthly_mxn'], d['price_yearly_mxn'])))
        check(f'3.3 {p["id"]}: los beneficios son idénticos y en el mismo orden', p['b'] == d['benefits'], (p['b'], d['benefits']))
    check('3.4 El ahorro anual que muestra la página es el mismo que calcula la base (12 pagos − precio anual)',
          all(p['m'] * 12 - p['a'] == next(x for x in db if x['id'] == p['id'])['yearly_savings_mxn'] for p in cat))
    check('3.5 Los precios del catálogo son enteros no negativos y el plan gratuito es el único con precio 0',
          all(isinstance(p['m'], int) and p['m'] >= 0 and p['a'] >= 0 for p in cat) and [p['id'] for p in cat if p['m'] == 0] == ['basica'])
    ctx.close()

def g4(br):
    print('\n[4] Dueña de mascota sin suscripción: «Tu plan» y botones')
    reset_state()
    n0 = len(be.p_log)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    settle(pg, 400)
    m = mine(pg); c = cards(pg)
    check('4.1 «Tu plan» muestra Huellita Básica con su lema', m['plan'] == 'Huellita Básica' and 'Plan Comunidad' in m['planFull'], m)
    check('4.2 Explica que es gratuito, sin vencimiento, y que el equipo activa los de pago a mano', 'Plan gratuito, sin vencimiento' in m['vig'] and 'el equipo lo activa a mano' in m['vig'], m['vig'])
    check('4.3 Sin suscripción NO hay botón de cancelar suscripción ni historial ni solicitud pendiente', not m['buttons'] and not m['hist'] and m['pending'] is None, m)
    check('4.4 El plan gratuito aparece como «Tu plan actual»', c['basica']['tags'] == ['Tu plan actual'] and not c['basica']['buttons'], c['basica'])
    check('4.5 Pro y VIP ofrecen «Solicitar este plan» (con el nombre del plan en la etiqueta accesible)',
          [b['text'] for b in c['pro']['buttons']] == ['Solicitar este plan'] and c['pro']['buttons'][0]['aria'] == 'Solicitar este plan: Huellita Pro' and c['vip']['buttons'][0]['aria'] == 'Solicitar este plan: Huellita VIP', (c['pro']['buttons'], c['vip']['buttons']))
    check('4.6 Los planes de aliados se muestran sin botón de solicitar, con la explicación «para cuentas de aliado comercial»',
          all(not c[k]['buttons'] and not c[k]['links'] and 'Este plan es para cuentas de aliado comercial.' in c[k]['small'] for k in ('plata', 'oro')), (c['plata'], c['oro']))
    check('4.7 Ya no hay enlaces de registro en ninguna tarjeta (la persona ya tiene cuenta)', all(not c[k]['links'] for k in c))
    check('4.8 La nota superior explica que se puede enviar una solicitud y que no hay cargos ni datos de pago',
          'Puedes enviar una solicitud' in txt(pg, '#stage-note') and 'sin cargos ni datos de pago' in txt(pg, '#stage-note'), txt(pg, '#stage-note'))
    check('4.9 Solo se consultaron «my_entitlements» y «plan_requests» (una vez cada uno)',
          sorted((r['path'].rsplit('/', 1)[1]) for r in plan_calls(since=n0)) == ['my_entitlements', 'plan_requests'], [r['path'] for r in plan_calls(since=n0)])
    rq = [r for r in plan_calls('plan_requests', n0)][0]
    check('4.10 La consulta pide solo las columnas necesarias (nunca resolved_by ni user_id), ordenadas y con tope',
          'select=id,plan_id,billing_period,status,user_note,admin_note,created_at,resolved_at' in rq['query'] and f'user_id=eq.{ANA}' in rq['query'] and 'resolved_by' not in rq['query'] and 'order=created_at.desc' in rq['query'] and 'limit=25' in rq['query'], rq['query'])
    check('4.11 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    check('4.12 No aparece «null», «undefined» ni «[object» en la pantalla', not junk(pg, 'main'), junk(pg, 'main'))
    check('4.13 Cambiar Mensual/Anual NO vuelve a consultar al servidor', (pg.click('[data-bill=y]'), settle(pg, 200), len(plan_calls(since=n0)) == 2)[2], len(plan_calls(since=n0)))
    ctx.close()

def code_of(rid): return rid.replace('-', '')[:8].upper()

def g5(br):
    print('\n[5] Solicitar un plan (sin cobros)')
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro')
    c = cards(pg)
    check('5.1 El formulario aparece solo en la tarjeta de Pro y el foco pasa a su primera opción', c['pro']['form'] and not any(c[k]['form'] for k in c if k != 'pro') and focus_info(pg)['name'] == 'rq-period', (focus_info(pg), {k: c[k]['form'] for k in c}))
    f = pg.evaluate("""(() => { const fm = document.querySelector('[data-plan=pro] form'); return {
        radios: Array.from(fm.querySelectorAll('input[type=radio]')).map(r => ({v: r.value, checked: r.checked, label: r.closest('label').textContent.trim()})),
        legend: fm.querySelector('legend').textContent, ta: {max: fm.querySelector('textarea').maxLength, label: fm.querySelector('label[for]').textContent, id: fm.querySelector('textarea').id},
        note: fm.querySelector('.note').textContent, btns: Array.from(fm.querySelectorAll('button')).map(b => [b.type, b.textContent]), aria: fm.getAttribute('aria-label')}; })()""")
    check('5.2 Periodo mensual elegido por defecto, con precios en los dos periodos', [(r['v'], r['checked'], r['label']) for r in f['radios']] == [('monthly', True, 'Mensual · $29 MXN'), ('yearly', False, 'Anual · $290 MXN')], f['radios'])
    check('5.3 El mensaje es opcional, de 300 caracteres como máximo, con etiqueta', f['ta']['max'] == 300 and 'Mensaje para el equipo (opcional)' in f['ta']['label'], f['ta'])
    check('5.4 El formulario aclara que no genera cargos ni pide tarjeta ni datos bancarios', 'no genera ningún cargo ni te pide tarjeta ni datos bancarios' in f['note'] and 'manualmente' in f['note'], f['note'])
    check('5.5 Botones «Enviar solicitud» (submit) y «Cancelar» (button); el formulario tiene nombre accesible', f['btns'] == [['submit', 'Enviar solicitud'], ['button', 'Cancelar']] and f['aria'] == 'Solicitar Huellita Pro', (f['btns'], f['aria']))
    check('5.6 Las demás tarjetas siguen ofreciendo «Solicitar este plan»', [b['text'] for b in cards(pg)['vip']['buttons']] == ['Solicitar este plan'])
    n0 = len(be.p_log)
    pg.click('[data-plan=pro] button[type=button]'); settle(pg, 150)
    fi = focus_info(pg)
    check('5.7 «Cancelar» cierra el formulario, devuelve el foco al botón de Pro y no llama al servidor', not cards(pg)['pro']['form'] and fi['fx'] == 'open-pro' and len(be.p_log) == n0, (fi, len(be.p_log) - n0))
    # el selector Mensual/Anual de arriba y el formulario abierto
    pg.click('[data-bill=y]'); settle(pg, 100); open_form(pg, 'pro')
    check('5.8 Con «Anual» elegido arriba, el formulario abre con el periodo anual preseleccionado', pg.is_checked('[data-plan=pro] input[value=yearly]'))
    pg.check('[data-plan=pro] input[value=monthly]'); pg.fill('[data-plan=pro] textarea', 'Tengo 2 perros y un gato')
    pg.click('[data-bill=m]'); settle(pg, 150)
    check('5.9 Cambiar el selector de arriba NO borra el formulario abierto ni lo que escribiste ni el periodo elegido',
          cards(pg)['pro']['form'] and pg.input_value('[data-plan=pro] textarea') == 'Tengo 2 perros y un gato' and pg.is_checked('[data-plan=pro] input[value=monthly]'), pg.input_value('[data-plan=pro] textarea'))
    pg.check('[data-plan=pro] input[value=yearly]')
    n0 = len(be.p_log)
    submit_form(pg, 'pro')
    rp = plan_calls('request_plan', n0)
    check('5.10 Se envió UNA sola llamada a request_plan con plan, periodo y mensaje exactos', len(rp) == 1 and rp[0]['body'] == {'p_plan': 'pro', 'p_period': 'yearly', 'p_note': 'Tengo 2 perros y un gato'}, [r['body'] for r in rp])
    row = pending_row(ANA)
    check('5.11 La base tiene UNA solicitud pendiente de Ana: Pro, anual, con su mensaje', row and (row['plan_id'], row['billing_period'], row['user_note'], row['status']) == ('pro', 'yearly', 'Tengo 2 perros y un gato', 'pending') and len(be.reqs(ANA)) == 1, be.reqs(ANA))
    s = say(pg)
    check('5.12 Aviso de éxito (role=status) con el código de la solicitud y la aclaración de que no hubo cargo', s and s['cls'] == 'msg ok' and s['role'] == 'status' and code_of(row['id']) in s['text'] and 'No se hizo ningún cargo' in s['text'] and 'Notificaciones' in s['text'], s)
    m = mine(pg)
    check('5.13 Aparece «Solicitud en revisión» con plan, periodo, código y tu mensaje, y el botón para cancelarla',
          m['pending'] and all(x in m['pending'] for x in ('Solicitud en revisión', 'Huellita Pro', 'anual', code_of(row['id']), 'Tu mensaje: Tengo 2 perros y un gato', 'Cancelar solicitud', 'No genera ningún cargo')), m['pending'])
    c = cards(pg)
    check('5.14 Pro queda como «Solicitud en revisión»; VIP muestra un botón desactivado; ya no hay formularios',
          c['pro']['tags'] == ['Solicitud en revisión'] and not c['pro']['buttons'] and c['vip']['buttons'] == [{'text': 'Hay una solicitud en revisión', 'disabled': True, 'aria': None, 'type': 'button'}] and not any(c[k]['form'] for k in c), (c['pro'], c['vip']))
    check('5.15 El foco queda en el título «Tu plan» (donde se anuncia el resultado)', focus_info(pg)['id'] == 'mine-h', focus_info(pg))
    check('5.16 La campana sube a 1 (aviso «Recibimos tu solicitud»)', eventually(lambda: bell(pg)['n'] == '1'), bell(pg))
    ntf = json.loads(be.sql(f"select coalesce(json_agg(to_jsonb(n)), '[]'::json) from public.notifications n where user_id = '{ANA}'"))
    check('5.17 Aviso para Ana: «Recibimos tu solicitud: Huellita Pro», sin cargos, con enlace a planes.html',
          len(ntf) == 1 and ntf[0]['title'] == 'Recibimos tu solicitud: Huellita Pro' and 'ningún cargo' in ntf[0]['body'] and ntf[0]['link'] == 'planes.html' and ntf[0]['type'] == 'suscripcion', ntf)
    adm = json.loads(be.sql(f"select coalesce(json_agg(to_jsonb(n)), '[]'::json) from public.notifications n where user_id = '{ADMIN}'"))
    check('5.18 El equipo recibe «Nueva solicitud de plan» con el código y SIN el correo ni el mensaje de la persona',
          len(adm) == 1 and adm[0]['title'] == 'Nueva solicitud de plan' and code_of(row['id']) in adm[0]['body'] and 'ana@' not in adm[0]['body'] and 'Tengo 2 perros' not in adm[0]['body'], adm)
    pg.reload(); waitjs(pg, MINE_READY)
    check('5.19 Al recargar la página la solicitud sigue en revisión', mine(pg)['pending'] is not None and cards(pg)['pro']['tags'] == ['Solicitud en revisión'])
    check('5.20 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()
    # sin mensaje
    reset_state()
    ctx, pg, log = open_planes(br, 'bruno@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'vip'); n0 = len(be.p_log)
    submit_form(pg, 'vip', note='   ')
    rp = plan_calls('request_plan', n0)
    row = pending_row(BRUNO)
    check('5.21 Sin mensaje (o solo espacios) se envía p_note = null y no se guarda texto vacío', len(rp) == 1 and rp[0]['body'] == {'p_plan': 'vip', 'p_period': 'monthly', 'p_note': None} and row and row['user_note'] is None, ([r['body'] for r in rp], row))
    check('5.22 La tarjeta de revisión no muestra «Tu mensaje» cuando no hay mensaje', mine(pg)['pending'] and 'Tu mensaje' not in mine(pg)['pending'], mine(pg)['pending'])
    ctx.close()
    # mensaje con saltos de línea
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro'); submit_form(pg, 'pro', note='línea uno\nlínea dos')
    check('5.23 Los saltos de línea del mensaje se conservan al mostrarlo', 'línea uno\nlínea dos' in (mine(pg)['pending'] or '').replace('\r', ''), mine(pg)['pending'])
    ctx.close()
    # preferencia «suscripción» apagada: la solicitud se registra pero no se crea aviso para la persona
    reset_state(); be.set_prefs(ANA, suscripcion=False)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro'); submit_form(pg, 'pro')
    check('5.24 Con las notificaciones de suscripción apagadas la solicitud se registra igual, sin aviso para la persona',
          pending_row(ANA) is not None and be.count(f"user_id = '{ANA}'") == 0 and be.count(f"user_id = '{ADMIN}'") == 1, (be.count(f"user_id = '{ANA}'"), be.count(f"user_id = '{ADMIN}'")))
    be.set_prefs(ANA, suscripcion=True)
    ctx.close()

def g6(br):
    print('\n[6] Cancelar una solicitud en revisión')
    reset_state()
    rid = be.make_request(ANA, 'pro', 'monthly', 'Quiero Pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    n0 = len(be.p_log)
    pg.click('button[data-fx=cancel-req]'); waitjs(pg, "!document.querySelector('.rq-pend')"); settle(pg, 200)
    cr = plan_calls('cancel_plan_request', n0)
    check('6.1 Se llamó UNA vez a cancel_plan_request con el identificador exacto', len(cr) == 1 and cr[0]['body'] == {'p_request': rid}, [r['body'] for r in cr])
    row = be.reqs(ANA)[0]
    check('6.2 La solicitud queda «cancelled» con fecha de resolución, y no se creó ninguna suscripción', row['status'] == 'cancelled' and row['resolved_at'] and be.sub(ANA) is None, row)
    m = mine(pg); s = say(pg)
    check('6.3 Desaparece la tarjeta de revisión y el historial muestra «Cancelada por ti»', m['pending'] is None and len(m['hist']) == 1 and m['hist'][0]['st'] == 'Cancelada por ti' and m['hist'][0]['name'] == 'Huellita Pro' and 'off' in m['hist'][0]['cls'].split(), m)
    check('6.4 Aviso de éxito y foco en el título', s and s['cls'] == 'msg ok' and 'Solicitud cancelada' in s['text'] and focus_info(pg)['id'] == 'mine-h', (s, focus_info(pg)))
    check('6.5 Los planes de pago vuelven a ofrecer «Solicitar este plan»', all([b['text'] for b in cards(pg)[k]['buttons']] == ['Solicitar este plan'] for k in ('pro', 'vip')))
    open_form(pg, 'vip')
    check('6.5b Al abrir un formulario se borra el aviso anterior', say(pg) is None, say(pg))
    submit_form(pg, 'vip', 'yearly')
    check('6.6 Después de cancelar se puede hacer otra solicitud (queda 1 cancelada y 1 pendiente)', [r['status'] for r in be.reqs(ANA)] == ['cancelled', 'pending'] and be.reqs(ANA)[1]['plan_id'] == 'vip', be.reqs(ANA))
    ctx.close()
    # doble clic
    reset_state()
    rid = be.make_request(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log); n0 = len(be.p_log)
    pg.dblclick('button[data-fx=cancel-req]'); settle(pg, 500)
    check('6.7 Doble clic en «Cancelar solicitud»: una sola llamada al servidor', len(plan_calls('cancel_plan_request', n0)) == 1, len(plan_calls('cancel_plan_request', n0)))
    ctx.close()
    # carrera: el equipo la aprobó mientras la página estaba abierta
    reset_state()
    rid = be.make_request(ANA, 'pro', note='Hola')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    be.resolve(rid, True, 'Aprobada a tiempo')
    pg.click('button[data-fx=cancel-req]'); waitjs(pg, "!document.querySelector('.rq-pend')"); settle(pg, 250)
    s = say(pg); m = mine(pg)
    check('6.8 Si el equipo ya la había resuelto, el servidor lo dice (no se cancela nada) y la pantalla se actualiza sola',
          s and s['cls'] == 'msg err' and 'No encontramos una solicitud pendiente tuya' in s['text'] and be.reqs(ANA)[0]['status'] == 'approved' and m['plan'] == 'Huellita Pro' and m['hist'] and m['hist'][0]['st'] == 'Aprobada', (s, m['plan'], m['hist']))
    check('6.9 El aviso de error usa role=alert', s and s['role'] == 'alert', s)
    ctx.close()
    # no se puede cancelar la solicitud de otra persona
    reset_state()
    rb = be.make_request(BRUNO, 'vip'); ra = be.make_request(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    r = rpc(pg, 'cancel_plan_request', {'p_request': rb})
    check('6.10 Ana no puede cancelar la solicitud de Bruno: el servidor la rechaza y sigue pendiente', not r['ok'] and 'No encontramos una solicitud pendiente tuya' in r['msg'] and be.reqs(BRUNO)[0]['status'] == 'pending', r)
    ctx.close()
    # con historial: se cancela exactamente la solicitud en revisión (no otra del historial)
    reset_state()
    h1 = be.make_request(ANA, 'pro', 'monthly', 'Vieja', status='rejected', admin_note='Ahora no', ago_min=3000)
    h2 = be.make_request(ANA, 'vip', 'yearly', None, status='cancelled', ago_min=2000)
    rp = be.make_request(ANA, 'pro', 'yearly', 'La actual', ago_min=5)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log); n0 = len(be.p_log)
    pg.click('button[data-fx=cancel-req]'); waitjs(pg, "!document.querySelector('.rq-pend')"); settle(pg, 250)
    cr = plan_calls('cancel_plan_request', n0); rows = be.reqs(ANA)
    check('6.11 Con historial: se cancela exactamente la solicitud en revisión y las demás quedan igual',
          len(cr) == 1 and cr[0]['body'] == {'p_request': rp} and [r['id'] for r in rows] == [h1, h2, rp] and [r['status'] for r in rows] == ['rejected', 'cancelled', 'cancelled'] and rows[0]['admin_note'] == 'Ahora no',
          ([r['body'] for r in cr], [(r['id'][:4], r['status']) for r in rows]))
    ctx.close()

def g7(br):
    print('\n[7] Respuesta del equipo: aprobada o rechazada')
    reset_state()
    rid = be.make_request(ANA, 'pro', 'monthly', 'Tengo 2 perros')
    be.resolve(rid, True, 'Bienvenida a Huellita Pro')
    ends = be.sql(f"select ends_at from public.subscriptions where user_id = '{ANA}' and status = 'active'")
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    exp = mx_date_of(f"'{ends}'::timestamptz")
    check('7.1 «Tu plan» muestra Huellita Pro con su lema y la fecha de vigencia (hora de México)', m['plan'] == 'Huellita Pro' and 'Plan Cuidadores' in m['planFull'] and m['vig'] == f'Vigente hasta el {exp}.', (m['planFull'], m['vig'], exp))
    check('7.2 Aún no aparece «te quedan N días» (faltan más de 15)', 'te quedan' not in m['vig'], m['vig'])
    h = m['hist']
    check('7.3 El historial muestra «Aprobada» con la respuesta del equipo, fecha de respuesta y código',
          len(h) == 1 and h[0]['st'] == 'Aprobada' and h[0]['status'] == 'approved' and 'ok' in h[0]['cls'].split() and 'Respuesta del equipo: Bienvenida a Huellita Pro' in h[0]['text'] and 'respondida el' in h[0]['text'] and code_of(rid) in h[0]['text'] and 'Tu mensaje: Tengo 2 perros' in h[0]['text'], h)
    check('7.4 En las tarjetas, Pro es «Tu plan actual» con su vigencia; Básica pasa a «Plan gratuito»; VIP se puede solicitar',
          c['pro']['tags'] == ['Tu plan actual'] and f'Vigente hasta el {exp}' in c['pro']['small'] and c['basica']['tags'] == ['Plan gratuito'] and [b['text'] for b in c['vip']['buttons']] == ['Solicitar este plan'], (c['pro'], c['basica'], c['vip']))
    check('7.5 Aparece el botón «Cancelar mi suscripción» y no hay solicitud en revisión', [b['text'] for b in m['buttons']] == ['Cancelar mi suscripción'] and m['pending'] is None, m['buttons'])
    nt = json.loads(be.sql(f"select coalesce(json_agg(title order by created_at), '[]'::json) from public.notifications where user_id = '{ANA}'"))
    check('7.6 El servidor avisó a Ana de la aprobación y la campana lo cuenta', 'Tu suscripción cambió' in nt and eventually(lambda: bell(pg)['n'] != ''), (nt, bell(pg)))
    check('7.7 Sin «null», «undefined» ni «Invalid Date» en la pantalla', not junk(pg, 'main'), junk(pg, 'main'))
    ctx.close()
    # rechazada
    reset_state()
    rid = be.make_request(BRUNO, 'vip', 'yearly', None)
    be.resolve(rid, False, 'Por ahora no podemos activarlo; escríbenos por el chat')
    ctx, pg, log = open_planes(br, 'bruno@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    h = m['hist']
    check('7.8 Rechazada: sigue con Huellita Básica, historial «Rechazada» (estilo de error) con la nota del equipo',
          m['plan'] == 'Huellita Básica' and len(h) == 1 and h[0]['st'] == 'Rechazada' and 'no' in h[0]['cls'].split() and 'Respuesta del equipo: Por ahora no podemos activarlo' in h[0]['text'], (m['plan'], h))
    check('7.9 Después de un rechazo se puede volver a solicitar', [b['text'] for b in c['vip']['buttons']] == ['Solicitar este plan'] and m['pending'] is None)
    check('7.10 Sin suscripción no hay botón de cancelar suscripción', not m['buttons'], m['buttons'])
    ctx.close()
    # anual y sin vencimiento
    reset_state()
    rid = be.make_request(ANA, 'vip', 'yearly'); be.resolve(rid, True)
    ends = be.sql(f"select ends_at from public.subscriptions where user_id = '{ANA}' and status = 'active'")
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    days = int(be.sql(f"select extract(day from ends_at - now())::int from public.subscriptions where user_id = '{ANA}' and status = 'active'"))
    check('7.11 Aprobada anual: vigencia de un año', m['vig'] == f"Vigente hasta el {mx_date_of(chr(39) + ends + chr(39) + '::timestamptz')}." and days in range(363, 367), (m['vig'], ends, days))
    check('7.12 Aprobada sin nota: el historial no muestra «Respuesta del equipo»', 'Respuesta del equipo' not in m['hist'][0]['text'], m['hist'])
    ctx.close()
    reset_state(); be.assign(ANA, 'pro', days=0)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    check('7.13 Sin fecha de vencimiento: lo dice y la tarjeta es «Tu plan actual» sin renovación', m['vig'] == 'Sin fecha de vencimiento definida.' and c['pro']['tags'] == ['Tu plan actual'] and not c['pro']['buttons'] and not any(x.startswith('Vigente') for x in c['pro']['small']), (m['vig'], c['pro']))
    ctx.close()
    # el historial muestra los estados y el orden de más reciente a más antiguo
    reset_state()
    be.make_request(ANA, 'pro', status='cancelled', ago_min=40); be.make_request(ANA, 'vip', status='rejected', admin_note='No', ago_min=30)
    be.make_request(ANA, 'pro', status='approved', admin_note='Sí', ago_min=20); be.make_request(ANA, 'vip', ago_min=5)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    check('7.14 El historial va de la más reciente a la más antigua, sin incluir la que está en revisión', [(x['name'], x['st']) for x in m['hist']] == [('Huellita Pro', 'Aprobada'), ('Huellita VIP', 'Rechazada'), ('Huellita Pro', 'Cancelada por ti')] and m['pending'] and 'Huellita VIP' in m['pending'], (m['hist'], m['pending']))
    ctx.close()
    # solo se muestran las solicitudes de ESTA persona, también para el equipo (RLS le permite leerlas todas)
    reset_state()
    be.make_request(BRUNO, 'vip', note='De Bruno'); be.make_request(ANA, 'pro', note='De Ana'); be.make_request(ADMIN, 'pro', status='rejected', admin_note='x', ago_min=10)
    ctx, pg, log = open_planes(br, 'dani@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    check('7.15 Una cuenta del equipo ve SOLO sus propias solicitudes (aunque la base le permita leer todas)', m['pending'] is None and len(m['hist']) == 1 and 'De Bruno' not in m['text'] and 'De Ana' not in m['text'], m['text'])
    rq = [r for r in plan_calls('plan_requests')][0]
    check('7.16 La consulta lleva el filtro user_id=eq.<su id>', f'user_id=eq.{ADMIN}' in rq['query'], rq['query'])
    ctx.close()
    reset_state()
    be.make_request(BRUNO, 'vip', note='De Bruno'); be.make_request(ANA, 'pro', note='De Ana')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    check('7.17 Ana solo ve su solicitud, no la de Bruno', m['pending'] and 'De Ana' in m['pending'] and 'Bruno' not in m['text'] and 'VIP' not in m['pending'], m['pending'])
    ctx.close()
    # la fecha se escribe en horario de Ciudad de México aunque el instante caiga ya en el día siguiente en UTC
    reset_state(); be.assign(ANA, 'pro', ends_sql="timestamptz '2026-12-04 23:30:00-06'", starts_ago_days=5)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    check('7.18 Un vencimiento el 4 dic a las 23:30 (México) se muestra como «4 dic 2026», no como el 5 (día en UTC)', m['vig'].startswith('Vigente hasta el 4 dic 2026') and '4 dic 2026' in ' '.join(cards(pg)['pro']['small']), (m['vig'], cards(pg)['pro']['small']))
    ctx.close()

def g8(br):
    print('\n[8] Vigencia y renovación')
    reset_state(); be.assign(ANA, 'pro', days=10)
    sid = be.sub(ANA)['id']; before = be.sub(ANA)['ends_at']
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    check('8.1 Faltan 10 días: lo dice y anuncia que ya se puede pedir la renovación', 'te quedan 10 días: ya puedes solicitar la renovación.' in m['vig'], m['vig'])
    check('8.2 La tarjeta de Pro ofrece «Solicitar renovación» (no «Tu plan actual»)', [b['text'] for b in c['pro']['buttons']] == ['Solicitar renovación'] and c['pro']['buttons'][0]['aria'] == 'Solicitar renovación: Huellita Pro' and not c['pro']['tags'], c['pro'])
    open_form(pg, 'pro'); submit_form(pg, 'pro', 'monthly', 'Renuevo')
    row = pending_row(ANA)
    check('8.3 La renovación se registra como una solicitud pendiente del mismo plan', row and row['plan_id'] == 'pro' and cards(pg)['pro']['tags'] == ['Solicitud en revisión'], row)
    be.resolve(row['id'], True, 'Renovada')
    after = be.sub(ANA)
    act = int(be.sql(f"select count(*) from public.subscriptions where user_id = '{ANA}' and status = 'active'"))
    ev = be.sql(f"select string_agg(event, ',' order by id) from public.subscription_events where user_id = '{ANA}'")
    check('8.4 Aprobar la renovación EXTIENDE la misma suscripción (no crea otra) y deja el registro «renewed»', after['id'] == sid and after['ends_at'] > before and act == 1 and ev.endswith('renewed'), (after['id'] == sid, act, ev))
    pg.reload(); waitjs(pg, MINE_READY)
    m = mine(pg)
    check('8.5 Tras renovar, la pantalla muestra la nueva fecha y ya no pide renovar', 'te quedan' not in m['vig'] and cards(pg)['pro']['tags'] == ['Tu plan actual'] and m['hist'][0]['st'] == 'Aprobada', (m['vig'], cards(pg)['pro']['tags']))
    ctx.close()
    # 16 días: aún no se puede
    reset_state(); be.assign(ANA, 'pro', days=16)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    check('8.6 Faltando 16 días NO se ofrece renovar: «Tu plan actual» con su vigencia', 'te quedan' not in m['vig'] and c['pro']['tags'] == ['Tu plan actual'] and not c['pro']['buttons'], (m['vig'], c['pro']))
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'monthly'})
    check('8.7 Si alguien lo fuerza desde la consola, el SERVIDOR lo rechaza con su explicación y no crea nada', not r['ok'] and 'Ya tienes ese plan vigente' in r['msg'] and 'Podrás pedir la renovación cuando falten 15 días o menos' in r['msg'] and not be.reqs(ANA), r)
    ctx.close()
    # 14 y 1 día
    for d, exp_txt in ((14, 'te quedan 14 días: ya puedes solicitar la renovación.'), (1, 'te quedan 1 día: ya puedes solicitar la renovación.')):
        reset_state(); be.assign(ANA, 'pro', days=d)
        ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
        check(f'8.8 Faltando {d} día(s) se ofrece renovar y el texto concuerda en singular/plural', exp_txt in mine(pg)['vig'] and cards(pg)['pro']['buttons'][0]['text'] == 'Solicitar renovación', mine(pg)['vig'])
        ctx.close()
    # cambiar a otro plan estando en Pro
    reset_state(); be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    check('8.9 Con Pro vigente se puede pedir VIP (cambio de plan) y Básica no ofrece botones', [b['text'] for b in cards(pg)['vip']['buttons']] == ['Solicitar este plan'] and not cards(pg)['basica']['buttons'])
    open_form(pg, 'vip'); submit_form(pg, 'vip')
    row = pending_row(ANA)
    be.resolve(row['id'], True)
    st = be.sql(f"select string_agg(plan_id || ':' || status, ',' order by created_at, id) from public.subscriptions where user_id = '{ANA}'")
    check('8.10 Aprobar el cambio reemplaza la suscripción anterior por VIP (una sola activa)', st == 'pro:replaced,vip:active', st)
    pg.reload(); waitjs(pg, MINE_READY)
    check('8.11 La pantalla muestra Huellita VIP y permite solicitar Pro de nuevo', mine(pg)['plan'] == 'Huellita VIP' and cards(pg)['vip']['tags'] == ['Tu plan actual'] and cards(pg)['pro']['buttons'][0]['text'] == 'Solicitar este plan')
    ctx.close()
    # plan vencido
    reset_state(); be.assign(ANA, 'pro', ends_sql="now() - interval '2 days'", starts_ago_days=33)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    m = mine(pg)
    check('8.12 Con el plan vencido la pantalla vuelve a Huellita Básica y se puede solicitar Pro', m['plan'] == 'Huellita Básica' and cards(pg)['pro']['buttons'][0]['text'] == 'Solicitar este plan' and not m['buttons'], (m['plan'], m['buttons']))
    ctx.close()

def g9(br):
    print('\n[9] Cancelar la suscripción (dos pasos)')
    reset_state(); be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    n0 = len(be.p_log)
    pg.click('button[data-fx=cancel-ask]'); waitjs(pg, "!!document.querySelector('.rq-confirm')")
    m = mine(pg)
    check('9.1 El primer clic NO cancela: pide confirmación y explica que se pierden los beneficios de inmediato y que no hubo cobros',
          m['confirm'] and '¿Cancelar tu suscripción a Huellita Pro?' in m['confirm'] and 'Perderás sus beneficios de inmediato' in m['confirm'] and 'nada que reembolsar' in m['confirm'] and not plan_calls('cancel_my_subscription', n0) and be.sub(ANA), m['confirm'])
    check('9.2 El foco pasa al botón «Sí, cancelar mi suscripción»', focus_info(pg)['fx'] == 'cancel-yes', focus_info(pg))
    pg.click('.rq-confirm button.ghost'); settle(pg, 150)
    check('9.3 «No, conservarla» cierra la confirmación, devuelve el foco y no llama al servidor', mine(pg)['confirm'] is None and focus_info(pg)['fx'] == 'cancel-ask' and not plan_calls('cancel_my_subscription', n0) and be.sub(ANA), focus_info(pg))
    pg.click('button[data-fx=cancel-ask]'); pg.click('button[data-fx=cancel-yes]'); waitjs(pg, "!document.querySelector('.rq-confirm') && !document.querySelector('button[data-fx=cancel-ask]')"); settle(pg, 250)
    check('9.4 Al confirmar: UNA llamada a cancel_my_subscription; la suscripción queda cancelada', len(plan_calls('cancel_my_subscription', n0)) == 1 and be.sub(ANA) is None and be.sub(ANA, 'cancelled') is not None)
    m = mine(pg); s = say(pg); c = cards(pg)
    check('9.5 La pantalla vuelve a Huellita Básica, sin botón de cancelar, con aviso de éxito y foco en el título',
          m['plan'] == 'Huellita Básica' and not m['buttons'] and s and s['cls'] == 'msg ok' and 'Suscripción cancelada' in s['text'] and 'nada que reembolsar' in s['text'] and focus_info(pg)['id'] == 'mine-h', (m['plan'], m['buttons'], s))
    check('9.6 Las tarjetas se actualizan: Pro se puede solicitar y Básica es «Tu plan actual»', c['pro']['buttons'][0]['text'] == 'Solicitar este plan' and c['basica']['tags'] == ['Tu plan actual'], (c['pro'], c['basica']))
    ctx.close()
    # doble clic en «Sí»
    reset_state(); be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log); n0 = len(be.p_log)
    pg.click('button[data-fx=cancel-ask]'); pg.dblclick('button[data-fx=cancel-yes]'); settle(pg, 500)
    check('9.7 Doble clic en «Sí, cancelar»: una sola llamada al servidor', len(plan_calls('cancel_my_subscription', n0)) == 1, len(plan_calls('cancel_my_subscription', n0)))
    ctx.close()
    # ya estaba cancelada desde otra pestaña
    reset_state(); be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    be.sql(f"update public.subscriptions set status = 'cancelled', cancelled_at = now() where user_id = '{ANA}'")
    pg.click('button[data-fx=cancel-ask]'); pg.click('button[data-fx=cancel-yes]'); waitjs(pg, "!document.querySelector('button[data-fx=cancel-ask]')"); settle(pg, 250)
    s = say(pg)
    check('9.8 Si ya estaba cancelada, el servidor lo explica y la pantalla se actualiza sola', s and s['cls'] == 'msg err' and 'No tienes una suscripción activa' in s['text'] and mine(pg)['plan'] == 'Huellita Básica', (s, mine(pg)['plan']))
    ctx.close()
    # cancelar la suscripción NO toca una solicitud en revisión
    reset_state(); be.assign(ANA, 'pro'); rid = be.make_request(ANA, 'vip')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    pg.click('button[data-fx=cancel-ask]'); pg.click('button[data-fx=cancel-yes]'); waitjs(pg, "!document.querySelector('button[data-fx=cancel-ask]')"); settle(pg, 250)
    check('9.9 La solicitud pendiente sigue en revisión después de cancelar la suscripción', be.reqs(ANA, 'pending') and mine(pg)['pending'] is not None and 'Huellita VIP' in mine(pg)['pending'])
    ctx.close()
    # con una solicitud en revisión, el plan vigente sigue marcado como «Tu plan actual»
    reset_state(); be.assign(ANA, 'pro'); be.make_request(ANA, 'vip')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    c = cards(pg)
    check('9.10 Con Pro vigente y una solicitud de VIP en revisión: Pro sigue como «Tu plan actual» y VIP como «Solicitud en revisión»', c['pro']['tags'] == ['Tu plan actual'] and c['vip']['tags'] == ['Solicitud en revisión'] and not c['pro']['buttons'], (c['pro']['tags'], c['vip']['tags']))
    ctx.close()

def g10(br):
    print('\n[10] Cuenta de aliado comercial')
    reset_state()
    ctx, pg, log = open_planes(br, 'cris@ejemplo.mx'); all_logs.append(log)
    m = mine(pg); c = cards(pg)
    check('10.1 Un aliado sin plan ve «Sin plan» y la invitación a pedir el que le interese', m['plan'] == 'Sin plan' and 'Todavía no tienes un plan de aliado' in m['vig'], (m['plan'], m['vig']))
    check('10.2 Los planes de aliado se pueden solicitar; los de dueños muestran que no corresponden',
          all([b['text'] for b in c[k]['buttons']] == ['Solicitar este plan'] for k in ('plata', 'oro')) and all('Este plan es para cuentas de dueño de mascota.' in c[k]['small'] and not c[k]['buttons'] for k in ('basica', 'pro', 'vip')), {k: (c[k]['buttons'], c[k]['small'][-1]) for k in c})
    open_form(pg, 'plata'); submit_form(pg, 'plata', 'yearly', 'Tengo una veterinaria')
    row = pending_row(CRIS)
    check('10.3 Solicitar Plata anual: queda pendiente y el aviso al equipo dice «cuenta de aliado» sin datos personales',
          row and (row['plan_id'], row['billing_period']) == ('plata', 'yearly') and be.count(f"user_id = '{ADMIN}' and body like '%cuenta de aliado%' and body not like '%cris@%'") == 1, (row, be.count(f"user_id = '{ADMIN}'")))
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'monthly'})
    check('10.4 Un aliado no puede pedir un plan de dueños (el servidor lo rechaza aunque se fuerce desde la consola)', not r['ok'] and 'no corresponde a tu tipo de cuenta' in r['msg'], r)
    be.resolve(row['id'], True, 'Listo')
    pg.reload(); waitjs(pg, MINE_READY)
    m = mine(pg)
    check('10.5 Aprobada: «Huellita de Plata» con su vigencia, y el botón de cancelar', m['plan'] == 'Huellita de Plata' and m['vig'].startswith('Vigente hasta el') and [b['text'] for b in m['buttons']] == ['Cancelar mi suscripción'], (m['plan'], m['vig'], m['buttons']))
    check('10.6 Plata es «Tu plan actual» y Oro se puede solicitar (mejora de plan)', cards(pg)['plata']['tags'] == ['Tu plan actual'] and [b['text'] for b in cards(pg)['oro']['buttons']] == ['Solicitar este plan'])
    ctx.close()
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    r = rpc(pg, 'request_plan', {'p_plan': 'plata', 'p_period': 'monthly'})
    check('10.7 Una dueña de mascota no puede pedir un plan de aliado', not r['ok'] and 'no corresponde a tu tipo de cuenta' in r['msg'] and not be.reqs(ANA), r)
    r = rpc(pg, 'request_plan', {'p_plan': 'basica', 'p_period': 'monthly'})
    check('10.8 Tampoco se puede «solicitar» el plan gratuito (no hace falta)', not r['ok'] and 'es gratuita' in r['msg'] and not be.reqs(ANA), r)
    r = rpc(pg, 'request_plan', {'p_plan': 'no-existe', 'p_period': 'monthly'})
    check('10.9 Un plan inexistente se rechaza', not r['ok'] and not be.reqs(ANA), r)
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'semanal'})
    check('10.10 Un periodo inventado se rechaza', not r['ok'] and not be.reqs(ANA), r)
    ctx.close()
    # avisos de vencimiento también para aliados (la cabecera pide generar los avisos una vez al día)
    reset_state(); be.assign(CRIS, 'plata', days=3)
    n0 = len(be.n_log)
    ctx, pg, log = open_planes(br, 'cris@ejemplo.mx'); all_logs.append(log)
    eventually(lambda: bell(pg)['n'] == '1')
    nt = json.loads(be.sql(f"select coalesce(json_agg(to_jsonb(n)), '[]'::json) from public.notifications n where user_id = '{CRIS}'"))
    check('10.11 Plan de aliado por vencer (3 días): llega «Huellita de Plata vence pronto» con enlace a Suscripciones y la campana lo cuenta',
          len(nt) == 1 and nt[0]['title'] == 'Huellita de Plata vence pronto' and nt[0]['link'] == 'planes.html' and bell(pg)['n'] == '1', (nt, bell(pg)))
    check('10.12 La generación se pidió una sola vez (cabecera) y sin errores', len([r for r in be.n_log[n0:] if r['path'].endswith('/generate_my_reminders')]) == 1 and not csp_problems(log))
    ctx.close()
    reset_state(); be.assign(CRIS, 'oro', ends_sql="now() - interval '2 days'", starts_ago_days=33)
    ctx, pg, log = open_planes(br, 'cris@ejemplo.mx'); all_logs.append(log)
    eventually(lambda: bell(pg)['n'] == '1')
    nt = json.loads(be.sql(f"select coalesce(json_agg(title), '[]'::json) from public.notifications where user_id = '{CRIS}'"))
    check('10.13 Plan de aliado vencido hace 2 días: «Huellita de Oro venció» y la pantalla ya muestra «Sin plan»', nt == ['Huellita de Oro venció'] and mine(pg)['plan'] == 'Sin plan', (nt, mine(pg)['plan']))
    ctx.close()

def g11(br):
    print('\n[11] Errores, carreras y entradas hostiles')
    # fallo del servidor al enviar
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro'); pg.fill('[data-plan=pro] textarea', 'Mi mensaje importante')
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path.endswith('/request_plan') else None
    pg.click('[data-plan=pro] button[type=submit]'); waitjs(pg, "!!document.getElementById('mine-msg') && !document.getElementById('mine-msg').hidden"); settle(pg, 250)
    s = say(pg); btn = pg.evaluate("(() => { const b = document.querySelector('[data-plan=pro] button[type=submit]'); return b ? {t: b.textContent, d: b.disabled} : null; })()")
    check('11.1 Si el servidor falla: aviso de error claro, el formulario SIGUE abierto con tu mensaje y el botón vuelve a estar disponible',
          s and s['cls'] == 'msg err' and s['role'] == 'alert' and 'error inesperado' in s['text'] and cards(pg)['pro']['form'] and pg.input_value('[data-plan=pro] textarea') == 'Mi mensaje importante' and btn == {'t': 'Enviar solicitud', 'd': False} and not be.reqs(ANA), (s, btn))
    check('11.2 Tras el error el foco vuelve al formulario', focus_info(pg)['name'] == 'rq-period', focus_info(pg))
    be.fail_rest = None
    pg.click('[data-plan=pro] button[type=submit]'); waitjs(pg, "!document.querySelector('form.rq-form')"); settle(pg, 250)
    check('11.3 Al reintentar funciona: una solicitud en la base y dos llamadas en total (la fallida y la buena)', len(be.reqs(ANA)) == 1 and be.reqs(ANA)[0]['user_note'] == 'Mi mensaje importante' and len(plan_calls('request_plan')) == 2, (len(be.reqs(ANA)), len(plan_calls('request_plan'))))
    ctx.close()
    # el equipo/otra pestaña ya dejó una pendiente
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro')
    be.make_request(ANA, 'vip', note='Desde otra pestaña')
    pg.click('[data-plan=pro] button[type=submit]'); waitjs(pg, "!document.querySelector('form.rq-form')"); settle(pg, 300)
    s = say(pg); m = mine(pg)
    check('11.4 Si ya había una pendiente (otra pestaña), el servidor lo explica, no se crea otra y la pantalla la muestra',
          s and s['cls'] == 'msg err' and 'Ya tienes una solicitud pendiente' in s['text'] and len(be.reqs(ANA, 'pending')) == 1 and m['pending'] and 'Huellita VIP' in m['pending'] and 'Desde otra pestaña' in m['pending'], (s, m['pending']))
    ctx.close()
    # fallo al cargar y reintento
    reset_state()
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path.endswith('/my_entitlements') else None
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', wait=False); all_logs.append(log)
    waitjs(pg, "!!document.querySelector('#mine-body .mine-card') && /No pudimos/.test(document.getElementById('mine-body').textContent)")
    m = mine(pg); c = cards(pg)
    check('11.5 Si no carga: mensaje claro con «Reintentar»; las tarjetas NO ofrecen botones ni enlaces de registro (la persona ya tiene cuenta)',
          'No pudimos consultar tu plan en este momento' in m['text'] and [b['text'] for b in m['buttons']] == ['Reintentar'] and all(not c[k]['buttons'] and not c[k]['links'] and 'No pudimos consultar tu estado' in ' '.join(c[k]['small']) for k in c), (m['text'], {k: c[k]['small'][-1] for k in c}))
    be.fail_rest = None
    pg.click('#mine-body button'); waitjs(pg, MINE_READY); settle(pg, 200)
    check('11.6 «Reintentar» recupera la pantalla normal', mine(pg)['plan'] == 'Huellita Básica' and cards(pg)['pro']['buttons'][0]['text'] == 'Solicitar este plan' and 'No pudimos' not in mine(pg)['text'])
    ctx.close()
    # cuenta suspendida
    reset_state()
    ctx, pg, log = open_planes(br, 'susi@ejemplo.mx'); all_logs.append(log)
    c = cards(pg)
    check('11.7 Cuenta suspendida: los planes de pago muestran «Cuenta suspendida» desactivado', all(c[k]['buttons'] == [{'text': 'Cuenta suspendida', 'disabled': True, 'aria': None, 'type': 'button'}] for k in ('pro', 'vip')), (c['pro']['buttons'], c['vip']['buttons']))
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'monthly'})
    check('11.8 Y el servidor también lo impide si se fuerza desde la consola', not r['ok'] and 'suspendida' in r['msg'] and not be.reqs(SUSI), r)
    ctx.close()
    # texto hostil: se muestra como texto, nunca como HTML
    reset_state()
    hostile_note = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>'
    hostile_admin = '<b id="x">negrita</b><a href="javascript:window.__pwned=3">clic</a>'
    be.make_request(ANA, 'pro', note=hostile_note, status='rejected', admin_note=hostile_admin, ago_min=30)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    h = pg.evaluate("(() => { const b = document.getElementById('mine-body'); return {imgs: b.querySelectorAll('img').length, scripts: b.querySelectorAll('script').length, as: b.querySelectorAll('a').length, bx: !!b.querySelector('#x'), pwned: window.__pwned === undefined, text: b.innerText}; })()")
    check('11.9 Mensajes con HTML o JavaScript (del usuario y del equipo) se ven como texto literal: sin elementos nuevos ni código ejecutado',
          h['imgs'] == 0 and h['scripts'] == 0 and h['as'] == 0 and not h['bx'] and h['pwned'] and hostile_note in h['text'] and hostile_admin in h['text'], h)
    open_form(pg, 'pro'); submit_form(pg, 'pro', note=hostile_note)
    h = pg.evaluate("(() => { const b = document.getElementById('mine-body'); return {imgs: b.querySelectorAll('img').length, pwned: window.__pwned === undefined, text: b.querySelector('.rq-pend').innerText}; })()")
    check('11.10 Lo mismo con el mensaje recién enviado: se guarda y se muestra literal', h['imgs'] == 0 and h['pwned'] and hostile_note in h['text'] and pending_row(ANA)['user_note'] == hostile_note, h)
    check('11.11 Sin errores de CSP ni de consola con texto hostil', not csp_problems(log), csp_problems(log))
    ctx.close()
    # doble envío
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro'); n0 = len(be.p_log)
    pg.dblclick('[data-plan=pro] button[type=submit]'); settle(pg, 600)
    check('11.12 Doble clic en «Enviar solicitud»: una sola llamada y una sola solicitud', len(plan_calls('request_plan', n0)) == 1 and len(be.reqs(ANA)) == 1, (len(plan_calls('request_plan', n0)), len(be.reqs(ANA))))
    reset_state()
    pg.reload(); waitjs(pg, MINE_READY); open_form(pg, 'pro'); n0 = len(be.p_log)
    pg.focus('[data-plan=pro] button[type=submit]'); pg.keyboard.press('Enter'); pg.keyboard.press('Enter'); settle(pg, 600)
    check('11.13 Enter dos veces seguidas en el botón de enviar: tampoco se duplica', len(plan_calls('request_plan', n0)) == 1 and len(be.reqs(ANA)) == 1, (len(plan_calls('request_plan', n0)), len(be.reqs(ANA))))
    reset_state()
    pg.reload(); waitjs(pg, MINE_READY); open_form(pg, 'pro'); n0 = len(be.p_log)
    pg.evaluate("(() => { const f = document.querySelector('form.rq-form'); f.requestSubmit(); f.requestSubmit(); })()"); settle(pg, 600)
    check('11.13b Dos envíos del formulario en el mismo instante (sin pasar por el botón): solo uno llega al servidor', len(plan_calls('request_plan', n0)) == 1 and len(be.reqs(ANA)) == 1, (len(plan_calls('request_plan', n0)), len(be.reqs(ANA))))
    ctx.close()
    # longitud del mensaje
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro'); pg.fill('[data-plan=pro] textarea', 'x' * 400)
    check('11.14 El campo no deja escribir más de 300 caracteres', len(pg.input_value('[data-plan=pro] textarea')) == 300, len(pg.input_value('[data-plan=pro] textarea')))
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'monthly', 'p_note': 'y' * 301})
    check('11.15 Si se fuerza un mensaje de 301 caracteres, el servidor lo rechaza', not r['ok'] and 'hasta 300 caracteres' in r['msg'] and not be.reqs(ANA), r)
    r = rpc(pg, 'request_plan', {'p_plan': 'pro', 'p_period': 'monthly', 'p_note': 'z' * 300})
    check('11.16 Con exactamente 300 caracteres sí se acepta', r['ok'] and len(be.reqs(ANA)[0]['user_note']) == 300, r)
    ctx.close()
    # sesión que caduca a mitad del proceso
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    open_form(pg, 'pro')
    be.access.clear(); be.refresh.clear()
    pg.evaluate("(() => { const s = JSON.parse(localStorage.getItem('tp-auth-v1')); s.expires_at = Math.floor(Date.now() / 1000) - 10; localStorage.setItem('tp-auth-v1', JSON.stringify(s)); })()")
    pg.click('[data-plan=pro] button[type=submit]'); waitjs(pg, "!!document.getElementById('mine-msg') && !document.getElementById('mine-msg').hidden"); settle(pg, 300)
    s = say(pg)
    check('11.17 Si la sesión caducó, avisa que hay que volver a entrar, no crea nada y deja el formulario con tu mensaje', s and s['cls'] == 'msg err' and 'sesión' in s['text'].lower() and not be.reqs(ANA) and cards(pg)['pro']['form'], s)
    ctx.close()
    # intentos de escritura directa desde la consola (la página solo usa funciones)
    reset_state(); rid = be.make_request(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    r1 = api(pg, 'PATCH', '/plan_requests?id=eq.' + rid, {'status': 'approved'})
    r2 = api(pg, 'POST', '/plan_requests', {'plan_id': 'vip'})
    r3 = api(pg, 'DELETE', '/plan_requests?id=eq.' + rid)
    check('11.18 Escribir directamente en plan_requests desde la consola NO funciona y la solicitud queda intacta', not r1['ok'] and not r2['ok'] and not r3['ok'] and be.reqs(ANA)[0]['status'] == 'pending' and len(be.reqs(ANA)) == 1, (r1, r2, r3))
    ctx.close()

def g12(br):
    print('\n[12] Accesibilidad, teléfono y teclado')
    reset_state()
    be.make_request(ANA, 'pro', status='cancelled', ago_min=60); be.make_request(ANA, 'vip', status='rejected', admin_note='No por ahora', ago_min=50)
    be.make_request(ANA, 'pro', status='approved', admin_note='Listo', ago_min=40); be.make_request(ANA, 'vip', note='Mi mensaje', ago_min=5)
    be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=390, h=900); all_logs.append(log)
    ov = lambda: pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check('12.1 (390 px) Sin desplazamiento horizontal con plan, solicitud en revisión e historial', ov() <= 0, ov())
    pg.click('button[data-fx=cancel-ask]'); settle(pg, 150)
    check('12.2 (390 px) Sin desplazamiento horizontal con la confirmación de cancelar abierta', ov() <= 0, ov())
    pg.click('.rq-confirm button.ghost'); settle(pg, 100)
    ctx.close()
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=390, h=900); all_logs.append(log)
    open_form(pg, 'pro'); pg.fill('[data-plan=pro] textarea', 'palabra ' * 40)
    check('12.3 (390 px) Sin desplazamiento horizontal con el formulario abierto', pg.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0)
    small = pg.evaluate("""Array.from(document.querySelectorAll('#mine button, #pu button, #pb button, .rq-form label.ck, [data-bill]')).filter(e => e.offsetParent !== null && !e.disabled && e.getBoundingClientRect().height < 44)
        .map(e => [e.tagName, e.textContent.trim().slice(0, 30), Math.round(e.getBoundingClientRect().height)])""")
    check('12.4 (390 px) Botones y opciones del formulario miden al menos 44 px de alto', not small, small)
    ids = pg.evaluate("(() => { const all = Array.from(document.querySelectorAll('[id]')).map(e => e.id); return all.filter((x, i) => all.indexOf(x) !== i); })()")
    check('12.5 No hay identificadores repetidos', not ids, ids)
    names = pg.evaluate("""Array.from(document.querySelectorAll('#mine input, #mine textarea, #mine button, #pu button, #pb button, #pu input, #pb input, #pu textarea, #pb textarea'))
        .filter(e => e.offsetParent !== null).map(e => { const lab = e.labels && e.labels[0] ? e.labels[0].textContent.trim() : ''; return [e.tagName, (e.getAttribute('aria-label') || lab || e.textContent).trim()]; }).filter(x => !x[1])""")
    check('12.6 Todo botón, opción y campo tiene nombre accesible', not names, names)
    hs = pg.evaluate("Array.from(document.querySelectorAll('main h1, main h2, main h3, main legend')).map(h => h.tagName + ':' + h.textContent.trim().slice(0, 30))")
    lv = [int(x[1]) for x in [h.split(':')[0] for h in hs] if x[0] == 'H']
    check('12.7 Los títulos no saltan niveles (h1 → h2 → h3)', all(b - a <= 1 for a, b in zip(lv, lv[1:])), hs)
    check('12.8 Las opciones de periodo están en un fieldset con leyenda', pg.evaluate("(() => { const f = document.querySelector('[data-plan=pro] fieldset'); return !!f && f.querySelector('legend').textContent.length > 3 && f.querySelectorAll('input[type=radio]').length === 2; })()"))
    ctx.close()
    # textos largos sin espacios no deben ensanchar la página
    reset_state()
    be.make_request(ANA, 'pro', note='W' * 280, status='rejected', admin_note='Z' * 450, ago_min=30); be.make_request(ANA, 'vip', note='Q' * 290, ago_min=5)
    for w_ in (390, 1100):
        ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=w_, h=900); all_logs.append(log)
        check(f'12.14 ({w_} px) Mensajes largos sin espacios (del usuario y del equipo) no ensanchan la página', pg.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0, pg.evaluate("document.documentElement.scrollWidth - window.innerWidth"))
        ctx.close()
    # solo con teclado
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    pg.focus('[data-plan=pro] button[data-fx=open-pro]'); pg.keyboard.press('Enter'); waitjs(pg, "!!document.querySelector('[data-plan=pro] form')")
    check('12.9 (teclado) Enter abre el formulario y el foco cae en la primera opción', focus_info(pg)['name'] == 'rq-period', focus_info(pg))
    pg.keyboard.press('ArrowDown'); check('12.10 (teclado) Las flechas cambian el periodo', pg.is_checked('[data-plan=pro] input[value=yearly]'))
    pg.keyboard.press('Tab'); pg.keyboard.type('Hola equipo'); pg.keyboard.press('Tab')
    check('12.11 (teclado) Tab lleva del periodo al mensaje y luego al botón de enviar', focus_info(pg)['text'] == 'Enviar solicitud', focus_info(pg))
    pg.keyboard.press('Enter'); waitjs(pg, "!document.querySelector('form.rq-form')"); settle(pg, 250)
    row = pending_row(ANA)
    check('12.12 (teclado) Enter envía la solicitud con lo elegido y escrito', row and row['billing_period'] == 'yearly' and row['user_note'] == 'Hola equipo', row)
    ctx.close()
    # la región de avisos está visible en el teléfono sin tener que desplazarse hasta el final
    reset_state()
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=390, h=700); all_logs.append(log)
    open_form(pg, 'pro'); submit_form(pg, 'pro')
    for _ in range(40):
        a = pg.evaluate('window.scrollY'); settle(pg, 100)
        if pg.evaluate('window.scrollY') == a: break
    y = pg.evaluate("(() => { const r = document.getElementById('mine-msg').getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom), innerHeight]; })()")
    check('12.13 (390 px) Tras enviar, el aviso de resultado queda a la vista (el foco va al título de arriba)', y[0] >= 0 and y[1] <= y[2], y)
    ctx.close()

# Contraste (WCAG AA: 4.5:1; 3:1 para texto grande) sobre los fondos reales de la paleta. Los controles desactivados están exentos.
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

def g13(br):
    print('\n[13] Contraste de colores (paleta fija)')
    for w_, tag in ((1100, 'escritorio'), (390, 'teléfono')):
        reset_state()
        ctx, pg, log = open_planes(br, None, w=w_); all_logs.append(log); settle(pg, 200)
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.1 ({tag}) Visitante: todo el texto cumple el contraste AA', not bad, bad[:3])
        ctx.close()
        reset_state()
        be.assign(ANA, 'pro', days=10)
        be.make_request(ANA, 'pro', status='cancelled', ago_min=60); be.make_request(ANA, 'vip', status='rejected', admin_note='No por ahora', ago_min=50)
        be.make_request(ANA, 'pro', status='approved', admin_note='Listo', ago_min=40); be.make_request(ANA, 'vip', note='Mi mensaje', ago_min=5)
        ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=w_); all_logs.append(log); settle(pg, 200)
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.2 ({tag}) Con renovación posible, solicitud en revisión y los 4 estados del historial', not bad, bad[:3])
        pg.click('button[data-fx=cancel-ask]'); settle(pg, 150)
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.3 ({tag}) Con la confirmación de cancelar abierta', not bad and mine(pg)['confirm'], bad[:3])
        ctx.close()
        reset_state(); be.assign(ANA, 'pro', days=10)
        ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', w=w_); all_logs.append(log)
        open_form(pg, 'pro'); pg.fill('[data-plan=pro] textarea', 'Hola')
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.4 ({tag}) Con el formulario de solicitud abierto', not bad, bad[:3])
        pg.fill('[data-plan=pro] textarea', 'x'); pg.click('[data-plan=pro] button[type=submit]'); settle(pg, 300)
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.5 ({tag}) Con el aviso de éxito visible', not bad and say(pg), bad[:3])
        ctx.close()
        reset_state()
        ctx, pg, log = open_planes(br, 'susi@ejemplo.mx', w=w_); all_logs.append(log)
        bad = pg.evaluate(AUDIT_JS)
        check(f'13.6 ({tag}) Cuenta suspendida y aviso de error', not bad, bad[:3])
        rid = be.make_request(ANA, 'pro')
        ctx.close()
    # error de carga
    reset_state()
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path.endswith('/my_entitlements') else None
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', wait=False); all_logs.append(log)
    waitjs(pg, "/No pudimos/.test(document.getElementById('mine-body').textContent)")
    bad = pg.evaluate(AUDIT_JS)
    check('13.7 Pantalla de error de carga', not bad, bad[:3])
    ctx.close()
    # control: la comprobación sí detecta un texto de bajo contraste
    reset_state(); be.make_request(ANA, 'pro', status='rejected', admin_note='Nota de control', ago_min=5)
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx'); all_logs.append(log)
    pg.evaluate("document.querySelectorAll('.rq-n, .rq-item small').forEach(e => e.style.setProperty('color', '#c9d3e8', 'important'))")
    bad = pg.evaluate(AUDIT_JS)
    check('13.8 Control: un texto claro sobre fondo claro SÍ es detectado por la comprobación', len(bad) >= 1, bad[:2])
    ctx.close()

def g14(br):
    print('\n[14] Perfil, avisos y menú')
    reset_state(); be.assign(ANA, 'pro')
    ctx, pg, log = open_planes(br, 'ana@ejemplo.mx', page='perfil.html'); all_logs.append(log)
    waitjs(pg, "document.getElementById('p-plan').textContent !== '…'")
    check('14.1 El perfil muestra el plan vigente con su lema', txt(pg, '#p-plan') == 'Huellita Pro · Plan Cuidadores', txt(pg, '#p-plan'))
    note = pg.evaluate("document.querySelector('#p-plan').closest('.card').innerText")
    check('14.2 El perfil ya no dice que «los asigna un administrador»: explica la solicitud sin cobros y enlaza a Suscripciones',
          'asigna un administrador' not in note and 'Todavía no hay pagos en línea' in note and pg.get_attribute('#p-plan >> xpath=ancestor::div[contains(@class,"card")]//a[contains(@class,"btn")]', 'href') == 'planes.html', note)
    check('14.3 El menú lateral lleva a «Mi suscripción»', pg.evaluate("Array.from(document.querySelectorAll('.side a')).some(a => a.getAttribute('href') === 'planes.html' && /suscripci/i.test(a.textContent))"))
    ctx.close()
    reset_state()
    ctx, pg, log = open_planes(br, 'cris@ejemplo.mx', page='perfil.html'); all_logs.append(log)
    waitjs(pg, "document.getElementById('p-plan').textContent !== '…'")
    check('14.4 Un aliado sin plan lo ve explicado y sin prometer cobros', txt(pg, '#p-plan') == 'Sin plan de aliado todavía (puedes pedirlo en Mi suscripción; no hay cobros)', txt(pg, '#p-plan'))
    ctx.close()
    # copia de las preferencias de notificaciones
    html = open(os.path.join(ROOT, 'notificaciones.html'), encoding='utf-8').read()
    check('14.5 Las preferencias de notificaciones ya no dicen que los cambios de suscripción «no se envían»: aparecen en la plataforma',
          'cambios de suscripción todavía no se envían' not in html and 'solicitud recibida, respuesta del equipo y vencimiento del plan' in html and 'Tu suscripción: solicitudes, respuestas y vencimiento' in html)
    # texto sobre planes en otras pantallas
    allsrc = ' '.join(open(os.path.join(ROOT, f), encoding='utf-8').read() for f in ('js/pages/carnet.js', 'js/pages/placa.js'))
    check('14.6 Carnet y placa ya no dicen «los asigna un administrador»: explican que se piden y el equipo los activa sin cargos', 'por ahora los asigna un administrador' not in allsrc and allsrc.count('sin cargos') >= 2)
    html = open(os.path.join(ROOT, 'planes.html'), encoding='utf-8').read()
    layout = open(os.path.join(ROOT, 'js/layout.js'), encoding='utf-8').read()
    check('14.7 El pie de página sigue diciendo que no hay pagos ni cobros', 'Aún no hay pagos ni cobros' in layout)
    # ningún archivo del sitio pide datos de tarjeta ni menciona pasarelas de pago
    bad = []
    for f in sorted(os.listdir(ROOT)) + ['js/' + x for x in os.listdir(os.path.join(ROOT, 'js'))] + ['js/pages/' + x for x in os.listdir(os.path.join(ROOT, 'js/pages'))]:
        pth = os.path.join(ROOT, f)
        if not os.path.isfile(pth) or not f.endswith(('.html', '.js')): continue
        t = open(pth, encoding='utf-8').read()
        if re.search(r'autocomplete=["\']cc-|cardnumber|stripe\.com|paypal\.com|mercadopago|openpay|conekta|checkout\.', t, re.I): bad.append(f)
    check('14.8 Ninguna página ni script pide datos de tarjeta ni carga una pasarela de pago', not bad, bad)

GROUPS = [(1, g1), (2, g2), (3, g3), (4, g4), (5, g5), (6, g6), (7, g7), (8, g8), (9, g9), (10, g10), (11, g11), (12, g12), (13, g13), (14, g14)]
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for n, f in GROUPS:
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
