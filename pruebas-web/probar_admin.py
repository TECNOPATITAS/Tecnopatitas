"""
Pruebas de interfaz de la Etapa 10 (panel de administración y guías públicas) en Chromium real.

Qué es real y qué es simulado:
  REAL      el HTML/CSS/JS del sitio con las MISMAS cabeceras de _headers (se detecta cualquier violación de CSP) y la base de datos:
            todas las funciones admin_*, private.require_admin, la bitácora, los disparadores, las políticas RLS y los permisos
            (PostgreSQL local con database/00_instalar_todo.sql; ver mock_etapa10.py). Una cuenta que NO es administradora recibe el
            mismo error 42501 que daría el servidor real.
  SIMULADO  PostgREST (traduce solo las funciones admin_* y la lectura de care_guides), Supabase Auth (mock_supabase.py) y Storage
            (la evidencia de las denuncias solo se firma para administradores).

Uso:  python3 pruebas-web/probar_admin.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), playwright + chromium.
Variables: TP_PORT (sitio, 8774), TP_ADMIN_DB (base, tp_admin), TP_SITE (carpeta del sitio; las «pruebas de las pruebas» usan una copia
           saboteada), TP_ONLY (ejecuta solo un grupo, p. ej. TP_ONLY=5).
"""
import datetime, http.server, json, os, re, socketserver, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa10 import Backend10, ADMIN_RPC

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_ROOT = os.path.abspath(os.path.join(HERE, '..'))
ROOT = os.path.abspath(os.environ.get('TP_SITE', REAL_ROOT))
PORT = int(os.environ.get('TP_PORT', 8774)); DB = os.environ.get('TP_ADMIN_DB', 'tp_admin')
ORIGIN = f'http://localhost:{PORT}'
CONFIG_JS = open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", CONFIG_JS).group(1)
ONLY = os.environ.get('TP_ONLY', '')
HOSTILE = '<img src=x onerror="window.__pwn=1"> <b>negrita</b> &amp; "comillas"'

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
be = Backend10(KEY, DB)
CUR = [None]
HELD = []
def release_held():
    """Responde, ya con normalidad, a las peticiones que se retuvieron (para probar respuestas tardías)."""
    items = list(HELD); HELD.clear()
    for route, req in items:
        res = be.handle(req.method, req.url, req.headers, req.post_data)
        route.fulfill(status=res[0], headers={**CORS, 'content-type': 'application/json'}, body='' if res[1] is None else json.dumps(res[1]))
