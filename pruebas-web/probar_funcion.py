"""
Pruebas de la función segura «submit-complaint» (Etapa 6).

Ejecuta el CÓDIGO REAL de supabase/functions/submit-complaint/index.ts (con Node: pruebas-web/servidor_funcion.mjs) contra una
base PostgreSQL LOCAL con el esquema REAL de database/ y un Storage y un Turnstile simulados. Comprueba validaciones, anti-robots,
límites, limpieza de fotos (EXIF/GPS/comentarios), anonimato y que no quede basura si algo falla.

Uso:  python3 pruebas-web/probar_funcion.py
Requiere: PostgreSQL local (PGHOST/PGPORT/PGUSER), Node 22+, Pillow, numpy.
"""
import datetime, http.client, io, json, os, re, struct, subprocess, sys, time, uuid
from zoneinfo import ZoneInfo
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
PORT = int(os.environ.get('TP_FN_PORT', 8799)); DB = os.environ.get('TP_WEB_DB', 'tp_web')
LEGACY = 'eyJ.clave-anterior-service_role.de-prueba'
KEY = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']+)'", open(os.path.join(ROOT, 'js/config.js'), encoding='utf-8').read()).group(1)
MX = ZoneInfo('America/Mexico_City')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

# ---------------------------------------------------------------- base de datos y servidor
def sh(*a, **kw): return subprocess.run(a, capture_output=True, text=True, **kw)
def sql(q, db=DB):
    r = sh('psql', '-X', '-q', '-t', '-A', '-d', db, '-c', q)
    return r.stdout.strip()
def prepare_db():
    env = dict(os.environ, PGOPTIONS='-c client_min_messages=warning')
    sh('psql', '-X', '-q', '-d', 'postgres', '-c', f'drop database if exists {DB}', '-c', f'create database {DB}')
    for f in ('database/pruebas/shim_supabase.sql', 'database/00_instalar_todo.sql'):
        r = subprocess.run(['psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-d', DB, '-o', '/dev/null'], input=open(os.path.join(ROOT, f), encoding='utf-8').read(),
                           capture_output=True, text=True, env=env)
        if r.returncode: raise SystemExit('No se pudo preparar la base: ' + r.stderr[:400])
def start_server():
    p = subprocess.Popen(['node', '--experimental-strip-types', '--no-warnings', os.path.join(HERE, 'servidor_funcion.mjs'), str(PORT)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=dict(os.environ, TP_WEB_DB=DB))
    t0 = time.time()
    while time.time() - t0 < 15:
        line = p.stdout.readline()
        if 'listo' in line: return p
        if p.poll() is not None: raise SystemExit('El servidor de prueba no arrancó: ' + line + p.stdout.read())
    raise SystemExit('El servidor de prueba no arrancó a tiempo')

def http_req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=60)
    c.request(method, path, body, headers or {})
    r = c.getresponse(); data = r.read(); c.close()
    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), data
def ctl(path, obj=None): return http_req('POST', path, json.dumps(obj or {}).encode(), {'content-type': 'application/json'})
def state(): return json.loads(http_req('GET', '/__state')[2])
def reset(): ctl('/__reset')
def config(**kw): ctl('/__config', kw)
def set_env(**kw): ctl('/__corrupt_env', kw)

def today(): return datetime.datetime.now(MX).date()
def good(**kw):
    f = dict(type='abandono', description='Hay un perro abandonado desde hace varios días en el terreno baldío.', approx_date=today().isoformat(),
             state='Jalisco', municipality='Zapopan', location_reference='Frente al parque', website='', **{'cf-turnstile-response': 'ok.' + uuid.uuid4().hex})
    f.update(kw); return f
