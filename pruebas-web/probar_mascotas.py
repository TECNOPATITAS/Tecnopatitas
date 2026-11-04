"""
Pruebas de interfaz de la Etapa 4 (mascotas, carnet, placa QR, fotos) en Chromium real, contra el simulador mock_etapa4.py.
Se sirve el sitio con las MISMAS cabeceras (_headers): cualquier violación de CSP se detecta.
Los códigos QR que muestra la página se fotografían y se decodifican con OpenCV (lector independiente).

Uso:  python3 pruebas-web/probar_mascotas.py     (requiere playwright + chromium, pillow, numpy, opencv-python-headless)
"""
import datetime, http.server, io, json, os, re, socketserver, sys, threading, urllib.parse
import numpy as np, cv2
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
from mock_supabase import CORS
from mock_etapa4 import Backend4

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PORT = int(os.environ.get('TP_PORT', 8766))
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

be = Backend4(KEY)
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

def sb_handler(route):
    req = route.request
    if req.method == 'OPTIONS': route.fulfill(status=204, headers=CORS); return
    ct = req.headers.get('content-type', '')
    raw = req.post_data_buffer
    # Playwright a veces no rellena post_data en peticiones DELETE bajo carga; el búfer sí viene completo.
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
    return ctx
def new_page(ctx, log):
    pg = ctx.new_page(); CUR[0] = pg
    pg.on('console', lambda m: log.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: log.append('PAGEERROR ' + str(e)))
    return pg

def waitjs(pg, expr, timeout=8.0):
    """Espera una condición JS sondeando con evaluate(). (page.wait_for_function usa eval() dentro de la página y la CSP estricta del sitio lo prohíbe.)"""
    import time
    t0 = time.time(); last = None
    while time.time() - t0 < timeout:
        try:
            if pg.evaluate(expr): return True
        except Exception as e: last = e
        time.sleep(0.04)
    raise TimeoutError(f'Condición no cumplida en {timeout}s: {expr[:140]} {last or ""}')

def eventually(cond, timeout=5.0):
    """La limpieza de archivos viejos es 'dispara y olvida' en la página: se espera a que el servidor simulado la reciba."""
    # OJO: con la API síncrona de Playwright, el simulador del servidor (page.route) solo atiende peticiones mientras se
    # llama a la API; un time.sleep() las dejaría detenidas. Por eso se espera con wait_for_timeout() de la página actual.
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond(): return True
        except Exception: pass
        try: CUR[0].wait_for_timeout(50)
        except Exception: time.sleep(0.05)
    return False
def csp_problems(log): return [m for m in log if 'Content Security Policy' in m or 'PAGEERROR' in m or 'Refused to' in m]

def login(br, email, pw, page='perfil'):
    ctx = new_ctx(br); log = []; pg = new_page(ctx, log)
    pg.goto(f'{ORIGIN}/login.html'); pg.fill('input[name=email]', email); pg.fill('input[name=pw]', pw); pg.click('button[type=submit]')
    pg.wait_for_url(re.compile(r'/perfil\.html$')); pg.wait_for_selector('body.tp-ok')
    if page != 'perfil': pg.goto(f'{ORIGIN}/{page}.html'); pg.wait_for_selector('body.tp-ok')
    return ctx, pg, log

