"""
Pruebas de las plantillas de correo de Supabase Auth (Gmail como servicio de correo).

Revisa los archivos de supabase/plantillas-correo/ SIN enviar nada: estructura, variables permitidas, ausencia de recursos externos,
mensajes de seguridad y, en Chromium, que se vean bien en teléfono y escritorio con contraste suficiente (WCAG AA).

Uso:  python3 pruebas-web/probar_correos.py        Requiere: playwright + chromium.   No necesita base de datos ni red.
"""
import html.parser, os, re, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get('TP_SITE', os.path.join(HERE, '..')))
DIR = os.path.join(ROOT, 'supabase', 'plantillas-correo')
FILES = ['confirmar-registro.html', 'recuperar-contrasena.html']
VARS_OK = {'.ConfirmationURL'}                      # solo se usa el enlace de confirmación (la persona no necesita ver más datos)
VARS_SUPABASE = {'.ConfirmationURL', '.Token', '.TokenHash', '.SiteURL', '.RedirectTo', '.Data', '.Email', '.NewEmail'}
SAMPLE = 'https://mtkbxnhsjqqdbrjeaslo.supabase.co/auth/v1/verify?token=EJEMPLO&type=signup&redirect_to=https://tecnopatitas.pages.dev/perfil.html'
src_planes = open(os.path.join(HERE, 'probar_planes.py'), encoding='utf-8').read()
AUDIT_JS = re.search(r'AUDIT_JS = r"""(.*?)"""', src_planes, re.S).group(1)

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {detail}')

class P(html.parser.HTMLParser):
    def __init__(s): super().__init__(); s.tags = []; s.attrs = []; s.text = []; s.stack = []; s.errors = []
    def handle_starttag(s, tag, attrs):
        s.tags.append(tag); s.attrs.append((tag, dict(attrs)))
        if tag not in ('meta', 'br', 'img', 'link', 'input', 'hr'): s.stack.append(tag)
    def handle_endtag(s, tag):
        if not s.stack or s.stack[-1] != tag: s.errors.append(f'cierre inesperado </{tag}> con {s.stack[-3:]}')
        else: s.stack.pop()
    def handle_data(s, d): s.text.append(d)

def lum(h):
    h = h.lstrip('#'); r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def ratio(a, b):
    l1, l2 = sorted((lum(a), lum(b)), reverse=True); return (l1 + 0.05) / (l2 + 0.05)

print('\n[1] Estructura y seguridad de las plantillas')
docs = {}
for f in FILES:
    pth = os.path.join(DIR, f)
    check(f'1.1 {f} existe', os.path.isfile(pth))
    t = open(pth, encoding='utf-8').read(); docs[f] = t
    p = P(); p.feed(t)
    check(f'1.2 {f}: HTML bien formado (etiquetas abiertas y cerradas)', not p.errors and not p.stack, (p.errors, p.stack))
    vs = set(re.findall(r'\{\{\s*(\.\w+)\s*\}\}', t))
    check(f'1.3 {f}: solo usa la variable {sorted(VARS_OK)} (y es una variable que Supabase reconoce)', vs == VARS_OK and vs <= VARS_SUPABASE, vs)
    check(f'1.4 {f}: no hay llaves {{ }} sueltas ni variables mal escritas', len(re.findall(r'\{\{', t)) == len(re.findall(r'\}\}', t)) == t.count('{{ .ConfirmationURL }}'), (t.count('{{'), t.count('}}')))
    hrefs = [a['href'] for tag, a in p.attrs if tag == 'a' and 'href' in a]
    check(f'1.5 {f}: los dos enlaces (botón y texto) apuntan al enlace de confirmación y a nada más', hrefs == ['{{ .ConfirmationURL }}'] * 2, hrefs)
    bad = [x for x in p.tags if x in ('script', 'iframe', 'object', 'embed', 'img', 'link', 'style', 'form', 'input', 'video', 'audio', 'svg')]
    check(f'1.6 {f}: sin scripts, imágenes, hojas de estilo ni formularios (nada externo que rastree o se bloquee)', not bad, bad)
    check(f'1.7 {f}: no carga recursos externos (src, url(), @import, http:// sin cifrar)', not re.search(r'\bsrc=|url\(|@import|http://', t, re.I))
    check(f'1.8 {f}: declara idioma es-MX y juego de caracteres UTF-8', 'lang="es-MX"' in t and 'charset="utf-8"' in t)
    check(f'1.9 {f}: aclara que nunca se pide contraseña, tarjetas ni datos bancarios por correo', 'nunca te pedirá por correo tu contraseña, tarjetas ni datos bancarios' in t)
    check(f'1.10 {f}: indica qué hacer si la persona no lo pidió', 'ignora este mensaje' in t)
    check(f'1.11 {f}: pide no compartir el enlace', 'No compartas este enlace' in t)
    check(f'1.12 {f}: pesa menos de 20 KB (Gmail recorta mensajes grandes)', len(t.encode('utf-8')) < 20000, len(t.encode('utf-8')))
    check(f'1.13 {f}: texto de respaldo para copiar el enlace si el botón falla', 'copia y pega este enlace' in t)
    check(f'1.14 {f}: sin cobros: no menciona precios, pagos ni suscripciones', not re.search(r'\$|MXN|pago|suscripci|tarjeta de cr', re.sub(r'ni datos bancarios|tarjetas', '', t), re.I), re.findall(r'\$|MXN|pago|suscripci', t))
    cols = set(c.upper() for c in re.findall(r'#[0-9A-Fa-f]{6}\b', t))
    pal = {'#80E3B9', '#C0B8E8', '#92C1E9', '#FFCBD9', '#1F2B4D', '#F7FAFF', '#FFFFFF', '#E9E6F7', '#E0DCF4', '#1B2440', '#3D4660'}
    check(f'1.15 {f}: usa solo colores de la paleta del proyecto', cols <= pal, cols - pal)
