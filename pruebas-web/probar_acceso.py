"""
Pruebas de interfaz de la Etapa 3 (registro, acceso, sesión, guardas y perfil) en un navegador real (Chromium),
contra un simulador de Supabase (mock_supabase.py). El sitio se sirve con las MISMAS cabeceras (_headers),
así que cualquier violación de la política de seguridad de contenido (CSP) se detecta.

Uso:  python3 pruebas-web/probar_acceso.py        (requiere: pip install playwright && playwright install chromium)
"""
import http.server, json, os, re, socketserver, sys, threading, time, urllib.parse
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import Backend, CORS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PORT = 8765
ORIGIN = f'http://localhost:{PORT}'
SB = 'https://mtkbxnhsjqqdbrjeaslo.supabase.co'
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()).group(1)

# --- cabeceras reales del sitio (_headers) ---
HEADERS = {}
for line in open(os.path.join(ROOT, '_headers'), encoding='utf-8').read().splitlines()[1:]:
    if ':' in line: k, v = line.strip().split(':', 1); HEADERS[k.strip()] = v.strip()
HEADERS.pop('Strict-Transport-Security', None)        # solo aplica a HTTPS

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=ROOT, **kw)
    def end_headers(self):
        for k, v in HEADERS.items(): self.send_header(k, v)
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, *a): pass
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(('127.0.0.1', PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

be = Backend(KEY)
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

def fulfill_cors(route, status, data):
    body = '' if data is None else json.dumps(data)
    route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body=body)

def sb_handler(route):
    req = route.request
    if req.method == 'OPTIONS':
        route.fulfill(status=204, headers=CORS); return
    raw = req.post_data_buffer
    status, data = be.handle(req.method, req.url, req.headers, req.post_data if req.post_data is not None else (raw.decode('utf-8', 'replace') if raw else None))
    fulfill_cors(route, status, data)

def new_ctx(browser):
    ctx = browser.new_context(viewport={'width': 1100, 'height': 900})
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), sb_handler)
    # Detector de "fuga": en una página protegida, el contenido NUNCA debe verse antes de que el servidor confirme la sesión/rol
    ctx.add_init_script("""setInterval(()=>{const b=document.body;if(!b||!b.dataset.guard)return;const m=document.getElementById('main');
      const css=[...document.styleSheets].some(s=>s.href&&/styles\\.css/.test(s.href));
      if(css&&m&&!b.classList.contains('tp-ok')&&getComputedStyle(m).visibility!=='hidden')sessionStorage.setItem('__leak','1')},3)""")
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    return ctx

def new_page(ctx, log):
    pg = ctx.new_page()
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    return pg

def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]
def msg_text(pg): return pg.locator('#msg').inner_text() if pg.locator('#msg').count() and pg.locator('#msg').is_visible() else ''
def path(pg): return urllib.parse.urlparse(pg.url).path.lstrip('/')
def fill_login(pg, email, pw):
    pg.fill('input[name=email]', email); pg.fill('input[name=pw]', pw); pg.click('button[type=submit]')