def post(fields, photos=(), ip=None, headers=None, raw_len=None):
    b = '----tp' + uuid.uuid4().hex; parts = []
    for k, v in fields.items():
        if v is None: continue
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + (v if isinstance(v, bytes) else str(v).encode('utf-8')) + b'\r\n')
    for i, ph in enumerate(photos):
        name, ctype, data = ph if isinstance(ph, tuple) else (f'foto{i}.jpg', 'image/jpeg', ph)
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photos"; filename="{name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + data + b'\r\n')
    body = b''.join(parts) + f'--{b}--\r\n'.encode()
    h = {'content-type': f'multipart/form-data; boundary={b}', 'content-length': str(raw_len if raw_len is not None else len(body)), 'apikey': KEY}
    if ip: h['cf-connecting-ip'] = ip
    h.update(headers or {})
    st, hd, data = http_req('POST', '/functions/v1/submit-complaint', body, h)
    try: j = json.loads(data)
    except Exception: j = {'_raw': data[:200].decode('utf-8', 'replace')}
    return st, j
n_rows = lambda: int(sql('select count(*) from public.complaints'))
def ts_calls(): return len([x for x in state()['log'] if x['svc'] == 'turnstile'])
_ip = [0]
def ip():
    _ip[0] += 1; return f'198.51.{_ip[0] // 250}.{_ip[0] % 250 + 1}'