asu = open(os.path.join(DIR, 'asuntos.txt'), encoding='utf-8').read()
subjects = [l.split('|')[1].strip() for l in asu.splitlines()[1:] if '|' in l]
check('1.16 Los asuntos están definidos, son cortos (≤ 60), en español y sin emojis', len(subjects) == 2 and all(0 < len(s) <= 60 for s in subjects) and not any(re.search(r'[\U0001F300-\U0001FAFF]', s) for s in subjects), subjects)
check('1.17 Las dos plantillas tienen títulos (<title>) iguales a su asunto', all(f'<title>{s}</title>' in docs[f] for f, s in zip(FILES, subjects)), subjects)
check('1.18 Contraste del texto de las plantillas: azul marino sobre cada fondo ≥ 4,5:1 y gris de apoyo sobre blanco ≥ 4,5:1',
      all(ratio('#1F2B4D', bg) >= 4.5 for bg in ('#80E3B9', '#FFCBD9', '#FFFFFF', '#E9E6F7')) and ratio('#3D4660', '#FFFFFF') >= 4.5 and ratio('#1B2440', '#FFFFFF') >= 4.5,
      [round(ratio('#1F2B4D', bg), 2) for bg in ('#80E3B9', '#FFCBD9', '#FFFFFF', '#E9E6F7')])

print('\n[2] Vista en Chromium (teléfono y escritorio)')
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for f in FILES:
        t = docs[f].replace('{{ .ConfirmationURL }}', SAMPLE)
        for w in (360, 390, 900):
            ctx = br.new_context(viewport={'width': w, 'height': 800}); pg = ctx.new_page()
            reqs = []; pg.on('request', lambda r: reqs.append(r.url))
            pg.route('**/*', lambda r: r.abort())          # sin red: si la plantilla intentara cargar algo externo, quedaría registrado
            pg.set_content(t)
            ov = pg.evaluate('document.documentElement.scrollWidth - window.innerWidth')
            check(f'2.1 {f} a {w} px: sin desplazamiento horizontal', ov <= 0, ov)
            bad = pg.evaluate(AUDIT_JS)
            check(f'2.2 {f} a {w} px: todo el texto visible cumple el contraste AA', not bad, bad[:3])
            links = pg.evaluate("Array.from(document.querySelectorAll('a')).map(a => [a.href, a.getBoundingClientRect().height, a.textContent.trim().slice(0, 40)])")
            check(f'2.3 {f} a {w} px: ambos enlaces llevan al enlace de confirmación; el botón mide ≥ 44 px de alto', len(links) == 2 and all(l[0] == SAMPLE for l in links) and links[0][1] >= 44, links)
            check(f'2.4 {f} a {w} px: no se intentó cargar nada externo', not [u for u in reqs if not u.startswith(('about:', 'data:'))], reqs)
            ctx.close()
        ctx = br.new_context(viewport={'width': 390, 'height': 800}); pg = ctx.new_page(); pg.set_content(t)
        txt = pg.inner_text('body')
        check(f'2.5 {f}: el texto visible no contiene variables sin sustituir ni «undefined»/«null»', not re.search(r'\{\{|\}\}|undefined|\bnull\b', txt), txt[:200])
        check(f'2.6 {f}: el preencabezado oculto no se ve en pantalla', pg.evaluate("(() => { const d = document.querySelector('body > div'); const r = d.getBoundingClientRect(); return r.height === 0 || getComputedStyle(d).display === 'none'; })()"))
        ctx.close()
    # control: la comprobación de contraste detecta un texto claro sobre fondo claro
    ctx = br.new_context(viewport={'width': 390, 'height': 800}); pg = ctx.new_page(); pg.set_content(docs[FILES[0]].replace('{{ .ConfirmationURL }}', SAMPLE).replace('color:#1B2440', 'color:#C9D3E8', 1))
    check('2.7 Control: un párrafo claro sobre fondo blanco SÍ es detectado', len(pg.evaluate(AUDIT_JS)) >= 1)
    ctx.close(); br.close()

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)} de {len(results)} comprobaciones correctas")
if bad:
    print('FALLARON:'); [print(' -', n, '->', d[:200]) for n, _, d in bad]
sys.exit(1 if bad else 0)