def route_supa(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    try: res = be.handle(req.method, req.url, req.headers, req.post_data)
    except Exception:
        import traceback; traceback.print_exc(); route.fulfill(status=500, headers=CORS, body='{"message":"error del simulador"}'); return
    if res[0] == 'abort': route.abort(); return
    if res[0] == 'hold': HELD.append((route, req)); return
    if len(res) == 3: route.fulfill(status=res[0], headers={**CORS, 'content-type': res[2]}, body=res[1]); return
    status, data = res
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
    try: seen = pg.inner_text('#ad-view')[:900].replace('\n', ' | ')
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
def settle(pg, ms=250): tick(pg, ms)
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def txt(pg, sel): return pg.inner_text(sel) if pg.locator(sel).count() else ''
JUNK_RE = re.compile(r'\bnull\b|undefined|\[object|\bNaN\b|Invalid Date|1969|1970')
def junk(pg, sel='#ad-view'): return JUNK_RE.findall(txt(pg, sel))
def read(path): return open(os.path.join(ROOT, path), encoding='utf-8').read()

READY = """(() => { const s = document.querySelector('#ad-view .adm-sec'); return !!s && !!document.getElementById('ad-h') && !/Cargando…/.test(s.textContent); })()"""
def open_admin(br, email, hash_='', w=1100, h=900, clock=False, ttl=None, valid_refresh=True, ctx=None, wait=True, page='admin.html'):
    ctx = ctx or new_ctx(br, w, h, clock)
    if email:
        scr, sess = session_script(email, ttl, valid_refresh); ctx.add_init_script(scr)
    log = []; pg = ctx.new_page(); CUR[0] = pg; pg.set_default_timeout(8000)
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    pg.goto(f'{ORIGIN}/{page}{hash_}')
    if wait: waitjs(pg, READY if page == 'admin.html' else "document.body.classList.contains('tp-ok')")
    return ctx, pg, log
def go(pg, sec):
    pg.click(f'#ad-nav a[data-sec={sec}]')
    waitjs(pg, f"(() => {{ const s = document.querySelector('#ad-view .adm-sec'); return !!s && s.dataset.sec === '{sec}'; }})()")
    waitjs(pg, READY)
def say(pg):
    return pg.evaluate("(() => { const m = document.getElementById('ad-msg'); return m && !m.hidden ? {cls: m.className, role: m.getAttribute('role'), text: m.textContent} : null; })()")
def wait_say(pg, kind=None, timeout=6.0):
    waitjs(pg, "(() => { const m = document.getElementById('ad-msg'); return !!m && !m.hidden && m.textContent.length > 0" + (f" && m.classList.contains('{kind}')" if kind else '') + "; })()", timeout)
    return say(pg)
def rows(pg, sel='#ad-view .adm-row'):
    return pg.evaluate("""(sel) => Array.from(document.querySelectorAll(sel)).map(r => ({id: r.dataset.id || null, code: r.dataset.code || null, slug: r.dataset.slug || null,
        text: r.innerText, badges: Array.from(r.querySelectorAll('.badge')).map(b => b.textContent)}))""", sel)
def row(pg, id_): return pg.locator(f'#ad-view .adm-row[data-id="{id_}"]')
def confirm(pg, scope, label):
    """Botón de dos pasos: pulsa «label» dentro de scope y luego «Sí»."""
    pg.click(f'{scope} button:text-is("{label}")')
    waitjs(pg, "!!document.querySelector('.adm-ask')")
    pg.click(f'{scope} .adm-ask button:text-is("Sí")')
def api(pg, fn, args=None):
    """Llama una función desde la consola de la página con su sesión, como lo haría alguien que manipula el navegador."""
    return pg.evaluate("""async ([f, a]) => { try { const r = await TP.rpc(f, a); return {ok: true, r}; }
        catch (e) { return {ok: false, status: e.status, code: e.code, msg: e.message}; } }""", [fn, args or {}])
def reset_state():
    be.sql("delete from auth.users where email like '%@masa.mx'")          # personas masivas de otros grupos
    be.reset_db(); be.rest_log.clear(); be.n_log.clear(); be.p_log.clear(); be.a_log.clear(); be.sign_log.clear(); be.calls.clear(); be.fail_rest = None
def group(n): return not ONLY or str(n) in ONLY.split(',')
def admin_calls(since=0): return [r for r in be.a_log[since:] if '/rpc/admin_' in r['path']]
def fn_calls(name, since=0): return [r for r in be.a_log[since:] if r['path'].endswith('/rpc/' + name)]
def bulk_users(n, prefix='u', kind='owner'):
    meta = json.dumps({'display_name': 'Persona', 'account_type': kind}).replace("'", "''")
    be.sql(f"insert into auth.users (id, email, raw_user_meta_data) select gen_random_uuid(), '{prefix}'||g||'@masa.mx', '{meta}' from generate_series(1, {n}) g")
def hostile_ran(pg): return pg.evaluate('window.__pwn === 1')

def setup_users():
    prepare_db()
    return dict(ADMIN=be.add_user('dani@ejemplo.mx', 'ClaveSegura123', name='Dani', admin=True),
                ADMIN2=be.add_user('eli@ejemplo.mx', 'ClaveSegura123', name='Eli', admin=True),
                ANA=be.add_user('ana@ejemplo.mx', 'ClaveSegura123', name='Ana'),
                BRUNO=be.add_user('bruno@ejemplo.mx', 'ClaveSegura123', name='Bruno'),
                CRIS=be.add_user('cris@ejemplo.mx', 'ClaveSegura123', name='Cris', account_type='business'),
                SUSI=be.add_user('susi@ejemplo.mx', 'ClaveSegura123', name='Susi', suspended=True))

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
# Controles sin nombre accesible, botones/enlaces demasiado pequeños (móvil) y desbordes horizontales
A11Y_JS = r"""
(opts) => {
  const out = [];
  const vis = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('[hidden]'); };
  document.querySelectorAll('#main input:not([type=hidden]), #main select, #main textarea').forEach(e => {
    if (!vis(e)) return;
    const name = (e.getAttribute('aria-label') || '') + (e.labels && e.labels.length ? Array.from(e.labels).map(l => l.textContent).join('') : '') + (e.getAttribute('aria-labelledby') ? 'x' : '');
    if (!name.trim()) out.push('sin nombre: ' + e.tagName + '#' + e.id);
  });
  document.querySelectorAll('#main button, #main a.btn').forEach(e => {
    if (!vis(e)) return;
    if (!(e.textContent.trim() || e.getAttribute('aria-label'))) out.push('botón sin texto');
    if (opts.touch) { const r = e.getBoundingClientRect(); if (r.height < 43.5) out.push('pequeño ' + Math.round(r.height) + 'px: ' + e.textContent.trim().slice(0, 30)); }
  });
  document.querySelectorAll('#main *').forEach(e => {
    if (['SELECT', 'INPUT', 'TEXTAREA', 'BUTTON', 'OPTION', 'svg', 'path'].includes(e.tagName) || !vis(e) || e.clientWidth <= 0) return;
    const own = Array.from(e.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    if (own && getComputedStyle(e).overflowX === 'visible' && e.scrollWidth > e.clientWidth + 1) out.push('texto largo desborda su caja: ' + e.tagName.toLowerCase() + '.' + String(e.className) + ' «' + e.textContent.trim().slice(0, 24) + '»');
  });
  if (document.documentElement.scrollWidth > window.innerWidth + 1) {
    let worst = null; const w = window.innerWidth;
    const clipped = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) if (getComputedStyle(p).overflowX !== 'visible') return true; return false; };
    document.querySelectorAll('#main *').forEach(e => { const r = e.getBoundingClientRect(); const rr = Math.max(r.right, r.left + e.scrollWidth); if (r.width && rr > w + 1 && !clipped(e) && (!worst || rr > worst.right)) worst = { e, right: rr }; });
    out.push('desborde horizontal ' + document.documentElement.scrollWidth + ' > ' + w + (worst ? ' · ' + worst.e.tagName.toLowerCase() + '.' + String(worst.e.className) + ' «' + worst.e.textContent.trim().slice(0, 24) + '»' : ''));
  }
  return out;
}
"""

# ================================================================== PRUEBAS
U = setup_users()
ADMIN, ADMIN2, ANA, BRUNO, CRIS, SUSI = U['ADMIN'], U['ADMIN2'], U['ANA'], U['BRUNO'], U['CRIS'], U['SUSI']
all_logs = []
ADMIN_FILES = ['js/pages/admin.js'] + [f'js/pages/admin-{s}.js' for s in ('usuarios', 'aliados', 'denuncias', 'guias', 'subs', 'atencion', 'bitacora')]
SRC = {f: read(f) for f in ADMIN_FILES + ['js/tp-guides.js', 'js/pages/guias.js']}
# ==== GRUPOS ====

def g1(br):
    print('\n[1] Estructura y seguridad de los archivos')
    html = read('admin.html')
    check('1.1 admin.html: protegida con data-guard="admin" y con los scripts en orden (cliente, interfaz, diseño, protección, ayudas y panel)',
          'data-guard="admin"' in html and re.search(r'tp-client\.js.*tp-ui\.js.*layout\.js.*guard\.js.*tp-biz\.js.*tp-guides\.js.*pages/admin\.js.*admin-usuarios\.js.*admin-aliados\.js.*admin-denuncias\.js.*admin-guias\.js.*admin-subs\.js.*admin-atencion\.js.*admin-bitacora\.js', html) is not None)
    check('1.2 admin.html: tiene el menú #ad-nav, la zona #ad-view y el aviso #ad-msg; ya no dice «se conecta en la Etapa 10»; no se indexa',
          all(x in html for x in ('id="ad-nav"', 'id="ad-view"', 'id="ad-msg"', 'name="robots" content="noindex"')) and 'Etapa 10' not in html)
    check('1.3 Todos los archivos del panel existen y pasan la revisión de sintaxis', all(os.path.exists(os.path.join(ROOT, f)) for f in ADMIN_FILES) and
          all(subprocess.run(['node', '--check', os.path.join(ROOT, f)], capture_output=True).returncode == 0 for f in ADMIN_FILES + ['js/tp-guides.js', 'js/pages/guias.js']))
    bad = {f: re.findall(r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function|setTimeout\(\s*[\'"]', s) for f, s in SRC.items()}
    check('1.4 Ningún archivo del panel ni de las guías usa innerHTML, eval ni document.write', not any(bad.values()), {k: v for k, v in bad.items() if v})
    check('1.5 El panel no escribe en tablas ni lee tablas: solo llama funciones admin_* (nada de TP.rest ni .from)', not any(re.search(r'TP\.rest|\.from\(|/rest/v1', s) for f, s in SRC.items() if f.startswith('js/pages/admin')))
    used = set()
    for f, s in SRC.items():
        if f.startswith('js/pages/admin'): used |= set(re.findall(r"A\.rpc\('([a-z_]+)'", s))
    sql = read('database/02_funciones.sql') + read('database/03_seguridad_rls.sql')
    check('1.6 Cada función que usa el panel existe en el SQL, está dada de alta en el simulador y tiene permiso de ejecución solo para «authenticated»',
          used and all(('public.' + u + '(') in sql and u in ADMIN_RPC and re.search(r'grant execute on function public\.' + u + r'\(.*\) to authenticated', read('database/03_seguridad_rls.sql')) for u in used), sorted(used))
    check('1.7 El panel usa las 28 funciones admin_* del servidor (ninguna queda sin pantalla)', len(used) == 28 and used == set(ADMIN_RPC), sorted(set(ADMIN_RPC) ^ used))
    check('1.8 Ningún archivo del sitio contiene claves secretas ni «service_role» en código (solo texto de ayuda en comentarios)',
          not any(re.search(r'service_role|sb_secret_|eyJhbGciOi', s) for s in SRC.values()))
    plans = json.loads(be.sql("select json_object_agg(id, name) from public.subscription_plans"))
    m = re.search(r"A\.PLAN = \{([^}]*)\}", SRC['js/pages/admin.js']); got = dict(re.findall(r"(\w+):\s*'([^']+)'", m.group(1))) if m else {}
    check('1.9 Los nombres de plan del panel son idénticos a los de la base de datos', got == plans, (got, plans))
    cats = re.search(r"care_guides.*?category\s+text not null check \(category in \(([^)]*)\)\)", read('database/01_esquema.sql'), re.S)
    db_cats = set(re.findall(r"'([a-z-]+)'", cats.group(1)))
    js_cats = set(re.findall(r"(?:^|[ {,])'?([a-z-]+)'?:\s*'[^']+'", re.search(r"CATEGORIES = \{([^}]*)\}", read('js/tp-guides.js'), re.S).group(1)))
    check('1.10 Las categorías de las guías del sitio son las mismas que permite la base de datos', db_cats == js_cats and len(db_cats) == 10, (db_cats ^ js_cats))
    check('1.11 Los textos del panel dicen que no hay cobros y que los administradores solo se crean desde la base de datos',
          'Aquí no se cobra nada' in html and 'únicamente desde la base de datos' in html)
    guias = read('guias.html')
    check('1.12 guias.html ya no es una vista de diseño: carga tp-guides.js y guias.js y no dice «no está conectada»',
          'Vista de diseño' not in guias and 'tp-guides.js' in guias and 'pages/guias.js' in guias)


def g2(br):
    print('\n[2] Control de acceso')
    reset_state()
    # visitante sin sesión
    ctx, pg, log = open_admin(br, None, wait=False); all_logs.append(log)
    waitjs(pg, "location.pathname.endsWith('login.html')")
    check('2.1 Una persona sin sesión es enviada a iniciar sesión y vuelve a admin.html', 'next=admin.html' in pg.url, pg.url)
    check('2.2 Sin sesión no se llamó a ninguna función de administración', not admin_calls(), admin_calls())
    ctx.close()
    # cuentas que no son de administración
    for who, email in (('dueña de mascota', 'ana@ejemplo.mx'), ('aliado comercial', 'cris@ejemplo.mx'), ('cuenta suspendida', 'susi@ejemplo.mx')):
        n0 = len(be.a_log)
        ctx, pg, log = open_admin(br, email, wait=False); all_logs.append(log)
        waitjs(pg, "document.body.classList.contains('tp-ok')")
        settle(pg, 300)
        body = txt(pg, '#main')
        check(f'2.3 ({who}) ve «Acceso restringido», sin menú ni datos del panel', 'Acceso restringido' in body and pg.locator('#ad-nav a').count() == 0 and pg.locator('#ad-view').count() == 0, body[:120])
        check(f'2.4 ({who}) no dispara ninguna función de administración', not admin_calls(n0), admin_calls(n0))
        ctx.close()
    # administrador
    n0 = len(be.a_log)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    labels = pg.evaluate("Array.from(document.querySelectorAll('#ad-nav a')).map(a => a.dataset.sec + '|' + a.textContent)")
    check('2.5 El administrador ve las 8 secciones en el menú, en orden', [l.split('|')[0] for l in labels] == ['dash', 'usuarios', 'aliados', 'denuncias', 'guias', 'subs', 'atencion', 'bitacora'], labels)
    check('2.6 El menú marca la sección actual (aria-current) y el título de la pestaña la nombra', pg.evaluate("document.querySelector('#ad-nav a[aria-current=page]').dataset.sec") == 'dash' and 'Administración' in pg.title(), pg.title())
    check('2.7 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    # intento desde la consola de una cuenta que no es de administración: el SERVIDOR lo rechaza
    ctx.close()
    ctx, pg, log = open_admin(br, 'ana@ejemplo.mx', page='perfil.html'); all_logs.append(log)
    ARGS = {'p_user': ANA, 'p_id': ANA, 'p_business': ANA, 'p_promo': ANA, 'p_subscription': ANA, 'p_request': ANA, 'p_conversation': ANA}
    bad = []
    for fn, (kind, types) in ADMIN_RPC.items():
        args = {}
        for k, t in types.items():
            args[k] = ANA if t == 'uuid' else (True if t == 'boolean' else 'x' if t == 'text' else 1 if t == 'integer' else '2027-01-01T00:00:00Z')
        r = api(pg, fn, args)
        if r['ok'] or r.get('status') != 403 or 'permiso' not in (r.get('msg') or '').lower() and 'autoriz' not in (r.get('msg') or '').lower(): bad.append((fn, r))
    check(f'2.8 Las {len(ADMIN_RPC)} funciones admin_* rechazan a una cuenta que no es de administración (aunque se llamen desde la consola)', not bad, bad[:3])
    check('2.9 Ninguna de esas llamadas cambió datos (ni bitácora, ni suspensiones, ni planes)', be.audit_rows() == [] and be.sql("select count(*) from public.subscriptions") == '0')
    ctx.close()
    # sin sesión desde la consola
    ctx, pg, log = open_admin(br, None, page='planes.html', wait=False); all_logs.append(log)
    settle(pg, 300)
    r = pg.evaluate("""async () => { try { await TP.rpc('admin_list_users', {}, {anon: true}); return 'ok'; } catch (e) { return e.status + ':' + e.code; } }""")
    check('2.10 Sin sesión, una función de administración responde «no autorizado» (401)', r.startswith('401'), r)
    ctx.close()
    # a mitad de sesión le quitan el rol: el panel muestra el error del servidor, sin romperse
    reset_state(); be.add_conv(ANA, 'Pregunta')
    ctx, pg, log = open_admin(br, 'eli@ejemplo.mx'); all_logs.append(log)
    be.sql(f"delete from public.admin_roles where user_id = '{ADMIN2}'")
    go(pg, 'atencion')
    m = txt(pg, '#ad-view .msg.err')
    check('2.11 Si le quitan el rol de administración con la página abierta, la siguiente consulta falla con un mensaje claro y sin datos', 'permiso' in m.lower() and pg.locator('#ad-view .adm-row').count() == 0, m)
    be.sql(f"insert into public.admin_roles (user_id, note) values ('{ADMIN2}', 'admin de pruebas')")
    ctx.close()


def g3(br):
    print('\n[3] Resumen (panel)')
    reset_state()
    b1 = be.add_biz(CRIS, 'Aliado pendiente', status='pending'); be.add_biz(CRIS, 'Aliado aprobado', status='approved'); be.add_biz(None, 'Demo', status='approved', demo=True)
    be.add_complaint('TP-AAAA-BBBB'); be.add_complaint('TP-CCCC-DDDD', status='en_revision'); be.add_complaint('TP-EEEE-FFFF', status='cerrada')
    c1 = be.add_conv(ANA, 'Sin responder'); c2 = be.add_conv(BRUNO, 'Otra', body='Hola'); be.staff_reply(c2, ADMIN, 'Te ayudamos')
    rid = be.make_request(ANA, 'pro'); be.assign(BRUNO, 'pro')
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    stats = pg.evaluate("Object.fromEntries(Array.from(document.querySelectorAll('[data-stat]')).map(c => [c.dataset.stat, {n: c.querySelector('.stat').textContent, todo: c.classList.contains('adm-todo'), tag: c.tagName, href: c.getAttribute('href')}]))")
    db = dict(users=int(be.sql("select count(*) from public.profiles")))
    check('3.1 Las 11 tarjetas aparecen y las cifras coinciden con la base de datos',
          len(stats) == 11 and stats['users']['n'] == str(db['users']) and stats['businesses']['n'] == '2' and stats['businesses_pending']['n'] == '1' and stats['complaints']['n'] == '3'
          and stats['complaints_pending']['n'] == '2' and stats['conversations_unanswered']['n'] == '1' and stats['conversations_open']['n'] == '2' and stats['plan_requests_pending']['n'] == '1'
          and stats['active_subscriptions']['n'] == '1' and stats['suspended_users']['n'] == '1' and stats['pets']['n'] == '0', {k: v['n'] for k, v in stats.items()})
    check('3.2 Lo pendiente de atender se resalta (aliados, denuncias, chat, solicitudes) y lo demás no', all(stats[k]['todo'] for k in ('businesses_pending', 'complaints_pending', 'conversations_unanswered', 'plan_requests_pending'))
          and not any(stats[k]['todo'] for k in ('users', 'complaints', 'pets', 'active_subscriptions', 'suspended_users')))
    check('3.3 Las tarjetas con sección son enlaces (teclado) y la de mascotas no', stats['users']['tag'] == 'A' and stats['complaints_pending']['href'] == '#denuncias' and stats['pets']['tag'] == 'DIV')
    pg.click('[data-stat=businesses_pending]'); waitjs(pg, READY); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'aliados'")
    waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length > 0")
    rs = rows(pg)
    check('3.4 Pulsar «Aliados en revisión» abre Aliados ya filtrado por «En revisión»', len(rs) == 1 and rs[0]['id'] == b1 and pg.input_value('#al-status') == 'pending', rs)
    check('3.5 La URL cambia a #aliados (el botón «atrás» funciona)', pg.url.endswith('#aliados'), pg.url)
    pg.go_back(); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'dash'"); waitjs(pg, READY)
    check('3.6 «Atrás» vuelve al resumen', pg.url.endswith('admin.html') or pg.url.endswith('#dash'), pg.url)
    pg.click('[data-stat=complaints_pending]'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'denuncias'"); waitjs(pg, READY)
    check('3.7 «Denuncias pendientes» abre la bandeja con las 2 pendientes', pg.input_value('#dn-filtro') == 'pendientes' and len(rows(pg)) == 2)
    go(pg, 'dash')
    be.add_complaint('TP-GGGG-HHHH')
    pg.click('button:text-is("Actualizar cifras")'); waitjs(pg, "document.querySelector('[data-stat=complaints_pending] .stat') && document.querySelector('[data-stat=complaints_pending] .stat').textContent === '3'")
    check('3.8 «Actualizar cifras» vuelve a consultar el servidor', pg.inner_text('[data-stat=complaints_pending] .stat') == '3')
    check('3.9 Sin textos «null», «undefined» ni fechas inválidas, y sin errores de consola/CSP', not junk(pg) and not csp_problems(log), (junk(pg), csp_problems(log)))
    ctx.close()
    # cero pendientes: nada resaltado
    reset_state()
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    check('3.10 Sin pendientes no se resalta nada', pg.locator('.adm-todo').count() == 0)
    ctx.close()


RUNNER_MARK = None

def open_user(pg, uid):
    pg.click(f'#ad-view .adm-row[data-id="{uid}"] button:has-text("Ver ficha")')
    waitjs(pg, "!!document.querySelector('#ad-view .adm-dl') && !/Cargando/.test(document.querySelector('#ad-view .adm-sec').textContent)")
def users_filter(pg, q):
    pg.fill('#us-q', q); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 150); waitjs(pg, READY)

def g4(br):
    print('\n[4] Usuarios')
    reset_state(); bulk_users(30, 'u')
    be.sql(f"update public.profiles set display_name = {HOSTILE!r} where id = '{BRUNO}'".replace('"', '"'))
    be.add_pet(ANA, 'SecretoNube')
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    go(pg, 'usuarios')
    rs = rows(pg); pager = txt(pg, '.adm-pager')
    check('4.1 La primera página muestra 25 cuentas y «Mostrando 1–25 de 36»; «Anterior» deshabilitado', len(rs) == 25 and 'Mostrando 1–25 de 36' in pager and pg.locator('.adm-pager button:text-is("← Anterior")').is_disabled(), (len(rs), pager))
    pg.click('.adm-pager button:text-is("Siguiente →")'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 11")
    check('4.2 «Siguiente» muestra las 11 restantes («26–36 de 36») y se deshabilita', 'Mostrando 26–36 de 36' in txt(pg, '.adm-pager') and pg.locator('.adm-pager button:text-is("Siguiente →")').is_disabled())
    users_filter(pg, 'ana@')
    rs = rows(pg)
    check('4.3 Buscar por correo encuentra una sola cuenta', len(rs) == 1 and rs[0]['id'] == ANA and 'ana@ejemplo.mx' in rs[0]['text'], rs)
    users_filter(pg, '   ana@   ')
    check('4.3b Los espacios al inicio y al final de lo buscado se quitan (en pantalla y en lo que se envía)', len(rows(pg)) == 1 and pg.input_value('#us-q') == 'ana@' and fn_calls('admin_list_users')[-1]['body']['p_search'] == 'ana@', (pg.input_value('#us-q'), fn_calls('admin_list_users')[-1]['body']))
    users_filter(pg, '%'); n_pct = len(rows(pg)); users_filter(pg, '_'); n_us = len(rows(pg))
    check('4.4 «%» y «_» se buscan como texto literal (no como comodines): «_» solo encuentra el nombre que de verdad lo contiene', n_pct == 0 and n_us == 1, (n_pct, n_us))
    users_filter(pg, 'masa')
    check('4.5 Buscar «masa» da 30 resultados en 2 páginas y volver a buscar reinicia en la primera', len(rows(pg)) == 25 and 'de 30' in txt(pg, '.adm-pager'))
    users_filter(pg, '')
    by = {r['id']: r for r in rows(pg)}
    users_filter(pg, 'dani'); r_adm = rows(pg)[0]
    users_filter(pg, 'susi'); r_sus = rows(pg)[0]
    check('4.6 Las insignias distinguen a las cuentas de administración y a las suspendidas', 'Administrador' in r_adm['badges'] and 'Suspendida' in r_sus['badges'], (r_adm['badges'], r_sus['badges']))
    users_filter(pg, 'bruno')
    r = rows(pg)[0]
    check('4.7 Un nombre con HTML se muestra como texto y no se ejecuta', HOSTILE in r['text'] and not hostile_ran(pg) and pg.locator('#ad-view img').count() == 0, r['text'][:100])
    users_filter(pg, 'ana@'); open_user(pg, ANA)
    d = txt(pg, '#ad-view .adm-dl')
    check('4.8 La ficha muestra correo, tipo, plan, conteos y solicitud', all(x in d for x in ('ana@ejemplo.mx', 'Dueño de mascota', 'Huellita Básica', 'Mascotas\n1', 'Ninguna en revisión', 'Sin registro')), d)
    check('4.9 La ficha no revela el contenido de las mascotas ni de las conversaciones (solo conteos)', 'SecretoNube' not in txt(pg, '#ad-view') and 'solo ves datos de la cuenta y conteos' in txt(pg, '#ad-view'))
    # suspender
    n0 = len(be.audit_rows())
    pg.fill('#us-reason', 'Reporte de abuso en el chat')
    confirm(pg, '#ad-view', 'Suspender cuenta')
    m = wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Reactivar cuenta')")
    prof = be.one('profiles', ANA); au = be.audit_rows('user_suspend')
    nt = json.loads(be.sql(f"select coalesce(json_agg(to_jsonb(n)), '[]'::json) from public.notifications n where user_id = '{ANA}' and title = 'Tu cuenta fue suspendida'"))
    check('4.10 Suspender: la cuenta queda suspendida, hay 1 línea de bitácora con el motivo y la persona recibe un aviso con el motivo',
          prof['is_suspended'] and len(au) == 1 and au[0]['details']['reason'] == 'Reporte de abuso en el chat' and au[0]['admin_id'] == ADMIN and len(nt) == 1 and nt[0]['body'] == 'Reporte de abuso en el chat', (prof['is_suspended'], au, nt))
    check('4.11 Se avisa con un mensaje de éxito (rol status) y la ficha ahora dice «Suspendida» con el botón «Reactivar cuenta»', m['role'] == 'status' and 'suspendida' in m['text'].lower() and 'Suspendida' in txt(pg, '#ad-view .badge'), m)
    # reactivar con doble clic: una sola vez
    pg.click('#ad-view button:text-is("Reactivar cuenta")'); waitjs(pg, "!!document.querySelector('.adm-ask')")
    pg.dblclick('#ad-view .adm-ask button:text-is("Sí")')
    wait_say(pg, 'ok'); settle(pg, 300)
    check('4.12 Reactivar con doble clic registra una sola acción (no hay dobles envíos)', len(be.audit_rows('user_reactivate')) == 1 and not be.one('profiles', ANA)['is_suspended'], be.audit_rows('user_reactivate'))
    # cancelar la confirmación no hace nada
    n1 = len(admin_calls())
    pg.click('#ad-view button:text-is("Suspender cuenta")'); waitjs(pg, "!!document.querySelector('.adm-ask')")
    check('4.13 Al pedir confirmación el foco pasa a «No» (acción segura por defecto)', pg.evaluate("document.activeElement.textContent") == 'No')
    pg.click('.adm-ask button:text-is("No")'); settle(pg, 150)
    check('4.14 Responder «No» no llama al servidor y deja el botón original con el foco', len(admin_calls()) == n1 and pg.evaluate("document.activeElement.textContent") == 'Suspender cuenta' and not be.one('profiles', ANA)['is_suspended'])
    # una cuenta de administración no se suspende
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY); users_filter(pg, 'eli@'); open_user(pg, ADMIN2)
    check('4.15 En la ficha de una cuenta de administración no hay botón de suspender', pg.locator('#ad-view button:text-is("Suspender cuenta")').count() == 0 and 'no se pueden suspender' in txt(pg, '#ad-view'))
    r = api(pg, 'admin_set_user_suspended', {'p_user': ADMIN2, 'p_suspended': True})
    check('4.16 Aunque se intente desde la consola, el servidor no deja suspender a un administrador', not r['ok'] and 'administrador' in r['msg'] and not be.one('profiles', ADMIN2)['is_suspended'], r)
    # asignar plan
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY); users_filter(pg, 'ana@'); open_user(pg, ANA)
    opts = pg.evaluate("Array.from(document.querySelectorAll('#us-plan option')).map(o => o.textContent)")
    check('4.17 A una dueña de mascota solo se le ofrecen planes de dueño (Pro y VIP)', opts == ['Huellita Pro', 'Huellita VIP'], opts)
    pg.select_option('#us-plan', 'vip'); pg.select_option('#us-period', 'yearly'); pg.fill('#us-end', '2027-03-15'); pg.fill('#us-note', 'Cortesía de lanzamiento')
    pg.click('#ad-view form[aria-label="Asignar un plan"] button[type=submit]')
    m = wait_say(pg, 'ok'); waitjs(pg, "/Huellita VIP/.test(document.querySelector('#ad-view .adm-dl').textContent)")
    sub = be.sub(ANA); endd = be.sql(f"select to_char(ends_at at time zone 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') from public.subscriptions where id = '{sub['id']}'")
    check('4.18 Asignar plan crea la suscripción VIP anual con el vencimiento elegido (fin del día en México), nota y bitácora, sin cobros',
          sub['plan_id'] == 'vip' and sub['billing_period'] == 'yearly' and endd == '2027-03-15 23:59:59' and sub['note'] == 'Cortesía de lanzamiento' and sub['assigned_by'] == ADMIN
          and len(be.audit_rows('subscription_assign')) == 1 and 'sin ningún cobro' in m['text'], (sub, endd))
    check('4.19 La persona recibe el aviso «Tu suscripción cambió»', int(be.sql(f"select count(*) from public.notifications where user_id = '{ANA}' and title = 'Tu suscripción cambió'")) == 1)
    check('4.20 La ficha ofrece «Ver en Suscripciones» y lleva a esa suscripción', pg.locator('#ad-view button:text-is("Ver en Suscripciones")').count() == 1)
    pg.click('button:text-is("Ver en Suscripciones")'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'subs'"); waitjs(pg, READY)
    check('4.21 …y abre la pestaña Suscripciones filtrada por ese correo', pg.evaluate("document.querySelector('.tabs button[aria-current=page]').dataset.tab") == 'subs' and pg.input_value('#su-q') == 'ana@ejemplo.mx' and len(rows(pg)) == 1, txt(pg, '#ad-view')[:200])
    # aliado
    go(pg, 'usuarios'); users_filter(pg, 'cris@'); open_user(pg, CRIS)
    opts = pg.evaluate("Array.from(document.querySelectorAll('#us-plan option')).map(o => o.textContent)")
    check('4.22 A un aliado comercial solo se le ofrecen planes de aliado (Plata y Oro)', opts == ['Huellita de Plata', 'Huellita de Oro'], opts)
    pg.click('#ad-view form[aria-label="Asignar un plan"] button[type=submit]'); wait_say(pg, 'ok'); settle(pg, 200)
    sub = be.sub(CRIS); days = float(be.sql(f"select extract(epoch from (ends_at - starts_at))/86400 from public.subscriptions where id = '{sub['id']}'"))
    check('4.23 Sin fecha de vencimiento, el plan mensual dura un mes', sub['plan_id'] == 'plata' and sub['billing_period'] == 'monthly' and 27.9 < days < 31.1, (sub, days))
    # errores
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path.endswith('/admin_set_user_suspended') else None
    go(pg, 'usuarios'); users_filter(pg, 'ana@'); open_user(pg, ANA)
    confirm(pg, '#ad-view', 'Suspender cuenta'); m = wait_say(pg, 'err')
    check('4.24 Si el servidor falla al suspender se muestra el error (rol alert), no se cambia nada y se puede reintentar', m['role'] == 'alert' and not be.one('profiles', ANA)['is_suspended'] and pg.locator('#ad-view .adm-ask button:text-is("Sí")').is_enabled(), m)
    be.fail_rest = None
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path.endswith('/admin_list_users') else None
    go_ok = pg.click('#ad-nav a[data-sec=dash]'); waitjs(pg, READY); pg.click('#ad-nav a[data-sec=usuarios]')
    waitjs(pg, "!!document.querySelector('#ad-view .msg.err')")
    check('4.25 Si falla la lista aparece el error con «Reintentar»', pg.locator('#ad-view button:text-is("Reintentar")').count() == 1)
    be.fail_rest = None; pg.click('#ad-view button:text-is("Reintentar")'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length > 0")
    check('4.26 «Reintentar» recupera la lista', len(rows(pg)) == 25)
    pg.evaluate("TPAdmin.go('usuarios', {id: '11111111-1111-4111-8111-111111111111'})"); waitjs(pg, "!!document.querySelector('#ad-view .msg.err')")
    check('4.27 Abrir una cuenta que no existe muestra un error entendible (sin «null»)', 'Usuario no encontrado' in txt(pg, '#ad-view') or 'No se encontró' in txt(pg, '#ad-view') or pg.locator('#ad-view .msg.err').count() == 1, txt(pg, '#ad-view'))
    check('4.28 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not [m for m in csp_problems(log)] and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()

STATUS_OPTS = "Array.from(document.querySelectorAll('#al-status option')).map(o => o.value)"
def open_biz(pg, bid):
    pg.click(f'#ad-view .adm-row[data-id="{bid}"] button:has-text("Revisar")')
    waitjs(pg, "!!document.querySelector('#ad-view .adm-dl') && !/Cargando/.test(document.querySelector('#ad-view .adm-sec').textContent)")
def biz(bid): return be.one('businesses', bid)

def g5(br):
    print('\n[5] Aliados')
    reset_state()
    p1 = be.add_biz(CRIS, 'Clínica Huellitas', status='pending', maps_query='Clínica Huellitas Zapopan')
    p2 = be.add_biz(BRUNO, HOSTILE, status='pending', description=HOSTILE)
    a1 = be.add_biz(CRIS, 'Estética Luna', 'estetica_canina', status='approved', municipality='Tlaquepaque')
    r1 = be.add_biz(CRIS, 'Tienda Rota', 'tienda', status='rejected'); s1 = be.add_biz(CRIS, 'Dog Spa', 'estetica_canina', status='suspended')
    dm = be.add_biz(None, 'Demo Veterinaria', status='approved', demo=True)
    pr = be.add_promo(p1, '2x1 en baños', 'Solo entre semana'); be.add_promo(p1, 'Vacuna gratis', HOSTILE, days=5, active=False)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    go(pg, 'aliados')
    rs = rows(pg)
    check('5.1 Por omisión se muestran los establecimientos «En revisión» (2)', {r['id'] for r in rs} == {p1, p2} and pg.input_value('#al-status') == 'pending', rs)
    check('5.2 Un nombre y una descripción con HTML se muestran como texto y no se ejecutan', any(HOSTILE in r['text'] for r in rs) and not hostile_ran(pg) and pg.locator('#ad-view img').count() == 0)
    pg.select_option('#al-status', 'approved'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    rs = {r['id']: r for r in rows(pg)}
    check('5.3 Filtrar «Aprobados» muestra el aliado y la ficha de demostración, esta marcada como tal', set(rs) == {a1, dm} and 'Demostración' in rs[dm]['badges'], rs.keys())
    pg.select_option('#al-status', ''); pg.fill('#al-q', 'tlaquepaque'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('5.4 Buscar por municipio sobre «Todos» encuentra el establecimiento', [r['id'] for r in rows(pg)] == [a1])
    pg.fill('#al-q', 'cris@ejemplo'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('5.5 Buscar por correo del dueño encuentra sus 4 establecimientos', len(rows(pg)) == 4)
    pg.fill('#al-q', ''); pg.select_option('#al-status', 'pending'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    open_biz(pg, p1)
    d = txt(pg, '#ad-view .adm-dl')
    check('5.6 La ficha muestra categoría, dirección, dueño, plan y horario («Sin horario»)', all(x in d for x in ('Veterinaria', 'Calle 5 #10', 'Zapopan, Jalisco', 'cris@ejemplo.mx', 'Sin plan', 'Sin horario')), d)
    href = pg.get_attribute('#ad-view a:has-text("Google Maps")', 'href'); rel = pg.get_attribute('#ad-view a:has-text("Google Maps")', 'rel')
    check('5.7 El enlace de mapa va a Google Maps (búsqueda directa), en pestaña nueva con noopener', href == 'https://www.google.com/maps/search/?api=1&query=' + 'Cl%C3%ADnica%20Huellitas%20Zapopan' and 'noopener' in rel, (href, rel))
    check('5.8 En revisión solo ofrece Aprobar y Rechazar; la verificación explica que exige estar aprobado',
          pg.locator('#ad-view button:text-is("Aprobar")').count() == 1 and pg.locator('#ad-view button:text-is("Rechazar")').count() == 1 and pg.locator('#ad-view button:text-is("Suspender")').count() == 0
          and 'solo se puede dar a establecimientos aprobados' in txt(pg, '#ad-view'))
    check('5.9 Las 2 promociones aparecen, con su estado y fechas', pg.locator('#ad-view [data-promo]').count() == 2 and 'Activa' in pg.evaluate("Array.from(document.querySelectorAll('#ad-view [data-promo] .badge')).map(b => b.textContent)") and 'Inactiva' in txt(pg, '#ad-view'))
    inputs = pg.evaluate("Array.from(document.querySelectorAll('#ad-view input, #ad-view textarea, #ad-view select')).map(e => e.getAttribute('aria-label') || (e.labels[0] && e.labels[0].textContent) || '?')")
    check('5.10 El panel no permite editar los datos del establecimiento: los únicos campos son los motivos de retiro de promociones', all('Motivo' in i for i in inputs) and len(inputs) == 2, inputs)
    # aprobar
    confirm(pg, '#ad-view', 'Aprobar'); m = wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Suspender')")
    nt = be.sql(f"select count(*) from public.notifications where user_id = '{CRIS}' and title = 'Actualización de tu establecimiento' and body like '%aprobado%'")
    check('5.11 Aprobar cambia el estado, avisa al dueño y queda en la bitácora', biz(p1)['status'] == 'approved' and nt == '1' and len(be.audit_rows('business_status')) == 1 and be.audit_rows('business_status')[0]['details']['status'] == 'approved', m)
    check('5.12 Ya aprobado ofrece Suspender, Regresar a revisión y la verificación; ya no Aprobar/Rechazar', pg.locator('#ad-view button:text-is("Aprobar")').count() == 0 and pg.locator('#ad-view button:text-is("Rechazar")').count() == 0 and pg.locator('#ad-view button:text-is("Suspender")').count() == 1
          and pg.locator('#ad-view button:text-is("Regresar a revisión")').count() == 1 and pg.locator('#ad-view button:text-is("Marcar como verificado")').count() == 1)
    check('5.13 Sin un plan que incluya la etiqueta, se avisa que no se mostrará', 'no se mostrará hasta que tenga un plan que la incluya' in txt(pg, '#ad-view'))
    confirm(pg, '#ad-view', 'Marcar como verificado'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Quitar verificación')")
    check('5.14 Verificar: queda verificado con fecha y en la bitácora', biz(p1)['verified'] and biz(p1)['verified_at'] and len(be.audit_rows('business_verify')) == 1)
    confirm(pg, '#ad-view', 'Suspender'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Aprobar')")
    check('5.15 Suspender retira el establecimiento, le quita la verificación y ya no ofrece «Rechazar»', biz(p1)['status'] == 'suspended' and not biz(p1)['verified'] and not biz(p1)['verified_at'] and pg.locator('#ad-view button:text-is("Rechazar")').count() == 0)
    confirm(pg, '#ad-view', 'Regresar a revisión'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Rechazar')")
    check('5.16 «Regresar a revisión» devuelve el estado a pendiente', biz(p1)['status'] == 'pending')
    confirm(pg, '#ad-view', 'Rechazar'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Aprobar')")
    check('5.17 Rechazar guarda el estado y avisa al dueño', biz(p1)['status'] == 'rejected' and int(be.sql(f"select count(*) from public.notifications where user_id = '{CRIS}' and body like '%no fue aprobado%'")) == 1)
    # plan que incluye verificación
    be.assign(CRIS, 'oro')
    pg.click('#ad-view button:text-is("Aprobar")'); pg.click('.adm-ask button:text-is("Sí")'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Marcar como verificado')")
    check('5.18 Con el plan de Oro ya no aparece el aviso de que la etiqueta no se mostrará', 'no se mostrará' not in txt(pg, '#ad-view') and 'Huellita de Oro' in txt(pg, '#ad-view .adm-dl'))
    # promociones
    ptxt = txt(pg, '#ad-view')
    check('5.18b Las promociones muestran sus fechas con formato en español, y una descripción con HTML se ve como texto', re.search(r'Del \d{1,2} [a-z]{3,4} 20\d\d al \d{1,2} [a-z]{3,4} 20\d\d', ptxt) is not None and HOSTILE in ptxt and not hostile_ran(pg) and pg.locator('#ad-view [data-promo] img').count() == 0, ptxt[-300:])
    pg.fill('#ad-view [data-promo] input[aria-label^="Motivo del retiro de «2x1"]', 'Precio engañoso')
    confirm(pg, f'#ad-view [data-promo="{pr}"]', 'Retirar promoción'); m = wait_say(pg, 'ok'); waitjs(pg, "document.querySelectorAll('#ad-view [data-promo]').length === 1")
    nt = be.sql(f"select body from public.notifications where user_id = '{CRIS}' and title = 'Se retiró una promoción'")
    au = be.audit_rows('promotion_delete')
    check('5.19 Retirar una promoción la borra, avisa al dueño con el motivo y queda en la bitácora', be.one('business_promotions', pr) is None and nt == 'Precio engañoso' and len(au) == 1 and au[0]['details']['reason'] == 'Precio engañoso', (nt, au))
    pg.click('#ad-view [data-promo] button:text-is("Retirar promoción")'); pg.click('.adm-ask button:text-is("Sí")'); wait_say(pg, 'ok'); waitjs(pg, "document.querySelectorAll('#ad-view [data-promo]').length === 0")
    check('5.20 Sin motivo, el aviso al dueño usa un texto estándar', int(be.sql(f"select count(*) from public.notifications where user_id = '{CRIS}' and title = 'Se retiró una promoción' and body = 'No cumplía las reglas del directorio.'")) == 1)
    check('5.21 Sin promociones se dice así', 'no tiene promociones' in txt(pg, '#ad-view'))
    pg.click('#ad-view button:text-is("Ver cuenta del dueño")'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'usuarios'"); waitjs(pg, READY); waitjs(pg, "!!document.querySelector('#ad-view .adm-dl')")
    check('5.22 «Ver cuenta del dueño» abre la ficha de esa cuenta', 'cris@ejemplo.mx' in txt(pg, '#ad-view .adm-dl'))
    # estado vacío y errores
    go(pg, 'aliados'); pg.select_option('#al-status', 'pending'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    open_biz(pg, p2)
    check('5.23 La ficha con HTML en nombre y descripción también se muestra como texto', HOSTILE in txt(pg, '#ad-view h3') and not hostile_ran(pg) and pg.locator('#ad-view img').count() == 0)
    r = api(pg, 'admin_set_business_status', {'p_business': p2, 'p_status': 'borrado'})
    check('5.24 El servidor rechaza un estado inventado', not r['ok'] and 'Estado no válido' in r['msg'] and biz(p2)['status'] == 'pending', r)
    r = api(pg, 'admin_set_business_verified', {'p_business': p2, 'p_verified': True})
    check('5.25 El servidor rechaza verificar un establecimiento que no está aprobado', not r['ok'] and 'aprobado' in r['msg'] and not biz(p2)['verified'], r)
    check('5.26 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()


def open_complaint(pg, cid):
    pg.click(f'#ad-view .adm-row[data-id="{cid}"] button:has-text("Abrir")')
    waitjs(pg, "!!document.querySelector('#ad-view .adm-dl') && !/Cargando/.test(document.querySelector('#ad-view .adm-sec').textContent)")
def anon_track(code):
    ok, out = be.psql_anon(f"select to_json(public.track_complaint('{code}'));")
    return json.loads(out) if ok and out else None

def g6(br):
    print('\n[6] Denuncias')
    reset_state()
    long_desc = 'Hay un perro encadenado sin sombra ' + ('y sin agua durante varios días seguidos. ' * 8) + 'FINAL-UNICO'
    c1 = be.add_complaint('TP-AAAA-BBBB', 'maltrato_fisico', 'recibida', long_desc, photos=2, ago_min=5, extra='El vecino dice que no es la primera vez')
    c2 = be.add_complaint('TP-CCCC-DDDD', 'abandono', 'en_revision', ago_min=20, priority='alta')
    c3 = be.add_complaint('TP-EEEE-FFFF', 'otra', 'cerrada', ago_min=60)
    c4 = be.add_complaint('TP-GGGG-HHHH', 'comercio_ilegal', 'recibida', description='Venta de cachorros: ' + HOSTILE, ago_min=2, state='Nuevo León', municipality='Monterrey')
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    go(pg, 'denuncias')
    rs = rows(pg)
    check('6.1 Por omisión se muestran las pendientes (recibidas y en revisión), la más nueva primero', [r['id'] for r in rs] == [c4, c1, c2], [r['code'] for r in rs])
    r1 = [r for r in rs if r['id'] == c1][0]
    check('6.2 Cada fila muestra código, estado, tipo, lugar y número de fotos', all(x in r1['text'] for x in ('TP-AAAA-BBBB', 'Maltrato físico', 'Zapopan, Jalisco', '2 foto(s)')) and 'Recibida' in r1['badges'], r1['text'])
    check('6.3 El extracto se corta a 160 caracteres y termina en «…»', '…' in r1['text'] and long_desc[:60] in r1['text'] and 'FINAL-UNICO' not in r1['text'])
    check('6.4 Una descripción con HTML se muestra como texto y no se ejecuta', any(HOSTILE in r['text'] for r in rs) and not hostile_ran(pg) and pg.locator('#ad-view img').count() == 0)
    check('6.5 La prioridad aparece solo donde existe', any('Prioridad alta' in b for b in [x for r in rs if r['id'] == c2 for x in r['badges']]) and not any('Prioridad' in b for b in r1['badges']))
    pg.select_option('#dn-filtro', 'cerrada'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 1"); 
    check('6.6 El filtro «Cerradas» muestra solo la cerrada', [r['id'] for r in rows(pg)] == [c3])
    pg.select_option('#dn-filtro', ''); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 4")
    check('6.7 «Todas» muestra las 4', len(rows(pg)) == 4)
    pg.select_option('#dn-filtro', 'pendientes'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 3")
    # detalle y fotos
    n_sign = len(be.sign_log); open_complaint(pg, c1)
    waitjs(pg, "document.querySelectorAll('#ad-view .adm-photos img').length === 2")
    d = txt(pg, '#ad-view')
    check('6.8 El detalle muestra descripción completa, lugar, referencia e información adicional', 'FINAL-UNICO' in d and 'Frente a la tienda azul' in d and 'El vecino dice que no es la primera vez' in d and 'Maltrato físico' in d)
    check('6.9 Se dice que la denuncia es anónima y no hay ningún dato de quien reporta (ni correo, ni cuenta, ni IP)', 'anónima' in d and not re.search(r'@|correo|IP\b|cuenta de', d.replace('ana@', '')), d[:400])
    imgs = pg.evaluate("Array.from(document.querySelectorAll('#ad-view .adm-photos img')).map(i => ({src: i.src, alt: i.alt, w: i.closest('a').target, rel: i.closest('a').rel, rp: i.referrerPolicy}))")
    sg = be.sign_log[n_sign:]
    check('6.10 Las fotos se piden con enlace firmado de 10 minutos, solo por un administrador, y se muestran con texto alternativo, en pestaña nueva con noopener y sin enviar la página de origen',
          len(sg) == 1 and sg[0]['uid'] == ADMIN and sg[0]['expiresIn'] == 600 and all(i['src'].startswith('https://mtkbxnhsjqqdbrjeaslo.supabase.co/storage/v1/object/sign/complaint-evidence/') and 'token=' in i['src'] for i in imgs)
          and [i['alt'] for i in imgs] == ['Foto de evidencia 1', 'Foto de evidencia 2'] and all(i['w'] == '_blank' and 'noopener' in i['rel'] and i['rp'] == 'no-referrer' for i in imgs), (sg, imgs))
    check('6.11 Hay un recordatorio de que «Canalizada» no significa denuncia oficial presentada', 'No significa que TECNOPATITAS haya presentado una denuncia oficial' in d)
    # guardar seguimiento
    pg.select_option('#dn-estado', 'en_proceso'); pg.select_option('#dn-prio', 'alta'); pg.check('#dn-atendida')
    pg.fill('#dn-publica', 'Estamos dando seguimiento a tu reporte'); pg.fill('#dn-notas', 'Llamé al refugio; pendiente respuesta')
    pg.click('#ad-view form[aria-label="Seguimiento de la denuncia"] button[type=submit]')
    m = wait_say(pg, 'ok'); waitjs(pg, "document.querySelector('#ad-view .badge') && /En proceso/.test(document.querySelector('#ad-view .adm-card').textContent)")
    row_ = be.one('complaints', c1); au = be.audit_rows('complaint_update')
    check('6.12 Guardar: estado, prioridad, atendida y las dos notas quedan en la base, con una línea de bitácora (sin el texto de las notas)',
          row_['status'] == 'en_proceso' and row_['priority'] == 'alta' and row_['attended'] and row_['attended_at'] and row_['public_update'] == 'Estamos dando seguimiento a tu reporte'
          and row_['internal_notes'] == 'Llamé al refugio; pendiente respuesta' and len(au) == 1 and au[0]['details']['status_to'] == 'en_proceso' and 'Llamé' not in json.dumps(au[0]), (row_, au))
    check('6.13 Quien tiene el código ve la actualización pública pero NUNCA las notas internas', (anon_track('TP-AAAA-BBBB') or {}).get('public_update') == 'Estamos dando seguimiento a tu reporte' and 'Llamé' not in json.dumps(anon_track('TP-AAAA-BBBB')), anon_track('TP-AAAA-BBBB'))
    check('6.14 La pantalla vuelve a cargar el registro con los valores guardados', pg.input_value('#dn-estado') == 'en_proceso' and pg.input_value('#dn-prio') == 'alta' and pg.is_checked('#dn-atendida') and pg.input_value('#dn-notas').startswith('Llamé'))
    # límites que impone el servidor (saltándose el maxlength del navegador)
    pg.evaluate("document.getElementById('dn-publica').value = 'x'.repeat(501)")
    pg.click('#ad-view form[aria-label="Seguimiento de la denuncia"] button[type=submit]'); m = wait_say(pg, 'err')
    check('6.15 Una actualización pública de más de 500 caracteres la rechaza el servidor con un mensaje claro y no cambia nada', 'hasta 500 caracteres' in m['text'] and be.one('complaints', c1)['public_update'] == 'Estamos dando seguimiento a tu reporte', m)
    pg.evaluate("document.getElementById('dn-publica').value = 'ok'; document.getElementById('dn-notas').value = 'y'.repeat(4001)")
    pg.click('#ad-view form[aria-label="Seguimiento de la denuncia"] button[type=submit]'); m = wait_say(pg, 'err')
    check('6.16 Notas internas de más de 4000 caracteres: el servidor las rechaza', 'hasta 4000 caracteres' in m['text'] and be.one('complaints', c1)['internal_notes'].startswith('Llamé'), m)
    r = api(pg, 'admin_update_complaint', {'p_id': c1, 'p_status': 'borrada'})
    check('6.17 Un estado inventado lo rechaza el servidor', not r['ok'] and 'Estado no válido' in r['msg'], r)
    check('6.18 Los atributos maxlength del formulario limitan 500 y 4000 caracteres', pg.get_attribute('#dn-publica', 'maxlength') == '500' and pg.get_attribute('#dn-notas', 'maxlength') == '4000')
    # canalizada y cerrada
    pg.fill('#dn-notas', 'Canalizada al refugio municipal'); pg.select_option('#dn-estado', 'canalizada')
    pg.click('#ad-view form[aria-label="Seguimiento de la denuncia"] button[type=submit]'); wait_say(pg, 'ok')
    check('6.19 «Canalizada» se guarda como estado, sin que el sistema afirme que se presentó una denuncia oficial', be.one('complaints', c1)['status'] == 'canalizada' and 'oficial' not in (anon_track('TP-AAAA-BBBB') or {}).get('public_update', ''))
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY)
    check('6.20 Al volver, la lista ya no incluye la denuncia canalizada (filtro «pendientes»)', c1 not in [r['id'] for r in rows(pg)] and len(rows(pg)) == 2)
    # sin fotos / fallo de firma
    pg.select_option('#dn-filtro', ''); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 4"); n_sign = len(be.sign_log); open_complaint(pg, c2); settle(pg, 300)
    check('6.21 Una denuncia sin fotos lo dice y no pide firmas al almacenamiento', 'no incluye fotos' in txt(pg, '#ad-view') and len(be.sign_log) == n_sign, (n_sign, len(be.sign_log)))
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY)
    c5 = be.add_complaint('TP-JJJJ-KKKK', photos=1, ago_min=1)
    pg.click('#ad-nav a[data-sec=dash]'); waitjs(pg, READY); go(pg, 'denuncias')
    be.storage_fail = 500
    open_complaint(pg, c5); waitjs(pg, "!!document.querySelector('#ad-view .adm-photos .msg.err')")
    check('6.22 Si el almacenamiento falla, la denuncia se ve igual y las fotos muestran un aviso', 'No se pudieron cargar las fotos' in txt(pg, '#ad-view .adm-photos') and 'Descripción' in txt(pg, '#ad-view'))
    be.storage_fail = None
    pg.click('#ad-view button:text-is("← Volver a la lista")'); waitjs(pg, "!!document.getElementById('dn-filtro')"); pg.select_option('#dn-filtro', ''); waitjs(pg, f"!!document.querySelector('#ad-view .adm-row[data-id=\"{c4}\"]')")
    open_complaint(pg, c4); waitjs(pg, "!!document.querySelector('#ad-view .adm-dl')")
    check('6.22b La ficha de una denuncia con HTML en su descripción lo muestra como texto y no lo ejecuta', HOSTILE in txt(pg, '#ad-view .adm-text') and not hostile_ran(pg) and pg.locator('#ad-view .adm-text img').count() == 0, txt(pg, '#ad-view .adm-text')[:120])
    # una cuenta que no es de administración NO puede firmar fotos
    ctx2, pg2, log2 = open_admin(br, 'ana@ejemplo.mx', page='perfil.html')
    r = pg2.evaluate("""async (p) => { try { return {ok: true, r: await TP.storage.sign('complaint-evidence', [p])}; } catch (e) { return {ok: false, code: e.code}; } }""", be.one('complaints', c5)['photo_paths'][0])
    check('6.23 Una cuenta que no es de administración no obtiene enlaces firmados de la evidencia', (r['ok'] and r['r'] == {}) or not r['ok'], r)
    ctx2.close()
    check('6.24 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()

def open_guide_form(pg, gid=None):
    if gid: pg.click(f'#ad-view .adm-row[data-id="{gid}"] button:has-text("Editar")')
    else: pg.click('#gu-nueva')
    waitjs(pg, "!!document.getElementById('gu-titulo')")
def fill_guide(pg, title=None, slug=None, cat=None, summary=None, content=None, source=None, publish=None):
    if title is not None: pg.fill('#gu-titulo', title)
    if slug is not None: pg.fill('#gu-slug', slug)
    if cat is not None: pg.select_option('#gu-categoria', cat)
    if summary is not None: pg.fill('#gu-resumen', summary)
    if content is not None: pg.fill('#gu-contenido', content)
    if source is not None: pg.fill('#gu-fuente', source)
    if publish is not None: pg.set_checked('#gu-publicar', publish)
def save_guide(pg):
    pg.click('#ad-view form[aria-label] button[type=submit]')
def guide(slug):
    out = be.sql(f"select to_jsonb(g) from public.care_guides g where slug = '{slug}'")
    return json.loads(out) if out else None

def g7(br):
    print('\n[7] Guías (editor)')
    reset_state()
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    go(pg, 'guias')
    check('7.1 Sin guías se muestra un estado vacío con la invitación a crear la primera', 'No hay guías' in txt(pg, '#ad-view') and pg.locator('#gu-nueva').count() == 1)
    open_guide_form(pg)
    check('7.2 La guía nueva empieza como borrador (casilla «Publicar» sin marcar) y recuerda que no sustituye a un veterinario', not pg.is_checked('#gu-publicar') and 'sustituyen la consulta con un veterinario' in txt(pg, '#ad-view'))
    pg.fill('#gu-titulo', 'Cuidados del Gato: ¡Básicos!')
    check('7.3 La dirección se propone sola desde el título (sin acentos ni signos)', pg.input_value('#gu-slug') == 'cuidados-del-gato-basicos', pg.input_value('#gu-slug'))
    pg.fill('#gu-slug', 'gato-basico'); pg.fill('#gu-titulo', 'Cuidados del gato básico')
    check('7.4 Si la editas a mano, ya no se pisa al seguir escribiendo el título', pg.input_value('#gu-slug') == 'gato-basico')
    pg.fill('#gu-contenido', 'Hola'); 
    check('7.5 El contador de caracteres se actualiza', '4 de 20000' in txt(pg, '#gu-cuenta'))
    # validaciones del navegador (el servidor repite todas)
    n0 = len(fn_calls('admin_save_guide'))
    fill_guide(pg, title='Hi'); save_guide(pg); m = wait_say(pg, 'err')
    check('7.6 Un título muy corto se avisa en pantalla, el foco va al campo y no se llama al servidor', 'título' in m['text'] and pg.evaluate("document.activeElement.id") == 'gu-titulo' and len(fn_calls('admin_save_guide')) == n0, m)
    fill_guide(pg, title='Cuidados del gato básico', slug='Mi Guía'); save_guide(pg); m = wait_say(pg, 'err')
    check('7.7 Una dirección con mayúsculas, espacios o acentos se rechaza antes de enviar', 'dirección' in m['text'] and pg.evaluate("document.activeElement.id") == 'gu-slug' and len(fn_calls('admin_save_guide')) == n0)
    fill_guide(pg, slug='gato-basico', content='   '); save_guide(pg); m = wait_say(pg, 'err')
    check('7.8 Un contenido vacío (solo espacios) se rechaza', 'contenido' in m['text'] and pg.evaluate("document.activeElement.id") == 'gu-contenido')
    pg.evaluate("document.getElementById('gu-contenido').value = 'z'.repeat(20001)"); save_guide(pg); m = wait_say(pg, 'err')
    check('7.9 Más de 20000 caracteres se rechazan antes de enviar', '20000' in m['text'] and len(fn_calls('admin_save_guide')) == n0)
    content = 'Primer párrafo del cuidado.\n\n## Alimentación\n\nDar agua fresca y alimento adecuado.\n\n<script>window.__pwn=1</script> <img src=x onerror="window.__pwn=1">'
    fill_guide(pg, content='\n  ' + content + '  \n\n', summary='Lo esencial para tu gato', cat='gatos', source='Contenido general de ejemplo, pendiente de revisión veterinaria')
    pg.click('#gu-vista'); waitjs(pg, "!document.getElementById('gu-prev').hidden")
    prev = pg.evaluate("({h3: Array.from(document.querySelectorAll('#gu-prev h3')).map(x => x.textContent), p: document.querySelectorAll('#gu-prev p.gd-p').length, imgs: document.querySelectorAll('#gu-prev img, #gu-prev script').length})")
    check('7.10 La vista previa muestra título, subtítulo («## ») y párrafos; el HTML escrito se ve como texto y no se ejecuta', prev['h3'] == ['Cuidados del gato básico', 'Alimentación'] and prev['p'] == 3 and prev['imgs'] == 0 and not hostile_ran(pg), prev)
    n_sv = len(fn_calls('admin_save_guide'))
    save_guide(pg); m = wait_say(pg, 'ok'); waitjs(pg, "/Editar guía/.test(document.querySelector('#ad-view h3').textContent)")
    g = guide('gato-basico'); au = be.audit_rows('guide_create')
    check('7.10b El navegador envía el texto sin espacios ni saltos de línea sobrantes al inicio y al final', fn_calls('admin_save_guide')[n_sv]['body']['p_content'] == content, fn_calls('admin_save_guide')[n_sv]['body']['p_content'][:60])
    check('7.11 Guardar crea la guía como BORRADOR (sin fecha de publicación), con una línea de bitácora que no incluye el contenido',
          g and not g['is_published'] and g['published_at'] is None and g['category'] == 'gatos' and g['content'] == content.strip() and len(au) == 1 and set(au[0]['details']) == {'slug', 'published'} and 'párrafo' not in json.dumps(au[0]), (g, au))
    check('7.12 El mensaje dice que es borrador y que el público no la ve; el formulario pasa a «Editar guía» con la guía cargada', 'borrador' in m['text'] and pg.input_value('#gu-titulo') == 'Cuidados del gato básico' and 'Borrador' in txt(pg, '#ad-view .badge'))
    # publicar
    pg.check('#gu-publicar'); save_guide(pg); m = wait_say(pg, 'ok'); settle(pg, 200)
    g = guide('gato-basico')
    check('7.13 Publicar marca la guía como publicada con fecha, y queda «guide_publish» en la bitácora', g['is_published'] and g['published_at'] and len(be.audit_rows('guide_publish')) == 1 and 'publicada' in m['text'], (g, m))
    pub = be.psql_anon("select count(*) from public.care_guides where slug = 'gato-basico';")
    check('7.14 El público (rol anon) ya puede leerla', pub == (True, '1'), pub)
    # duplicado
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY)
    open_guide_form(pg); fill_guide(pg, title='Otra guía', slug='gato-basico', content='Texto'); save_guide(pg); m = wait_say(pg, 'err')
    check('7.15 Una dirección repetida la rechaza el servidor con un mensaje claro y no se crea otra guía', 'Ya existe otra guía con esa dirección' in m['text'] and be.sql("select count(*) from public.care_guides") == '1', m)
    pg.click('button:text-is("Cancelar")'); waitjs(pg, READY)
    check('7.16 «Cancelar» vuelve a la lista sin guardar', len(rows(pg)) == 1)
    g1 = rows(pg)[0]
    check('7.17 La lista muestra la guía publicada con su categoría, fuente y el enlace «Ver publicada» seguro',
          'Publicada' in g1['badges'] and 'Gatos' in g1['text'] and pg.get_attribute('#ad-view a:text-is("Ver publicada")', 'href') == 'guias.html?g=gato-basico' and 'noopener' in pg.get_attribute('#ad-view a:text-is("Ver publicada")', 'rel'), g1)
    # editar y despublicar
    open_guide_form(pg, g1['id']); fill_guide(pg, title='Cuidados del gato (revisado)'); pg.uncheck('#gu-publicar'); save_guide(pg); wait_say(pg, 'ok'); settle(pg, 200)
    g = guide('gato-basico')
    check('7.18 Quitar «Publicar» despublica la guía y lo registra («guide_unpublish»); el título editado se guarda', not g['is_published'] and g['title'] == 'Cuidados del gato (revisado)' and len(be.audit_rows('guide_unpublish')) == 1)
    check('7.19 El público (anon) ya no la ve', be.psql_anon("select count(*) from public.care_guides where slug = 'gato-basico';") == (True, '0'))
    fill_guide(pg, summary='Resumen nuevo'); save_guide(pg); wait_say(pg, 'ok'); settle(pg, 200)
    check('7.20 Editar sin cambiar la publicación registra «guide_update»', len(be.audit_rows('guide_update')) == 1)
    # filtros
    be.add_guide('perros-1', 'Perros uno', 'perros', True); be.add_guide('conejos-1', 'Conejos uno', 'conejos', False)
    pg.click('button:text-is("← Volver a la lista")'); waitjs(pg, READY)
    pg.select_option('#gu-estado', 'draft'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('7.21 El filtro «Borradores» muestra los 2 borradores', {r['slug'] for r in rows(pg)} == {'gato-basico', 'conejos-1'})
    pg.select_option('#gu-estado', 'published'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('7.22 El filtro «Publicadas» muestra solo la publicada', [r['slug'] for r in rows(pg)] == ['perros-1'])
    pg.select_option('#gu-estado', ''); pg.fill('#gu-q', 'conejos'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('7.23 Buscar por título encuentra la guía', [r['slug'] for r in rows(pg)] == ['conejos-1'])
    # eliminar
    gid = rows(pg)[0]['id']; open_guide_form(pg, gid)
    confirm(pg, '#ad-view', 'Eliminar guía'); m = wait_say(pg, 'ok'); waitjs(pg, READY)
    au = be.audit_rows('guide_delete')
    check('7.24 Eliminar pide confirmación, borra la guía, vuelve a la lista y deja «guide_delete» solo con la dirección', guide('conejos-1') is None and len(au) == 1 and set(au[0]['details']) == {'slug'} and 'eliminada' in m['text'] and pg.locator('#gu-nueva').count() == 1 and pg.locator('#gu-titulo').count() == 0, (au, m))
    check('7.25 Una dirección repetida entre mayúsculas: el servidor la normaliza a minúsculas (no existen dos direcciones que solo difieran en la mayúscula)', api(pg, 'admin_save_guide', {'p_id': None, 'p_slug': 'PERROS-1', 'p_title': 'Duplicada', 'p_summary': '', 'p_content': 'x', 'p_category': 'perros'})['ok'] is False)
    check('7.26 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()

def open_sub_tab(pg, tab):
    pg.click(f'.tabs button[data-tab={tab}]'); waitjs(pg, f"document.querySelector('.tabs button[aria-current=page]').dataset.tab === '{tab}'"); waitjs(pg, READY)
def code_of(rid): return rid.replace('-', '')[:8].upper()

def g8(br):
    print('\n[8] Suscripciones y solicitudes de plan')
    reset_state()
    r1 = be.make_request(ANA, 'pro', 'monthly', note='Me interesa el carnet digital', ago_min=300)
    r2 = be.make_request(BRUNO, 'vip', 'yearly', note=HOSTILE, ago_min=200)
    r3 = be.make_request(CRIS, 'plata', 'monthly', ago_min=100)
    old_rej = be.make_request(SUSI, 'pro', status='rejected', admin_note='Cuenta suspendida', ago_min=4000)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', '#subs'); all_logs.append(log)
    rs = rows(pg)
    check('8.1 Abrir #subs muestra «Solicitudes de plan» con las pendientes, la más antigua primero', [r['id'] for r in rs] == [r1, r2, r3], [r['code'] for r in rs])
    check('8.2 Cada solicitud muestra código, correo, tipo de cuenta, plan pedido y periodo, plan actual y el mensaje de la persona',
          all(x in rs[0]['text'] for x in (code_of(r1), 'ana@ejemplo.mx', 'Dueño de mascota', 'Huellita Pro', 'mensual', 'Plan actual: Huellita Básica', 'Me interesa el carnet digital')) and 'anual' in rs[1]['text'] and 'Aliado comercial' in rs[2]['text'], rs[0]['text'])
    settle(pg, 200)
    check('8.2b El mensaje de la persona con HTML se ve como texto y no se ejecuta', HOSTILE in rs[1]['text'] and not hostile_ran(pg) and pg.locator('#ad-view .adm-row img').count() == 0, rs[1]['text'][-120:])
    check('8.3 Se aclara que aprobar no cobra nada', 'No se cobra nada' in txt(pg, '#ad-view'))
    check('8.4 La pestaña activa está marcada (aria-current)', pg.evaluate("document.querySelector('.tabs button[aria-current=page]').dataset.tab") == 'requests')
    # aprobar
    sc = f'#ad-view .adm-row[data-id="{r1}"]'
    pg.fill(f'{sc} input[type=text]', 'Listo, ya está activo'); pg.fill(f'{sc} input[type=date]', '2027-02-10')
    confirm(pg, sc, 'Aprobar y activar plan'); m = wait_say(pg, 'ok'); waitjs(pg, f"!document.querySelector('{sc}')")
    sub = be.sub(ANA); endd = be.sql(f"select to_char(ends_at at time zone 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') from public.subscriptions where id = '{sub['id']}'")
    nt = be.sql(f"select count(*) from public.notifications where user_id = '{ANA}' and title = 'Tu suscripción cambió'")
    check('8.5 Aprobar activa el plan con el vencimiento elegido, resuelve la solicitud, avisa y deja bitácora', sub['plan_id'] == 'pro' and endd == '2027-02-10 23:59:59' and be.reqs(ANA)[0]['status'] == 'approved'
          and be.reqs(ANA)[0]['admin_note'] == 'Listo, ya está activo' and nt == '1' and len(be.audit_rows('plan_request_approve')) == 1 and 'quedó activo' in m['text'], (sub, endd))
    check('8.6 La solicitud resuelta desaparece de «Pendientes» (quedan 2)', len(rows(pg)) == 2)
    # rechazar
    sc = f'#ad-view .adm-row[data-id="{r2}"]'
    pg.fill(f'{sc} input[type=text]', 'Por ahora no tenemos plan anual'); confirm(pg, sc, 'Rechazar'); wait_say(pg, 'ok'); waitjs(pg, f"!document.querySelector('{sc}')")
    nt = be.sql(f"select body from public.notifications where user_id = '{BRUNO}' and title like '%no fue aprobada%'")
    check('8.7 Rechazar deja la nota, avisa a la persona con esa nota, no crea suscripción y queda en bitácora', be.reqs(BRUNO)[0]['status'] == 'rejected' and nt == 'Por ahora no tenemos plan anual' and be.sub(BRUNO) is None and len(be.audit_rows('plan_request_reject')) == 1)
    pg.select_option('#su-rstatus', 'rejected'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 2"); rs = rows(pg)
    check('8.8 El filtro «Rechazadas» muestra la nota del equipo y la fecha de resolución', any('Por ahora no tenemos plan anual' in r['text'] and 'Resuelta' in r['text'] for r in rs) and not any('Aprobar y activar' in r['text'] for r in rs))
    pg.select_option('#su-rstatus', ''); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 4")
    check('8.9 «Todas» muestra las 4 solicitudes', len(rows(pg)) == 4)
    r = api(pg, 'admin_resolve_plan_request', {'p_request': r1, 'p_approve': False})
    check('8.10 Una solicitud ya resuelta no se puede volver a resolver (lo impide el servidor)', not r['ok'] and 'ya fue resuelta' in r['msg'], r)
    r = api(pg, 'admin_assign_subscription', {'p_user': ANA, 'p_plan': 'oro'})
    check('8.11 No se puede dar un plan de aliado a una cuenta de dueño (lo impide el servidor)', not r['ok'] and 'no corresponde' in r['msg'] and be.sub(ANA)['plan_id'] == 'pro', r)
    # suscripciones
    be.assign(BRUNO, 'vip', days=10); be.assign(CRIS, 'plata', days=40)
    open_sub_tab(pg, 'subs')
    rs = {r['id']: r for r in rows(pg)}
    subs = {s['user_id']: s for s in json.loads(be.sql("select json_agg(to_jsonb(s)) from public.subscriptions s where status = 'active'"))}
    check('8.12 «Suscripciones» lista las 3 activas, la que vence antes primero', len(rs) == 3 and [r['id'] for r in rows(pg)][0] == subs[BRUNO]['id'], [r['text'][:30] for r in rows(pg)])
    check('8.13 La que vence en 10 días lleva la insignia «Por vencer» y dice cuántos días quedan', 'Por vencer' in rs[subs[BRUNO]['id']]['badges'] and 'quedan 10 día' in rs[subs[BRUNO]['id']]['text'], rs[subs[BRUNO]['id']]['text'])
    pg.select_option('#su-sstatus', 'expiring'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('8.14 El filtro «Por vencer» muestra solo esa', [r['id'] for r in rows(pg)] == [subs[BRUNO]['id']])
    pg.select_option('#su-sstatus', 'active'); pg.fill('#su-q', 'cris@'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    check('8.15 Buscar por correo funciona', [r['id'] for r in rows(pg)] == [subs[CRIS]['id']])
    # renovar
    sc = f'#ad-view .adm-row[data-id="{subs[CRIS]["id"]}"]'
    before = be.sql(f"select ends_at from public.subscriptions where id = '{subs[CRIS]['id']}'")
    confirm(pg, sc, 'Renovar un periodo'); m = wait_say(pg, 'ok'); settle(pg, 250)
    gain = float(be.sql(f"select extract(epoch from (ends_at - '{before}'::timestamptz))/86400 from public.subscriptions where id = '{subs[CRIS]['id']}'"))
    check('8.16 Renovar extiende el vencimiento un mes, avisa a la persona y deja bitácora', 27 < gain < 32 and len(be.audit_rows('subscription_renew')) == 1 and int(be.sql(f"select count(*) from public.notifications where user_id = '{CRIS}' and title = 'Tu suscripción fue renovada'")) == 1, gain)
    # cambiar fecha
    n0 = len(fn_calls('admin_set_subscription_dates'))
    pg.click(f'{sc} button:text-is("Cambiar fecha")'); m = wait_say(pg, 'err')
    check('8.17 Cambiar la fecha sin elegir una no llama al servidor (evita dejar la suscripción sin vencimiento por error)', 'fecha' in m['text'] and len(fn_calls('admin_set_subscription_dates')) == n0)
    pg.fill(f'{sc} input[type=date]', '2027-06-30'); pg.click(f'{sc} button:text-is("Cambiar fecha")'); wait_say(pg, 'ok'); settle(pg, 250)
    endd = be.sql(f"select to_char(ends_at at time zone 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') from public.subscriptions where id = '{subs[CRIS]['id']}'")
    check('8.18 La fecha nueva se guarda (fin de ese día en México) y queda en la bitácora', endd == '2027-06-30 23:59:59' and len(be.audit_rows('subscription_dates')) == 1)
    # cancelar
    confirm(pg, sc, 'Cancelar suscripción'); wait_say(pg, 'ok'); waitjs(pg, f"!document.querySelector('{sc}')")
    check('8.19 Cancelar pasa la suscripción a «cancelada», avisa y deja bitácora', be.sub(CRIS) is None and be.sub(CRIS, 'cancelled') is not None and len(be.audit_rows('subscription_cancel')) == 1)
    pg.select_option('#su-sstatus', 'cancelled'); pg.fill('#su-q', ''); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 200); waitjs(pg, READY)
    rs = rows(pg)
    check('8.20 Las canceladas aparecen en su filtro, sin botones para renovarlas ni cancelarlas', len(rs) == 1 and 'Cancelada' in rs[0]['badges'] and 'Renovar' not in rs[0]['text'] and pg.locator('#ad-view button:text-is("Renovar un periodo")').count() == 0)
    # vencidas
    be.sql(f"update public.subscriptions set starts_at = now() - interval '33 days', ends_at = now() - interval '3 days' where user_id = '{ANA}' and status = 'active'")
    pg.select_option('#su-sstatus', 'active'); pg.click('#ad-view form[role=search] button[type=submit]'); settle(pg, 250); waitjs(pg, READY)
    rs = rows(pg)
    check('8.21 Una suscripción activa cuya fecha ya pasó dice «venció hace 3 día(s)» y se puede renovar', any('ana@ejemplo.mx' in r['text'] and 'venció hace 3 día' in r['text'] for r in rs), [r['text'][:60] for r in rs])
    pg.click(f'#ad-view .adm-row:has-text("ana@ejemplo.mx") button:text-is("Ver cuenta")'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'usuarios'"); waitjs(pg, "!!document.querySelector('#ad-view .adm-dl')")
    check('8.22 «Ver cuenta» abre la ficha de esa persona', 'ana@ejemplo.mx' in txt(pg, '#ad-view .adm-dl'))
    allsrc = txt(pg, '#main')
    check('8.23 Ninguna pantalla del panel pide datos de pago (tarjeta, CLABE, etc.)', not re.search(r'tarjeta|CLABE|cvv|cc-number', allsrc, re.I) and pg.locator('input[autocomplete^=cc-]').count() == 0)
    check('8.24 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()


def open_thread(pg, cid):
    pg.click(f'#ad-view .adm-row[data-id="{cid}"] button:has-text("Abrir")')
    waitjs(pg, "!!document.getElementById('at-respuesta')")
def msgs_in_db(cid): return json.loads(be.sql(f"select coalesce(json_agg(to_jsonb(m) order by created_at, id), '[]'::json) from public.messages m where conversation_id = '{cid}'"))
def bubbles(pg): return pg.evaluate("Array.from(document.querySelectorAll('#ad-view .adm-bubble')).map(b => ({role: b.dataset.role, text: b.querySelector('.txt').textContent, who: b.querySelector('.who').textContent}))")
def user_say(cid, uid, body): be.sql(f"insert into public.messages (conversation_id, sender_id, body) values ('{cid}', '{uid}', '{body.replace(chr(39), chr(39) * 2)}')")

def g9(br):
    print('\n[9] Atención al cliente')
    reset_state()
    c1 = be.add_conv(ANA, 'Duda del plan', HOSTILE, ago_min=30)
    c2 = be.add_conv(BRUNO, 'Gracias', 'Hola', ago_min=90); be.staff_reply(c2, ADMIN, 'Con gusto')
    c3 = be.add_conv(CRIS, 'Cerrada ya', 'Resuelto', status='cerrada', ago_min=500)
    c4 = be.add_conv(ANA, 'Pregunta antigua', 'Sigo esperando', ago_min=300)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', '#atencion'); all_logs.append(log)
    rs = rows(pg)
    check('9.1 Por omisión: «Sin responder», la más antigua primero (c4 y luego c1)', [r['id'] for r in rs] == [c4, c1] and all('Sin responder' in r['badges'] for r in rs), [r['text'][:30] for r in rs])
    check('9.2 Cada fila muestra asunto, nombre, correo, número de mensajes y el último mensaje con quién lo escribió', all(x in rs[0]['text'] for x in ('Pregunta antigua', 'Ana', 'ana@ejemplo.mx', '1 mensaje', 'Persona: Sigo esperando')), rs[0]['text'])
    check('9.3 Un mensaje con HTML se ve como texto y no se ejecuta', HOSTILE in rs[1]['text'] and not hostile_ran(pg) and pg.locator('#ad-view img').count() == 0)
    pg.select_option('#at-filtro', 'open'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 3"); rs = {r['id']: r for r in rows(pg)}
    check('9.4 «Abiertas» muestra 3; la que contestó el equipo dice «Respondida» y su último mensaje es «Equipo: …»', set(rs) == {c1, c2, c4} and 'Respondida' in rs[c2]['badges'] and 'Equipo: Con gusto' in rs[c2]['text'])
    pg.select_option('#at-filtro', 'closed'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 1")
    check('9.5 «Cerradas» muestra solo la cerrada, con su insignia', rows(pg)[0]['id'] == c3 and 'Cerrada' in rows(pg)[0]['badges'])
    pg.select_option('#at-filtro', 'all'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 4")
    pg.select_option('#at-filtro', 'pending'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 2")
    # abrir y responder
    open_thread(pg, c1)
    bs = bubbles(pg)
    check('9.6 La conversación muestra los mensajes con su autor (Persona / Equipo), como texto', len(bs) == 1 and bs[0]['role'] == 'user' and bs[0]['who'] == 'Persona' and bs[0]['text'] == HOSTILE and not hostile_ran(pg))
    check('9.7 La cabecera muestra el asunto, quién escribe y su correo', all(x in txt(pg, '#ad-view') for x in ('Duda del plan', 'Ana', 'ana@ejemplo.mx')))
    n0 = len(fn_calls('admin_reply_conversation'))
    pg.fill('#at-respuesta', '    \n  '); pg.click('#ad-view form[aria-label=Responder] button[type=submit]'); m = wait_say(pg, 'err')
    check('9.8 Enviar una respuesta vacía (o solo espacios) se avisa y no llama al servidor', 'Escribe tu respuesta' in m['text'] and len(fn_calls('admin_reply_conversation')) == n0)
    pg.evaluate("document.getElementById('at-respuesta').value = 'x'.repeat(2001)"); pg.click('#ad-view form[aria-label=Responder] button[type=submit]'); m = wait_say(pg, 'err')
    check('9.9 Más de 2000 caracteres se avisa antes de enviar', '2000' in m['text'] and len(fn_calls('admin_reply_conversation')) == n0)
    pg.fill('#at-respuesta', 'Hola Ana, ya revisamos tu plan.'); check('9.10 El contador cuenta lo escrito', '31 de 2000' in txt(pg, '#at-cuenta'), txt(pg, '#at-cuenta'))
    pg.dblclick('#ad-view form[aria-label=Responder] button[type=submit]'); m = wait_say(pg, 'ok'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-bubble').length === 2")
    ms_ = msgs_in_db(c1); conv = be.one('conversations', c1)
    check('9.11 Responder (aun con doble clic) crea UN mensaje del equipo, con el administrador como autor, y la conversación queda «respondida»', len(ms_) == 2 and ms_[1]['sender_role'] == 'staff' and ms_[1]['sender_id'] == ADMIN and conv['last_sender'] == 'staff', ms_)
    check('9.12 La persona recibe un aviso y la respuesta aparece en el hilo; el cuadro queda vacío', int(be.sql(f"select count(*) from public.notifications where user_id = '{ANA}' and type = 'mensaje'")) >= 1 and bubbles(pg)[1]['role'] == 'staff' and bubbles(pg)[1]['who'] == 'Equipo TECNOPATITAS' and pg.input_value('#at-respuesta') == '')
    # envío doble que se salta el botón (p. ej. Enter dos veces o un script): el panel lo ignora mientras el primero sigue en curso
    n_msgs = len(msgs_in_db(c1)); pg.fill('#at-respuesta', 'Respuesta enviada dos veces a la vez')
    pg.evaluate("() => { const f = document.querySelector('form[aria-label=Responder]'); f.requestSubmit(); f.requestSubmit(); }"); wait_say(pg, 'ok'); settle(pg, 400)
    check('9.12b Dos envíos simultáneos del formulario (sin pasar por el botón) crean UN solo mensaje', len(msgs_in_db(c1)) == n_msgs + 1, (n_msgs, len(msgs_in_db(c1))))
    # cerrar / reabrir
    confirm(pg, '#ad-view', 'Cerrar conversación'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Reabrir conversación')")
    check('9.13 Cerrar cambia el estado y deja bitácora; el botón pasa a «Reabrir conversación»', be.one('conversations', c1)['status'] == 'cerrada' and len(be.audit_rows('conversation_status')) == 1 and 'Cerrada' in txt(pg, '#ad-view .badge'))
    check('9.14 Con la conversación cerrada, la ayuda avisa que responder la reabre', 'se vuelve a abrir' in txt(pg, '#ad-view form'))
    pg.fill('#at-respuesta', 'Reabro con una respuesta'); pg.click('#ad-view form[aria-label=Responder] button[type=submit]'); wait_say(pg, 'ok'); settle(pg, 300)
    check('9.15 Responder en una conversación cerrada la reabre', be.one('conversations', c1)['status'] == 'abierta')
    confirm(pg, '#ad-view', 'Cerrar conversación'); wait_say(pg, 'ok'); waitjs(pg, "!!Array.from(document.querySelectorAll('#ad-view button')).find(b => b.textContent === 'Reabrir conversación')")
    confirm(pg, '#ad-view', 'Reabrir conversación'); wait_say(pg, 'ok'); settle(pg, 300)
    check('9.16 «Reabrir conversación» funciona y queda en bitácora', be.one('conversations', c1)['status'] == 'abierta' and len(be.audit_rows('conversation_status')) == 3)
    pg.click('#ad-view button:text-is("Ver cuenta")'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'usuarios'"); waitjs(pg, "!!document.querySelector('#ad-view .adm-dl')")
    check('9.17 «Ver cuenta» abre la ficha de quien escribe', 'ana@ejemplo.mx' in txt(pg, '#ad-view .adm-dl'))
    r = api(pg, 'admin_reply_conversation', {'p_conversation': '11111111-1111-4111-8111-111111111111', 'p_body': 'hola'})
    check('9.18 Responder a una conversación que no existe lo rechaza el servidor', not r['ok'] and 'no encontrada' in r['msg'].lower(), r)
    # hilo largo
    big = be.add_conv(BRUNO, 'Hilo largo', 'inicio', ago_min=10)
    be.sql(f"update public.messages set created_at = now() - interval '1 hour' where conversation_id = '{big}'")
    be.sql(f"insert into public.messages (conversation_id, sender_id, body, created_at) select '{big}', '{BRUNO}', 'm' || g, now() - (205 - g) * interval '1 second' from generate_series(1, 204) g")
    go(pg, 'atencion'); pg.select_option('#at-filtro', 'all'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length >= 5"); open_thread(pg, big)
    check('9.19 Un hilo de más de 200 mensajes muestra los últimos 200 y lo dice', len(bubbles(pg)) == 200 and 'cuenta suspendida' not in txt(pg, '#ad-view') and 'últimos 200 mensajes de 205' in txt(pg, '#ad-view') and bubbles(pg)[-1]['text'] == 'm204', (len(bubbles(pg)), bubbles(pg)[-1]['text'], [l for l in txt(pg, '#ad-view').split('\n') if 'ltimos' in l]))
    # cuenta suspendida
    cs = be.add_conv(SUSI, 'No puedo entrar', 'Por favor revisen')
    go(pg, 'atencion'); pg.select_option('#at-filtro', 'all'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length >= 6"); open_thread(pg, cs)
    check('9.20 Si la persona tiene la cuenta suspendida, la cabecera lo indica y aun así se le puede responder', 'cuenta suspendida' in txt(pg, '#ad-view') and pg.locator('#at-respuesta').is_enabled())
    check('9.21 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()

def g9b(br):
    print('\n[9b] Atención: actualización automática')
    reset_state()
    c1 = be.add_conv(ANA, 'Con reloj', 'Primer mensaje', ago_min=20)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', '#atencion', clock=True); all_logs.append(log)
    n0 = len(fn_calls('admin_list_conversations'))
    be.add_conv(BRUNO, 'Llegó otra', 'Nueva consulta', ago_min=1)
    pg.clock.run_for(30000); tick(pg, 500)
    check('9.22 La bandeja se actualiza sola a los 30 s: aparece la conversación nueva', len(rows(pg)) == 2 and len(fn_calls('admin_list_conversations')) == n0 + 1, (len(rows(pg)), len(fn_calls('admin_list_conversations')) - n0))
    pg.evaluate("document.getElementById('at-filtro').focus(); document.querySelector('#ad-view .adm-row').dataset.marca = 'x'")
    pg.clock.run_for(30000); tick(pg, 400)
    check('9.23 Si no hay cambios, la actualización no vuelve a dibujar la lista (conserva el foco)', len(fn_calls('admin_list_conversations')) == n0 + 2 and pg.evaluate("document.activeElement.id") == 'at-filtro' and pg.evaluate("!!document.querySelector('#ad-view .adm-row[data-marca]')"))
    open_thread(pg, c1)
    pg.fill('#at-respuesta', 'Borrador de respuesta que no debe perderse')
    user_say(c1, ANA, 'Segundo mensaje de la persona')
    g0 = len(fn_calls('admin_get_conversation'))
    pg.clock.run_for(15000); tick(pg, 500)
    check('9.24 La conversación abierta se actualiza sola a los 15 s: aparece el mensaje nuevo', len(bubbles(pg)) == 2 and bubbles(pg)[1]['text'] == 'Segundo mensaje de la persona' and len(fn_calls('admin_get_conversation')) == g0 + 1, bubbles(pg))
    check('9.25 …y lo que estabas escribiendo NO se pierde', pg.input_value('#at-respuesta') == 'Borrador de respuesta que no debe perderse')
    pg.evaluate("document.querySelector('#ad-view .adm-bubble').dataset.marca = 'x'")
    pg.clock.run_for(15000); tick(pg, 400)
    check('9.26 Si no hay mensajes nuevos no se redibuja el hilo', len(fn_calls('admin_get_conversation')) == g0 + 2 and len(bubbles(pg)) == 2 and pg.evaluate("!!document.querySelector('#ad-view .adm-bubble[data-marca]')"))
    # pestaña oculta: pausa
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true})")
    k0 = len(admin_calls()); pg.clock.run_for(60000); tick(pg, 300)
    check('9.27 Con la pestaña oculta la actualización automática se pausa', len(admin_calls()) == k0, len(admin_calls()) - k0)
    pg.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false})")
    user_say(c1, ANA, 'Tercero'); pg.clock.run_for(15000); tick(pg, 500)
    check('9.28 Al volver a la pestaña se reanuda', len(bubbles(pg)) == 3)
    # al salir de la sección, se detienen los temporizadores
    pg.click('#ad-nav a[data-sec=dash]'); waitjs(pg, READY); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'dash'"); waitjs(pg, "document.querySelectorAll('[data-stat]').length === 11"); tick(pg, 300)
    k0 = len(admin_calls()); pg.clock.run_for(120000); tick(pg, 300)
    check('9.29 Al salir de Atención los temporizadores se cancelan: no hay más llamadas', len(admin_calls()) == k0, [r['path'] for r in admin_calls(k0)][:4])
    go(pg, 'atencion'); pg.clock.run_for(1000); tick(pg, 300)
    go(pg, 'dash'); waitjs(pg, "document.querySelectorAll('[data-stat]').length === 11"); tick(pg, 300)
    k0 = len(admin_calls()); pg.clock.run_for(120000); tick(pg, 300)
    check('9.29b Lo mismo si se sale desde la bandeja (sin conversación abierta): no hay más llamadas', len(admin_calls()) == k0, [r['path'] for r in admin_calls(k0)][:4])
    check('9.30 Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

def g10(br):
    print('\n[10] Bitácora')
    reset_state()
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', '#bitacora'); all_logs.append(log)
    check('10.1 Sin acciones se dice así', 'Todavía no hay acciones registradas' in txt(pg, '#ad-view'))
    def as_admin(script): ok, out = be.psql(script, uid=ADMIN); assert ok, out
    as_admin(f"select public.admin_set_user_suspended('{ANA}', true, {HOSTILE!r});")
    as_admin(f"select public.admin_assign_subscription('{BRUNO}', 'pro');")
    as_admin("select public.admin_save_guide(null, 'guia-de-prueba', 'Guía de prueba', '', 'Texto', 'perros', '', true);")
    as_admin("select public.admin_save_guide((select id from public.care_guides where slug = 'guia-de-prueba'), 'guia-de-prueba', 'Guía de prueba', '', 'Texto', 'perros', '', false);")
    be.sql("insert into public.admin_audit_log (admin_id, action, target_table, target_id, details) values (null, 'accion_nueva_rara', 'x', '1234567890', '{}')")
    pg.click('button:text-is("Actualizar")'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length >= 5")
    rs = rows(pg)
    names = [r['text'].split('\n')[0].strip() for r in rs]
    check('10.3 Cada acción conocida se muestra con su nombre en español y la desconocida con su nombre original', names[0] == 'accion_nueva_rara' and 'Usuario suspendido' in names and 'Plan asignado' in names and 'Guía creada' in names and 'Guía despublicada' in names, names)
    sus = [r for r in rs if r['text'].startswith('Usuario suspendido')][0]['text']
    check('10.4 Muestra quién la hizo (nombre y correo), sobre qué y el detalle, con HTML como texto', 'Por: Dani · dani@ejemplo.mx' in sus and 'sobre profiles' in sus and 'reason:' in sus and HOSTILE[:20] in sus and not hostile_ran(pg))
    check('10.5 Una acción sin sesión (SQL Editor) lo dice', 'SQL Editor (sin sesión)' in rs[0]['text'])
    pg.select_option('#bi-filtro', 'guide_'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 2")
    check('10.6 El filtro «Guías» muestra solo guide_*', all(r['text'].startswith('Guía') for r in rows(pg)))
    pg.select_option('#bi-filtro', 'user_'); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 1")
    check('10.7 El filtro «Usuarios» muestra solo user_*', rows(pg)[0]['text'].startswith('Usuario suspendido'))
    r = api(pg, 'admin_list_audit', {'p_prefix': "user%'; drop table x;--"})
    check('10.8 Un filtro con símbolos lo rechaza el servidor', not r['ok'] and 'Filtro no válido' in r['msg'], r)
    # paginación
    be.sql("insert into public.admin_audit_log (admin_id, action, target_table, target_id) select null, 'user_suspend', 'profiles', gen_random_uuid()::text from generate_series(1, 120)")
    tot = int(be.sql('select count(*) from public.admin_audit_log'))
    pg.select_option('#bi-filtro', ''); waitjs(pg, "document.querySelectorAll('#ad-view .adm-row').length === 50")
    check(f'10.9 Muestra 50 por página: «1–50 de {tot}»', f'Mostrando 1–50 de {tot}' in txt(pg, '.adm-pager'), txt(pg, '.adm-pager'))
    pg.click('.adm-pager button:text-is("Siguiente →")'); waitjs(pg, "/51–100/.test(document.querySelector('.adm-pager').textContent)"); pg.click('.adm-pager button:text-is("Siguiente →")'); waitjs(pg, f"/101–{tot}/.test(document.querySelector('.adm-pager').textContent)")
    check(f'10.10 Las páginas 2 y 3 completan las {tot} (la última con {tot - 100})', len(rows(pg)) == tot - 100 and pg.locator('.adm-pager button:text-is("Siguiente →")').is_disabled())
    btns = pg.evaluate("Array.from(document.querySelectorAll('#ad-view button')).map(b => b.textContent)")
    check('10.11 Es solo lectura: no hay botones de borrar ni editar (solo Actualizar y paginación)', set(btns) <= {'Actualizar', '← Anterior', 'Siguiente →'}, btns)
    check('10.12 Sin errores de consola ni CSP; sin textos «null» o fechas inválidas', not csp_problems(log) and not junk(pg), (csp_problems(log), junk(pg)))
    ctx.close()

def g11(br):
    print('\n[11] Navegación, direcciones y avisos del equipo')
    reset_state()
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    for sec, title in (('denuncias', 'Denuncias'), ('atencion', 'Atención al cliente'), ('subs', 'Suscripciones y solicitudes de plan'), ('bitacora', 'Bitácora de administración'), ('guias', 'Guías de cuidado'), ('aliados', 'Aliados'), ('usuarios', 'Usuarios')):
        pg.evaluate(f"location.hash = '#{sec}'"); waitjs(pg, f"document.querySelector('#ad-view .adm-sec').dataset.sec === '{sec}'"); waitjs(pg, READY)
        check(f'11.1 La dirección #{sec} abre «{title}»: título, menú y pestaña', txt(pg, '#ad-h') == title and pg.evaluate("document.querySelector('#ad-nav a[aria-current=page]').dataset.sec") == sec and title.split(' ')[0] in pg.title())
    pg.evaluate("location.hash = '#cosa-rara'"); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'dash'"); waitjs(pg, READY)
    check('11.2 Una dirección desconocida lleva al resumen', txt(pg, '#ad-h') == 'Resumen')
    pg.evaluate("location.hash = '#usuarios'"); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'usuarios'"); waitjs(pg, READY)
    check('11.3 Al cambiar de sección el foco pasa al título de la sección (lectores de pantalla)', pg.evaluate("document.activeElement.id") == 'ad-h')
    pg.go_back(); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'dash'"); pg.go_forward(); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'usuarios'")
    check('11.4 Los botones atrás y adelante del navegador funcionan', True)
    open_user(pg, ANA); pg.click('#ad-nav a[data-sec=usuarios]'); waitjs(pg, "!!document.getElementById('us-q')")
    check('11.5 Pulsar en el menú la sección donde ya estás vuelve a su lista', pg.locator('#us-q').count() == 1 and pg.locator('#ad-view .adm-dl').count() == 0)
    go(pg, 'dash'); pg.click('[data-stat=businesses]'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'aliados'"); waitjs(pg, READY)
    check('11.6 Las tarjetas del resumen abren la sección con su filtro («Aliados registrados» → Todos)', pg.input_value('#al-status') == '')
    go(pg, 'dash'); go(pg, 'aliados')
    check('11.7 Entrar por el menú NO arrastra el filtro anterior (vuelve al valor por omisión)', pg.input_value('#al-status') == 'pending')
    ctx.close()
    # avisos del equipo
    reset_state()
    be.add_complaint('TP-NNNN-PPPP'); cid = be.add_conv(ANA, 'Aviso al equipo'); ok, out = be.psql("select public.request_plan('pro', 'monthly', null);", uid=BRUNO); assert ok, out
    links = json.loads(be.sql(f"select coalesce(json_agg(link order by link), '[]'::json) from public.notifications where user_id = '{ADMIN}'"))
    check('11.8 Los avisos al equipo (denuncia, chat, solicitud de plan) apuntan a su sección del panel', links == ['admin.html#atencion', 'admin.html#denuncias', 'admin.html#subs'], links)
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', page='notificaciones.html', wait=False); all_logs.append(log)
    waitjs(pg, "document.querySelectorAll('a[aria-label^=\"Ver:\"]').length === 3")
    hrefs = pg.evaluate("Array.from(document.querySelectorAll('a[aria-label^=\"Ver:\"]')).map(a => a.getAttribute('href')).sort()")
    check('11.9 En Notificaciones el botón «Ver» conserva la dirección con la sección (#denuncias, etc.)', hrefs == ['admin.html#atencion', 'admin.html#denuncias', 'admin.html#subs'], hrefs)
    pg.click('a[href="admin.html#denuncias"]'); waitjs(pg, "location.pathname.endsWith('admin.html')"); waitjs(pg, "!!document.querySelector('#ad-view .adm-sec') && document.querySelector('#ad-view .adm-sec').dataset.sec === 'denuncias'"); waitjs(pg, READY)
    check('11.10 Pulsar «Ver» en el aviso de denuncia abre directamente la bandeja de Denuncias con la pendiente', [r['code'] for r in rows(pg)] == ['TP-NNNN-PPPP'], rows(pg))
    check('11.11 Tras abrir ese aviso queda marcado como leído', int(be.sql(f"select count(*) from public.notifications where user_id = '{ADMIN}' and link = 'admin.html#denuncias' and is_read")) == 1)
    ctx.close()

def g12(br):
    print('\n[12] Errores, sesión y respuestas tardías')
    reset_state(); bulk_users(3, 'e')
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', '#usuarios'); all_logs.append(log)
    # red caída
    be.fail_rest = lambda path, method: ('abort', None) if path.endswith('/admin_list_audit') else None
    go(pg, 'bitacora') if False else None
    pg.click('#ad-nav a[data-sec=bitacora]'); waitjs(pg, "!!document.querySelector('#ad-view .msg.err')")
    check('12.1 Sin conexión se explica con un mensaje anunciado a lectores de pantalla (role=alert), no una pantalla en blanco, y hay «Reintentar»', 'conexión' in txt(pg, '#ad-view .msg.err').lower() and pg.locator('#ad-view button:text-is("Reintentar")').count() == 1 and pg.locator('#ad-view .msg.err[role=alert]').count() == 1, txt(pg, '#ad-view .msg.err'))
    be.fail_rest = None; pg.click('#ad-view button:text-is("Reintentar")'); waitjs(pg, "!document.querySelector('#ad-view .msg.err')")
    check('12.2 Al volver la conexión, «Reintentar» recupera la pantalla', pg.locator('#ad-view .msg.err').count() == 0)
    # respuesta mal formada
    be.fail_rest = lambda path, method: (200, {'cosa': 'rara'}) if path.endswith('/admin_list_users') else None
    pg.click('#ad-nav a[data-sec=usuarios]'); waitjs(pg, READY)
    check('12.3 Si el servidor responde algo inesperado en una lista, se muestra vacía sin romper la página', pg.locator('#ad-view .adm-row').count() == 0 and not [m for m in log if 'PAGEERROR' in m], [m for m in log if 'PAGEERROR' in m])
    be.fail_rest = lambda path, method: (200, {}) if path.endswith('/admin_dashboard_stats') else None
    pg.click('#ad-nav a[data-sec=dash]'); waitjs(pg, READY); waitjs(pg, "document.querySelectorAll('[data-stat] .stat').length === 11")   # (la segunda espera evita una carrera: READY podía cumplirse con la vista anterior)
    stats = pg.evaluate("Array.from(document.querySelectorAll('[data-stat] .stat')).map(s => s.textContent)")
    check('12.4 Si faltan cifras en el resumen se muestran como 0 (nunca «NaN» o «undefined»)', len(stats) == 11 and set(stats) == {'0'} and not junk(pg), stats)
    be.fail_rest = None
    # respuesta tardía de otra sección
    be.fail_rest = lambda path, method: ('hold', None) if path.endswith('/admin_list_users') and not HELD else None
    pg.click('#ad-nav a[data-sec=usuarios]'); tick(pg, 200)
    be.fail_rest = None
    pg.click('#ad-nav a[data-sec=aliados]'); waitjs(pg, "document.querySelector('#ad-view .adm-sec').dataset.sec === 'aliados'"); waitjs(pg, READY)
    release_held(); tick(pg, 500)
    check('12.5 Una respuesta tardía de la sección anterior NO pisa la pantalla actual', pg.evaluate("document.querySelector('#ad-view .adm-sec').dataset.sec") == 'aliados' and pg.locator('#us-q').count() == 0 and txt(pg, '#ad-h') == 'Aliados')
    # sesión vencida
    be.access.clear(); be.refresh.clear()
    pg.click('#ad-nav a[data-sec=denuncias]'); waitjs(pg, "location.pathname.endsWith('login.html')")
    check('12.6 Si la sesión caduca y no se puede renovar, se pide iniciar sesión de nuevo y se regresa al panel después', 'next=admin.html' in pg.url, pg.url)
    check('12.7 Sin errores de consola inesperados', not [m for m in log if 'PAGEERROR' in m or 'Content Security' in m], [m for m in log if 'PAGEERROR' in m])
    ctx.close()

def g13(br):
    print('\n[13] Accesibilidad, teléfono y contraste')
    reset_state()
    p1 = be.add_biz(CRIS, 'Clínica ' + 'H' * 90, status='pending'); be.add_promo(p1, title='P' * 60, description='D' * 200)
    be.add_complaint('TP-AAAA-BBBB', photos=1, status='recibida', description='x' * 400, ref='R' * 150); be.make_request(ANA, 'pro', note='Hola'); be.assign(BRUNO, 'vip', days=9)
    c1 = be.add_conv(ANA, 'S' * 100, body='W' * 300); be.add_guide('g1', 'G' * 100, 'perros', True); be.add_guide('g2', 'Guía dos', 'gatos', False)
    ok, out = be.psql(f"select public.admin_set_user_suspended('{SUSI}', true, 'prueba');", uid=ADMIN)
    SECS = [('dash', None), ('usuarios', None), ('usuarios', lambda pg: open_user(pg, ANA)), ('aliados', None), ('aliados', lambda pg: open_biz(pg, p1)),
            ('denuncias', None), ('denuncias', lambda pg: (pg.click('#ad-view .adm-row button:has-text("Abrir")'), waitjs(pg, "!!document.querySelector('#ad-view .adm-dl')"), waitjs(pg, "document.querySelectorAll('#ad-view .adm-photos img').length === 1"))),
            ('guias', None), ('guias', lambda pg: open_guide_form(pg, rows(pg)[0]['id'])), ('subs', None), ('subs', lambda pg: open_sub_tab(pg, 'subs')),
            ('atencion', None), ('atencion', lambda pg: open_thread(pg, c1)), ('bitacora', None)]
    for w_, tag in ((1100, 'escritorio'), (390, 'teléfono 390 px')):
        ctx, pg, log = open_admin(br, 'dani@ejemplo.mx', w=w_, h=900 if w_ > 500 else 800); all_logs.append(log)
        bad_a11y, bad_ct = [], []
        for sec, act in SECS:
            go(pg, sec)
            if act: act(pg); settle(pg, 250)
            a = pg.evaluate(A11Y_JS, {'touch': w_ < 500}); c = pg.evaluate(AUDIT_JS)
            if a: bad_a11y.append((sec + ('' if act is None else '/detalle'), a[:3]))
            if c: bad_ct.append((sec, c[:2]))
        check(f'13.1 ({tag}) Todas las pantallas del panel: campos con nombre, botones con texto' + (', objetivos táctiles de al menos 44 px' if w_ < 500 else '') + ' y sin desbordes horizontales', not bad_a11y, bad_a11y[:4])
        check(f'13.2 ({tag}) Contraste de texto suficiente (WCAG AA) en todas las pantallas', not bad_ct, bad_ct[:3])
        check(f'13.3 ({tag}) Sin errores de consola ni CSP', not csp_problems(log), csp_problems(log))
        ctx.close()
    ctx, pg, log = open_admin(br, 'dani@ejemplo.mx'); all_logs.append(log)
    go(pg, 'denuncias')
    pg.evaluate("document.querySelectorAll('.adm-row small').forEach(e => e.style.setProperty('color', '#c9d3e8', 'important'))")
    check('13.4 Control: un texto claro sobre fondo claro SÍ es detectado por la comprobación de contraste', len(pg.evaluate(AUDIT_JS)) >= 1)
    # teclado: el flujo de confirmación se maneja sin ratón
    go(pg, 'usuarios'); open_user(pg, ANA)
    pg.focus('#ad-view button:text-is("Suspender cuenta")'); pg.keyboard.press('Enter'); waitjs(pg, "!!document.querySelector('.adm-ask')")
    check('13.5 Con el teclado: Enter abre la confirmación y el foco queda en «No»', pg.evaluate("document.activeElement.textContent") == 'No')
    pg.keyboard.press('Shift+Tab'); check('13.6 Shift+Tab llega a «Sí» y Enter confirma', pg.evaluate("document.activeElement.textContent") == 'Sí')
    pg.keyboard.press('Enter'); wait_say(pg, 'ok'); check('13.7 La acción se hizo con teclado solamente', be.one('profiles', ANA)['is_suspended'])
    nav = pg.evaluate("document.getElementById('ad-nav').getAttribute('aria-label')")
    check('13.8 El menú tiene nombre accesible y los mensajes usan roles status/alert', nav == 'Secciones del panel' and say(pg)['role'] == 'status')
    go(pg, 'atencion'); open_thread(pg, c1)
    check('13.9 La conversación es una región «log» con nombre y se puede recorrer con el teclado (tabindex 0)', pg.evaluate("(() => { const l = document.querySelector('#ad-view .adm-thread'); return !!l && l.getAttribute('role') === 'log' && l.tabIndex === 0 && !!l.getAttribute('aria-label'); })()"))
    ctx.close()

def pub(br, query='', email=None, w=1100, h=900):
    ctx, pg, log = open_admin(br, email, wait=False, page='guias.html' + query, w=w, h=h); all_logs.append(log)
    return ctx, pg, log
GD_READY = "!document.querySelector('#gd-estado') || document.getElementById('gd-lista').children.length > 0 || (document.getElementById('gd-estado') && !document.getElementById('gd-estado').hidden && !/Cargando/.test(document.getElementById('gd-estado').textContent)) || !document.getElementById('gd-articulo').hidden && !/Cargando/.test(document.getElementById('gd-articulo').textContent)"

def g14(br):
    print('\n[14] Guías públicas')
    reset_state()
    g_a = be.add_guide('cuidados-del-gato', 'Cuidados del gato', 'gatos', True, content='Primer párrafo.\n\n## Alimentación\n\nAgua fresca.\n\n' + HOSTILE + '\n\n<script>window.__pwn=1</script>', summary='Lo esencial', ago_min=5)
    be.add_guide('paseos-del-perro', 'Paseos del perro', 'perros', True, summary='Rutina de paseo', ago_min=10, source='')
    be.add_guide('borrador-secreto', 'Borrador secreto', 'aves', False, content='NO PUBLICAR')
    ctx, pg, log = pub(br)
    waitjs(pg, "document.getElementById('gd-lista').children.length === 2")
    cards = pg.evaluate("Array.from(document.querySelectorAll('#gd-lista .gd-card')).map(c => ({t: c.querySelector('h3').textContent, cat: c.querySelector('.badge').textContent, href: c.querySelector('a').getAttribute('href')}))")
    check('14.1 El público ve solo las guías publicadas (2), la más reciente primero, con categoría y enlace a su dirección', [c['t'] for c in cards] == ['Cuidados del gato', 'Paseos del perro'] and cards[0]['cat'] == 'Gatos' and cards[0]['href'] == 'guias.html?g=cuidados-del-gato', cards)
    check('14.2 Un borrador no aparece ni su texto está en la página', 'Borrador secreto' not in txt(pg, '#main') and 'NO PUBLICAR' not in pg.content())
    check('14.3 Se cuenta cuántas guías hay y no se dice que sea una «vista de diseño»', txt(pg, '#gd-count') == '2 guías' and 'diseño' not in txt(pg, '#main').lower())
    reqs = [r for r in be.a_log if r['path'] == '/rest/v1/care_guides']
    check('14.4 La lista se pide sin sesión (rol anónimo) y sin traer el contenido de las guías', reqs and not any(r['auth'] for r in reqs) and all('content' not in r['query'] for r in reqs[:1]), reqs[:1])
    ctx_l, pg_l, log_l = pub(br, email='ana@ejemplo.mx'); n_l = len(be.a_log); waitjs(pg_l, "document.getElementById('gd-lista').children.length === 2")
    reqs_l = [r for r in be.a_log[:] if r['path'] == '/rest/v1/care_guides'][-1:]
    check('14.4b Aun con una sesión iniciada, la lista pública se pide como visitante (sin enviar la sesión)', reqs_l and not reqs_l[0]['auth'], reqs_l); ctx_l.close()
    pg.fill('#gd-q', 'PASEO'); tick(pg, 150)
    check('14.5 Buscar ignora mayúsculas y acentos, y el contador sigue lo que se ve («1 guía»)', [c.get_attribute('data-slug') for c in pg.locator('#gd-lista .gd-card').all()] == ['paseos-del-perro'] and txt(pg, '#gd-count') == '1 guía', txt(pg, '#gd-count'))
    pg.fill('#gd-q', ''); pg.select_option('#gd-cat', 'gatos'); tick(pg, 150)
    check('14.6 El filtro por categoría funciona y el contador lo sigue', [c.get_attribute('data-slug') for c in pg.locator('#gd-lista .gd-card').all()] == ['cuidados-del-gato'] and txt(pg, '#gd-count') == '1 guía', txt(pg, '#gd-count'))
    pg.select_option('#gd-cat', 'aves'); tick(pg, 150)
    check('14.7 Sin coincidencias se explica y el contador dice «0 guías»', pg.locator('#gd-lista .gd-card').count() == 0 and 'No hay guías que coincidan' in txt(pg, '#gd-estado') and txt(pg, '#gd-count') == '0 guías', txt(pg, '#gd-count'))
    ctx.close()
    ctx, pg, log = pub(br, '?g=cuidados-del-gato'); waitjs(pg, "!document.getElementById('gd-articulo').hidden && !!document.getElementById('gd-titulo')")
    art = pg.evaluate("({h2: document.getElementById('gd-titulo').textContent, h3: Array.from(document.querySelectorAll('#gd-articulo h3')).map(x => x.textContent), p: document.querySelectorAll('#gd-articulo p.gd-p').length, bad: document.querySelectorAll('#gd-articulo script, #gd-articulo img').length, focus: document.activeElement.id, title: document.title})")
    check('14.8 El artículo muestra título, subtítulo («## ») y párrafos; el foco va al título y la pestaña lleva su nombre', art['h2'] == 'Cuidados del gato' and art['h3'] == ['Alimentación'] and art['p'] == 4 and art['focus'] == 'gd-titulo' and 'Cuidados del gato' in art['title'], art)
    check('14.9 El HTML escrito en la guía se ve como texto y no se ejecuta', art['bad'] == 0 and not hostile_ran(pg) and '<script>window.__pwn=1</script>' in txt(pg, '#gd-articulo') and HOSTILE in txt(pg, '#gd-articulo'))
    check('14.10 Hay enlace para volver y aviso de que es información general', pg.get_attribute('#gd-articulo a.btn', 'href') == 'guias.html' and 'no sustituye la consulta con un veterinario' in txt(pg, '#gd-articulo'))
    ctx.close()
    for q, why in (('?g=borrador-secreto', 'un borrador'), ('?g=no-existe', 'una guía inexistente'), ('?g=%3Cscript%3E', 'una dirección con símbolos'), ('?g=', 'una dirección vacía')):
        n0 = len(be.a_log)
        ctx, pg, log = pub(br, q); waitjs(pg, "!document.getElementById('gd-articulo').hidden && /No encontramos esa guía/.test(document.getElementById('gd-articulo').textContent)")
        sent = [r['query'] for r in be.a_log[n0:] if r['path'] == '/rest/v1/care_guides']
        check(f'14.11 ({why}) responde «No encontramos esa guía» y no revela nada', 'NO PUBLICAR' not in pg.content() and not any('<' in x or '%3C' in x for x in sent), sent)
        ctx.close()
    be.fail_rest = lambda path, method: (500, dict(message='boom', details=None, hint=None, code='XX000')) if path == '/rest/v1/care_guides' else None
    ctx, pg, log = pub(br); waitjs(pg, "!document.getElementById('gd-estado').hidden && document.getElementById('gd-estado').classList.contains('err')")
    check('14.12 Si falla la carga se avisa con «Reintentar»', pg.locator('#gd-estado button:text-is("Reintentar")').count() == 1)
    be.fail_rest = None; pg.click('#gd-estado button:text-is("Reintentar")'); waitjs(pg, "document.getElementById('gd-lista').children.length === 2")
    check('14.13 «Reintentar» recupera la lista', True)
    ctx.close()
    reset_state()
    ctx, pg, log = pub(br); waitjs(pg, "!document.getElementById('gd-estado').hidden && /Aún no hay guías/.test(document.getElementById('gd-estado').textContent)")
    check('14.14 Sin guías publicadas se dice con claridad', True)
    ctx.close()
    be.add_guide('titulo-raro', HOSTILE, 'aves', True, summary=HOSTILE, source=HOSTILE)
    ctx, pg, log = pub(br); waitjs(pg, "document.getElementById('gd-lista').children.length === 1")
    lt = txt(pg, '#gd-lista'); lran = hostile_ran(pg) or pg.locator('#gd-lista img').count() > 0
    ctx.close()
    ctx, pg, log = pub(br, '?g=titulo-raro'); waitjs(pg, "!document.getElementById('gd-articulo').hidden && !!document.getElementById('gd-titulo')")
    at = txt(pg, '#gd-articulo')
    check('14.14b Un título, resumen y fuente con HTML se ven como texto (en la lista y en el artículo) y no se ejecutan', HOSTILE in lt and HOSTILE in txt(pg, '#gd-titulo') and at.count(HOSTILE) >= 3 and not lran and not hostile_ran(pg) and pg.locator('#gd-articulo img, #gd-lista img').count() == 0, (lt[:80], at[:200]))
    ctx.close(); be.sql("delete from public.care_guides where slug = 'titulo-raro'")
    be.add_guide('uno', 'Uno', 'perros', True); be.add_guide('larga', 'L' * 100, 'gatos', True, summary='R' * 200, source='F' * 120, ago_min=3)
    ctx, pg, log = pub(br, w=390, h=800); waitjs(pg, "document.getElementById('gd-lista').children.length === 2")
    check('14.15 En el teléfono (390 px) no hay desbordes y el contraste es suficiente', not pg.evaluate(A11Y_JS, {'touch': False}) and not pg.evaluate(AUDIT_JS), (pg.evaluate(A11Y_JS, {'touch': False}), pg.evaluate(AUDIT_JS)[:2]))
    ctx2, pg2, log2 = pub(br, '?g=larga', w=390, h=800); waitjs(pg2, "!document.getElementById('gd-articulo').hidden && !!document.getElementById('gd-titulo')")
    check('14.15b El artículo con título, resumen y fuente muy largos tampoco desborda en el teléfono', not pg2.evaluate(A11Y_JS, {'touch': False}) and not pg2.evaluate(AUDIT_JS), (pg2.evaluate(A11Y_JS, {'touch': False}), pg2.evaluate(AUDIT_JS)[:2])); ctx2.close()
    check('14.16 Sin errores de consola ni CSP; la página no carga ningún script del panel', not csp_problems(log) and 'admin' not in ' '.join(pg.evaluate("Array.from(document.scripts).map(s => s.src)")), csp_problems(log))
    ctx.close()


def gdebug(br):
    """Solo para investigar un fallo: ejecuta el archivo indicado en TP_DEBUG_PY con las utilidades de este programa."""
    exec(open(os.environ['TP_DEBUG_PY'], encoding='utf-8').read(), globals(), {'br': br})
GROUPS = [(1, g1), (2, g2), (3, g3), (4, g4), (5, g5), (6, g6), (7, g7), (8, g8), (9, g9), (10, g9b), (11, g10), (12, g11), (13, g12), (14, g13), (15, g14)] + ([(99, gdebug)] if os.environ.get('TP_DEBUG_PY') else [])
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