# ---------------------------------------------------------------- imágenes de prueba
def gradient(w, h, seed=1):
    y, x = np.indices((h, w)); arr = np.stack([(x * 255 // max(w, 1)), (y * 255 // max(h, 1)), ((x + y) * 255 // max(w + h, 1))], -1).astype(np.uint8)
    return Image.fromarray(arr ^ np.random.RandomState(seed).randint(0, 12, arr.shape).astype(np.uint8))
def jpg(w=320, h=240, **kw):
    b = io.BytesIO(); gradient(w, h).save(b, 'JPEG', quality=85, **kw); return b.getvalue()
def jpg_with_secrets():
    e = Image.Exif(); e[0x010F] = 'CamaraSecreta'; e[0x0110] = 'ModeloXYZ-777'; e[0x0132] = '2026:11:04 12:34:56'
    gps = e.get_ifd(0x8825); gps[1] = 'N'; gps[2] = (19.0, 25.0, 59.0); gps[3] = 'W'; gps[4] = (99.0, 7.0, 30.0)
    return jpg(exif=e.tobytes(), comment=b'COMENTARIO-PRIVADO-123', icc_profile=b'\x00' * 200 + b'PERFIL-SECRETO')
def pixels(data):
    im = Image.open(io.BytesIO(data)); im.load(); return np.array(im.convert('RGB'))
SECRETS = [b'Exif', b'CamaraSecreta', b'ModeloXYZ', b'COMENTARIO-PRIVADO', b'PERFIL-SECRETO', b'JFIF', b'SECRETPAYLOAD', b'GPS']
def clean_jpeg(data):
    return data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9' and not any(s in data for s in SECRETS)

# ================================================================ pruebas
prepare_db()
srv = start_server()
try:
    # ---------- 1. Petición, configuración y CORS ----------
    print('\n[1] Petición, configuración y CORS')
    reset()
    st, hd, _ = http_req('OPTIONS', '/functions/v1/submit-complaint', None, {'origin': 'https://tecnopatitas.pages.dev', 'access-control-request-method': 'POST'})
    check('OPTIONS (preflight) responde 204 con las cabeceras CORS que usa el navegador', st == 204 and hd.get('access-control-allow-origin') == '*' and 'apikey' in hd.get('access-control-allow-headers', '') and 'POST' in hd.get('access-control-allow-methods', ''), (st, hd))
    st, hd, d = http_req('GET', '/functions/v1/submit-complaint')
    check('GET no está permitido (405)', st == 405 and json.loads(d)['ok'] is False, (st, d))
    reset(); set_env(TURNSTILE_SECRET_KEY='')
    st, j = post(good(), ip=ip())
    check('Sin TURNSTILE_SECRET_KEY el reporte NO se acepta (falla cerrado, 503)', st == 503 and j.get('code') == 'not_configured' and n_rows() == 0 and ts_calls() == 0, (st, j))
    reset(); set_env(TURNSTILE_SECRET_KEY=None, SUPABASE_SECRET_KEYS='', SUPABASE_SERVICE_ROLE_KEY='')
    st, j = post(good(), ip=ip())
    check('Sin clave del servidor tampoco (503)', st == 503 and n_rows() == 0, (st, j))
    reset(); set_env(SUPABASE_URL='')
    st, j = post(good(), ip=ip())
    check('Sin SUPABASE_URL tampoco (503)', st == 503 and n_rows() == 0, (st, j))
    reset(); set_env(SUPABASE_SECRET_KEYS='esto no es json', SUPABASE_SERVICE_ROLE_KEY=LEGACY)
    st, j = post(good(), ip=ip())
    check('Si SUPABASE_SECRET_KEYS no se puede leer usa SUPABASE_SERVICE_ROLE_KEY (formato anterior: apikey + Authorization)', st == 200 and re.match(r'^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$', j.get('code', '')), (st, j))
    reset(); set_env(SUPABASE_SECRET_KEYS=json.dumps({'otra': 'sb_' + 'secret_PRUEBA_LOCAL_no_es_real'}))
    st, j = post(good(), ip=ip())
    check('Si no hay llave «default» toma la primera que exista', st == 200, (st, j))
    reset()
    st, j = post(good(), ip=ip())
    check('Con la clave nueva (sb_secret_) solo envía «apikey», sin «Authorization» (si no, Supabase responde Invalid JWT)', st == 200, (st, j))
    t0 = ts_calls(); st, j = post(good(), photos=[b'\x00' * 9_000_000], ip=ip())
    check('Un envío de más de 8 MB se rechaza (413) antes de leerlo y sin tocar Turnstile', st == 413 and ts_calls() == t0, (st, j))

    # ---------- 2. Validación (no gasta el token de Turnstile ni toca la base) ----------
    print('\n[2] Validación de los datos')
    reset(); base_rows = n_rows()
    def rej(name, status, **kw):
        t0 = ts_calls(); st, j = post(good(**kw), ip=ip())
        check(name, st == status and j.get('ok') is False and isinstance(j.get('error'), str) and 'sb_secret' not in json.dumps(j) and n_rows() == base_rows and ts_calls() == t0, (st, j))
    rej('Tipo inválido', 400, type='hackeo'); rej('Sin tipo', 400, type=None)
    rej('Descripción de 29 caracteres', 400, description='x' * 29)
    rej('Descripción solo de espacios y saltos', 400, description=' \n ' * 30)
    rej('Descripción de 4001 caracteres', 400, description='y' * 4001)
    rej('20 emojis son 20 caracteres (no 40): se rechaza como en la base de datos', 400, description='🐶' * 20)
    rej('Fecha con formato incorrecto', 400, approx_date='04/11/2026'); rej('Fecha imposible (30 de febrero)', 400, approx_date='2026-02-30')
    rej('Fecha anterior al año 2000', 400, approx_date='1999-12-31')
    rej('Fecha dos días en el futuro', 400, approx_date=(today() + datetime.timedelta(days=2)).isoformat())
    rej('Estado de 1 carácter', 400, state='J'); rej('Municipio vacío', 400, municipality='   ')
    rej('Estado de 81 caracteres', 400, state='e' * 81)
    rej('Referencia de 301 caracteres', 400, location_reference='r' * 301)
    rej('Campo de texto enviado como archivo', 400, type=None)
    t0 = ts_calls(); st, j = post(good(**{'cf-turnstile-response': 'ok.' + uuid.uuid4().hex}), photos=[jpg()] * 4, ip=ip())
    check('Más de 3 fotos (400): se rechaza sin tocar Turnstile y no se sube nada', st == 400 and state()['uploads'] == 0 and n_rows() == base_rows and ts_calls() == t0, (st, j))
    st, j = post({**good(), 'photos': 'texto en lugar de archivo'}, ip=ip())
    check('«photos» enviado como texto se rechaza', st in (400, 415) and n_rows() == base_rows, (st, j))
    st, j = post(good(approx_date=(today() + datetime.timedelta(days=1)).isoformat()), ip=ip())
    check('Mañana sí es válido (zona horaria de México)', st == 200, (st, j))
    r1 = sql("select tracking_code from public.complaints order by created_at desc limit 1")
    st, j = post(good(description='Perro   con\x00 dato ‮ raro y varias palabras para llegar al mínimo requerido de caracteres.'), ip=ip())
    desc = sql("select description from public.complaints order by created_at desc limit 1")
    check('Los caracteres de control y de cambio de dirección se eliminan del texto', st == 200 and '\x00' not in desc and '‮' not in desc and 'Perro' in desc, repr(desc))
    st, j = post(good(municipality='Zapo\x00pan\u200b', state='Jali\u202esco', location_reference='Frente\x07 al parque'), ip=ip())
    fila = sql("select municipality||'|'||state||'|'||location_reference from public.complaints order by created_at desc limit 1")
    check('También se limpian el estado, el municipio y la referencia', st == 200 and fila == 'Zapopan|Jalisco|Frente al parque', repr(fila))
    st, j = post(good(location_reference=''), ip=ip())
    check('Referencia vacía → se guarda como nula', st == 200 and sql("select location_reference is null from public.complaints order by created_at desc limit 1") == 't', (st, j))

    # ---------- 3. Anti-robots ----------
    print('\n[3] Cloudflare Turnstile')
    reset(); base_rows = n_rows()
    st, j = post({k: v for k, v in good().items() if k != 'cf-turnstile-response'}, ip=ip())
    check('Sin token → 403 «captcha» y no se guarda nada', st == 403 and j.get('code') == 'captcha' and n_rows() == base_rows and ts_calls() == 0, (st, j))
    st, j = post(good(**{'cf-turnstile-response': 'falso-123'}), ip=ip())
    check('Token inválido → 403 «captcha»', st == 403 and j.get('code') == 'captcha' and n_rows() == base_rows, (st, j))
    t0 = ts_calls(); st, j = post(good(**{'cf-turnstile-response': 'ok.' + 'a' * 2100}), ip=ip())
    check('Token de más de 2048 caracteres → 403 sin llamar a Cloudflare', st == 403 and ts_calls() == t0, (st, j))
    tok = 'ok.' + uuid.uuid4().hex
    st1, j1 = post(good(**{'cf-turnstile-response': tok}), ip=ip())
    st2, j2 = post(good(**{'cf-turnstile-response': tok}), ip=ip())
    check('El mismo token no sirve dos veces (reenviar la misma petición)', st1 == 200 and st2 == 403 and j2.get('code') == 'captcha', (st1, st2, j2))
    check('La función envió a Cloudflare la clave SECRETA del servidor (no la del navegador) y el token', all(x['secretOk'] for x in state()['log'] if x['svc'] == 'turnstile'), state()['log'])
    config(turnstile='down'); b = n_rows()
    st, j = post(good(), ip=ip())
    check('Si Cloudflare no responde: 503 «captcha_unavailable» y NO se acepta el reporte (falla cerrado)', st == 503 and j.get('code') == 'captcha_unavailable' and n_rows() == b, (st, j))
    config(turnstile='http500')
    st, j = post(good(), ip=ip())
    check('Si Cloudflare responde error 500: igual, no se acepta', st == 503 and n_rows() == b, (st, j))
    config(turnstile='normal'); set_env(TURNSTILE_SECRET_KEY='clave-equivocada')
    st, j = post(good(), ip=ip())
    check('Si la clave secreta configurada es incorrecta: 503 (no es culpa de quien denuncia) y no se acepta', st == 503 and n_rows() == b, (st, j))
    set_env(TURNSTILE_SECRET_KEY='1x0000000000000000000000000000000AA-prueba')

    # ---------- 4. Camino feliz ----------
    print('\n[4] Reporte sin fotos y con fotos')
    reset(); b = n_rows()
    st, j = post(good(), ip=ip())
    code = j.get('code', '')
    row = sql("select type||'|'||state||'|'||municipality||'|'||status||'|'||cardinality(photo_paths) from public.complaints where tracking_code = '%s'" % code)
    check('Reporte sin fotos: 200 con código de seguimiento y fila guardada', st == 200 and j.get('ok') is True and re.match(r'^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$', code) and row == 'abandono|Jalisco|Zapopan|recibida|0' and n_rows() == b + 1, (st, j, row))
    st, hd, d = http_req('POST', '/rest/v1/rpc/track_complaint', json.dumps({'p_code': code}).encode(), {'content-type': 'application/json'})
    tr = json.loads(d)
    check('El código sirve para consultar el estado (track_complaint)', st == 200 and tr.get('status') == 'recibida', (st, d))
    check('La respuesta de la función no trae nada más que ok y código', set(j) == {'ok', 'code'}, j)

    reset()
    secret = jpg_with_secrets()
    prog = jpg(400, 300, progressive=True)
    trailing = jpg(200, 150) + b'SECRETPAYLOAD-' + b'\x00' * 50
    check('(Preparación) las fotos de prueba SÍ traen datos ocultos antes de enviarlas', all(s in secret for s in (b'Exif', b'CamaraSecreta', b'COMENTARIO-PRIVADO')) and b'SECRETPAYLOAD' in trailing, '')
    st, j = post(good(), photos=[secret, prog, trailing], ip=ip())
    code = j.get('code', ''); stt = state()
    paths = sql("select array_to_string(photo_paths, ',') from public.complaints where tracking_code = '%s'" % code).split(',')
    check('3 fotos: 200, tres archivos con nombre «carpeta/1.jpg…3.jpg» en el espacio privado y las rutas guardadas en la denuncia',
          st == 200 and len(paths) == 3 and len(stt['objects']) == 3 and sorted(paths) == sorted(stt['objects']) and
          all(re.match(r'^[0-9a-f-]{36}/[123]\.jpg$', p) for p in paths) and len({p.split('/')[0] for p in paths}) == 1, (st, j, paths, stt['objects']))
    objs = {p: http_req('GET', '/__object?path=' + p)[2] for p in paths}
    check('Los archivos guardados NO conservan EXIF, GPS, cámara, comentarios, perfil de color ni datos escondidos al final', all(clean_jpeg(o) for o in objs.values()), {p: [s for s in SECRETS if s in o] for p, o in objs.items()})
    check('...y siguen siendo imágenes válidas con los MISMOS píxeles', np.array_equal(pixels(objs[paths[0]]), pixels(secret)) and np.array_equal(pixels(objs[paths[1]]), pixels(prog)) and np.array_equal(pixels(objs[paths[2]]), pixels(trailing[:trailing.index(b'SECRETPAYLOAD')])), '')
    check('...y Pillow ya no encuentra EXIF', all(len(Image.open(io.BytesIO(o)).getexif()) == 0 for o in objs.values()), '')
    up = [x for x in stt['log'] if x['svc'] == 'upload']
    check('Se subieron como image/jpeg y sin sobrescribir', all(x['type'] == 'image/jpeg' for x in up) and len(up) == 3, up)
    check('El nombre del archivo no tiene relación con el nombre original (se ignora «foto0.jpg»)', not any('foto' in p for p in paths), paths)

    # ---------- 5. Fotos inválidas ----------
    print('\n[5] Fotos inválidas')
    reset(); b = n_rows()
    png = io.BytesIO(); gradient(100, 80).save(png, 'PNG')
    big = io.BytesIO(); Image.fromarray(np.random.RandomState(5).randint(0, 255, (1700, 1700, 3), dtype=np.uint8)).save(big, 'JPEG', quality=95)
    wide = jpg(5000, 20)
    cut = jpg(300, 200)[:-300]
    def badphoto(name, status, data, ctype='image/jpeg'):
        t0 = ts_calls(); st, j = post(good(), photos=[('f.jpg', ctype, data)], ip=ip())
        check(name, st == status and j.get('ok') is False and n_rows() == b and state()['uploads'] == 0 and ts_calls() == t0, (st, j))
    badphoto('PNG disfrazado de .jpg → 415', 415, png.getvalue())
    badphoto('JPEG con el final cortado → 415', 415, cut)
    badphoto('HTML con extensión .jpg → 415', 415, b'<html><script>alert(1)</script></html>' * 20)
    badphoto('Un archivo que empieza como JPEG pero luego es basura → 415', 415, b'\xff\xd8' + b'\xff\xe1\x00\x10Exif\x00\x00' + b'\x00' * 200)
    badphoto('Foto de más de 2 MB → 413', 413, big.getvalue())
    badphoto('Foto de 5000 px de ancho → 413', 413, wide)
    badphoto('SVG → 415', 415, b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>' * 5, 'image/svg+xml')
    st, j = post(good(), photos=[('vacia.jpg', 'image/jpeg', b'')], ip=ip())
    check('Un archivo vacío se ignora (se trata como si no hubiera foto)', st == 200 and state()['uploads'] == 0, (st, j))

    # ---------- 6. Límites ----------
    print('\n[6] Límites por visitante y globales')
    reset(); same = '203.0.113.200'
    oks = [post(good(), ip=same)[0] for _ in range(5)]
    st6, j6 = post(good(), ip=same)
    check('5 reportes por hora desde una misma IP; el 6.º recibe 429', oks == [200] * 5 and st6 == 429 and j6.get('code') == 'rate', (oks, st6, j6))
    st, j = post(good(), ip=same, headers={'x-forwarded-for': '9.9.9.9', 'x-real-ip': '8.8.8.8'})
    check('Cambiar x-forwarded-for / x-real-ip NO evita el límite (manda cf-connecting-ip)', st == 429, (st, j))
    st, j = post(good(), ip='203.0.113.201')
    check('Otra IP sí puede enviar', st == 200, (st, j))
    st, j = post(good(), ip=None, headers={'x-forwarded-for': '203.0.113.210, 10.0.0.1'})
    check('Sin cf-connecting-ip se usa la primera IP de x-forwarded-for', st == 200, (st, j))
    st, j = post(good(), ip=None, headers={'x-forwarded-for': '203.0.113.210'})
    check('...y es la misma huella (cuenta contra el mismo visitante)', st == 200, (st, j))
    check('No queda ninguna IP en la base de datos (solo huellas)', sql("select count(*) from private.rate_limits where key like '%203.0.113%' or key like '%198.51%'") == '0', '')
    check('La tabla de denuncias no tiene columnas de identidad', sql("select count(*) from information_schema.columns where table_name='complaints' and column_name ~ '(user|owner|email|phone|reporter|session|^ip$|ip_|_ip)'") == '0', '')
    # cuota de archivos
    reset()
    sql("insert into storage.objects (bucket_id, name, metadata) values ('complaint-evidence', 'cuota/1.jpg', '{\"size\": 400000000}')")
    b = n_rows(); st, j = post(good(), photos=[jpg()], ip=ip())
    check('Con las evidencias ocupando demasiado espacio: 503, mensaje claro y NO se sube nada', st == 503 and 'fotograf' in j.get('error', '') and state()['uploads'] == 0 and n_rows() == b, (st, j))
    st, j = post(good(), ip=ip())
    check('...pero un reporte sin fotos entra', st == 200, (st, j))
    sql("delete from storage.objects where name = 'cuota/1.jpg'")

    # ---------- 7. Fallos a mitad de camino ----------
    print('\n[7] Fallos a mitad de camino (no debe quedar basura)')
    reset(); b = n_rows()
    config(failUploadAt=2)
    st, j = post(good(), photos=[jpg(300, 200, ), jpg(310, 200), jpg(320, 200)], ip=ip()); s = state()
    check('Si falla la subida de la 2.ª foto: 502, se borra la 1.ª y no se registra nada', st == 502 and j.get('code') == 'upload' and s['objects'] == [] and n_rows() == b, (st, j, s['objects']))
    check('...y el espacio registrado en la base también quedó limpio', sql("select count(*) from storage.objects where bucket_id = 'complaint-evidence'") == '0', '')
    reset(); config(failRpc='submit_complaint')
    st, j = post(good(), photos=[jpg(), jpg(330, 200)], ip=ip()); s = state()
    check('Si falla el registro de la denuncia: 500, se borran las fotos ya subidas y no se filtra el detalle del error', st == 500 and s['objects'] == [] and 'fallo simulado' not in json.dumps(j) and n_rows() == b, (st, j, s['objects']))
    reset(); config(failRpc='complaint_precheck')
    st, j = post(good(), photos=[jpg()], ip=ip()); s = state()
    check('Si falla el paso previo: 500 y no se sube nada', st == 500 and s['uploads'] == 0 and 'fallo simulado' not in json.dumps(j), (st, j))
    reset()
    st, j = post(good(), photos=[jpg()], ip=ip())
    check('Después de los fallos todo vuelve a funcionar', st == 200, (st, j))

    # ---------- 8. Campo trampa y anonimato ----------
    print('\n[8] Campo trampa, anonimato y secretos')
    reset(); b = n_rows()
    st, j = post(good(website='http://spam.example'), photos=[jpg()], ip=ip())
    fake = j.get('code', '')
    check('Campo trampa lleno: responde «éxito» con un código de aspecto real pero NO guarda nada ni sube fotos ni gasta límites', st == 200 and re.match(r'^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$', fake) and n_rows() == b and state()['uploads'] == 0 and ts_calls() == 0, (st, j))
    st, hd, d = http_req('POST', '/rest/v1/rpc/track_complaint', json.dumps({'p_code': fake}).encode(), {'content-type': 'application/json'})
    check('...y ese código falso no existe (no se puede consultar)', st == 200 and json.loads(d) is None, d)
    reset()
    st, j = post(good(), photos=[jpg()], ip='203.0.113.222', headers={'user-agent': 'Navegador-Secreto/9', 'referer': 'https://sitio.ejemplo/privado', 'cookie': 'sesion=abc'})
    dump = json.dumps(state()['log']) + json.dumps(j) + sql("select row_to_json(c)::text from public.complaints c order by created_at desc limit 1") + sql("select string_agg(key, ',') from private.rate_limits")
    check('Ni la IP, ni el user-agent, ni el referer, ni las cookies aparecen en la base de datos, las respuestas ni los registros de la función',
          not any(x in dump for x in ('203.0.113.222', 'Navegador-Secreto', 'sitio.ejemplo', 'sesion=abc')), '')
    allresp = ''.join(json.dumps(post(good(type='malo'), ip=ip())[1]) for _ in range(2))
    check('Ninguna respuesta contiene la clave secreta del servidor ni la de Turnstile', 'sb_secret' not in allresp and 'prueba' not in allresp and LEGACY not in allresp, allresp[:200])
    src = open(os.environ.get('TP_FN_FILE') or os.path.join(ROOT, 'supabase/functions/submit-complaint/index.ts'), encoding='utf-8').read()
    check('El código de la función no trae ninguna clave escrita (todas salen de variables de entorno)', not re.search(r'sb_secret_[A-Za-z0-9]|eyJ[A-Za-z0-9]{10,}|0x4[A-Za-z0-9_-]{15,}', src) and 'Deno.env.get' in src, '')
    check('La función no escribe en los registros (console) ni el texto del reporte ni la IP', 'console.' not in src, '')

finally:
    srv.terminate()

fails = [r for r in results if not r[1]]
print(f'\n=== {len(results) - len(fails)}/{len(results)} pruebas correctas ===')
for n, ok, d in fails: print('  FALLA:', n, '->', d)
sys.exit(1 if fails else 0)