# ---------- imágenes de prueba ----------
def img(w, h, fmt='JPEG', exif=False, alpha=False):
    y, x = np.indices((h, w)); arr = np.stack([(x * 255 // w), (y * 255 // h), ((x + y) * 255 // (w + h))], -1).astype(np.uint8)
    arr = (arr ^ (np.random.RandomState(1).randint(0, 8, arr.shape).astype(np.uint8)))
    im = Image.fromarray(arr)
    if alpha: im = im.convert('RGBA'); im.putalpha(Image.new('L', (w, h), 90))
    b = io.BytesIO(); kw = {}
    if exif:
        e = Image.Exif(); e[0x010F] = 'CamaraSecreta'; e[0x0132] = '2026:11:04 12:00:00'; kw['exif'] = e
    im.save(b, fmt, **kw); return b.getvalue()
def upload_file(pg, sel, data, name, mime): pg.set_input_files(sel, files=[dict(name=name, mimeType=mime, buffer=data)])
def objects(bucket): return {k[1]: o for k, o in be.objects.items() if k[0] == bucket}
def posts(table, method='POST'): return [c for c in be.calls if c['path'] == '/rest/v1/' + table and c['method'] == method]
def visible_msg(pg, sel): return pg.locator(sel).inner_text() if pg.locator(sel).count() and pg.locator(sel).first.is_visible() else ''
def seed_pet(uid, name, species='perro'):
    be.tables['pets'].append(dict(id=__import__('uuid').uuid4().hex[:8] + '-0000-4000-8000-' + __import__('uuid').uuid4().hex[:12], owner_id=uid, name=name, photo_path=None,
        species=species, breed=None, sex=None, birth_date=None, weight_kg=None, description=None, vet_info=None, created_at='2026-11-0%dT00:00:00Z%03d' % (1 + len(be.tables['pets']) % 9, len(be.tables['pets']))))
def decode_qr(png):
    im = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    for det in (cv2.QRCodeDetector(), cv2.QRCodeDetectorAruco()):
        for scale in (1, 2, 3):
            g = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST) if scale > 1 else im
            txt, _, _ = det.detectAndDecode(g)
            if txt: return txt
    return ''
def today(delta=0): return (datetime.date.today() + datetime.timedelta(days=delta)).isoformat()

with sync_playwright() as pw:
    br = pw.chromium.launch()
    OWNER, PW = 'dueno@ejemplo.mx', 'ClaveDueno123'

    # ================= 1. Mis mascotas =================
    print('\n[1] Mis mascotas')
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña Prueba'); other = be.add_user('otra@ejemplo.mx', 'ClaveOtra12345', 'owner', 'Otra')
    seed_pet(other, 'MascotaAjena')
    ctx, pg, log = login(br, OWNER, PW, 'mascota'); pg.wait_for_selector('#m-contador')
    waitjs(pg, "document.getElementById('m-contador').textContent.includes('de 30')")
    check('Sin mascotas: estado vacío y contador 0 de 30', pg.locator('#m-lista .empty').count() == 1 and '0 de 30' in pg.inner_text('#m-contador'))
    check('Una cuenta NO ve las mascotas de otra persona', 'MascotaAjena' not in pg.inner_text('body'))
    n0 = len(be.calls)
    for label, fill in [('nombre vacío', dict(n='', e='perro')), ('sin especie', dict(n='Luna', e='')), ('peso 0', dict(n='Luna', e='perro', w='0')),
                        ('peso 201', dict(n='Luna', e='perro', w='201')), ('nacimiento futuro', dict(n='Luna', e='perro', b=today(30))),
                        ('nacimiento antes de 1990', dict(n='Luna', e='perro', b='1985-05-05'))]:
        pg.fill('#m-nombre', fill['n']); pg.select_option('#m-especie', fill['e']); pg.fill('#m-peso', fill.get('w', '')); pg.fill('#m-nac', fill.get('b', ''))
        pg.click('#m-guardar')
        check(f'Validación en pantalla: {label}', pg.locator('#msg-form.err').count() == 1 and pg.locator('#msg-form').is_visible(), visible_msg(pg, '#msg-form'))
    check('Los datos inválidos NO llegan al servidor', len(posts('pets')) == 0)
    pg.fill('#m-nombre', 'Luna'); pg.select_option('#m-especie', 'perro'); pg.fill('#m-raza', 'Mestiza'); pg.select_option('#m-sexo', 'hembra')
    pg.fill('#m-nac', '2023-01-15'); pg.fill('#m-peso', '12.5'); pg.fill('#m-desc', '<img src=x onerror="window.__xss=1"> Juguetona'); pg.fill('#m-vet', 'Alérgica al pollo')
    pg.click('#m-guardar'); pg.wait_for_selector('#m-lista .pet')
    body = posts('pets')[0]['body']
    check('Crear mascota: el cuerpo solo lleva campos permitidos (sin owner_id)', set(body) <= {'name', 'species', 'breed', 'sex', 'birth_date', 'weight_kg', 'description', 'vet_info'} and 'owner_id' not in body, body)
    check('Crear mascota: aparece la ficha con sus datos', all(s in pg.inner_text('#m-lista') for s in ['Luna', 'Perro', 'Mestiza', 'Hembra', '12.5 kg', 'Alérgica al pollo']))
    check('Edad calculada en español', re.search(r'Edad: \d+ años?', pg.inner_text('#m-lista')) is not None, pg.inner_text('#m-lista'))
    check('Texto con HTML/JS se muestra como TEXTO (sin XSS)', pg.evaluate('window.__xss') is None and pg.locator('#m-lista img[src="x"]').count() == 0 and '<img src=x' in pg.inner_text('#m-lista'))
    check('Mensaje de éxito y formulario limpio', 'Mascota agregada' in visible_msg(pg, '#msg-form') and pg.input_value('#m-nombre') == '')
    check('Contador actualizado', '1 de 30' in pg.inner_text('#m-contador'))
    check('Hay enlace a su carnet con ?pet=', pg.locator('#m-lista a[href^="carnet.html?pet="]').count() == 1)

    # --- fotos
    pg.fill('#m-nombre', 'Michi'); pg.select_option('#m-especie', 'gato')
    big = img(3000, 2000, 'JPEG', exif=True)
    assert b'CamaraSecreta' in big
    upload_file(pg, '#m-foto', big, 'michi.jpg', 'image/jpeg'); pg.click('#m-guardar'); waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===2")
    pets = be.tables['pets']; michi = next(p for p in pets if p['name'] == 'Michi')
    ob = objects('pet-photos')
    check('Foto: se subió UN archivo a pet-photos con ruta <id-usuario>/<uuid>.jpg', len(ob) == 1 and re.match(r'^' + uid + r'/[0-9a-f-]{36}\.jpg$', list(ob)[0]), list(ob))
    data = list(ob.values())[0]['data']; im = Image.open(io.BytesIO(data))
    check('Foto reducida a 1600 px como máximo y re-codificada como JPEG', im.format == 'JPEG' and max(im.size) <= 1600 and len(data) < len(big), (im.format, im.size, len(data), len(big)))
    check('Foto: se eliminaron los metadatos EXIF (cámara, fecha, ubicación)', b'CamaraSecreta' not in data and not im.getexif())
    check('La mascota guarda la ruta de su foto', michi['photo_path'] == list(ob)[0])
    pg.wait_for_selector('#m-lista img.pic')
    waitjs(pg, "[...document.querySelectorAll('#m-lista img.pic')].every(i=>i.complete&&i.naturalWidth>0)")
    src = pg.get_attribute('#m-lista img.pic', 'src')
    check('La foto privada se muestra con URL FIRMADA temporal', '/storage/v1/object/sign/pet-photos/' in src and 'token=' in src, src)
    # reemplazar con PNG transparente
    pg.click('#m-lista .pet:nth-child(2) button:has-text("Editar")')
    check('Editar: el formulario se llena y cambia el título', pg.input_value('#m-nombre') == 'Michi' and 'Editar a Michi' in pg.inner_text('#m-form-title') and pg.is_visible('#m-quitar-fila'))
    upload_file(pg, '#m-foto', img(400, 300, 'PNG', alpha=True), 'nueva.png', 'image/png'); pg.click('#m-guardar')
    waitjs(pg, "document.getElementById('msg-form').textContent.includes('Cambios guardados')")
    ob2 = objects('pet-photos'); michi = next(p for p in be.tables['pets'] if p['name'] == 'Michi')
    check('Reemplazar foto: el archivo anterior se borra del almacenamiento (queda 1)', michi['photo_path'] in ob2 and michi['photo_path'] != list(ob)[0] and eventually(lambda: len(objects('pet-photos')) == 1), list(objects('pet-photos')))
    check('Reemplazar foto: un PNG transparente se guarda como JPEG', Image.open(io.BytesIO(list(ob2.values())[0]['data'])).format == 'JPEG')
    pg.click('#m-lista .pet:nth-child(2) button:has-text("Editar")'); pg.check('#m-quitar'); pg.click('#m-guardar')
    waitjs(pg, "document.getElementById('msg-form').textContent.includes('Cambios guardados')")
    michi = next(p for p in be.tables['pets'] if p['name'] == 'Michi')
    check('Quitar foto: la ruta queda vacía y el archivo se borra', michi['photo_path'] is None and eventually(lambda: len(objects('pet-photos')) == 0))
    check('Sin foto se muestra un icono de la especie', pg.locator('#m-lista .pet .ph-emoji').count() == 2)

    # --- archivos no permitidos
    ncalls = len(be.calls)
    pg.fill('#m-nombre', 'Bad1'); pg.select_option('#m-especie', 'ave')
    for label, data, name, mime, expect in [('archivo de texto disfrazado de .jpg', b'esto no es una imagen', 'falso.jpg', 'image/jpeg', 'No se pudo leer'),
                                           ('GIF', b'GIF89a\x01\x00\x01\x00', 'a.gif', 'image/gif', 'JPG, PNG o WebP'),
                                           ('PDF', b'%PDF-1.4', 'a.pdf', 'application/pdf', 'JPG, PNG o WebP'),
                                           ('imagen de más de 15 MB', b'\xff\xd8\xff' + b'0' * (16 * 1024 * 1024), 'enorme.jpg', 'image/jpeg', 'pesa demasiado')]:
        upload_file(pg, '#m-foto', data, name, mime); pg.click('#m-guardar')
        waitjs(pg, "document.getElementById('msg-form').classList.contains('err')")
        check(f'Rechaza {label}', expect in visible_msg(pg, '#msg-form'), visible_msg(pg, '#msg-form'))
    check('Los archivos rechazados no producen ninguna petición a Supabase ni crean la mascota', len(be.calls) == ncalls and len([p for p in be.tables['pets'] if p['owner_id'] == uid]) == 2, (len(be.calls) - ncalls))
    pg.set_input_files('#m-foto', []); pg.fill('#m-nombre', '')

    # --- falla el almacenamiento: la mascota se guarda igual, con aviso honesto
    pg.fill('#m-nombre', 'Kiwi'); pg.select_option('#m-especie', 'ave'); upload_file(pg, '#m-foto', img(300, 200), 'k.jpg', 'image/jpeg')
    be.storage_fail = 500; pg.click('#m-guardar'); waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===3")
    be.storage_fail = None
    check('Si falla la subida de la foto: la mascota se guarda y se avisa claramente', 'se guardó, pero la foto no se pudo actualizar' in visible_msg(pg, '#msg-form'), visible_msg(pg, '#msg-form'))

    # --- eliminar
    pg.click('#m-lista .pet:nth-child(3) button:has-text("Eliminar")')
    check('Eliminar pide confirmación y avisa del carnet y la placa', 'Se borrará también su carnet y su placa QR' in pg.inner_text('#m-lista'))
    pg.click('#m-lista button:has-text("Cancelar")')
    check('Cancelar no borra nada', pg.locator('#m-lista .pet').count() == 3)
    pg.click('#m-lista .pet:nth-child(3) button:has-text("Eliminar")'); pg.click('#m-lista button:has-text("Sí, eliminar")')
    waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===2")
    check('Eliminar: la mascota desaparece', 'Kiwi' not in pg.inner_text('#m-lista') and 'fue eliminada' in visible_msg(pg, '#msg-global'))
    check('Eliminar: se limpian sus archivos', eventually(lambda: len(objects('pet-photos')) == 0))
    pg.fill('#m-nombre', 'Fotito'); pg.select_option('#m-especie', 'conejo'); upload_file(pg, '#m-foto', img(500, 400), 'f.jpg', 'image/jpeg'); pg.click('#m-guardar')
    waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===3"); fot = list(objects('pet-photos'))
    check('Mascota con foto: el archivo existe antes de eliminarla', len(fot) == 1, fot)
    pg.click('#m-lista .pet:nth-child(3) button:has-text("Eliminar")'); pg.click('#m-lista button:has-text("Sí, eliminar")')
    waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===2")
    check('Eliminar una mascota CON foto borra también su archivo del almacenamiento', eventually(lambda: len(objects('pet-photos')) == 0), list(objects('pet-photos')))
    check('Páginas de la Etapa 4: sin errores de script ni violaciones de CSP (mascota)', not csp_problems(log), csp_problems(log)[:3])
    ctx.close()

    # --- límite de 30 mascotas y cuenta suspendida
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña')
    for i in range(29): seed_pet(uid, f'm{i}')
    ctx, pg, log = login(br, OWNER, PW, 'mascota'); waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===29")
    pg.fill('#m-nombre', 'Numero30'); pg.select_option('#m-especie', 'perro'); pg.click('#m-guardar'); waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===30")
    check('Con 29 mascotas se puede agregar la 30.ª', True)
    check('Con 30 mascotas el formulario queda bloqueado y avisa del límite', pg.is_disabled('#m-guardar') and pg.is_visible('#m-limite') and '30 mascotas' in pg.inner_text('#m-limite'))
    ctx.close()
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña', suspended=True); seed_pet(uid, 'Pelusa')
    ctx, pg, log = login(br, OWNER, PW, 'mascota'); pg.wait_for_selector('#m-lista .pet')
    check('Cuenta suspendida: ve sus mascotas pero no puede editar ni eliminar ni crear', pg.is_disabled('#m-guardar') and pg.is_disabled('#m-lista button:has-text("Editar")') and pg.is_disabled('#m-lista button:has-text("Eliminar")'))
    ctx.close()

    # ================= 2. Carnet digital =================
    print('\n[2] Carnet digital')
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña'); other = be.add_user('otra@ejemplo.mx', 'ClaveOtra12345', 'owner', 'Otra')
    seed_pet(uid, 'Luna'); seed_pet(uid, 'Michi', 'gato'); seed_pet(uid, 'Kiwi', 'ave'); seed_pet(other, 'Ajena')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('#c-contenido:not([hidden])'); pg.wait_for_selector('#vac-msg', state='attached')
    check('Plan Básica: avisa que el carnet no está incluido', 'no incluye el carnet de salud digital' in pg.inner_text('#c-plan'), pg.inner_text('#c-plan'))
    check('Plan Básica: no hay botones para agregar registros', not any(pg.locator(f'#sec-{k} button:has-text("Agregar")').count() for k in ('vac', 'des', 'cit')) or all(not pg.locator(f'#sec-{k} button:has-text("Agregar")').first.is_visible() for k in ('vac', 'des', 'cit')))
    check('El selector lista SOLO las mascotas propias', [o for o in pg.locator('#c-mascota option').all_inner_texts()] == ['Luna (Perro)', 'Michi (Gato)', 'Kiwi (Ave)'], pg.locator('#c-mascota option').all_inner_texts())
    check('Sin plan no se muestra la creación de placa QR (aviso de Huellita VIP)', 'Huellita VIP' in pg.inner_text('#sec-qr') and pg.locator('#sec-qr button:has-text("Crear placa QR")').count() == 0)
    ctx.close()

    be.set_plan(OWNER, 'pro')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('#vac-msg', state='attached')
    check('Plan Pro: avisa el límite de 2 mascotas con carnet', 'permite carnet de salud para 2 mascotas' in pg.inner_text('#c-plan'))
    pg.click('#sec-vac button:has-text("Agregar vacuna")')
    n0 = len(posts('pet_vaccinations'))
    def vac(name, applied, nxt='', vet='', notes=''):
        pg.fill('#vac-vaccine_name', name); pg.fill('#vac-applied_on', applied); pg.fill('#vac-next_due_on', nxt); pg.fill('#vac-veterinario' if False else '#vac-veterinarian', vet); pg.fill('#vac-notes', notes)
        pg.click('#sec-vac form button[type=submit]')
    for label, args in [('vacuna sin nombre', ('', today(-3))), ('sin fecha de aplicación', ('Rabia', '')), ('aplicada en el futuro', ('Rabia', today(10))),
                        ('próxima fecha anterior a la aplicación', ('Rabia', today(-3), today(-20))), ('fecha antes de 1990', ('Rabia', '1980-01-01'))]:
        vac(*args)
        check(f'Carnet, validación: {label}', pg.locator('#vac-msg.err').count() == 1 and pg.is_visible('#vac-msg'), visible_msg(pg, '#vac-msg'))
    check('Carnet: los datos inválidos no llegan al servidor', len(posts('pet_vaccinations')) == n0)
    vac('Rabia <b>fuerte</b>', today(-400), today(-35), 'Dra. López', 'Sin reacciones'); pg.wait_for_selector('#sec-vac .recs li:not(.empty-li)')
    b = posts('pet_vaccinations')[-1]['body']
    check('Vacuna guardada: el cuerpo lleva pet_id y solo campos permitidos', set(b) <= {'pet_id', 'vaccine_name', 'applied_on', 'next_due_on', 'veterinarian', 'notes'} and b['pet_id'] == be.tables['pets'][0]['id'], b)
    txt = pg.inner_text('#sec-vac .recs')
    check('La vacuna se muestra con fechas en español, veterinario y notas', all(s in txt for s in ['Rabia <b>fuerte</b>', 'Aplicada:', 'Dra. López', 'Sin reacciones']) and re.search(r'\d{1,2} [a-z]{3} \d{4}', txt) is not None, txt)
    check('Una próxima fecha ya pasada se marca como «Vencida»', pg.locator('#sec-vac .badge.warn', has_text='Vencida').count() == 1)
    check('Nombre con HTML se muestra como texto (sin etiquetas reales)', pg.locator('#sec-vac .recs b').count() == 1 and '<b>' in txt)
    pg.click('#sec-vac button:has-text("Editar")')
    check('Editar vacuna: el formulario se llena', pg.input_value('#vac-vaccine_name') == 'Rabia <b>fuerte</b>' and pg.input_value('#vac-applied_on') == today(-400))
    pg.fill('#vac-notes', 'Notas nuevas'); pg.click('#sec-vac form button[type=submit]'); waitjs(pg, "document.getElementById('vac-msg').textContent.includes('Cambios guardados')")
    check('Editar vacuna: PATCH con los campos del formulario y notas actualizadas', posts('pet_vaccinations', 'PATCH')[-1]['body']['notes'] == 'Notas nuevas' and 'Notas nuevas' in pg.inner_text('#sec-vac .recs'))
    # desparasitación
    pg.click('#sec-des button:has-text("Agregar desparasitación")'); pg.fill('#des-product_name', 'Antiparasitario X'); pg.select_option('#des-kind', 'ambas'); pg.fill('#des-applied_on', today(-5)); pg.fill('#des-next_due_on', today(60))
    pg.click('#sec-des form button[type=submit]'); pg.wait_for_selector('#sec-des .recs li:not(.empty-li)')
    check('Desparasitación guardada y mostrada con su tipo', 'Antiparasitario X' in pg.inner_text('#sec-des') and 'Interna y externa' in pg.inner_text('#sec-des') and pg.locator('#sec-des .badge.warn').count() == 0)
    # citas
    pg.click('#sec-cit button:has-text("Agregar cita")'); pg.select_option('#cit-kind', 'vacunacion'); pg.fill('#cit-scheduled_at', '2026-12-01T10:30'); pg.fill('#cit-clinic', 'Clínica Patitas'); pg.fill('#cit-reason', 'Refuerzo')
    pg.click('#sec-cit form button[type=submit]'); pg.wait_for_selector('#sec-cit .recs li:not(.empty-li)')
    cb = posts('pet_appointments')[-1]['body']
    check('Cita: la hora se envía en UTC correctamente desde hora de Ciudad de México (10:30 → 16:30Z)', cb['scheduled_at'].startswith('2026-12-01T16:30:00'), cb['scheduled_at'])
    check('Cita: se muestra la hora de Ciudad de México y el estado', '10:30' in pg.inner_text('#sec-cit .recs') and 'Programada' in pg.inner_text('#sec-cit .recs') and 'Vacunación' in pg.inner_text('#sec-cit .recs'), pg.inner_text('#sec-cit .recs'))
    pg.click('#sec-cit button:has-text("Editar")')
    check('Cita: al editar, la hora se rellena igual que se escribió (10:30)', pg.input_value('#cit-scheduled_at') == '2026-12-01T10:30', pg.input_value('#cit-scheduled_at'))
    pg.select_option('#cit-status', 'realizada'); pg.click('#sec-cit form button[type=submit]'); waitjs(pg, "document.getElementById('cit-msg').textContent.includes('Cambios guardados')")
    check('Cita marcada como realizada (consulta)', 'Realizada' in pg.inner_text('#sec-cit .recs'))
    # límite de plan del servidor (Pro: 2 mascotas). Mascota 2 con carnet → ok; mascota 3 → rechazo del servidor
    pg.select_option('#c-mascota', index=1); waitjs(pg, "document.querySelector('#sec-vac .recs .empty-li')")
    pg.click('#sec-vac button:has-text("Agregar vacuna")'); vac('Triple felina', today(-10)); pg.wait_for_selector('#sec-vac .recs li:not(.empty-li)')
    check('Cambiar de mascota recarga el carnet y el enlace ?pet=', 'pet=' + be.tables['pets'][1]['id'] in pg.url, pg.url)
    pg.select_option('#c-mascota', index=2); waitjs(pg, "document.querySelector('#sec-vac .recs .empty-li')")
    pg.click('#sec-vac button:has-text("Agregar vacuna")'); vac('Quíntuple aviar', today(-10)); pg.wait_for_selector('#vac-msg.err', state='visible')
    check('Con Pro, el servidor rechaza el carnet de una 3.ª mascota y la pantalla lo explica', 'permite carnet de salud para 2 mascota' in visible_msg(pg, '#vac-msg'), visible_msg(pg, '#vac-msg'))
    check('Las vacunas de una mascota no aparecen en otra', 'Rabia' not in pg.inner_text('#sec-vac .recs'))
    # eliminar con confirmación
    pg.select_option('#c-mascota', index=0); pg.wait_for_selector('#sec-vac .recs li:not(.empty-li)')
    pg.click('#sec-vac button:has-text("Eliminar")'); pg.click('#sec-vac button:has-text("Cancelar")')
    check('Eliminar registro: cancelar no borra', len(be.tables['pet_vaccinations']) == 2)
    pg.click('#sec-vac button:has-text("Eliminar")'); pg.click('#sec-vac button:has-text("Sí, eliminar")'); pg.wait_for_selector('#sec-vac .empty-li')
    check('Eliminar registro: se borra', len([v for v in be.tables['pet_vaccinations'] if v['vaccine_name'].startswith('Rabia')]) == 0)
    check('Carnet: sin errores de script ni CSP', not csp_problems(log), csp_problems(log)[:3])
    # ?pet= honra la mascota; un valor inválido cae en la primera
    pg.goto(f"{ORIGIN}/carnet.html?pet={be.tables['pets'][1]['id']}"); pg.wait_for_selector('#c-contenido:not([hidden])')
    check('?pet= selecciona esa mascota', pg.input_value('#c-mascota') == be.tables['pets'][1]['id'])
    pg.goto(f"{ORIGIN}/carnet.html?pet={be.tables['pets'][3]['id']}"); pg.wait_for_selector('#c-contenido:not([hidden])')
    check('?pet= con la mascota de OTRA persona se ignora (primera mascota propia)', pg.input_value('#c-mascota') == be.tables['pets'][0]['id'])
    ctx.close()
    be.reset(); be.add_user(OWNER, PW, 'owner', 'Dueña')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('#c-vacio:not([hidden])')
    check('Sin mascotas: invita a registrar una primero', 'Primero registra una mascota' in pg.inner_text('#c-vacio') and pg.is_hidden('#c-contenido'))
    ctx.close()

    # ================= 3. Placa QR =================
    print('\n[3] Placa QR (privado y público)')
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña Prueba'); seed_pet(uid, 'Luna'); seed_pet(uid, 'Michi', 'gato')
    be.tables['pets'][0]['breed'] = 'Mestiza'
    be.set_plan(OWNER, 'pro')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('#sec-qr h3')
    check('Plan Pro: la placa QR no se puede crear (avisa que es de Huellita VIP)', pg.locator('#sec-qr button:has-text("Crear placa QR")').count() == 0 and 'Huellita VIP' in pg.inner_text('#sec-qr'))
    ctx.close()
    be.set_plan(OWNER, 'vip')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('#sec-qr button:has-text("Crear placa QR")')
    pg.click('#sec-qr button:has-text("Crear placa QR")'); pg.wait_for_selector('.qrpic svg')
    row = be.tables['pet_qr_profiles'][0]; link = pg.input_value('.qrinfo input')
    check('Crear placa: el cuerpo solo lleva pet_id (el token lo genera el servidor)', posts('pet_qr_profiles')[0]['body'] == {'pet_id': be.tables['pets'][0]['id']}, posts('pet_qr_profiles')[0]['body'])
    check('El enlace público es <sitio>/qr.html?t=<64 hex>', re.fullmatch(re.escape(ORIGIN) + r'/qr\.html\?t=[0-9a-f]{64}', link) is not None and link.endswith(row['public_token']), link)
    check('Desde localhost avisa que el QR solo serviría ahí', 'solo funcionaría aquí' in pg.inner_text('.qrinfo'))
    png = pg.locator('.qrpic svg').screenshot()
    check('El QR que se ve en pantalla SE DECODIFICA al enlace exacto (lector independiente)', decode_qr(png) == link, decode_qr(png))
    with pg.expect_download() as dl: pg.click('button:has-text("Descargar PNG")')
    pngd = open(dl.value.path(), 'rb').read()
    check('Descargar PNG: archivo PNG que se decodifica al enlace', pngd[:8] == b'\x89PNG\r\n\x1a\n' and decode_qr(pngd) == link and dl.value.suggested_filename == 'placa-qr-luna.png', dl.value.suggested_filename)
    with pg.expect_download() as dl2: pg.click('button:has-text("Descargar SVG")')
    svg = open(dl2.value.path(), encoding='utf-8').read()
    check('Descargar SVG: documento SVG válido con el código', svg.startswith('<svg') and '<path' in svg and 'script' not in svg.lower())
    # validaciones
    pg.check('#sec-qr form label:has-text("Mostrar el teléfono públicamente") input'); pg.click('#sec-qr button:has-text("Guardar placa")')
    check('Mostrar teléfono sin escribirlo → error', 'escríbelo primero' in visible_msg(pg, '#sec-qr form .msg'))
    pg.fill('#sec-qr form input[type=tel]', 'abc'); pg.click('#sec-qr button:has-text("Guardar placa")')
    check('Teléfono con letras → error', 'solo puede llevar números' in visible_msg(pg, '#sec-qr form .msg'))
    pg.fill('#sec-qr form input[type=tel]', ''); pg.uncheck('#sec-qr form label:has-text("Mostrar el teléfono públicamente") input')
    pg.check('#sec-qr form label:has-text("Mostrar la foto pública") input'); pg.click('#sec-qr button:has-text("Guardar placa")')
    check('Mostrar la foto sin haber subido una → error', 'sube primero la que quieres hacer pública' in visible_msg(pg, '#sec-qr form .msg'))
    check('Las validaciones no producen peticiones PATCH', len(posts('pet_qr_profiles', 'PATCH')) == 0)
    pg.uncheck('#sec-qr form label:has-text("Mostrar la foto pública") input')
    # guardar con contacto + mensaje
    pg.fill('#sec-qr form textarea', 'Si me encuentras, llámanos. <script>alert(1)</script>'); pg.fill('#sec-qr form input[type=text][maxlength="80"]', 'Ana')
    pg.fill('#sec-qr form input[type=tel]', '55 1234 5678'); pg.check('#sec-qr form label:has-text("Mostrar el teléfono públicamente") input'); pg.click('#sec-qr button:has-text("Guardar placa")')
    waitjs(pg, "[...document.querySelectorAll('#sec-qr .msg')].some(m=>m.textContent.includes('Placa guardada'))")
    pb = posts('pet_qr_profiles', 'PATCH')[-1]['body']
    check('Placa guardada: PATCH sin token, sin pet_id y con lo elegido', 'public_token' not in pb and 'pet_id' not in pb and pb['show_phone'] is True and pb['contact_phone'] == '55 1234 5678', pb)
    ctx.close()

    # --- página pública (visitante anónimo, otro contexto)
    pub = new_ctx(br); plog = []; pp = new_page(pub, plog)
    pp.goto(link); pp.wait_for_selector('.pubcard h1')
    ptxt = pp.inner_text('#q-contenido')
    check('Página pública: muestra nombre, especie y raza', 'Luna' in ptxt and 'Perro' in ptxt and 'Mestiza' in ptxt, ptxt)
    check('Página pública: muestra el mensaje como texto (sin ejecutar HTML)', 'Si me encuentras' in ptxt and pp.locator('#q-contenido script').count() == 0 and '<script>' in ptxt)
    check('Página pública: teléfono autorizado con enlace tel: seguro', pp.get_attribute('#q-contenido a[href^="tel:"]', 'href') == 'tel:5512345678' and 'Ana' in ptxt)
    check('Página pública: NO aparece correo, dirección ni datos del dueño', not re.search(r'@|ejemplo|Dueña|dirección de|owner', ptxt.replace('TECNOPATITAS no comparte direcciones ni correos', '')), ptxt)
    pcalls = [c for c in be.calls if c['path'] == '/rest/v1/rpc/get_public_pet_profile']
    check('La consulta pública va SIN sesión (sin cabecera Authorization)', pcalls and all('authorization' not in c['headers'] for c in pcalls), [list(c['headers']) for c in pcalls][:1])
    check('Página pública: sin errores de script ni CSP', not csp_problems(plog), csp_problems(plog)[:3])
    check('La página pública no se indexa y no envía el enlace como Referer', pp.locator('meta[name=robots][content*=noindex]').count() == 1 and pp.locator('meta[name=referrer][content=no-referrer]').count() == 1)
    for label, url in [('sin código', '/qr.html'), ('código corto', '/qr.html?t=abc'), ('inyección SQL', "/qr.html?t=' OR '1'='1"), ('código con 64 letras no hex', '/qr.html?t=' + 'z' * 64)]:
        before = len([c for c in be.calls if 'get_public_pet_profile' in c['path']])
        pp.goto(ORIGIN + url); pp.wait_for_selector('.pubcard h1')
        check(f'Enlace inválido ({label}): aviso neutro y NO consulta al servidor', 'Enlace no disponible' in pp.inner_text('#q-contenido') and len([c for c in be.calls if 'get_public_pet_profile' in c['path']]) == before)
    pp.goto(ORIGIN + '/qr.html?t=' + '0' * 64); pp.wait_for_selector('.pubcard h1')
    check('Código bien formado pero inexistente: MISMO aviso (no revela nada)', 'Enlace no disponible' in pp.inner_text('#q-contenido'))
    pub.close()

    # --- foto pública, privacidad, desactivar, regenerar
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('.qrpic svg')
    nb = len(be.calls); pg.goto(link); pg.wait_for_selector('.pubcard h1')
    pc = [c for c in be.calls[nb:] if c['path'] == '/rest/v1/rpc/get_public_pet_profile']
    check('Aunque el dueño tenga la sesión abierta, la página pública NO envía su sesión', pc and all('authorization' not in c['headers'] for c in pc) and pg.evaluate("!!localStorage.getItem('tp-auth-v1')"), [list(c['headers']) for c in pc])
    pg.goto(f'{ORIGIN}/carnet.html'); pg.wait_for_selector('.qrpic svg')
    upload_file(pg, '#sec-qr input[type=file]', img(2400, 1600, 'JPEG', exif=True), 'luna-qr.jpg', 'image/jpeg')
    pg.check('#sec-qr form label:has-text("Mostrar la foto pública") input'); pg.click('#sec-qr button:has-text("Guardar placa")')
    waitjs(pg, "[...document.querySelectorAll('#sec-qr .msg')].some(m=>m.textContent.includes('Placa guardada'))")
    qo = objects('qr-photos'); row = be.tables['pet_qr_profiles'][0]
    check('Foto pública: se sube a qr-photos (carpeta propia) y se guarda en la placa', len(qo) == 1 and row['qr_photo_path'] in qo and row['qr_photo_path'].startswith(uid + '/'), list(qo))
    qimg = Image.open(io.BytesIO(list(qo.values())[0]['data']))
    check('Foto pública: reducida a 800 px y sin metadatos EXIF', max(qimg.size) <= 800 and b'CamaraSecreta' not in list(qo.values())[0]['data'], qimg.size)
    check('La foto de la FICHA sigue privada: no se subió nada a pet-photos', len(objects('pet-photos')) == 0)
    check('La placa avisa que la foto es pública', 'PÚBLICA' in pg.inner_text('#sec-qr'))
    ctx.close()
    pub = new_ctx(br); pp = new_page(pub, []); pp.goto(link); pp.wait_for_selector('.pubcard img.pic')
    waitjs(pp, "document.querySelector('.pubcard img.pic').complete && document.querySelector('.pubcard img.pic').naturalWidth>0")
    check('Página pública: la foto autorizada se muestra desde el bucket público', '/storage/v1/object/public/qr-photos/' in pp.get_attribute('.pubcard img.pic', 'src'))
    be.tables['pet_qr_profiles'][0]['show_photo'] = False; pp.reload(); pp.wait_for_selector('.pubcard h1')
    check('Con «mostrar foto» apagado, la página pública NO la muestra', pp.locator('.pubcard img').count() == 0)
    be.tables['pet_qr_profiles'][0]['show_name'] = False; pp.reload(); pp.wait_for_selector('.pubcard h1')
    check('Con «mostrar nombre» apagado, no aparece el nombre', pp.inner_text('.pubcard h1') == 'Mascota' and 'Luna' not in pp.inner_text('#q-contenido'))
    be.tables['pet_qr_profiles'][0]['show_name'] = True; be.tables['pet_qr_profiles'][0]['is_active'] = False; pp.reload(); pp.wait_for_selector('.pubcard h1')
    check('Placa desactivada: el MISMO aviso que un enlace inexistente', 'Enlace no disponible' in pp.inner_text('#q-contenido'))
    be.tables['pet_qr_profiles'][0]['is_active'] = True
    pub.close()
    # regenerar enlace
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('.qrpic svg'); old = pg.input_value('.qrinfo input')
    pg.click('button:has-text("Generar enlace nuevo")')
    check('Regenerar: pide confirmación y advierte que los QR impresos dejarán de funcionar', 'dejarán de funcionar' in pg.inner_text('.qrinfo'))
    pg.click('button:has-text("Sí, generar nuevo")'); waitjs(pg, "document.querySelector('.qrinfo input').value!==%s" % json.dumps(old))
    new = pg.input_value('.qrinfo input')
    check('Regenerar: el enlace nuevo se ve y se decodifica en el nuevo QR', new != old and decode_qr(pg.locator('.qrpic svg').screenshot()) == new)
    pub = new_ctx(br); pp = new_page(pub, []); pp.goto(old); pp.wait_for_selector('.pubcard h1')
    check('Regenerar: el enlace ANTERIOR deja de funcionar', 'Enlace no disponible' in pp.inner_text('#q-contenido'))
    pp.goto(new); pp.wait_for_selector('.pubcard h1'); check('Regenerar: el enlace nuevo funciona', 'Luna' in pp.inner_text('#q-contenido'))
    pub.close()
    # el servidor rechaza una foto pública que apunta a la carpeta de otra persona (disparador guard_qr)
    r = pg.evaluate("""async (p)=>{try{await TP.rest('/pet_qr_profiles',{method:'PATCH',query:'pet_id=eq.'+p,body:{qr_photo_path:'00000000-0000-4000-8000-000000000000/robada.jpg'},prefer:'return=representation'});return 'ok'}catch(e){return e.code}}""", be.tables['pets'][0]['id'])
    check('El servidor rechaza una foto pública fuera de la carpeta propia (23514)', r == '23514', r)
    ctx.close()
    # el plan vence: la placa se conserva y se edita, pero ya no se pueden subir fotos nuevas
    be.set_plan(OWNER, 'basica')
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('.qrpic svg')
    check('Plan vencido: la placa existente sigue visible y editable', pg.locator('.qrpic svg').count() == 1 and not pg.is_disabled('#sec-qr button:has-text("Guardar placa")'))
    upload_file(pg, '#sec-qr input[type=file]', img(500, 400), 'otra.jpg', 'image/jpeg'); pg.click('#sec-qr button:has-text("Guardar placa")')
    waitjs(pg, "[...document.querySelectorAll('#sec-qr .msg')].some(m=>m.classList.contains('err')&&m.textContent.length>5)")
    check('Plan vencido: subir otra foto falla con un mensaje claro', 'No se pudo subir la imagen' in pg.inner_text('#sec-qr form .msg'), pg.inner_text('#sec-qr form .msg'))
    check('Plan vencido: la foto anterior no se pierde', len(objects('qr-photos')) == 1)
    pg.fill('#sec-qr form textarea', 'Mensaje nuevo con plan vencido'); pg.set_input_files('#sec-qr input[type=file]', []); pg.click('#sec-qr button:has-text("Guardar placa")')
    waitjs(pg, "[...document.querySelectorAll('#sec-qr .msg')].some(m=>m.textContent.includes('Placa guardada'))")
    check('Plan vencido: se puede seguir editando el texto de la placa', be.tables['pet_qr_profiles'][0]['public_message'] == 'Mensaje nuevo con plan vencido')
    ctx.close()
    # eliminar la mascota borra también la foto pública
    be.set_plan(OWNER, 'vip'); ctx, pg, log = login(br, OWNER, PW, 'mascota'); pg.wait_for_selector('#m-lista .pet')
    pg.click('#m-lista .pet:nth-child(1) button:has-text("Eliminar")'); pg.click('#m-lista button:has-text("Sí, eliminar")'); waitjs(pg, "document.querySelectorAll('#m-lista .pet').length===1")
    check('Eliminar mascota: se borran su placa y la foto pública', len(be.tables['pet_qr_profiles']) == 0 and eventually(lambda: len(objects('qr-photos')) == 0))
    ctx.close()
    # cuenta suspendida
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña', suspended=True); seed_pet(uid, 'Luna'); be.set_plan(OWNER, 'vip')
    be.tables['pet_qr_profiles'].append(dict(id='q1', pet_id=be.tables['pets'][0]['id'], public_token='a' * 64, is_active=True, show_name=True, show_photo=False, show_breed=True, public_message=None, contact_name=None, contact_phone=None, show_phone=False, qr_photo_path=None))
    ctx, pg, log = login(br, OWNER, PW, 'carnet'); pg.wait_for_selector('.qrpic svg')
    check('Cuenta suspendida: la placa se ve pero no se puede modificar', pg.is_disabled('#sec-qr button:has-text("Guardar placa")') and pg.is_disabled('button:has-text("Generar enlace nuevo")'))
    ctx.close()

    # ================= 4. Foto de perfil =================
    print('\n[4] Foto de perfil')
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña')
    ctx, pg, log = login(br, OWNER, PW, 'perfil'); pg.wait_for_selector('#p-foto')
    check('Sin foto: se muestra el icono y no el botón de quitar', pg.is_visible('#p-avatar-ph') and pg.is_hidden('#p-avatar') and pg.is_hidden('#p-foto-quitar'))
    upload_file(pg, '#p-foto', img(1200, 900, 'JPEG', exif=True), 'yo.jpg', 'image/jpeg'); waitjs(pg, "document.getElementById('msg-foto').textContent.includes('Foto actualizada')")
    av = objects('avatars'); prof = be.profiles[uid]
    check('Foto de perfil: se guarda en avatars/<id>/<uuid>.jpg y en el perfil', len(av) == 1 and prof['avatar_path'] in av and re.match(r'^' + uid + r'/[0-9a-f-]{36}\.jpg$', prof['avatar_path']), list(av))
    check('Foto de perfil: reducida a 512 px y sin EXIF', max(Image.open(io.BytesIO(list(av.values())[0]['data'])).size) <= 512 and b'CamaraSecreta' not in list(av.values())[0]['data'])
    waitjs(pg, "document.getElementById('p-avatar').complete&&document.getElementById('p-avatar').naturalWidth>0")
    check('Se muestra con URL firmada y se oculta el icono', '/storage/v1/object/sign/avatars/' in pg.get_attribute('#p-avatar', 'src') and pg.is_hidden('#p-avatar-ph'))
    old = prof['avatar_path']; upload_file(pg, '#p-foto', img(300, 300, 'PNG'), 'otra.png', 'image/png'); waitjs(pg, "document.getElementById('msg-foto').textContent.includes('Foto actualizada')")
    check('Cambiar la foto borra la anterior (siempre ≤ 3 archivos del tope)', eventually(lambda: len(objects('avatars')) == 1 and old not in objects('avatars')))
    upload_file(pg, '#p-foto', b'no soy imagen', 'x.jpg', 'image/jpeg'); waitjs(pg, "document.getElementById('msg-foto').classList.contains('err')")
    check('Un archivo que no es imagen se rechaza', 'No se pudo leer' in pg.inner_text('#msg-foto') and len(objects('avatars')) == 1)
    pg.click('#p-foto-quitar'); waitjs(pg, "document.getElementById('msg-foto').textContent.includes('Foto eliminada')")
    check('Quitar la foto: perfil sin ruta, archivo borrado, vuelve el icono', be.profiles[uid]['avatar_path'] is None and eventually(lambda: len(objects('avatars')) == 0) and pg.is_visible('#p-avatar-ph'), (be.profiles[uid]['avatar_path'], list(objects('avatars')), pg.is_visible('#p-avatar-ph')))
    check('Perfil con foto: sin errores de script ni CSP', not csp_problems(log), csp_problems(log)[:3])
    ctx.close()
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña', suspended=True)
    ctx, pg, log = login(br, OWNER, PW, 'perfil'); pg.wait_for_selector('#p-foto')
    check('Cuenta suspendida: no puede cambiar su foto', pg.is_disabled('#p-foto'))
    ctx.close()

    # ================= 5. Cliente de archivos (seguridad de rutas y tipos) =================
    print('\n[5] Cliente de archivos')
    be.reset(); uid = be.add_user(OWNER, PW, 'owner', 'Dueña')
    ctx, pg, log = login(br, OWNER, PW, 'perfil')
    js = """async ()=>{
      const out={},jpg=new Blob([new Uint8Array([255,216,255])],{type:'image/jpeg'}),uid=JSON.parse(localStorage.getItem('tp-auth-v1')).user.id;
      const t=async(k,f)=>{try{await f();out[k]='ok'}catch(e){out[k]=e.code}};
      await t('trav',()=>TP.storage.upload('pet-photos','../otro/x.jpg',jpg));
      await t('traversal2',()=>TP.storage.upload('pet-photos',uid+'/../x.jpg',jpg));
      await t('subcarpeta',()=>TP.storage.upload('pet-photos',uid+'/a/b.jpg',jpg));
      await t('bucket',()=>TP.storage.upload('guide-images',uid+'/x.jpg',jpg));
      await t('tipo',()=>TP.storage.upload('pet-photos',uid+'/x.jpg',new Blob(['hola'],{type:'text/html'})));
      await t('svg',()=>TP.storage.upload('pet-photos',uid+'/x.jpg',new Blob(['<svg/>'],{type:'image/svg+xml'})));
      await t('punto2',()=>TP.storage.upload('pet-photos',uid+'/..',jpg));
      await t('punto2r',()=>TP.storage.remove('pet-photos',[uid+'/..']));
      await t('remove',()=>TP.storage.remove('pet-photos',['../x.jpg']));
      out.pub1=TP.storage.publicUrl('avatars',uid+'/x.jpg'); out.pub2=TP.storage.publicUrl('qr-photos','../x.jpg');
      out.pub3=TP.storage.publicUrl('qr-photos',uid+'/x.jpg');
      out.pub4=TP.storage.publicUrl('business-media',uid+'/x.jpg'); out.pub5=TP.storage.publicUrl('business-media','../x.jpg'); out.pub6=TP.storage.publicUrl('pet-photos',uid+'/x.jpg');
      out.sign=JSON.stringify(await TP.storage.sign('pet-photos',['../x.jpg','nada']));
      return out}"""
    r = pg.evaluate(js)
    check('Rutas con «..» o subcarpetas se rechazan en el cliente antes de enviar nada', r['trav'] == 'bad_path' and r['traversal2'] == 'bad_path' and r['subcarpeta'] == 'bad_path', r)
    check('Buckets no previstos se rechazan', r['bucket'] == 'bad_path' and r['remove'] == 'bad_path')
    check('Una ruta que termina en «..» (carpeta superior) se rechaza al subir y al borrar', r['punto2'] == 'bad_path' and r['punto2r'] == 'bad_path', r)
    check('Solo se suben imágenes JPG/PNG/WebP (HTML y SVG se rechazan)', r['tipo'] == 'bad_file_type' and r['svg'] == 'bad_file_type', r)
    check('Solo qr-photos y business-media tienen URL pública; rutas raras y buckets privados no producen URL', r['pub1'] is None and r['pub2'] is None and r['pub3'].startswith('https://mtkbxnhsjqqdbrjeaslo.supabase.co/storage/v1/object/public/qr-photos/')
          and r['pub4'].startswith('https://mtkbxnhsjqqdbrjeaslo.supabase.co/storage/v1/object/public/business-media/') and r['pub5'] is None and r['pub6'] is None, r)
    check('Firmar rutas inválidas devuelve vacío sin llamar al servidor', r['sign'] == '{}' and not [c for c in be.calls if '/object/sign/' in c['path']])
    check('Ninguna llamada de archivos (rechazadas) llegó al servidor', not [c for c in be.calls if c['path'].startswith('/storage/')], [c['path'] for c in be.calls if c['path'].startswith('/storage/')][:3])
    ctx.close()
    br.close()

ok = sum(1 for _, c, _ in results if c)
print(f'\n===== {ok} / {len(results)} pruebas correctas =====')
for n, c, d in results:
    if not c: print('FALLA:', n, '->', d)
sys.exit(0 if ok == len(results) else 1)
