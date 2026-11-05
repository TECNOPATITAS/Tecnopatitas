"""
Pruebas de interfaz de la Etapa 5 (directorio público y panel de aliados) en Chromium real, contra el simulador mock_etapa5.py.
Se sirve el sitio con las MISMAS cabeceras (_headers): cualquier violación de CSP se detecta.

Uso:  python3 pruebas-web/probar_aliados.py     (requiere playwright + chromium, pillow, numpy)
"""
import datetime, http.server, io, json, os, re, socketserver, sys, threading, time, urllib.parse
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa5 import Backend5, today_mx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PORT = int(os.environ.get('TP_PORT', 8767))
ORIGIN = f'http://localhost:{PORT}'
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()).group(1)

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
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(('127.0.0.1', PORT), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

be = Backend5(KEY)
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

def sb_handler(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    ct = req.headers.get('content-type', '')
    raw = req.post_data_buffer
    text = None if 'multipart' in ct else (req.post_data if req.post_data is not None else (raw.decode('utf-8', 'replace') if raw else None))
    res = be.handle(req.method, req.url, req.headers, text, raw)
    if len(res) == 3: route.fulfill(status=res[0], headers={**CORS, 'content-type': res[2]}, body=res[1])
    else:
        status, data = res
        route.fulfill(status=status, headers={**CORS, 'content-type': 'application/json'}, body='' if data is None else json.dumps(data))

CUR = [None]
def new_ctx(br):
    ctx = br.new_context(viewport={'width': 1100, 'height': 1000}, accept_downloads=True)
    ctx.route(re.compile(r'https://mtkbxnhsjqqdbrjeaslo\.supabase\.co/.*'), sb_handler)
    ctx.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/css'}, body=''))
    ctx.route(re.compile(r'https://www\.google\.com/maps/.*'), lambda r: r.fulfill(status=200, headers={'content-type': 'text/html'}, body='mapa'))
    return ctx
def new_page(ctx, log):
    pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    return pg

def waitjs(pg, expr, timeout=8.0):
    """Espera una condición JS sondeando con evaluate(). (page.wait_for_function usa eval() y la CSP del sitio lo prohíbe.)
    Con la API síncrona de Playwright el simulador del servidor solo atiende peticiones mientras se llama a la API: se espera con wait_for_timeout."""
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
def body_text(pg): return pg.inner_text('body')

def login_biz(br, email, pw, page='panel-aliado'):
    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/login.html'); pg.fill('input[name=email]', email); pg.fill('input[name=pw]', pw); pg.click('button[type=submit]')
    pg.wait_for_url(re.compile(r'/panel-aliado\.html$')); pg.wait_for_selector('body.tp-ok')
    if page != 'panel-aliado': pg.goto(f'{ORIGIN}/{page}.html'); pg.wait_for_selector('body.tp-ok')
    return ctx, pg, log

def img(w, h, fmt='JPEG', exif=False):
    y, x = np.indices((h, w)); arr = np.stack([(x * 255 // w), (y * 255 // h), ((x + y) * 255 // (w + h))], -1).astype(np.uint8)
    arr = (arr ^ (np.random.RandomState(1).randint(0, 8, arr.shape).astype(np.uint8)))
    im = Image.fromarray(arr); b = io.BytesIO(); kw = {}
    if exif:
        e = Image.Exif(); e[0x010F] = 'CamaraSecreta'; e[0x0132] = '2026:11:04 12:00:00'; kw['exif'] = e
    im.save(b, fmt, **kw); return b.getvalue()
def upload_file(pg, sel, data, name='f.jpg', mime='image/jpeg'): pg.set_input_files(sel, files=[dict(name=name, mimeType=mime, buffer=data)])
def objects(bucket='business-media'): return {k[1]: o for k, o in be.objects.items() if k[0] == bucket}
def calls(table, method): return [c for c in be.calls if c['path'] == '/rest/v1/' + table and c['method'] == method]
def put_object(owner_uid, name, data=None, bucket='business-media'):
    path = f'{owner_uid}/{name}'; be.objects[(bucket, path)] = dict(owner=owner_uid, size=1, type='image/jpeg', data=data or img(40, 30)); return path
def sec(pg, key, ready_title):
    """Abre una sección del panel y espera a que termine de cargar."""
    pg.click(f'#pa-tabs a[data-sec={key}]')
    waitjs(pg, f"(()=>{{const m=document.getElementById('pa-modulo');return m.textContent.includes({json.dumps(ready_title)})&&!m.textContent.includes('Cargando…')}})()")
JUNK_RE = re.compile(r'\bnull\b|undefined|\[object|\bNaN\b')
def junk(pg, sel): return JUNK_RE.findall(txt(pg, sel))
def dtext(pg): return txt(pg, '#d-lista')
def cards(pg): return pg.locator('#d-lista article.biz')
def card(pg, name): return pg.locator('#d-lista article.biz', has=pg.locator('h3', has_text=name)).first

with sync_playwright() as pw:
    br = pw.chromium.launch()
    BIZ, PW = 'aliado@ejemplo.mx', 'ClaveAliado123'

    # ================= 1. Directorio público =================
    print('\n[1] Directorio público')
    be.reset()
    oro_u = be.add_user('oro@ejemplo.mx', PW, 'business', 'Dueño Oro'); be.set_plan('oro@ejemplo.mx', 'oro')
    pla_u = be.add_user('plata@ejemplo.mx', PW, 'business', 'Dueño Plata'); be.set_plan('plata@ejemplo.mx', 'plata')
    sin_u = be.add_user('sin@ejemplo.mx', PW, 'business', 'Dueño Sin plan')
    logo = put_object(oro_u, 'logo.jpg'); ph1 = put_object(oro_u, 'f1.jpg'); ph2 = put_object(oro_u, 'f2.jpg')
    b_oro = be.add_business('oro@ejemplo.mx', 'Veterinaria Huellitas', 'veterinaria', description='Consultas y vacunas para perros y gatos.', address='Calle Sol 12',
                            municipality='Coyoacán', state='CDMX', phone='55 1234 5678', whatsapp_url='https://wa.me/525512345678', maps_query='Veterinaria Huellitas Coyoacán',
                            logo_path=logo, photo_paths=[ph1, ph2], hours={'lun': '09:00-18:00', 'dom': 'Cerrado'}, verified=True)
    be.add_promo(b_oro, '2x1 en baños', 0, 10)
    be.add_promo(b_oro, 'Promoción vencida', -20, -5)
    be.add_promo(b_oro, 'Promoción pausada', 0, 10, active=False)
    b_pla = be.add_business('plata@ejemplo.mx', 'Estética Canina Plata', 'estetica_canina', description='Cortes y baños.', address='Av. Luna 5', municipality='Benito Juárez',
                            phone='55 8888 0000', whatsapp_url='https://wa.me/525588880000', hours={'lun': '10:00-17:00'}, verified=True)
    be.add_promo(b_pla, 'Promo Plata', 0, 5)
    b_sin = be.add_business('sin@ejemplo.mx', 'Tienda Sin Plan', 'tienda', description='Alimento y accesorios.', address='Centro 3', phone='55 0000 1111', hours={'lun': '09:00-10:00'})
    be.add_business('sin@ejemplo.mx', 'Negocio Pendiente SA', 'otro', status='pending')
    be.add_business('sin@ejemplo.mx', 'Negocio Suspendido SA', 'otro', status='suspended')
    be.add_business('sin@ejemplo.mx', 'Negocio Rechazado SA', 'otro', status='rejected')
    be.add_business(None, 'Veterinaria Demo', 'veterinaria', demo=True, description='Ficha ficticia.', address='Calle Falsa 123')

    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/directorio.html'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length>0")
    names = pg.eval_on_selector_all('#d-lista article.biz h3', 'e => e.map(x => x.textContent)')
    check('Se muestran solo los establecimientos aprobados (no pendientes, suspendidos ni rechazados)', sorted(names) == sorted(['Veterinaria Huellitas', 'Estética Canina Plata', 'Tienda Sin Plan', 'Veterinaria Demo']), names)
    check('El conteo coincide', '4 establecimientos' in txt(pg, '#d-count'), txt(pg, '#d-count'))
    check('El plan Oro aparece primero («Destacados primero»)', names[0] == 'Veterinaria Huellitas', names)
    dc = [c for c in be.calls if c['path'] == '/rest/v1/rpc/directory_search']
    check('El directorio se consulta SIN sesión (solo clave pública, sin Authorization)', dc and all('authorization' not in c['headers'] for c in dc), dc[:1])
    c_oro = card(pg, 'Veterinaria Huellitas'); c_pla = card(pg, 'Estética Canina Plata'); c_sin = card(pg, 'Tienda Sin Plan'); c_demo = card(pg, 'Veterinaria Demo')
    t_oro, t_pla, t_sin, t_demo = c_oro.inner_text(), c_pla.inner_text(), c_sin.inner_text(), c_demo.inner_text()
    check('Oro: etiqueta «Aliado verificado», «Destacado», promoción vigente, teléfono y dirección', all(x in t_oro for x in ['Aliado verificado', 'Destacado', 'Promoción vigente', '55 1234 5678', 'Calle Sol 12', 'Coyoacán']), t_oro)
    check('Oro: botón de WhatsApp con el enlace exacto', c_oro.locator('a', has_text='WhatsApp').get_attribute('href') == 'https://wa.me/525512345678')
    check('Oro: el logotipo se carga desde el bucket público', (c_oro.locator('img.bizlogo').get_attribute('src') or '').endswith('/storage/v1/object/public/business-media/' + logo))
    check('Plata: ficha completa (teléfono) pero SIN etiqueta de verificado aunque la base lo marque, SIN WhatsApp y SIN «Destacado»',
          '55 8888 0000' in t_pla and 'Aliado verificado' not in t_pla and 'Destacado' not in t_pla and c_pla.locator('a', has_text='WhatsApp').count() == 0 and 'Promoción vigente' in t_pla, t_pla)
    check('Sin plan: solo nombre, categoría, descripción y dirección (sin teléfono, sin «Ver ficha», sin promociones)',
          'Alimento y accesorios' in t_sin and 'Centro 3' in t_sin and '55 0000 1111' not in t_sin and c_sin.locator('button').count() == 0 and 'Promoción' not in t_sin, t_sin)
    check('Ficha de demostración: marcada como ejemplo y SIN enlaces de mapa', 'Ejemplo de demostración' in t_demo and c_demo.locator('a').count() == 0, t_demo)
    h_ver = c_oro.locator('a', has_text='Ver ubicación').get_attribute('href'); h_ruta = c_oro.locator('a', has_text='Cómo llegar').get_attribute('href')
    check('«Ver ubicación» y «Cómo llegar» son enlaces directos a Google Maps con el texto codificado',
          h_ver == 'https://www.google.com/maps/search/?api=1&query=' + urllib.parse.quote('Veterinaria Huellitas Coyoacán', safe='') and
          h_ruta == 'https://www.google.com/maps/dir/?api=1&destination=' + urllib.parse.quote('Veterinaria Huellitas Coyoacán', safe=''), (h_ver, h_ruta))
    h2 = c_sin.locator('a', has_text='Cómo llegar').get_attribute('href')
    check('Sin texto propio para el mapa se usa nombre + dirección', h2 == 'https://www.google.com/maps/dir/?api=1&destination=' + urllib.parse.quote('Tienda Sin Plan, Centro 3', safe=''), h2)
    check('Los enlaces externos abren en pestaña nueva con noopener', c_oro.locator('a[target=_blank]').count() == 3 and all('noopener' in (a.get_attribute('rel') or '') for a in c_oro.locator('a[target=_blank]').all()))
    check('No se muestra nada que identifique a la persona dueña', 'Dueño Oro' not in body_text(pg) and 'oro@ejemplo.mx' not in body_text(pg))
    check('El directorio no muestra textos técnicos como «null» o «undefined»', not junk(pg, '#d-lista') and not junk(pg, '#d-estado'), junk(pg, '#d-lista'))
    check('El directorio funciona sin violar la CSP', not csp_problems(log), csp_problems(log))

    # --- ficha completa ---
    n_track = len([c for c in be.calls if c['path'] == '/rest/v1/rpc/directory_track'])
    c_oro.locator('button', has_text='Ver ficha').click(); waitjs(pg, "!!document.querySelector('.bizdetail:not([hidden]) table.hours')")
    dt = c_oro.locator('.bizdetail').inner_text()
    check('Ficha: descripción, horario en orden de semana, teléfono y solo la promoción vigente', 'Consultas y vacunas' in dt and dt.index('Lunes') < dt.index('Domingo') and 'Cerrado' in dt and '09:00-18:00' in dt
          and '2x1 en baños' in dt and 'Promoción vencida' not in dt and 'Promoción pausada' not in dt, dt)
    gal = c_oro.locator('.gallery img')
    check('Ficha: dos fotos desde el bucket público, con texto alternativo', gal.count() == 2 and all(i.get_attribute('src').startswith('https://mtkbxnhsjqqdbrjeaslo.supabase.co/storage/v1/object/public/business-media/') and i.get_attribute('alt') for i in gal.all()))
    check('Ficha: el teléfono es un enlace tel: limpio', c_oro.locator('.bizdetail a[href^="tel:"]').get_attribute('href') == 'tel:5512345678')
    pg.wait_for_timeout(300)
    stat = [s for s in be.tables['business_daily_stats'] if s['business_id'] == b_oro['id']]
    check('Abrir la ficha cuenta UNA visita', len(stat) == 1 and stat[0]['views'] == 1 and stat[0]['map_clicks'] == 0, stat)
    c_oro.locator('button', has_text='Ocultar ficha').click(); c_oro.locator('button', has_text='Ver ficha').click(); waitjs(pg, "!!document.querySelector('.bizdetail:not([hidden]) table.hours')")
    pg.wait_for_timeout(300)
    check('Abrir y cerrar varias veces la misma ficha no suma visitas', be.tables['business_daily_stats'][0]['views'] == 1, be.tables['business_daily_stats'])
    nview = [c for c in be.calls if c['path'] == '/rest/v1/rpc/directory_track' and c['body'] == {'p_id': b_oro['id'], 'p_event': 'view'}]
    check('La página envía UNA sola visita por ficha y por carga (no depende solo del límite del servidor)', len(nview) == 1, len(nview))
    with ctx.expect_page() as newp: c_oro.locator('a', has_text='Cómo llegar').click()
    newp.value.close(); pg.wait_for_timeout(300)
    check('Tocar «Cómo llegar» cuenta un clic en el mapa', be.tables['business_daily_stats'][0]['map_clicks'] == 1, be.tables['business_daily_stats'])
    for _ in range(4):
        with ctx.expect_page() as newp: c_oro.locator('a', has_text='Ver ubicación').click()
        newp.value.close()
    pg.wait_for_timeout(300)
    check('Los clics repetidos de la misma persona en el mismo día se limitan a 3', be.tables['business_daily_stats'][0]['map_clicks'] == 3, be.tables['business_daily_stats'])
    pg.reload(); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length>0")
    card(pg, 'Veterinaria Huellitas').locator('button', has_text='Ver ficha').click(); waitjs(pg, "!!document.querySelector('.bizdetail:not([hidden]) table.hours')"); pg.wait_for_timeout(300)
    check('Recargar la página y volver a abrir la ficha el mismo día no cuenta otra visita', be.tables['business_daily_stats'][0]['views'] == 1, be.tables['business_daily_stats'])
    be.client_ip = '198.51.100.9'
    pg.reload(); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length>0")
    card(pg, 'Veterinaria Huellitas').locator('button', has_text='Ver ficha').click(); waitjs(pg, "!!document.querySelector('.bizdetail:not([hidden]) table.hours')"); pg.wait_for_timeout(300)
    check('Otra persona (otra huella) sí suma su visita', be.tables['business_daily_stats'][0]['views'] == 2, be.tables['business_daily_stats'])
    stats_before = json.dumps(be.tables['business_daily_stats']); b_demo = next(b for b in be.tables['businesses'] if b['is_demo']); n0 = len(be.calls)
    pg.evaluate("id => { TPBiz.track(id, 'view'); TPBiz.track(id, 'map'); TPBiz.track('no-es-un-uuid', 'view'); TPBiz.track(null, 'map'); }", b_demo['id']); pg.wait_for_timeout(400)
    sent = [c for c in be.calls[n0:] if c['path'] == '/rest/v1/rpc/directory_track']
    check('Una ficha de demostración no suma visitas ni clics aunque se intente', json.dumps(be.tables['business_daily_stats']) == stats_before and len(sent) == 2, (len(sent), be.tables['business_daily_stats']))
    check('Un identificador inválido no genera ninguna petición al servidor', all(c['body']['p_id'] == b_demo['id'] for c in sent))

    # --- búsqueda ---
    pg.fill('#d-q', 'estética'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===1")
    check('Buscar por nombre filtra (sin distinguir mayúsculas)', 'Estética Canina Plata' in dtext(pg) and cards(pg).count() == 1)
    pg.fill('#d-q', ''); pg.select_option('#d-cat', 'tienda'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===1 && document.getElementById('d-lista').textContent.includes('Tienda Sin Plan')")
    check('Filtrar por categoría', 'Tienda Sin Plan' in dtext(pg))
    pg.select_option('#d-cat', ''); pg.fill('#d-q', 'zzzz'); waitjs(pg, "!!document.querySelector('#d-estado .empty')")
    check('Sin resultados: mensaje claro', 'No encontramos establecimientos' in txt(pg, '#d-estado') and cards(pg).count() == 0 and txt(pg, '#d-count') == '')
    pg.fill('#d-q', ''); pg.select_option('#d-orden', 'name'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===4")
    names = pg.eval_on_selector_all('#d-lista article.biz h3', 'e => e.map(x => x.textContent)')
    check('Orden por nombre (A–Z)', names == sorted(names, key=str.lower), names)
    pg.fill('#d-q', "50%_' OR 1=1 --"); waitjs(pg, "!!document.querySelector('#d-estado .empty')")
    check('Caracteres especiales en la búsqueda se tratan como texto (sin errores)', not csp_problems(log) and cards(pg).count() == 0)
    pg.goto(f'{ORIGIN}/directorio.html?q=tienda&cat=tienda'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===1")
    check('Se respetan ?q= y ?cat= de la dirección', pg.input_value('#d-q') == 'tienda' and pg.input_value('#d-cat') == 'tienda')
    pg.goto(f'{ORIGIN}/directorio.html?cat=%3Cscript%3E&q=' + 'a' * 300); pg.wait_for_timeout(500)
    check('Parámetros extraños de la dirección se ignoran o se recortan', pg.input_value('#d-cat') == '' and len(pg.input_value('#d-q')) == 80, (pg.input_value('#d-cat'), len(pg.input_value('#d-q'))))

    # --- error y reintento ---
    be.fail_dir = 500
    pg.goto(f'{ORIGIN}/directorio.html'); waitjs(pg, "!!document.querySelector('#d-estado .msg.err')")
    check('Si el servidor falla: aviso de error con botón Reintentar', pg.locator('#d-estado button', has_text='Reintentar').count() == 1 and cards(pg).count() == 0)
    be.fail_dir = None
    pg.click('#d-estado button'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===4")
    check('Reintentar recupera la lista', cards(pg).count() == 4)
    ctx.close()

    # --- paginación ---
    be.reset(); u = be.add_user('muchos@ejemplo.mx', PW, 'business', 'Muchos')
    for i in range(30): be.add_business('muchos@ejemplo.mx', f'Negocio {i:02d}', 'otro')
    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/directorio.html?cat=otro'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===12")
    check('Paginación: 12 por página, conteo total y botón con los que faltan', '30 establecimientos' in txt(pg, '#d-count') and 'Mostrar más (18 restantes)' in pg.inner_text('#d-mas'), pg.inner_text('#d-mas'))
    pg.click('#d-mas'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===24"); pg.click('#d-mas'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===30")
    ids = pg.eval_on_selector_all('#d-lista article.biz h3', 'e => e.map(x => x.textContent)')
    check('Paginación: se cargan las 30 sin repetir y el botón desaparece', len(set(ids)) == 30 and not pg.is_visible('#d-mas'))
    ctx.close()

    # --- contenido hostil ---
    be.reset(); hu = be.add_user('hostil@ejemplo.mx', PW, 'business', 'Hostil'); be.set_plan('hostil@ejemplo.mx', 'oro')
    xss = '<img src=x onerror="window.__pwn=1">'
    lg = put_object(hu, 'logo.jpg')
    hb = be.add_business('hostil@ejemplo.mx', xss + 'Vet', 'veterinaria', description=xss + '<script>window.__pwn=2</script>texto', address=xss, phone='javascript:alert(1)',
                         whatsapp_url='javascript:alert(2)', maps_query='a&b=c#d', logo_path='../otro/x.jpg', photo_paths=['../x.jpg', 'https://evil.example/x.jpg', lg],
                         hours={'lun': xss, '<b>x</b>': '09:00-10:00'})
    be.add_promo(hb, xss + 'promo', 0, 3, description=xss + '<a href="javascript:alert(3)">x</a>')
    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/directorio.html'); waitjs(pg, "document.querySelectorAll('#d-lista article.biz').length===1")
    ch = cards(pg).first
    ch.locator('button', has_text='Ver ficha').click(); waitjs(pg, "!!document.querySelector('.bizdetail:not([hidden])')"); pg.wait_for_timeout(300)
    check('Contenido con HTML (nombre, descripción, dirección, horario, promoción) se muestra como texto: no crea elementos ni ejecuta nada', pg.evaluate('window.__pwn') is None and pg.locator('#d-lista img[src="x"], #d-lista a[href^="javascript"], #d-lista script').count() == 0 and ch.inner_text().count(xss) >= 3, ch.inner_text()[:300])
    check('Teléfono o WhatsApp con esquema peligroso no generan enlace', ch.locator('a[href^="javascript"]').count() == 0 and ch.locator('a[href^="tel:"]').count() == 0 and ch.locator('a', has_text='WhatsApp').count() == 0)
    check('Rutas de imagen raras (../, https://externo) se descartan; solo queda la foto legítima', ch.locator('img.bizlogo').count() == 0 and ch.locator('.gallery img').count() == 1, ch.locator('.gallery img').count())
    check('El texto del mapa con &, = y # va codificado', ch.locator('a', has_text='Cómo llegar').get_attribute('href') == 'https://www.google.com/maps/dir/?api=1&destination=' + urllib.parse.quote('a&b=c#d', safe=''))
    check('Sin violaciones de la CSP con contenido hostil', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ================= 2. Panel: acceso y alta =================
    print('\n[2] Panel de aliados: acceso y alta')
    be.reset(); be.add_user('dueno@ejemplo.mx', PW, 'owner', 'Dueña')
    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/panel-aliado.html'); pg.wait_for_url(re.compile(r'login\.html\?next=panel-aliado\.html'), timeout=5000)
    check('Sin sesión, el panel redirige a iniciar sesión', 'login.html' in pg.url and 'next=panel-aliado.html' in pg.url, pg.url)
    pg.fill('input[name=email]', 'dueno@ejemplo.mx'); pg.fill('input[name=pw]', PW); pg.click('button[type=submit]'); pg.wait_for_url(re.compile(r'/perfil\.html$'))
    pg.goto(f'{ORIGIN}/panel-aliado.html'); pg.wait_for_selector('.authcard')
    check('Una cuenta de dueño de mascota NO entra al panel de aliados', 'Solo para aliados comerciales' in body_text(pg) and pg.locator('#pa-modulo').count() == 0)
    check('Y no se pidió ningún dato de establecimientos', not [c for c in be.calls if c['path'] in ('/rest/v1/businesses',)])
    ctx.close()

    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); other = be.add_user('otro@ejemplo.mx', PW, 'business', 'Otro Aliado')
    be.add_business('otro@ejemplo.mx', 'Negocio Ajeno Secreto', 'tienda')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "!document.getElementById('pa-modulo').textContent.includes('Cargando')")
    check('Sin establecimientos: se invita a registrar el primero, sin pestañas', 'Registra tu establecimiento' in txt(pg, '#pa-modulo') and not pg.is_visible('#pa-tabs'))
    check('Nunca se ve el establecimiento de otra cuenta', 'Negocio Ajeno Secreto' not in body_text(pg))
    gets = [c for c in be.calls if c['path'] == '/rest/v1/businesses' and c['method'] == 'GET']
    check('La consulta de establecimientos se limita a la cuenta con sesión', gets and 'owner_id=eq.' + uid in gets[0]['query'], gets[:1])
    n0 = len(be.calls)
    pg.get_by_role('button', name='Registrar establecimiento').click()
    check('Nombre vacío: aviso y NO se envía nada', 'Escribe el nombre' in txt(pg, '#pa-modulo .msg') and len(be.calls) == n0)
    pg.get_by_label('Nombre del establecimiento').fill('Estética Peluditos'); pg.get_by_role('button', name='Registrar establecimiento').click()
    check('Sin categoría: aviso y NO se envía nada', 'Elige la categoría' in txt(pg, '#pa-modulo .msg') and len(be.calls) == n0)
    pg.get_by_label('Categoría').select_option('estetica_canina'); pg.get_by_label('Teléfono del negocio').fill('abc'); pg.get_by_role('button', name='Registrar establecimiento').click()
    check('Teléfono con letras: aviso y NO se envía nada', 'teléfono' in txt(pg, '#pa-modulo .msg').lower() and len(be.calls) == n0)
    pg.get_by_label('Teléfono del negocio').fill('55 1111 2222'); pg.get_by_label('Descripción').fill('Baños y cortes.'); pg.get_by_label('Dirección del local').fill('Calle 5 #10')
    pg.get_by_label('Municipio o alcaldía').fill('Tlalpan'); pg.get_by_label('Estado').fill('CDMX')
    pg.get_by_role('button', name='Registrar establecimiento').click(); waitjs(pg, "document.getElementById('pa-estado').textContent.includes('En revisión')")
    post = calls('businesses', 'POST')
    check('El alta envía solo datos del negocio (sin estado, verificación ni dueño)', len(post) == 1 and set(post[0]['body']) <= {'name', 'category', 'description', 'address', 'state', 'municipality', 'phone', 'maps_query'}
          and post[0]['body']['name'] == 'Estética Peluditos', post[:1])
    row = [b for b in be.tables['businesses'] if b['name'] == 'Estética Peluditos'][0]
    check('Queda «pendiente» y no verificado, a nombre de la cuenta con sesión', row['status'] == 'pending' and not row['verified'] and row['owner_id'] == uid)
    check('Aviso de «en revisión»: no aparece en el directorio hasta que lo apruebe un administrador', 'NO aparece en el directorio' in txt(pg, '#pa-estado') and 'registrado' in txt(pg, '#pa-msg').lower())
    check('Sin plan se explica qué se publica y que no hay cobros', 'solo nombre, categoría, descripción y dirección' in txt(pg, '#pa-estado') and 'cobros todavía no están habilitados' in txt(pg, '#pa-estado'))
    check('Aparecen las pestañas y el formulario de datos con lo capturado', pg.is_visible('#pa-tabs') and pg.get_by_label('Nombre del establecimiento').input_value() == 'Estética Peluditos' and pg.locator('#pa-tabs a').count() == 5)
    d = pg.evaluate("TP.rpc('directory_search', {p_limit: 50}, {anon: true})")
    check('Mientras está en revisión NO aparece en el directorio público', 'Estética Peluditos' not in [x['name'] for x in d], [x['name'] for x in d])
    check('Un establecimiento pendiente no ofrece enlace al directorio', pg.locator('#pa-estado a').count() == 0)
    check('El panel funciona sin violar la CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ================= 3. Panel: datos comerciales =================
    print('\n[3] Panel: datos comerciales')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno')
    logo = put_object(uid, 'logo.jpg'); ph = put_object(uid, 'f1.jpg'); ph2 = put_object(uid, 'f2.jpg')
    b1 = be.add_business(BIZ, 'Veterinaria Central', 'veterinaria', status='pending', description='Antes', logo_path=logo, photo_paths=[ph, ph2])
    be.add_promo(b1, 'Promo vieja', 0, 5); be.add_stat(b1, 1, 3, 1)
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    check('El panel muestra el nombre del negocio y su estado «En revisión»', 'Veterinaria Central' in txt(pg, '#pa-estado') and 'En revisión' in txt(pg, '#pa-estado'))
    check('WhatsApp aparece bloqueado con el plan actual y se explica por qué', pg.get_by_label('WhatsApp del negocio').is_disabled() and 'Huellita de Oro' in txt(pg, '#pa-modulo'))
    pg.get_by_label('Descripción').fill('Consultas generales y vacunación.'); pg.get_by_label('Nombre del establecimiento').fill('Veterinaria Central Plus')
    pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    pt = calls('businesses', 'PATCH')
    check('Guardar envía los datos editables y NO envía WhatsApp, estado ni verificación', len(pt) == 1 and 'whatsapp_url' not in pt[0]['body'] and not ({'status', 'verified', 'owner_id', 'is_demo'} & set(pt[0]['body'])), pt[:1])
    check('Los cambios llegan a la base y se actualiza el encabezado', be.tables['businesses'][0]['name'] == 'Veterinaria Central Plus' and 'Veterinaria Central Plus' in txt(pg, '#pa-estado'))
    check('En revisión: no se dice que se publica de inmediato', 'se publican de inmediato' not in txt(pg, '#pa-modulo'))
    pg.get_by_label('Nombre del establecimiento').fill(''); pg.get_by_role('button', name='Guardar cambios').click()
    check('Nombre vacío al editar: aviso y no se envía otra modificación', 'Escribe el nombre' in txt(pg, '#pa-modulo .msg') and len(calls('businesses', 'PATCH')) == 1)
    pg.get_by_label('Nombre del establecimiento').fill('Veterinaria Central Plus'); pg.get_by_label('Teléfono del negocio').fill('55-1234-5678 ext 9')
    pg.get_by_role('button', name='Guardar cambios').click()
    check('Teléfono no válido al editar: aviso y no se envía', 'teléfono' in txt(pg, '#pa-modulo .msg').lower() and len(calls('businesses', 'PATCH')) == 1)

    # WhatsApp con plan Oro
    be.set_plan(BIZ, 'oro'); be.tables['businesses'][0]['status'] = 'approved'; pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    wa = pg.get_by_label('WhatsApp del negocio')
    check('Con Oro el campo de WhatsApp está habilitado', wa.is_enabled() and 'Huellita de Oro' in txt(pg, '#pa-estado'))
    check('Con Oro y aprobado el panel ofrece ver la ficha en el directorio', pg.locator('#pa-estado a[href^="directorio.html?q="]').count() == 1)
    wa.fill('abc'); pg.get_by_role('button', name='Guardar cambios').click()
    check('WhatsApp con letras: aviso', 'WhatsApp' in txt(pg, '#pa-modulo .msg') and len(calls('businesses', 'PATCH')) == 1)
    wa.fill('123'); pg.get_by_role('button', name='Guardar cambios').click()
    check('WhatsApp con pocos dígitos: aviso', '10 dígitos' in txt(pg, '#pa-modulo .msg') and len(calls('businesses', 'PATCH')) == 1)
    wa.fill('(55) 1234-5678'); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    check('Un número a 10 dígitos se guarda como enlace wa.me de México', be.tables['businesses'][0]['whatsapp_url'] == 'https://wa.me/525512345678', be.tables['businesses'][0]['whatsapp_url'])
    check('Aprobado: se avisa que los cambios se publican de inmediato', 'se publican de inmediato' in txt(pg, '#pa-modulo'))
    wa.fill(''); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    check('Quitar el WhatsApp tras haberlo guardado SÍ se envía y se guarda (compara con lo último guardado)', be.tables['businesses'][0]['whatsapp_url'] is None, calls('businesses', 'PATCH')[-1]['body'])
    wa.fill('52 55 1234 5678'); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    check('Se acepta el prefijo 52 del país', be.tables['businesses'][0]['whatsapp_url'] == 'https://wa.me/525512345678')
    be.set_plan(BIZ, 'plata'); wa.fill('55 9999 0000'); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "!!document.querySelector('#pa-modulo .msg.err')")
    check('Si el plan cambió mientras tanto, el SERVIDOR rechaza el WhatsApp y se muestra su mensaje', 'Tu plan no incluye el botón directo a WhatsApp' in txt(pg, '#pa-modulo .msg') and be.tables['businesses'][0]['whatsapp_url'] == 'https://wa.me/525512345678')

    # eliminar
    pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    pg.get_by_role('button', name='Eliminar este establecimiento').click()
    check('Eliminar pide confirmación y explica qué se borra', 'no se puede deshacer' in txt(pg, '#pa-modulo').lower() and len(be.tables['businesses']) == 1)
    pg.get_by_role('button', name='Cancelar').click()
    check('Cancelar no borra nada', len(be.tables['businesses']) == 1 and pg.get_by_role('button', name='Eliminar este establecimiento').count() == 1)
    pg.get_by_role('button', name='Eliminar este establecimiento').click(); pg.get_by_role('button', name='Sí, eliminar todo').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Registra tu establecimiento')")
    check('Confirmar elimina el establecimiento, sus promociones y estadísticas', not be.tables['businesses'] and not be.tables['business_promotions'] and not be.tables['business_daily_stats'])
    check('También se borran sus imágenes del almacenamiento', eventually(lambda: not objects()), list(objects()))
    check('El panel vuelve a ofrecer el alta y confirma la eliminación', 'Establecimiento eliminado' in txt(pg, '#pa-msg') and not pg.is_visible('#pa-tabs'))
    ctx.close()

    # ================= 4. Panel: logotipo y fotos =================
    print('\n[4] Panel: logotipo y fotos')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.set_plan(BIZ, 'plata')
    b1 = be.add_business(BIZ, 'Estética Foto', 'estetica_felina', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    sec(pg, 'fotos', 'Logotipo y fotos')
    check('Las imágenes se anuncian como públicas', 'PÚBLICAS' in txt(pg, '#pa-modulo'))
    big = img(1600, 1200, exif=True)
    upload_file(pg, '#pa-modulo input[type=file] >> nth=0', big, 'logo.jpg'); waitjs(pg, "!!document.querySelector('#pa-modulo img.avatar')")
    objs = objects(); (lp, lo), = objs.items()
    im = Image.open(io.BytesIO(lo['data']))
    check('Logotipo: se sube un JPEG reducido a 512 px y SIN datos ocultos (EXIF)', lo['type'] == 'image/jpeg' and max(im.size) <= 512 and b'CamaraSecreta' not in lo['data'] and not im.getexif(), (lo['type'], im.size))
    check('Logotipo: carpeta de la cuenta, nombre aleatorio, y se guarda su ruta en el establecimiento', re.match('^' + uid + r'/[0-9a-f-]{36}\.jpg$', lp) and be.tables['businesses'][0]['logo_path'] == lp, lp)
    check('Logotipo: se muestra desde la URL pública del bucket', (pg.get_attribute('#pa-modulo img.avatar', 'src') or '').endswith('/storage/v1/object/public/business-media/' + lp))
    waitjs(pg, "document.querySelector('#pa-modulo img.avatar').complete")
    check('La imagen pública realmente se descarga y se dibuja (sin bloqueo de CSP)', pg.evaluate("document.querySelector('#pa-modulo img.avatar').naturalWidth") > 0)
    old_logo = lp
    upload_file(pg, '#pa-modulo input[type=file] >> nth=0', img(300, 300), 'otro.jpg'); waitjs(pg, f"document.querySelector('#pa-modulo img.avatar').src.indexOf({json.dumps(old_logo)})<0")
    check('Reemplazar el logotipo borra el archivo anterior', eventually(lambda: len(objects()) == 1 and old_logo not in objects()), list(objects()))
    pg.get_by_role('button', name='Quitar logotipo').click(); waitjs(pg, "!document.querySelector('#pa-modulo img.avatar')")
    check('Quitar el logotipo limpia la ruta y borra el archivo', be.tables['businesses'][0]['logo_path'] is None and eventually(lambda: not objects()), list(objects()))

    n_files = 0
    for i in range(6):
        upload_file(pg, '#pa-modulo input[type=file] >> nth=1', img(900 + i, 700), f'f{i}.jpg'); waitjs(pg, f"document.querySelectorAll('#pa-modulo .gallery figure').length=={i + 1}")
    check('Se pueden subir 6 fotos y se muestran en la galería', len(be.tables['businesses'][0]['photo_paths']) == 6 and len(objects()) == 6)
    check('Con 6 fotos el campo para agregar otra se desactiva y se avisa', pg.locator('#pa-modulo input[type=file]').nth(1).is_disabled() and 'máximo' in txt(pg, '#pa-modulo'))
    first = be.tables['businesses'][0]['photo_paths'][0]
    pg.get_by_role('button', name='Quitar la foto 1').click(); waitjs(pg, "document.querySelectorAll('#pa-modulo .gallery figure').length==5")
    check('Quitar una foto la borra del establecimiento y del almacenamiento', first not in be.tables['businesses'][0]['photo_paths'] and eventually(lambda: first not in objects() and len(objects()) == 5))
    check('Al quitar una se vuelve a poder agregar', pg.locator('#pa-modulo input[type=file]').nth(1).is_enabled())
    n0 = len(objects())
    upload_file(pg, '#pa-modulo input[type=file] >> nth=1', b'<html>no soy imagen</html>', 'falso.jpg'); waitjs(pg, "!!document.querySelector('#pa-modulo .msg.err')")
    check('Un archivo que NO es imagen se rechaza con un aviso y no se sube nada', len(objects()) == n0 and txt(pg, '#pa-modulo .msg.err') != '', txt(pg, '#pa-modulo .msg'))
    be.storage_fail = 500
    upload_file(pg, '#pa-modulo input[type=file] >> nth=1', img(400, 300), 'ok.jpg'); waitjs(pg, "!!document.querySelector('#pa-modulo .msg.err')")
    be.storage_fail = None
    check('Si Storage falla: aviso de error y las fotos del establecimiento no cambian', len(be.tables['businesses'][0]['photo_paths']) == 5 and len(objects()) == n0)
    be.fail_patch = True
    upload_file(pg, '#pa-modulo input[type=file] >> nth=1', img(400, 300), 'ok2.jpg'); waitjs(pg, "!!document.querySelector('#pa-modulo .msg.err')")
    be.fail_patch = False
    check('Si falla guardar la ruta, la imagen recién subida se borra (no quedan archivos huérfanos)', eventually(lambda: len(objects()) == n0) and len(be.tables['businesses'][0]['photo_paths']) == 5, len(objects()))
    check('Las imágenes siempre se suben a la carpeta de la propia cuenta', all(p.startswith(uid + '/') for p in objects()))
    check('Fotos y logotipo funcionan sin violar la CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.add_business(BIZ, 'Sin plan Fotos', 'otro', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'fotos', 'Logotipo y fotos')
    check('Sin plan se avisa que el directorio aún no mostrará logotipo ni fotos (pero se pueden dejar listas)', 'todavía no muestra logotipo ni fotos' in txt(pg, '#pa-modulo'))
    ctx.close()

    # ================= 5. Panel: horarios =================
    print('\n[5] Panel: horarios')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.set_plan(BIZ, 'plata')
    b1 = be.add_business(BIZ, 'Veterinaria Horas', 'veterinaria', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'horarios', 'Horarios de atención')
    check('Horario vacío: los 7 días «Sin indicar» y sus horas desactivadas', pg.locator('#pa-modulo table.hours tbody tr').count() == 7 and pg.get_by_label('Estado del lunes').input_value() == '' and pg.get_by_label('Lunes: abre').is_disabled())
    pg.get_by_label('Estado del lunes').select_option('open'); check('Al marcar «Abierto» se habilitan las horas', pg.get_by_label('Lunes: abre').is_enabled())
    pg.get_by_label('Lunes: abre').fill('09:00'); pg.get_by_label('Lunes: cierra').fill('18:30'); pg.get_by_label('Estado del domingo').select_option('closed')
    pg.get_by_role('button', name='Guardar horario').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horario guardado')")
    check('Se guarda como {lun: «09:00-18:30», dom: «Cerrado»} y nada más', be.tables['businesses'][0]['hours'] == {'lun': '09:00-18:30', 'dom': 'Cerrado'}, be.tables['businesses'][0]['hours'])
    check('Se envía solo la columna de horario', calls('businesses', 'PATCH')[-1]['body'] == {'hours': {'lun': '09:00-18:30', 'dom': 'Cerrado'}})
    pg.get_by_role('button', name='Copiar el lunes a lunes–viernes').click(); pg.get_by_role('button', name='Guardar horario').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horario guardado')")
    check('«Copiar el lunes a lunes–viernes» llena martes a viernes', be.tables['businesses'][0]['hours'] == {'lun': '09:00-18:30', 'mar': '09:00-18:30', 'mie': '09:00-18:30', 'jue': '09:00-18:30', 'vie': '09:00-18:30', 'dom': 'Cerrado'}, be.tables['businesses'][0]['hours'])
    pg.get_by_label('Estado del sábado').select_option('open'); pg.get_by_label('Sábado: abre').fill('10:00'); pg.get_by_label('Sábado: cierra').fill('10:00')
    n = len(calls('businesses', 'PATCH')); pg.get_by_role('button', name='Guardar horario').click()
    check('Apertura y cierre iguales: aviso y no se envía', 'no pueden ser iguales' in txt(pg, '#pa-modulo .msg') and len(calls('businesses', 'PATCH')) == n)
    pg.get_by_label('Sábado: abre').fill(''); pg.get_by_role('button', name='Guardar horario').click()
    check('Hora vacía: aviso y no se envía', 'apertura y la de cierre' in txt(pg, '#pa-modulo .msg') and len(calls('businesses', 'PATCH')) == n)
    pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'horarios', 'Horarios de atención')
    check('Al volver, el horario guardado se muestra tal cual', pg.get_by_label('Estado del martes').input_value() == 'open' and pg.get_by_label('Martes: abre').input_value() == '09:00' and pg.get_by_label('Martes: cierra').input_value() == '18:30'
          and pg.get_by_label('Estado del domingo').input_value() == 'closed' and pg.get_by_label('Estado del sábado').input_value() == '')
    for d in ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'domingo']: pg.get_by_label('Estado del ' + d).select_option('')
    pg.get_by_role('button', name='Guardar horario').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horario guardado')")
    check('Dejar todos los días «Sin indicar» guarda un horario vacío', be.tables['businesses'][0]['hours'] == {})
    be.tables['businesses'][0]['hours'] = {'lun-vie': '9 a 6', 'dom': 'cerrado'}
    pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'horarios', 'Horarios de atención')
    check('Un horario con formato anterior se avisa y «cerrado» en minúsculas se reconoce', 'formato distinto' in txt(pg, '#pa-modulo') and pg.get_by_label('Estado del domingo').input_value() == 'closed')
    pg.get_by_role('button', name='Guardar horario').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horario guardado')")
    check('Al guardar se reemplaza el formato anterior por el de la tabla', be.tables['businesses'][0]['hours'] == {'dom': 'Cerrado'}, be.tables['businesses'][0]['hours'])
    check('Horarios funcionan sin violar la CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    # ================= 6. Panel: promociones =================
    print('\n[6] Panel: promociones')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); b1 = be.add_business(BIZ, 'Veterinaria Promo', 'veterinaria', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'promos', 'Promociones')
    check('Sin plan: se explica y no se puede crear (botón desactivado)', 'Necesitas un plan de aliado' in txt(pg, '#pa-modulo') and pg.get_by_role('button', name='＋ Nueva promoción').is_disabled() and 'todavía no están habilitados' in txt(pg, '#pa-modulo').replace('\n', ' '))
    ctx.close()

    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.set_plan(BIZ, 'plata'); b1 = be.add_business(BIZ, 'Veterinaria Promo', 'veterinaria', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'promos', 'Promociones')
    check('Plata: 1 promoción al mes, quedan 1', '1 promoción nueva al mes' in txt(pg, '#pa-modulo') and 'te queda 1' in txt(pg, '#pa-modulo') and pg.get_by_role('button', name='＋ Nueva promoción').is_enabled(), txt(pg, '#pa-modulo'))
    pg.get_by_role('button', name='＋ Nueva promoción').click()
    n = len(calls('business_promotions', 'POST'))
    pg.get_by_label('Título de la promoción').fill('ab'); pg.get_by_role('button', name='Publicar promoción').click()
    check('Título muy corto: aviso y no se envía', 'entre 3 y 100' in txt(pg, '#pa-modulo form .msg') and len(calls('business_promotions', 'POST')) == n)
    pg.get_by_label('Título de la promoción').fill('Baño gratis con consulta'); t0 = today_mx()
    pg.get_by_label('Empieza').fill((t0 + datetime.timedelta(days=5)).isoformat()); pg.get_by_label('Termina').fill((t0 + datetime.timedelta(days=2)).isoformat()); pg.get_by_role('button', name='Publicar promoción').click()
    check('Término anterior al inicio: aviso y no se envía', 'anterior' in txt(pg, '#pa-modulo form .msg') and len(calls('business_promotions', 'POST')) == n)
    pg.get_by_label('Empieza').fill(t0.isoformat()); pg.get_by_label('Termina').fill((t0 + datetime.timedelta(days=400)).isoformat()); pg.get_by_role('button', name='Publicar promoción').click()
    check('Más de un año de duración: aviso y no se envía', 'un año' in txt(pg, '#pa-modulo form .msg') and len(calls('business_promotions', 'POST')) == n)
    pg.get_by_label('Título de la promoción').evaluate("e => { e.value = 'x'.repeat(101); }"); pg.get_by_label('Termina').fill((t0 + datetime.timedelta(days=30)).isoformat()); pg.get_by_role('button', name='Publicar promoción').click()
    check('Título de más de 100 caracteres: aviso y no se envía', 'entre 3 y 100' in txt(pg, '#pa-modulo form .msg') and len(calls('business_promotions', 'POST')) == n)
    pg.get_by_label('Título de la promoción').fill('Baño gratis con consulta'); pg.get_by_label('Detalle').fill('Presentando esta promoción.')
    pg.get_by_role('button', name='Publicar promoción').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Promoción publicada')")
    pp = calls('business_promotions', 'POST')
    check('Publicar envía solo los campos permitidos y el establecimiento actual', len(pp) == 1 and set(pp[0]['body']) == {'business_id', 'title', 'description', 'starts_on', 'ends_on', 'is_active'} and pp[0]['body']['business_id'] == b1['id'], pp[:1])
    check('La promoción aparece como «Vigente»', 'Vigente' in txt(pg, '#pa-modulo ul.recs') and 'Baño gratis con consulta' in txt(pg, '#pa-modulo ul.recs'))
    check('Plata: ya no quedan promociones este mes y el botón se desactiva', 'ya no te quedan' in txt(pg, '#pa-modulo') and pg.get_by_role('button', name='＋ Nueva promoción').is_disabled())
    r = pg.evaluate("""async (bid) => { try { await TP.rest('/business_promotions', {method:'POST', body:{business_id:bid, title:'Otra promo', ends_on:'%s'}, prefer:'return=minimal'}); return 'ok'; } catch (e) { return TP.errorMessage(e); } }""" % (t0 + datetime.timedelta(days=3)).isoformat(), b1['id'])
    check('Aunque se saltara la página, el SERVIDOR impone el límite mensual del plan', 'ya las usaste' in r and len(be.tables['business_promotions']) == 1, r)
    live = pg.evaluate("id => TP.rpc('directory_get', {p_id: id}, {anon: true})", b1['id'])
    check('La promoción vigente se ve en el directorio público (plan Plata)', [x['title'] for x in live['promotions']] == ['Baño gratis con consulta'], live)

    pg.get_by_role('button', name='Pausar').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Pausada')")
    check('Pausar: solo cambia is_active, se marca «Pausada» y sale del directorio', calls('business_promotions', 'PATCH')[-1]['body'] == {'is_active': False} and pg.evaluate("id => TP.rpc('directory_get', {p_id: id}, {anon: true})", b1['id'])['promotions'] == [])
    pg.get_by_role('button', name='Activar').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Vigente')")
    check('Activar la vuelve a mostrar', len(pg.evaluate("id => TP.rpc('directory_get', {p_id: id}, {anon: true})", b1['id'])['promotions']) == 1)
    pg.get_by_role('button', name='Editar').click(); pg.get_by_label('Título de la promoción').fill('Baño gratis (editado)'); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    check('Editar envía solo título, detalle y fechas y actualiza la lista', set(calls('business_promotions', 'PATCH')[-1]['body']) == {'title', 'description', 'starts_on', 'ends_on'} and 'Baño gratis (editado)' in txt(pg, '#pa-modulo ul.recs'))
    pg.get_by_role('button', name='Eliminar').click(); check('Eliminar pide confirmación', '¿Eliminar esta promoción?' in txt(pg, '#pa-modulo') and len(be.tables['business_promotions']) == 1)
    pg.get_by_role('button', name='Cancelar').click(); check('Cancelar no borra', len(be.tables['business_promotions']) == 1)
    pg.get_by_role('button', name='Eliminar').click(); pg.get_by_role('button', name='Sí, eliminar').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Promoción eliminada')")
    check('Confirmar elimina la promoción', not be.tables['business_promotions'] and 'Todavía no has publicado' in txt(pg, '#pa-modulo'))
    check('(Limitación conocida) El cupo mensual cuenta promociones creadas este mes: al borrar una se libera el cupo', 'te queda 1' in txt(pg, '#pa-modulo'))
    check('Promociones funcionan sin violar la CSP', not csp_problems(log), csp_problems(log))
    # estados por fecha
    be.add_promo(b1, 'Programada', 3, 9); be.add_promo(b1, 'Ya venció', -9, -3); pg.reload(); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'promos', 'Promociones')
    tl = txt(pg, '#pa-modulo ul.recs')
    check('Estados por fecha: «Programada» y «Vencida»', 'Programada' in tl and 'Vencida' in tl, tl)
    ctx.close()

    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.set_plan(BIZ, 'oro'); b1 = be.add_business(BIZ, 'Veterinaria Oro', 'veterinaria', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'promos', 'Promociones')
    check('Oro: promociones ilimitadas', 'ilimitadas' in txt(pg, '#pa-modulo'))
    for i in range(3):
        pg.get_by_role('button', name='＋ Nueva promoción').click(); pg.get_by_label('Título de la promoción').fill(f'Promo número {i + 1}'); pg.get_by_role('button', name='Publicar promoción').click()
        waitjs(pg, f"document.querySelectorAll('#pa-modulo ul.recs li:not(.empty-li)').length=={i + 1}")
    check('Oro: se pueden publicar varias promociones el mismo mes', len(be.tables['business_promotions']) == 3 and pg.get_by_role('button', name='＋ Nueva promoción').is_enabled())
    ctx.close()

    # ================= 7. Panel: estadísticas =================
    print('\n[7] Panel: estadísticas')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); other = be.add_user('otro@ejemplo.mx', PW, 'business', 'Otro')
    b1 = be.add_business(BIZ, 'Veterinaria Cifras', 'veterinaria', status='approved'); bo = be.add_business('otro@ejemplo.mx', 'Ajena', 'otro', status='approved')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')"); sec(pg, 'stats', 'Estadísticas básicas')
    check('Sin datos: mensaje claro y sin tabla', 'Todavía no hay datos' in txt(pg, '#pa-modulo') and pg.locator('#pa-modulo table').count() == 0)
    for d, v, c in [(0, 4, 1), (1, 2, 0), (6, 1, 2), (7, 5, 3), (29, 10, 1)]: be.add_stat(b1, d, v, c)
    be.add_stat(b1, 45, 100, 100); be.add_stat(bo, 0, 999, 999)
    sec(pg, 'datos', 'Datos comerciales'); sec(pg, 'stats', 'Estadísticas básicas')
    tiles = pg.eval_on_selector_all('#pa-modulo .statcard', 'e => e.map(x => [x.querySelector(".big").textContent, x.querySelector("small").textContent])')
    check('Totales de 7 y de 30 días (visitas y clics) correctos', tiles == [['7', 'visitas a la ficha · 7 días'], ['22', 'visitas a la ficha · 30 días'], ['3', 'clics en el mapa · 7 días'], ['7', 'clics en el mapa · 30 días']], tiles)
    check('No se cuentan los datos de hace más de 30 días ni los de otro negocio', '100' not in [t[0] for t in tiles] and '999' not in body_text(pg))
    rows = pg.eval_on_selector_all('#pa-modulo table.statsday tbody tr', 'e => e.map(r => [r.querySelector("th").textContent, ...Array.from(r.querySelectorAll(".n")).map(n => n.textContent)])')
    check('La tabla muestra los últimos 14 días, de hoy hacia atrás', len(rows) == 14 and rows[0][1:] == ['4', '1'] and rows[1][1:] == ['2', '0'] and rows[6][1:] == ['1', '2'] and rows[7][1:] == ['5', '3'], rows[:8])
    check('Se aclara que son cifras aproximadas y anónimas', 'aproximadas y anónimas' in txt(pg, '#pa-modulo'))
    w = pg.eval_on_selector_all('#pa-modulo .sbar .fill.v', 'e => e.map(x => x.style.width)')
    check('Las barras son proporcionales al valor más alto (5 = 100 %)', w[0] == '80%' and w[1] == '40%' and w[2] == '0%' and w[6] == '20%' and w[7] == '100%', w[:8])
    check('Estadísticas funcionan sin violar la CSP', not csp_problems(log), csp_problems(log))
    # las propias visitas no cuentan
    ctx2 = new_ctx(br); log2 = []; pg2 = new_page(ctx2, log2)
    pg2.goto(f'{ORIGIN}/login.html'); pg2.fill('input[name=email]', BIZ); pg2.fill('input[name=pw]', PW); pg2.click('button[type=submit]'); pg2.wait_for_url(re.compile(r'panel-aliado'))
    pg2.goto(f'{ORIGIN}/directorio.html'); waitjs(pg2, "document.querySelectorAll('#d-lista article.biz').length>0")
    CUR[0] = pg2
    before = json.dumps(be.tables['business_daily_stats'])
    be.set_plan(BIZ, 'plata')
    pg2.reload(); waitjs(pg2, "document.querySelectorAll('#d-lista article.biz').length>0")
    card(pg2, 'Veterinaria Cifras').locator('button', has_text='Ver ficha').click(); waitjs(pg2, "!!document.querySelector('.bizdetail:not([hidden])')"); pg2.wait_for_timeout(300)
    check('Las visitas de la propia dueña a su ficha NO se cuentan', json.dumps(be.tables['business_daily_stats']) == before)
    dsrch = [c for c in be.calls if c['path'] in ('/rest/v1/rpc/directory_search', '/rest/v1/rpc/directory_get')]
    dtr = [c for c in be.calls if c['path'] == '/rest/v1/rpc/directory_track' and 'authorization' in c['headers']]
    check('Con sesión iniciada el directorio se sigue consultando como público (sin enviar la sesión), salvo el contador de visitas', dsrch and not [c for c in dsrch if 'authorization' in c['headers']] and dtr, (len(dsrch), len(dtr)))
    ctx2.close()
    ctx3 = new_ctx(br); log3 = []; pg3 = new_page(ctx3, log3); pg3.goto(f'{ORIGIN}/directorio.html'); waitjs(pg3, "document.querySelectorAll('#d-lista article.biz').length>0")
    card(pg3, 'Veterinaria Cifras').locator('button', has_text='Ver ficha').click(); waitjs(pg3, "!!document.querySelector('.bizdetail:not([hidden])')"); pg3.wait_for_timeout(300)
    today_row = [s for s in be.tables['business_daily_stats'] if s['business_id'] == b1['id'] and s['day'] == today_mx().isoformat()][0]
    check('(Control) La visita de otra persona en las mismas condiciones SÍ se cuenta', today_row['views'] == 5, today_row)
    ctx3.close(); CUR[0] = pg
    ctx.close()

    # ================= 8. Panel: varios establecimientos, estados y cuenta suspendida =================
    print('\n[8] Panel: varios establecimientos, estados y cuenta suspendida')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); be.set_plan(BIZ, 'oro')
    bA = be.add_business(BIZ, 'Alfa Pendiente', 'tienda', status='pending')
    bB = be.add_business(BIZ, 'Beta Aprobada', 'veterinaria', status='approved', verified=True, description='Descripción de Beta')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    opts = pg.eval_on_selector_all('#pa-sel option', 'o => o.map(x => x.textContent)')
    check('Con varios establecimientos aparece un selector con todos los propios', opts == ['Alfa Pendiente', 'Beta Aprobada'], opts)
    check('Estado «En revisión» del primero', 'En revisión' in txt(pg, '#pa-estado') and 'NO aparece' in txt(pg, '#pa-estado'))
    pg.select_option('#pa-sel', bB['id']); waitjs(pg, "document.getElementById('pa-estado').textContent.includes('Beta Aprobada')")
    check('Al cambiar de establecimiento cambian el estado y el formulario', 'Aprobada' in txt(pg, '#pa-estado') and 'ya aparece en el directorio' in txt(pg, '#pa-estado') and pg.get_by_label('Descripción').input_value() == 'Descripción de Beta')
    check('Oro + verificado: se informa que la etiqueta se muestra', 'es «Aliado verificado»' in txt(pg, '#pa-estado') and 'botón de WhatsApp' in txt(pg, '#pa-estado'))
    pg.get_by_label('Descripción').fill('Cambiada en Beta'); pg.get_by_role('button', name='Guardar cambios').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Cambios guardados')")
    check('Los cambios se aplican al establecimiento elegido y no al otro', [b['description'] for b in be.tables['businesses']] == [None, 'Cambiada en Beta'] and calls('businesses', 'PATCH')[-1]['query'] == 'id=eq.' + bB['id'])
    sec(pg, 'horarios', 'Horarios de atención'); pg.get_by_label('Estado del lunes').select_option('closed'); pg.get_by_role('button', name='Guardar horario').click(); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horario guardado')")
    check('Horario, fotos y promociones también actúan sobre el establecimiento elegido', be.tables['businesses'][1]['hours'] == {'lun': 'Cerrado'} and be.tables['businesses'][0]['hours'] == {})
    pg.get_by_role('button', name='＋ Registrar otro establecimiento').click()
    check('«Registrar otro» abre el alta con opción de cancelar y oculta las pestañas', 'Registrar otro establecimiento' in txt(pg, '#pa-modulo') and not pg.is_visible('#pa-tabs') and pg.get_by_role('button', name='Cancelar').count() == 1)
    pg.get_by_role('button', name='Cancelar').click(); waitjs(pg, "document.getElementById('pa-tabs').hidden===false")
    check('Cancelar regresa al panel', pg.is_visible('#pa-tabs'))
    for nm in ['Gamma', 'Delta']:
        pg.get_by_role('button', name='＋ Registrar otro establecimiento').click(); pg.get_by_label('Nombre del establecimiento').fill(nm); pg.get_by_label('Categoría').select_option('otro'); pg.get_by_role('button', name='Registrar establecimiento').click()
        waitjs(pg, f"document.getElementById('pa-estado').textContent.includes({json.dumps(nm)})")
    check('Cada alta nueva queda «pendiente» y seleccionada', len(be.tables['businesses']) == 4 and all(b['status'] == 'pending' for b in be.tables['businesses'] if b['name'] in ('Gamma', 'Delta')))
    pg.get_by_role('button', name='＋ Registrar otro establecimiento').click(); pg.get_by_label('Nombre del establecimiento').fill('Épsilon'); pg.get_by_label('Categoría').select_option('otro'); pg.get_by_role('button', name='Registrar establecimiento').click(); waitjs(pg, "document.getElementById('pa-estado').textContent.includes('Épsilon')")
    check('Con 5 establecimientos desaparece el botón para registrar otro', len(be.tables['businesses']) == 5 and pg.get_by_role('button', name='＋ Registrar otro establecimiento').count() == 0)
    r = pg.evaluate("""async () => { try { await TP.rest('/businesses', {method:'POST', body:{name:'Sexto', category:'otro'}, prefer:'return=minimal'}); return 'ok'; } catch (e) { return TP.errorMessage(e); } }""")
    check('Aunque se saltara la página, el SERVIDOR impone el límite de 5 establecimientos', 'límite de establecimientos' in r and len(be.tables['businesses']) == 5, r)
    pg.goto(f'{ORIGIN}/panel-aliado.html#horarios'); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').textContent.includes('Horarios de atención')")
    check('La dirección con #horarios abre esa sección directamente', pg.locator('#pa-tabs a[aria-current=page]').get_attribute('data-sec') == 'horarios')
    pg.goto(f'{ORIGIN}/panel-aliado.html#<script>'); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    check('Un # desconocido o raro se ignora y se abre «Datos comerciales»', pg.locator('#pa-tabs a[aria-current=page]').get_attribute('data-sec') == 'datos')
    ctx.close()

    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno')
    be.add_business(BIZ, 'Negocio Suspendido', 'otro', status='suspended'); be.add_business(BIZ, 'Negocio Rechazado', 'otro', status='rejected')
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    st = txt(pg, '#pa-estado')
    check('Suspendido: se explica y se indica cómo pedir ayuda', 'Suspendida' in st and 'no aparece en el directorio' in st and 'chat' in st, st)
    pg.select_option('#pa-sel', be.tables['businesses'][1]['id']); waitjs(pg, "document.getElementById('pa-estado').textContent.includes('Negocio Rechazado')")
    check('Rechazado: se explica y se indica cómo pedir ayuda', 'No aprobada' in txt(pg, '#pa-estado') and 'chat' in txt(pg, '#pa-estado'))
    check('Sin plan ni verificación: se aclara que solo un administrador asigna la etiqueta', 'solo puede asignarla un administrador' in txt(pg, '#pa-estado'))
    ctx.close()

    be.reset(); be.add_user('susp@ejemplo.mx', PW, 'business', 'Suspendida', suspended=True); be.set_plan('susp@ejemplo.mx', 'oro')
    be.add_business('susp@ejemplo.mx', 'Negocio de Suspendida', 'otro', status='approved'); su = be.users['susp@ejemplo.mx']['id']
    ctx, pg, log = login_biz(br, 'susp@ejemplo.mx', PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    check('Cuenta suspendida: aviso de la página y todos los controles de datos desactivados', 'suspendida' in body_text(pg) and pg.locator('#pa-modulo form input:not([disabled]), #pa-modulo form select:not([disabled]), #pa-modulo form textarea:not([disabled]), #pa-modulo form button:not([disabled])').count() == 0)
    check('Cuenta suspendida: no puede registrar otro establecimiento ni eliminar', pg.get_by_role('button', name='＋ Registrar otro establecimiento').count() == 0 and pg.get_by_role('button', name='Eliminar este establecimiento').is_disabled())
    sec(pg, 'fotos', 'Logotipo y fotos'); check('Cuenta suspendida: fotos desactivadas', pg.locator('#pa-modulo input[type=file]:not([disabled])').count() == 0)
    sec(pg, 'horarios', 'Horarios de atención'); check('Cuenta suspendida: horarios desactivados', pg.get_by_role('button', name='Guardar horario').is_disabled() and pg.get_by_label('Estado del lunes').is_disabled())
    sec(pg, 'promos', 'Promociones'); check('Cuenta suspendida: no puede crear promociones', pg.get_by_role('button', name='＋ Nueva promoción').is_disabled())
    check('Cuenta suspendida: ninguna modificación llegó al servidor', not [c for c in be.calls if c['method'] in ('POST', 'PATCH', 'DELETE') and c['path'].startswith('/rest/v1/business')])
    r = pg.evaluate("""async (id) => { try { const r = await TP.rest('/businesses', {method:'PATCH', query:'id=eq.'+id, body:{name:'Hackeado'}, prefer:'return=representation'}); return JSON.stringify(r); } catch (e) { return TP.errorMessage(e); } }""", be.tables['businesses'][0]['id'])
    check('Aunque se saltara la página, el SERVIDOR no deja modificar a una cuenta suspendida', be.tables['businesses'][0]['name'] == 'Negocio de Suspendida' and r == '[]', r)
    ctx.close()

    be.reset(); be.add_user('susp2@ejemplo.mx', PW, 'business', 'Suspendida 2', suspended=True)
    ctx, pg, log = login_biz(br, 'susp2@ejemplo.mx', PW); waitjs(pg, "!document.getElementById('pa-modulo').textContent.includes('Cargando')")
    check('Suspendida sin establecimientos: el alta está desactivada y se explica', pg.get_by_role('button', name='Registrar establecimiento').is_disabled() and 'suspendida' in txt(pg, '#pa-modulo'))
    ctx.close()

    # --- ninguna sección debe mostrar «null» / «undefined» en ninguna combinación de estado y plan ---
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado Uno'); bm = be.add_business(BIZ, 'Matriz', 'otro', status='pending')
    ctx, pg, log = login_biz(br, BIZ, PW); bad = []
    for status in ('pending', 'approved', 'suspended', 'rejected'):
        for plan in (None, 'plata', 'oro'):
            bm['status'] = status
            if plan: be.set_plan(BIZ, plan)
            else: be.user_plan.pop(uid, None)
            pg.goto(f'{ORIGIN}/panel-aliado.html'); pg.wait_for_selector('body.tp-ok'); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
            for k, t in [('datos', 'Datos comerciales'), ('fotos', 'Logotipo y fotos'), ('horarios', 'Horarios de atención'), ('promos', 'Promociones'), ('stats', 'Estadísticas básicas')]:
                sec(pg, k, t)
                f = junk(pg, '#pa-modulo') + junk(pg, '#pa-estado')
                if f: bad.append((status, plan, k, f))
    check('Ninguna sección ni encabezado muestra «null», «undefined» o «NaN» (4 estados × 3 planes × 5 secciones)', not bad, bad[:3])
    ctx.close()

    # ================= 9. Contenido hostil en el panel =================
    print('\n[9] Panel: contenido hostil')
    be.reset(); uid = be.add_user(BIZ, PW, 'business', 'Aliado <b>Uno</b>'); be.set_plan(BIZ, 'oro')
    xss = '<img src=x onerror="window.__pwn=1">'
    bh = be.add_business(BIZ, xss + 'Nombre', 'otro', status='approved', description='<script>window.__pwn=2</script>', address=xss, hours={'lun': xss, '<i>x</i>': '09:00-10:00'},
                         logo_path='../x.jpg', photo_paths=['https://evil.example/x.jpg', '../y.jpg'])
    be.add_promo(bh, xss + 'promo', 0, 5, description='<a href="javascript:alert(1)">x</a>'); be.add_stat(bh, 0, 1, 1)
    ctx, pg, log = login_biz(br, BIZ, PW); waitjs(pg, "document.getElementById('pa-modulo').querySelector('form')")
    for k, t in [('datos', 'Datos comerciales'), ('fotos', 'Logotipo y fotos'), ('horarios', 'Horarios de atención'), ('promos', 'Promociones'), ('stats', 'Estadísticas básicas')]: sec(pg, k, t)
    pg.wait_for_timeout(300)
    check('Nada del servidor se interpreta como HTML en ninguna sección (nombre, descripción, horario, promoción)', pg.evaluate('window.__pwn') is None and pg.locator('#pa-modulo img[src="x"], #pa-estado img[src="x"]').count() == 0 and pg.locator('#pa-modulo a[href^="javascript"]').count() == 0)
    check('Rutas de imagen raras guardadas en la base no generan imágenes en el panel', pg.locator('#pa-modulo img').count() == 0)
    sec(pg, 'promos', 'Promociones'); check('El texto con HTML se ve como texto', xss in txt(pg, '#pa-modulo ul.recs'))
    check('Contenido hostil sin violaciones de la CSP', not csp_problems(log), csp_problems(log))
    ctx.close()

    br.close()

ok = sum(1 for _, c, _ in results if c)
print(f'\n===== {ok} / {len(results)} pruebas correctas =====')
for n, c, d in results:
    if not c: print('FALLA:', n, '->', d)
sys.exit(0 if ok == len(results) else 1)