def auth_calls(): return [c for c in be.calls if c['path'].startswith('/auth/v1/')]

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ================= 1. Páginas públicas sin errores ni violaciones de CSP =================
    print('\n[1] Páginas públicas y política de seguridad (CSP)')
    be.reset(); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    for p in ['index', 'guias', 'directorio', 'denuncias', 'planes', 'sobre-nosotros', 'registro', 'login', 'recuperar']:
        pg.goto(f'{ORIGIN}/{p}.html'); pg.wait_for_load_state('load')
    check('Ninguna página pública produce errores de script ni violaciones de CSP', not csp_problems(log), csp_problems(log)[:3])
    pg.goto(f'{ORIGIN}/index.html')
    check('Visitante: la cabecera ofrece Iniciar sesión y Crear cuenta', pg.locator('#acts a', has_text='Iniciar sesión').count() == 1 and pg.locator('#acts a', has_text='Crear cuenta').count() == 1)
    check('Visitante: solo el directorio (público, sin sesión) consulta a Supabase; el resto de las páginas no hace llamadas', be.calls and all(c['path'] == '/rest/v1/rpc/directory_search' and 'authorization' not in c['headers'] for c in be.calls), be.calls[:2])
    n_dir = len(be.calls); pg.goto(f'{ORIGIN}/guias.html'); pg.goto(f'{ORIGIN}/planes.html'); pg.goto(f'{ORIGIN}/index.html'); pg.wait_for_load_state('load')
    check('Visitante: guías, planes e inicio no llaman a Supabase solo por navegar', len(be.calls) == n_dir, be.calls[n_dir:][:2])
    ctx.close()

    # ================= 2. Guardas: visitante sin sesión =================
    print('\n[2] Páginas privadas sin sesión')
    for p in ['perfil', 'mascota', 'carnet', 'notificaciones', 'chat', 'panel-aliado', 'admin']:
        be.reset(); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
        pg.goto(f'{ORIGIN}/{p}.html'); pg.wait_for_url(re.compile(r'login\.html'))
        check(f'{p}.html sin sesión → redirige a login con ?next={p}.html', f'next={p}.html' in pg.url, pg.url)
        check(f'{p}.html: el contenido nunca fue visible antes de redirigir', pg.evaluate("sessionStorage.getItem('__leak')") is None)
        ctx.close()

    # ================= 3. Registro =================
    print('\n[3] Registro')
    be.reset(confirm_on=True); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/registro.html')
    def reg(name, email, pw, pw2, tipo, consent=True):
        pg.fill('input[name=nombre]', name); pg.fill('input[name=email]', email); pg.fill('input[name=pw]', pw); pg.fill('input[name=pw2]', pw2)
        pg.select_option('select[name=tipo]', tipo or '')
        pg.set_checked('input[name=consent]', consent); pg.click('button[type=submit]')
    reg('Ana', 'ana@ejemplo.mx', 'corta', 'corta', 'owner'); pg.wait_for_timeout(150)
    check('Contraseña corta: se rechaza en el navegador y NO llega al servidor', 'al menos 10' in msg_text(pg) and not auth_calls(), msg_text(pg))
    reg('Ana', 'ana@ejemplo.mx', 'MiClaveSegura1', 'OtraDistinta1', 'owner'); pg.wait_for_timeout(150)
    check('Contraseñas distintas: se rechaza', 'no coinciden' in msg_text(pg), msg_text(pg))
    reg('Ana', 'anabelen@ejemplo.mx', 'anabelen12345', 'anabelen12345', 'owner'); pg.wait_for_timeout(150)
    check('Contraseña que contiene el correo: se rechaza en el navegador', 'no debe contener tu correo' in msg_text(pg) and not auth_calls(), msg_text(pg))
    reg('Ana', 'ana@ejemplo.mx', 'password123456', 'password123456', 'owner'); pg.wait_for_timeout(150)
    check('Contraseña muy común: se rechaza en el navegador', 'demasiado común' in msg_text(pg) and not auth_calls(), msg_text(pg))
    reg('Ana', 'no-es-correo', 'MiClaveSegura1', 'MiClaveSegura1', 'owner'); pg.wait_for_timeout(150)
    check('Correo inválido: se rechaza', 'correo electrónico válido' in msg_text(pg) and not auth_calls(), (msg_text(pg), len(auth_calls())))
    reg('Ana', 'ana@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', '', True); pg.wait_for_timeout(150)
    check('Sin tipo de cuenta: se rechaza', 'tipo de cuenta' in msg_text(pg) and not auth_calls(), msg_text(pg))
    reg('Ana', 'ana@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'owner', False); pg.wait_for_timeout(150)
    check('Sin aceptar el uso de datos: se rechaza', 'aceptar' in msg_text(pg), msg_text(pg))
    check('Opciones del tipo de cuenta: solo dueño y aliado (no hay administrador)', pg.eval_on_selector_all('select[name=tipo] option', 'o => o.map(x => x.value)') == ['', 'owner', 'business'])
    reg('Ana', 'ana@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'owner', True); pg.wait_for_selector('#msg.ok', timeout=3000)
    sc = [c for c in be.calls if c['path'] == '/auth/v1/signup'][0]
    check('Con confirmación por correo activa: avisa de revisar el correo y NO inicia sesión', 'confirma tu correo' in msg_text(pg) and not pg.evaluate("!!localStorage.getItem('tp-auth-v1')"), msg_text(pg))
    check('El mensaje no afirma que el correo "fue enviado"', 'fue enviado' not in msg_text(pg).lower() and 'te enviamos' not in msg_text(pg).lower() or 'enviaremos' in msg_text(pg))
    check('La petición lleva la clave publishable y NO lleva cabecera Authorization', sc['headers'].get('apikey') == KEY and 'authorization' not in sc['headers'], sc['headers'])
    check('Se envía el nombre y el tipo de cuenta como metadatos', sc['body']['data'] == {'display_name': 'Ana', 'account_type': 'owner'}, sc['body'])
    check('redirect_to apunta a login.html del mismo sitio', f'redirect_to={urllib.parse.quote(ORIGIN + "/login.html?confirmado=1", safe="")}' in sc['query'], sc['query'])
    check('Registro con confirmación pendiente: el perfil nace como dueño', be.profiles[be.users['ana@ejemplo.mx']['id']]['account_type'] == 'owner')
    check('Ninguna violación de CSP en el registro', not csp_problems(log), csp_problems(log)[:2])
    # tipo manipulado desde las herramientas del navegador
    be.reset(); pg.goto(f'{ORIGIN}/registro.html')
    pg.evaluate("document.querySelector('select[name=tipo]').add(new Option('admin','admin'))")
    reg('Mallory', 'mallory@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'admin'); pg.wait_for_timeout(200)
    check('Si alguien inyecta la opción "admin" en el formulario, el navegador la rechaza y no llama al servidor', 'tipo de cuenta' in msg_text(pg) and not auth_calls(), msg_text(pg))
    pg.evaluate("TP.signUp({email:'mallory@ejemplo.mx', password:'MiClaveSegura1', displayName:'Mallory', accountType:'admin'}).catch(()=>{})"); pg.wait_for_timeout(300)
    sc = [c for c in be.calls if c['path'] == '/auth/v1/signup'][0]
    check('Aun llamando al cliente directamente con "admin", se envía "owner" (el servidor además lo sanea con el disparador)', sc['body']['data']['account_type'] == 'owner', sc['body'])
    # correo ya existente
    be.reset(); be.add_user('ya@ejemplo.mx', 'ClaveExistente1'); pg.goto(f'{ORIGIN}/registro.html')
    reg('Otra', 'ya@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'owner'); pg.wait_for_selector('#msg.ok', timeout=3000)
    check('Correo ya registrado: misma respuesta que uno nuevo (no revela si existe)', 'confirma tu correo' in msg_text(pg))
    # servicio de correo limitado
    be.reset(smtp_authorized=['equipo@ejemplo.mx']); pg.goto(f'{ORIGIN}/registro.html')
    reg('Pública', 'publico@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'owner'); pg.wait_for_selector('#msg.err', timeout=3000)
    check('SMTP de pruebas (solo equipo): mensaje claro y honesto', 'cuentas de prueba' in msg_text(pg), msg_text(pg))
    be.reset(); be.rate_limited = True; pg.goto(f'{ORIGIN}/registro.html')
    reg('Rápida', 'rapida@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'owner'); pg.wait_for_selector('#msg.err', timeout=3000)
    check('Límite de peticiones (429): mensaje claro', 'Demasiados intentos' in msg_text(pg), msg_text(pg))
    # confirmación desactivada → entra directo
    be.reset(confirm_on=False); pg.goto(f'{ORIGIN}/registro.html')
    reg('Beto Aliado', 'beto@ejemplo.mx', 'MiClaveSegura1', 'MiClaveSegura1', 'business'); pg.wait_for_url(re.compile(r'panel-aliado\.html'), timeout=4000)
    check('Sin confirmación por correo: el aliado entra directo a su panel', 'panel-aliado.html' in pg.url)
    check('El perfil del aliado nació como "business"', be.profiles[be.users['beto@ejemplo.mx']['id']]['account_type'] == 'business')
    ctx.close()

    # ================= 4. Inicio de sesión =================
    print('\n[4] Inicio de sesión y roles')
    def fresh(**users):
        be.reset(); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
        be.add_user('dueno@ejemplo.mx', 'ClaveDueno123', 'owner', 'Dueña Uno')
        be.add_user('aliado@ejemplo.mx', 'ClaveAliado123', 'business', 'Aliado Uno')
        be.add_user('admin@ejemplo.mx', 'ClaveAdmin123', 'owner', 'Admin Uno', admin=True)
        be.add_user('pendiente@ejemplo.mx', 'ClavePend123', confirmed=False)
        be.add_user('susp@ejemplo.mx', 'ClaveSusp1234', 'owner', 'Suspendido', suspended=True)
        return ctx, log, pg
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html')
    fill_login(pg, 'dueno@ejemplo.mx', 'mala'); pg.wait_for_selector('#msg.err')
    check('Contraseña incorrecta: mensaje genérico y no entra', msg_text(pg) == 'Correo o contraseña incorrectos.' and path(pg) == 'login.html', msg_text(pg))
    fill_login(pg, 'nadie@ejemplo.mx', 'mala'); pg.wait_for_timeout(300)
    check('Correo inexistente: exactamente el mismo mensaje (no revela si la cuenta existe)', msg_text(pg) == 'Correo o contraseña incorrectos.', msg_text(pg))
    fill_login(pg, 'pendiente@ejemplo.mx', 'ClavePend123'); pg.wait_for_timeout(300)
    check('Correo sin confirmar: mensaje claro', 'confirmas tu correo' in msg_text(pg), msg_text(pg))
    fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html'), timeout=4000)
    check('Dueño: entra a su perfil', path(pg) == 'perfil.html')
    pg.wait_for_selector('body.tp-ok')
    check('Perfil muestra los datos propios', pg.input_value('#p-nombre') == 'Dueña Uno' and pg.input_value('#p-email') == 'dueno@ejemplo.mx')
    check('Perfil: tipo de cuenta y plan', 'Dueño de mascota' in pg.inner_text('#p-tipo') and 'Huellita Básica' in pg.inner_text('#p-plan'), (pg.inner_text('#p-tipo'), pg.inner_text('#p-plan')))
    check('Cabecera con sesión: "Mi cuenta" y "Salir"', pg.locator('#acts a', has_text='Mi cuenta').count() == 1 and pg.locator('#logout').count() == 1)
    check('Menú lateral del dueño: ve Mis mascotas y NO ve Panel de aliado ni Administración',
          pg.locator('.side a[href="mascota.html"]').is_visible() and not pg.locator('.side a[href="panel-aliado.html"]').is_visible() and not pg.locator('.side a[href="admin.html"]').is_visible())
    check('Las peticiones autenticadas llevan Bearer y apikey', all(c['headers'].get('authorization', '').startswith('Bearer at.') and c['headers'].get('apikey') == KEY for c in be.calls if c['path'].startswith('/rest/v1/')))
    tok = pg.evaluate("localStorage.getItem('tp-auth-v1')")
    check('La sesión guardada no contiene la contraseña', 'ClaveDueno123' not in tok)
    # roles: guardas
    for target, esperado in [('admin', 'Acceso restringido'), ('panel-aliado', 'Solo para aliados')]:
        pg.goto(f'{ORIGIN}/{target}.html'); pg.wait_for_selector('body.tp-ok')
        check(f'Dueño en {target}.html: acceso denegado ("{esperado}")', esperado in pg.inner_text('#main') and 'Dashboard' not in pg.inner_text('#main'), pg.inner_text('#main')[:80])
    pg.goto(f'{ORIGIN}/mascota.html'); pg.wait_for_selector('body.tp-ok')
    check('Dueño en mascota.html: acceso permitido', 'Mis mascotas' in pg.inner_text('#main') and 'Acceso restringido' not in pg.inner_text('#main'))
    # cerrar sesión
    pg.click('#logout'); pg.wait_for_url(re.compile(r'index\.html'), timeout=4000)
    check('Cerrar sesión: vuelve al inicio y borra la sesión del navegador', pg.evaluate("localStorage.getItem('tp-auth-v1')") is None)
    check('Cerrar sesión: llama a /logout con scope=local', any(c['path'] == '/auth/v1/logout' and 'scope=local' in c['query'] for c in be.calls))
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_url(re.compile(r'login\.html'), timeout=4000)
    check('Tras cerrar sesión, las páginas privadas vuelven a pedir inicio de sesión', 'login.html' in pg.url)
    ctx.close()
    # aliado y admin
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'aliado@ejemplo.mx', 'ClaveAliado123'); pg.wait_for_url(re.compile(r'panel-aliado\.html'), timeout=4000)
    pg.wait_for_selector('body.tp-ok')
    check('Aliado: entra a su panel', 'Panel de aliados' in pg.inner_text('#main') and pg.locator('#pa-modulo').count() == 1 and 'Solo para aliados' not in pg.inner_text('#main'))
    check('Cabecera del aliado: "Mi negocio"', pg.locator('#acts a', has_text='Mi negocio').count() == 1)
    pg.goto(f'{ORIGIN}/mascota.html'); pg.wait_for_selector('body.tp-ok')
    check('Aliado en mascota.html: acceso denegado', 'Solo para dueños' in pg.inner_text('#main'), pg.inner_text('#main')[:80])
    pg.goto(f'{ORIGIN}/admin.html'); pg.wait_for_selector('body.tp-ok')
    check('Aliado en admin.html: acceso denegado', 'Acceso restringido' in pg.inner_text('#main'))
    check('Páginas protegidas: el contenido no fue visible antes de la verificación (aliado)', pg.evaluate("sessionStorage.getItem('__leak')") is None)
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_selector('body.tp-ok')
    check('Perfil del aliado: plan sin asignar explicado con honestidad', 'Sin plan de aliado' in pg.inner_text('#p-plan') and 'no hay cobros' in pg.inner_text('#p-plan'), pg.inner_text('#p-plan'))
    check('Menú del aliado: sin Mis mascotas, con Panel de aliado', not pg.locator('.side a[href="mascota.html"]').is_visible() and pg.locator('.side a[href="panel-aliado.html"]').is_visible())
    ctx.close()
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'admin@ejemplo.mx', 'ClaveAdmin123'); pg.wait_for_url(re.compile(r'admin\.html'), timeout=4000)
    pg.wait_for_selector('body.tp-ok')
    check('Administrador (verificado con is_admin() en el servidor): entra al panel', 'Dashboard' in pg.inner_text('#main'))
    check('La comprobación de admin se hizo contra el servidor (rpc/is_admin)', any(c['path'] == '/rest/v1/rpc/is_admin' for c in be.calls))
    check('Cabecera del admin: "Administración"', pg.locator('#acts a', has_text='Administración').count() == 1)
    ctx.close()
    # ?next= y redirecciones abiertas (un contexto limpio por intento)
    for evil in ['https://evil.example/robo', '//evil.example', 'javascript:alert(1)', '../admin.html', 'admin.html%0d%0a']:
        ctx, log, pg = fresh()
        pg.goto(f'{ORIGIN}/login.html?next={urllib.parse.quote(evil, safe="")}'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html'), timeout=4000)
        check(f'?next={evil!r}: se ignora y va a la página propia del rol', urllib.parse.urlparse(pg.url).netloc == f'localhost:{PORT}' and path(pg) == 'perfil.html', pg.url)
        ctx.close()
    ctx, log, pg = fresh()
    pg.goto(f'{ORIGIN}/login.html?next=mascota.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'/mascota\.html$'), timeout=4000)
    check('?next=mascota.html (página interna permitida): se respeta', path(pg) == 'mascota.html')
    ctx.close(); ctx, log, pg = fresh()
    pg.goto(f'{ORIGIN}/login.html?next=admin.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html'), timeout=4000)
    check('?next=admin.html para un dueño: no lo manda a una pantalla que lo rechaza', path(pg) == 'perfil.html')
    check('Ninguna violación de CSP en el flujo con sesión', not csp_problems(log), csp_problems(log)[:2])
    ctx.close()

    # ================= 5. Seguridad del contenido (XSS) =================
    print('\n[5] Texto malicioso en datos del usuario')
    be.reset(); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    xss = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>'
    be.add_user('x@ejemplo.mx', 'ClaveXss12345', 'owner', xss, phone='55 1234 5678')
    pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'x@ejemplo.mx', 'ClaveXss12345'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    check('Un nombre con HTML/script se muestra como TEXTO y no se ejecuta', pg.evaluate("window.__xss") is None and pg.locator('main img[src="x"]').count() == 0 and pg.locator('main script').count() == 0 and pg.input_value('#p-nombre') == xss)
    ctx.close()

    # ================= 6. Perfil =================
    print('\n[6] Perfil')
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    pg.fill('#p-nombre', 'X'); pg.click('#f-datos button'); pg.wait_for_selector('#msg-datos.err')
    check('Nombre demasiado corto: se rechaza sin llamar al servidor', 'entre 2 y 80' in pg.inner_text('#msg-datos') and not any(c['method'] == 'PATCH' for c in be.calls))
    pg.fill('#p-nombre', 'Dueña Renombrada'); pg.fill('#p-tel', 'abc'); pg.click('#f-datos button'); pg.wait_for_selector('#msg-datos.err')
    check('Teléfono inválido: se rechaza', 'teléfono' in pg.inner_text('#msg-datos').lower())
    pg.fill('#p-tel', '33 1234 5678'); pg.click('#f-datos button'); pg.wait_for_selector('#msg-datos.ok')
    uid = be.users['dueno@ejemplo.mx']['id']
    check('Guardar perfil: persiste nombre y teléfono', be.profiles[uid]['display_name'] == 'Dueña Renombrada' and be.profiles[uid]['phone'] == '33 1234 5678')
    patch = [c for c in be.calls if c['method'] == 'PATCH'][-1]
    check('El PATCH solo envía display_name y phone (jamás account_type / is_suspended)', set(patch['body'].keys()) == {'display_name', 'phone'}, patch['body'])
    check('El PATCH va filtrado por el id propio', patch['query'] == f'id=eq.{uid}', patch['query'])
    # cambio de contraseña
    pg.fill('#pw-actual', 'incorrecta'); pg.fill('#pw-nueva', 'NuevaClaveSegura9'); pg.fill('#pw-repetir', 'NuevaClaveSegura9'); pg.click('#f-pw button'); pg.wait_for_selector('#msg-pw.err')
    check('Cambiar contraseña con la actual equivocada: se rechaza y NO se cambia', 'actual no es correcta' in pg.inner_text('#msg-pw') and be.users['dueno@ejemplo.mx']['password'] == 'ClaveDueno123' and not any(c['method'] == 'PUT' for c in be.calls))
    pg.fill('#pw-actual', 'ClaveDueno123'); pg.fill('#pw-nueva', 'corta'); pg.fill('#pw-repetir', 'corta'); pg.click('#f-pw button'); pg.wait_for_timeout(200)
    check('Contraseña nueva débil: se rechaza', 'al menos 10' in pg.inner_text('#msg-pw'))
    pg.fill('#pw-actual', 'ClaveDueno123'); pg.fill('#pw-nueva', 'NuevaClaveSegura9'); pg.fill('#pw-repetir', 'NuevaClaveSegura9'); pg.click('#f-pw button'); pg.wait_for_selector('#msg-pw.ok')
    check('Cambiar contraseña con la actual correcta: se actualiza', be.users['dueno@ejemplo.mx']['password'] == 'NuevaClaveSegura9')
    check('Los campos de contraseña se limpian tras el cambio', pg.input_value('#pw-actual') == '' and pg.input_value('#pw-nueva') == '')
    pg.click('#p-salir'); pg.wait_for_url(re.compile(r'index\.html'))
    check('Botón "Cerrar sesión" del perfil funciona', pg.evaluate("localStorage.getItem('tp-auth-v1')") is None)
    ctx.close()
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'susp@ejemplo.mx', 'ClaveSusp1234'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    check('Cuenta suspendida: aviso visible y formularios bloqueados', 'suspendida' in pg.inner_text('#main') and pg.locator('#f-datos button').is_disabled() and pg.locator('#f-pw button').is_disabled())
    ctx.close()

    # ================= 7. Enlaces del correo (confirmación y recuperación) =================
    print('\n[7] Enlaces del correo')
    ctx, log, pg = fresh()
    uid = be.users['dueno@ejemplo.mx']['id']; at = 'at.' + uid + '.900'; rt = 'rt.' + uid + '.900'; be.access[at] = uid; be.refresh[rt] = uid
    pg.goto(f'{ORIGIN}/login.html?confirmado=1#access_token={at}&refresh_token={rt}&expires_in=3600&token_type=bearer&type=signup')
    pg.wait_for_url(re.compile(r'perfil\.html'), timeout=4000)
    check('Enlace de confirmación: inicia sesión y lleva al perfil', path(pg) == 'perfil.html')
    check('Los tokens desaparecen de la barra de direcciones', 'access_token' not in pg.url and 'refresh_token' not in pg.url and '#' not in pg.url, pg.url)
    ctx.close()
    ctx, log, pg = fresh()
    pg.goto(f'{ORIGIN}/login.html?confirmado=1#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired')
    pg.wait_for_selector('#msg.err')
    check('Enlace de confirmación vencido: mensaje claro y URL limpia', 'venció' in msg_text(pg) and 'error_code' not in pg.url, (msg_text(pg), pg.url))
    ctx.close()
    ctx, log, pg = fresh()
    pg.goto(f'{ORIGIN}/recuperar.html'); pg.fill('input[name=email]', 'dueno@ejemplo.mx'); pg.click('button[type=submit]'); pg.wait_for_selector('#msg.ok')
    rc = [c for c in be.calls if c['path'] == '/auth/v1/recover'][0]
    check('Recuperar: llama a /recover con redirect_to a nueva-contrasena.html', 'nueva-contrasena.html' in urllib.parse.unquote(rc['query']), rc['query'])
    check('Recuperar: el mensaje no confirma si el correo existe ni promete un envío', 'Si existe una cuenta' in msg_text(pg) and 'enviamos' not in msg_text(pg).lower(), msg_text(pg))
    pg.fill('input[name=email]', 'nadie@ejemplo.mx'); pg.click('button[type=submit]'); pg.wait_for_selector('#msg.ok')
    check('Recuperar con correo inexistente: misma respuesta', 'Si existe una cuenta' in msg_text(pg))
    ctx.close()
    ctx, log, pg = fresh()
    pg.goto(f'{ORIGIN}/nueva-contrasena.html'); pg.wait_for_selector('#msg.err')
    check('Nueva contraseña sin enlace de recuperación: formulario oculto y mensaje', pg.locator('#f-nueva').is_hidden() and 'enlace' in msg_text(pg), msg_text(pg))
    ctx.close()
    ctx, log, pg = fresh()
    uid = be.users['dueno@ejemplo.mx']['id']; at = 'at.' + uid + '.901'; rt = 'rt.' + uid + '.901'; be.access[at] = uid; be.refresh[rt] = uid
    pg.goto(f'{ORIGIN}/nueva-contrasena.html#access_token={at}&refresh_token={rt}&expires_in=3600&token_type=bearer&type=recovery')
    pg.wait_for_selector('#f-nueva:not([hidden])')
    check('Enlace de recuperación válido: muestra el formulario y limpia la URL', '#' not in pg.url)
    pg.fill('input[name=pw]', 'RecuperadaSegura7'); pg.fill('input[name=pw2]', 'Distinta'); pg.click('button[type=submit]'); pg.wait_for_selector('#msg.err')
    check('Contraseñas distintas: se rechaza', 'no coinciden' in msg_text(pg))
    pg.fill('input[name=pw]', 'RecuperadaSegura7'); pg.fill('input[name=pw2]', 'RecuperadaSegura7'); pg.click('button[type=submit]'); pg.wait_for_url(re.compile(r'perfil\.html'), timeout=5000)
    check('Recuperación completa: contraseña cambiada y sesión abierta', be.users['dueno@ejemplo.mx']['password'] == 'RecuperadaSegura7' and path(pg) == 'perfil.html')
    # estar logueado normalmente NO permite abrir nueva-contrasena sin enlace
    pg.goto(f'{ORIGIN}/nueva-contrasena.html'); pg.wait_for_selector('#msg.err')
    check('Con sesión normal, nueva-contrasena.html sin enlace NO permite cambiar la contraseña sin la actual', pg.locator('#f-nueva').is_hidden())
    ctx.close()

    # ================= 8. Renovación y caducidad de la sesión =================
    print('\n[8] Sesión: renovación y caducidad')
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    s = json.loads(pg.evaluate("localStorage.getItem('tp-auth-v1')")); s['expires_at'] = int(time.time()) - 10
    pg.evaluate("v => localStorage.setItem('tp-auth-v1', v)", json.dumps(s)); n0 = len([c for c in be.calls if 'refresh_token' in c['query']])
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_selector('body.tp-ok')
    check('Sesión por vencer: se renueva sola con el refresh token', len([c for c in be.calls if 'refresh_token' in c['query']]) == n0 + 1 and path(pg) == 'perfil.html')
    s2 = json.loads(pg.evaluate("localStorage.getItem('tp-auth-v1')"))
    check('Se guardó un access token nuevo', s2['access_token'] != s['access_token'])
    s2['expires_at'] = int(time.time()) - 10; s2['refresh_token'] = 'rt.inventado'
    pg.evaluate("v => localStorage.setItem('tp-auth-v1', v)", json.dumps(s2))
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_url(re.compile(r'login\.html'), timeout=4000)
    check('Refresh token inválido: se cierra la sesión y pide iniciar sesión', pg.evaluate("localStorage.getItem('tp-auth-v1')") is None and 'next=perfil.html' in pg.url, pg.url)
    # access token revocado en el servidor
    pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    be.access.clear()
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_url(re.compile(r'login\.html'), timeout=4000)
    check('Token rechazado por el servidor (401): sesión local eliminada y redirige', pg.evaluate("localStorage.getItem('tp-auth-v1')") is None)
    ctx.close()
    # sin red al verificar
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'perfil\.html')); pg.wait_for_selector('body.tp-ok')
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), lambda r: r.abort(), times=50)
    pg.goto(f'{ORIGIN}/perfil.html'); pg.wait_for_selector('body.tp-ok')
    check('Sin conexión: avisa y NO borra la sesión', 'No se pudo' in pg.inner_text('#main') and pg.evaluate("localStorage.getItem('tp-auth-v1')") is not None, pg.inner_text('#main')[:100])
    ctx.close()

    # ---- cierre de sesión en otra pestaña
    ctx, log, pg = fresh(); pg.goto(f'{ORIGIN}/login.html'); fill_login(pg, 'dueno@ejemplo.mx', 'ClaveDueno123'); pg.wait_for_url(re.compile(r'/perfil\.html$')); pg.wait_for_selector('body.tp-ok')
    pg2 = new_page(ctx, []); pg2.goto(f'{ORIGIN}/notificaciones.html'); pg2.wait_for_selector('body.tp-ok')
    pg.click('#logout'); pg.wait_for_url(re.compile(r'/index\.html$'), timeout=4000)
    try: pg2.wait_for_url(re.compile(r'login\.html'), timeout=4000)
    except Exception: pass
    check('Cerrar sesión en una pestaña saca de las páginas privadas abiertas en otras pestañas', 'next=notificaciones.html' in pg2.url, pg2.url)
    check('Cerrar sesión manualmente lleva al inicio (no al login con ?next=)', path(pg) == 'index.html' and 'next=' not in pg.url, pg.url)
    ctx.close()

    # ================= 9. Clave secreta en la configuración =================
    print('\n[9] Protección contra claves secretas en config.js')
    be.reset(); ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    ctx.route(f'{ORIGIN}/js/config.js', lambda r: r.fulfill(status=200, content_type='application/javascript',
        body="window.TP_CONFIG=Object.freeze({SUPABASE_URL:'https://mtkbxnhsjqqdbrjeaslo.supabase.co',SUPABASE_PUBLISHABLE_KEY:'sb_" + "secret_ABCDEFGHIJKLMNOP'});"))
    pg.goto(f'{ORIGIN}/login.html'); pg.wait_for_selector('#msg.err'); pg.wait_for_timeout(200)
    check('Con una clave secreta en config.js, el sitio bloquea el formulario y muestra el error', pg.locator('button[type=submit]').is_disabled() and 'no está configurado' in msg_text(pg), msg_text(pg))
    check('...y no realiza ninguna petición a Supabase con esa clave', len(be.calls) == 0 and any('SECRETA' in m for m in log), (len(be.calls), log[:2]))
    ctx.close()
    br.close()

fails = [r for r in results if not r[1]]
print(f'\n===== {len(results) - len(fails)} / {len(results)} pruebas correctas =====')
for n, _, d in fails: print('FALLA:', n, '->', d)
srv.shutdown()
sys.exit(1 if fails else 0)
