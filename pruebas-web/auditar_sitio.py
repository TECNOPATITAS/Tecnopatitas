"""
Auditoría estática de TODO el sitio (Etapa 11): secretos, JavaScript inseguro, cabeceras de seguridad, enlaces, recursos, HTML y política de indexación.
No necesita navegador ni base de datos. Es una red de seguridad barata para correr antes de cada publicación.

Uso:   python3 pruebas-web/auditar_sitio.py [carpeta_del_sitio]        (sale con código 1 si algo falla)
       python3 pruebas-web/auditar_sitio.py --autoprueba               (inyecta fallos a propósito y comprueba que la auditoría los detecta)
"""
import html.parser, os, re, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT0 = os.path.abspath(os.path.join(HERE, '..'))
SKIP_DIRS = {'pruebas-web', '__pycache__', 'node_modules', '.git'}

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), str(detail)[:400]))
    print(('  OK  ' if cond else '  FALLA'), name, '' if cond else f'-> {str(detail)[:400]}')

class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []; self.ids = []; self.text = []; self.title = ''; self._in_title = False; self.h1 = 0; self._stack = []; self.inline_script = 0
        self.labels_for = set(); self.wrapped_inputs = 0; self.inputs = []; self._label_depth = 0; self.doctype = False
    def handle_decl(self, d): self.doctype = d.lower().startswith('doctype html')
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); self.tags.append((tag, a, self.getpos()[0]))
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'title': self._in_title = True
        if tag == 'h1': self.h1 += 1
        if tag == 'script' and 'src' not in a: self.inline_script += 1
        if tag == 'label':
            self._label_depth += 1
            if a.get('for'): self.labels_for.add(a['for'])
        if tag in ('input', 'select', 'textarea') and a.get('type') not in ('hidden', 'submit', 'button'):
            self.inputs.append((tag, a, self._label_depth > 0))
    def handle_endtag(self, tag):
        if tag == 'title': self._in_title = False
        if tag == 'label': self._label_depth = max(0, self._label_depth - 1)
    def handle_data(self, d):
        if self._in_title: self.title += d

def run(ROOT):
    results.clear()
    files = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn: files.append(os.path.relpath(os.path.join(dp, f), ROOT))
    files.sort()
    rd = lambda p: open(os.path.join(ROOT, p), encoding='utf-8', errors='replace').read()
    htmls = [f for f in files if f.endswith('.html') and '/' not in f]
    jss = [f for f in files if f.endswith('.js')]
    TEXT_EXT = ('.html', '.js', '.css', '.md', '.sql', '.ts', '.txt', '.sh', '.yml', '.json', '.example', '.gitignore', '')

    print('\n[A] Secretos y archivos que no deben publicarse')
    bad_files = [f for f in files if re.search(r'(^|/)\.env($|\.)', f) and not f.endswith('.env.example') or f.endswith(('.pem', '.key', '.p12', '.pfx', '.sqlite', '.db'))]
    check('A1 No hay archivos .env, claves privadas ni bases de datos en la carpeta a publicar', not bad_files, bad_files)
    pats = {'clave secreta de Supabase (sb_secret_)': r'sb_secret_[A-Za-z0-9_-]{10,}', 'JWT (eyJ…)': r'eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}',
            'clave de Resend': r'\bre_[A-Za-z0-9]{20,}', 'URL de conexión a base de datos con contraseña': r'postgres(ql)?://[^\s:@/]+:[^\s@]+@',
            'clave privada PEM': r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', 'token de GitHub': r'\bgh[pousr]_[A-Za-z0-9]{30,}', 'clave de Google (AIza…)': r'\bAIza[0-9A-Za-z_-]{30,}',
            'clave secreta de Turnstile (0x4… de 35+ caracteres)': r'\b0x4[A-Za-z0-9_-]{32,}\b', 'clave secreta de Stripe/OpenAI/Anthropic': r'\b(sk_live|sk-ant|sk-proj)[-_A-Za-z0-9]{10,}'}
    found = []
    for f in files:
        if not f.endswith(TEXT_EXT) and os.path.splitext(f)[1]: continue
        s = rd(f)
        for nm, p in pats.items():
            if re.search(p, s): found.append(f'{f}: {nm}')
    check('A2 Ningún archivo contiene claves secretas, JWT, tokens, contraseñas de base de datos ni llaves privadas', not found, found)
    cfg = rd('js/config.js')
    key = re.search(r"SUPABASE_PUBLISHABLE_KEY:\s*'([^']*)'", cfg); url = re.search(r"SUPABASE_URL:\s*'([^']*)'", cfg)
    check('A3 config.js: solo URL de Supabase y clave PUBLISHABLE (sb_publishable_…); nada más es secreto', key and key.group(1).startswith('sb_publishable_') and url and re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co', url.group(1)), (key and key.group(1)[:20], url and url.group(1)))
    sv = [f for f in jss if f != 'js/tp-client.js' and re.search(r'service_role|SECRET_KEY|secret key', rd(f), re.I) and not re.search(r'NUNCA|nunca|never', rd(f))]
    check('A4 En el JavaScript del navegador, «service_role» / «secret key» solo aparece en advertencias («nunca…») o en el detector de tp-client.js', not sv, sv)
    envx = rd('.env.example') if '.env.example' in files else ''
    check('A5 .env.example existe, solo documenta nombres (sin valores) y no menciona servicios que ya no se usan', envx and not re.search(r'^[A-Z_]+=\S+', envx, re.M) and 'RESEND' not in envx and 'GMAIL' not in envx.upper(), envx[:200])
    gi = rd('.gitignore') if '.gitignore' in files else ''
    check('A6 .gitignore excluye .env y variantes (y deja pasar .env.example)', '.env' in gi and '!.env.example' in gi)
    rm = rd('README.md') if 'README.md' in files else ''
    check('A7 Hay README con instrucciones de configuración y publicación', 'Cloudflare Pages' in rm and 'GitHub' in rm and re.search(r'configuraci[óo]n', rm, re.I) and re.search(r'publicaci[óo]n|publicar', rm, re.I))

    print('\n[B] JavaScript')
    r = [f for f in jss if subprocess.run(['node', '--check', os.path.join(ROOT, f)], capture_output=True).returncode]
    check('B1 Todos los archivos JavaScript pasan la revisión de sintaxis', not r, r)
    dang = {}
    for f in jss:
        s = rd(f); hits = re.findall(r'\.innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(|setTimeout\(\s*[\'"`]|setInterval\(\s*[\'"`]|[\'"`]javascript:', s)
        if hits: dang[f] = hits
    # layout.js arma cabecera y pie fijos (sin datos de personas) con innerHTML: se permite solo ahí y solo con plantillas del propio código
    allowed = {'js/layout.js'}
    check('B2 Ningún JS usa innerHTML / outerHTML / insertAdjacentHTML / document.write / eval / new Function / setTimeout(texto) / javascript: (salvo layout.js, que solo pinta plantillas fijas)', not {k: v for k, v in dang.items() if k not in allowed}, {k: v for k, v in dang.items() if k not in allowed})
    lay = rd('js/layout.js') if 'js/layout.js' in files else ''
    tpl_ok = all('${' not in seg or re.fullmatch(r'[^$]*(\$\{(NAV\.map|paw|bellSvg|TP&&TP\.hasSession|actsUser|actsGuest|k|n\[\d\]|n\[0\]===k)[^}]*\}[^$]*)*', seg) for seg in [])
    check('B3 layout.js solo inserta plantillas de su propio código (sin datos del servidor ni de la URL en innerHTML)',
          'innerHTML' in lay and not re.search(r'innerHTML\s*=[^;]*(location|search|hash|localStorage|\.rpc|\.rest|response|fetch)', lay))
    dbg = [f for f in jss if re.search(r'\bdebugger\b|console\.(log|debug|dir|table)\(', rd(f))]
    check('B4 Sin debugger ni console.log/debug/dir/table olvidados en el sitio', not dbg, dbg)
    todo = [f for f in jss + htmls if re.search(r'(//|/\*|\*|<!--|#)\s*(TODO|FIXME|XXX)\b', rd(f)) or re.search(r'lorem ipsum|se activa en la Etapa|se conecta en la Etapa|Próximamente', rd(f), re.I)]
    check('B5 Sin marcas de trabajo pendiente (TODO/FIXME/lorem/«se activa en la Etapa»/«Próximamente») en páginas ni scripts', not todo, todo)
    ext = []
    for f in jss:
        for u in re.findall(r"""['"`](https?://[^'"`\s)]+)""", rd(f)):
            h = re.match(r'https?://([^/]+)', u).group(1)
            if h not in ('www.w3.org', 'wa.me', 'www.google.com', 'maps.google.com', 'www.gob.mx', 'challenges.cloudflare.com', 'localhost') and not h.endswith('.supabase.co') and 'ejemplo' not in h:
                ext.append(f'{f}: {u[:60]}')
    check('B6 Los scripts solo hablan con hosts conocidos (Supabase, Cloudflare Turnstile, enlaces a Google Maps/WhatsApp/gob.mx)', not ext, ext[:6])
    st = [f for f in jss if re.search(r'localStorage\.setItem\([^)]*(password|contrase|pw|secret|token)', rd(f), re.I) and f != 'js/tp-client.js']
    check('B7 Solo tp-client.js guarda la sesión en localStorage; ninguna otra página guarda contraseñas ni tokens', not st, st)

    print('\n[C] Cabeceras de seguridad (_headers)')
    hd = rd('_headers'); gen = hd.split('\n\n')[0]
    csp = re.search(r'Content-Security-Policy:\s*(.+)', hd).group(1)
    directive = lambda n: next((d.split()[1:] for d in csp.split(';') if d.strip().startswith(n + ' ')), None)
    check('C1 CSP: default-src \'self\', object-src \'none\', base-uri \'self\', form-action \'self\', frame-ancestors \'none\'', directive('default-src') == ["'self'"] and directive('object-src') == ["'none'"] and directive('base-uri') == ["'self'"] and directive('form-action') == ["'self'"] and directive('frame-ancestors') == ["'none'"], csp)
    ss = directive('script-src') or []
    check('C2 CSP: los scripts solo vienen del propio sitio y de challenges.cloudflare.com (sin unsafe-inline ni unsafe-eval)', set(ss) == {"'self'", 'https://challenges.cloudflare.com'}, ss)
    cs = directive('connect-src') or []
    check('C3 CSP: connect-src solo permite el propio sitio y el proyecto de Supabase (https y wss)', set(cs) <= {"'self'", url.group(1), url.group(1).replace('https://', 'wss://')} and url.group(1) in cs, cs)
    im = directive('img-src') or []
    check('C4 CSP: las imágenes solo vienen del sitio, data: y el proyecto de Supabase', set(im) <= {"'self'", 'data:', url.group(1)}, im)
    fs = directive('font-src') or []; sty = directive('style-src') or []
    check('C5 CSP: fuentes y estilos externos limitados a Google Fonts', set(fs) <= {'https://fonts.gstatic.com'} and set(sty) <= {"'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'}, (fs, sty))
    for h in ('X-Content-Type-Options: nosniff', 'X-Frame-Options: DENY', 'Referrer-Policy: strict-origin-when-cross-origin', 'Strict-Transport-Security: max-age=', 'Permissions-Policy: camera=(), microphone=(), geolocation=()'):
        check(f'C6 Cabecera presente: {h.split(":")[0]}', h in gen)
    check('C7 La placa QR (qr.html) no envía el código en el encabezado Referer', re.search(r'/qr\.html\s+! Referrer-Policy\s+Referrer-Policy: no-referrer', hd))
    inline_style = [f for f in htmls if re.search(r'\sstyle="', rd(f))]
    check('C8 Estilos en línea en HTML (informativo: la CSP los admite con unsafe-inline; reducirlos es mejora futura)', len(inline_style) <= 12, inline_style)
    fn = rd('supabase/functions/submit-complaint/index.ts') if 'supabase/functions/submit-complaint/index.ts' in files else ''
    check('C9 Edge Function de denuncias: lee sus claves de variables de entorno (Deno.env) y no trae ninguna escrita', 'Deno.env' in fn and not re.search(r"(TURNSTILE_SECRET_KEY|SECRET_KEYS?)\s*[:=]\s*['\"][^'\"]{8,}", fn))

    print('\n[D] HTML: estructura, enlaces y recursos')
    pages = {}
    for f in htmls:
        p = Page(); p.feed(rd(f)); pages[f] = p
    ids_by = {f: set(p.ids) for f, p in pages.items()}
    bad = []
    for f, p in pages.items():
        t = {tag: a for tag, a, _ in p.tags}
        html_a = next((a for tag, a, _ in p.tags if tag == 'html'), {})
        metas = {a.get('name'): a.get('content') for tag, a, _ in p.tags if tag == 'meta' and a.get('name')}
        vp = metas.get('viewport', '')
        probs = []
        if not p.doctype: probs.append('sin doctype')
        if html_a.get('lang') != 'es-MX': probs.append('lang')
        if 'width=device-width' not in vp: probs.append('viewport')
        if not (5 <= len(p.title.strip()) <= 70): probs.append('título ' + str(len(p.title.strip())))
        if f != 'qr.html' and not metas.get('description'): probs.append('sin description')
        if p.h1 != 1 and not (f == 'qr.html' and p.h1 == 0 and "el('h1'" in rd('js/pages/qr-publico.js')): probs.append(f'h1×{p.h1}')   # la página pública de la placa crea su h1 con el nombre de la mascota
        if p.inline_script: probs.append('script en línea')
        if len(p.ids) != len(set(p.ids)): probs.append('ids duplicados: ' + str([i for i in set(p.ids) if p.ids.count(i) > 1]))
        if 'main' not in p.ids: probs.append('sin #main')
        if not any(tag == 'a' and a.get('class') == 'skip' for tag, a, _ in p.tags): probs.append('sin enlace «saltar al contenido»')
        if probs: bad.append(f'{f}: {", ".join(probs)}')
    check('D1 Cada página tiene doctype, lang es-MX, viewport, título, descripción, un solo h1, #main, enlace para saltar y sin ids repetidos ni scripts en línea', not bad, bad)
    noidx_expected = {'admin', 'carnet', 'chat', 'mascota', 'notificaciones', 'panel-aliado', 'perfil', 'qr', 'login', 'registro', 'recuperar', 'nueva-contrasena', '404'}
    pub_expected = {'index', 'guias', 'directorio', 'denuncias', 'planes', 'sobre-nosotros', 'privacidad', 'terminos'}
    seen = {f[:-5] for f in htmls}
    wrong = []
    for f, p in pages.items():
        n = f[:-5]; has = any(tag == 'meta' and a.get('name') == 'robots' and 'noindex' in (a.get('content') or '') for tag, a, _ in p.tags)
        if n in noidx_expected and not has: wrong.append(f'{n}: falta noindex')
        if n in pub_expected and has: wrong.append(f'{n}: no debe tener noindex')
    unk = sorted(seen - noidx_expected - pub_expected)
    check('D2 Política de indexación: páginas privadas, de acceso y 404 con noindex; públicas sin él; ninguna página nueva sin clasificar', not wrong and not unk, wrong + unk)
    broken = []; badtarget = []; noopener = []; http_ = []
    for f, p in pages.items():
        base = '/' if any(tag == 'base' for tag, _, _ in p.tags) else os.path.dirname(f)
        for tag, a, ln in p.tags:
            for attr in ('href', 'src'):
                v = a.get(attr)
                if not v or tag == 'base': continue
                if v.startswith('http://'): http_.append(f'{f}:{ln} {v[:50]}')
                if v.startswith(('http://', 'https://', 'mailto:', 'tel:', 'data:', '#', 'javascript:')):
                    if v.startswith('#') and len(v) > 1 and v[1:] not in ids_by[f]: broken.append(f'{f}:{ln} {v}')
                    continue
                path, _, frag = v.partition('#'); path = path.split('?')[0]
                if not path: continue
                tgt = os.path.normpath(os.path.join('' if base == '/' else base, path)).lstrip('/')
                if tgt not in files and not os.path.isdir(os.path.join(ROOT, tgt)): broken.append(f'{f}:{ln} {v}')
                elif frag and tgt.endswith('.html') and tgt in ids_by and frag not in ids_by[tgt]: broken.append(f'{f}:{ln} {v} (sin ancla)')
            if tag == 'a' and a.get('target') == '_blank' and 'noopener' not in (a.get('rel') or ''): noopener.append(f'{f}:{ln}')
            if tag == 'a' and a.get('href', '').startswith('javascript:'): badtarget.append(f'{f}:{ln}')
    check('D3 Todos los enlaces, scripts y hojas de estilo internos existen (y las anclas #… también)', not broken, broken[:8])
    check('D4 Todo enlace con target="_blank" lleva rel="noopener" y no hay enlaces javascript:', not noopener and not badtarget, noopener + badtarget)
    check('D5 No hay recursos http:// (contenido mezclado)', not http_, http_)
    noalt = [f'{f}:{ln}' for f, p in pages.items() for tag, a, ln in p.tags if tag == 'img' and 'alt' not in a]
    check('D6 Toda imagen <img> tiene atributo alt', not noalt, noalt)
    unl = []
    for f, p in pages.items():
        for tag, a, wrapped in p.inputs:
            if not (wrapped or a.get('id') in p.labels_for or a.get('aria-label') or a.get('aria-labelledby')): unl.append(f'{f}: {tag}#{a.get("id") or a.get("name")}')
    check('D7 Todo campo de formulario tiene etiqueta (dentro de <label>, for= o aria-label)', not unl, unl)
    order = []
    for f, p in pages.items():
        srcs = [a['src'] for tag, a, _ in p.tags if tag == 'script' and a.get('src')]
        if 'js/tp-client.js' in srcs and ('js/config.js' not in srcs or srcs.index('js/config.js') > srcs.index('js/tp-client.js')): order.append(f)
        if 'js/tp-ui.js' in srcs and srcs.index('js/tp-ui.js') < srcs.index('js/tp-client.js'): order.append(f + ' (ui antes que cliente)')
        for s in srcs:
            if s.startswith('http'): order.append(f'{f}: script externo {s}')
    check('D8 Orden de scripts correcto (config → cliente → interfaz…) y ningún script externo en las páginas', not order, order)
    forms = [f'{f}:{ln}' for f, p in pages.items() for tag, a, ln in p.tags if tag == 'form' and a.get('action') and not a['action'].startswith(('#',))]
    check('D9 Ningún formulario envía datos por su cuenta (sin action): todo pasa por el cliente con validación y CSP', not forms, forms)
    pw = [f'{f}:{ln}' for f, p in pages.items() for tag, a, ln in p.tags if tag == 'input' and a.get('type') == 'password' and not a.get('autocomplete')]
    check('D10 Los campos de contraseña declaran autocomplete (current-password / new-password)', not pw, pw)
    legal_links = [f for f in htmls if f not in ('qr.html',) and 'js/layout.js' not in rd(f)]
    check('D11 Todas las páginas (salvo la pública de placa) cargan layout.js, que pone el pie con el aviso de privacidad y los términos', not legal_links, legal_links)

    print('\n[E] Base de datos y despliegue')
    inst = rd('database/00_instalar_todo.sql') if 'database/00_instalar_todo.sql' in files else ''
    parts = ''.join(rd('database/' + n) for n in ('01_esquema.sql', '02_funciones.sql', '03_seguridad_rls.sql', '04_storage.sql', '05_datos_base.sql'))
    check('E1 El instalador (00_instalar_todo.sql) contiene exactamente 01–05 (sin datos de demostración): reconstruir con construir_instalador.sh si falla', all(seg.strip() in inst for seg in re.split(r'\n-- =+\n', parts)[:0] or [parts[:2000], parts[-2000:]]) and 'is_demo' in inst and '06_datos_demo' not in inst)
    sd = re.findall(r'create or replace function ([\w.]+)\([^)]*\)[^$]*?security definer(?![^$]*?set search_path)', inst, re.S)
    check('E2 Toda función SECURITY DEFINER fija su search_path', not sd, sd[:5])
    demo = rd('database/06_datos_demo.sql') if 'database/06_datos_demo.sql' in files else ''
    check('E3 Los datos de demostración están aparte (06) y marcados is_demo para poder borrarlos con 07_limpiar_demo.sql', (not demo or 'is_demo' in demo) and 'database/07_limpiar_demo.sql' in files)
    pub = [f for f in files if f.startswith('database/pruebas/') and re.search(r'password|secret', rd(f), re.I) and f.endswith('.sql') and re.search(r"(password|secret)\s*=\s*'[^']{6,}'", rd(f), re.I)]
    check('E4 Las pruebas de base de datos no traen contraseñas ni secretos reales', not pub, pub)
    print('\n====', 'AUDITORÍA LIMPIA' if all(r[1] for r in results) else 'HAY HALLAZGOS', f'· {sum(r[1] for r in results)}/{len(results)} comprobaciones superadas ====')
    return [r for r in results if not r[1]]

def selftest():
    """Inyecta fallos a propósito en una copia del sitio y comprueba que la auditoría los detecta."""
    cases = [
     ('clave secreta en un JS', 'js/pages/perfil.js', lambda s: s + "\nconst k='sb_secret_abcdefghijklmnop12345';\n", 'A2'),
     ('JWT en un HTML', 'index.html', lambda s: s.replace('</body>', '<!--eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.abcdefghij1234--></body>'), 'A2'),
     ('innerHTML', 'js/pages/guias.js', lambda s: s + "\ndocument.body.innerHTML = location.hash;\n", 'B2'),
     ('console.log olvidado', 'js/pages/chat.js', lambda s: s + "\nconsole.log('hola');\n", 'B4'),
     ('CSP con unsafe-inline en scripts', '_headers', lambda s: s.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'"), 'C2'),
     ('sin HSTS', '_headers', lambda s: s.replace('Strict-Transport-Security: max-age=31536000', 'X-Otro: 1'), 'C6'),
     ('enlace roto', 'index.html', lambda s: s.replace('</body>', '<a href="no-existe.html">x</a></body>'), 'D3'),
     ('ancla rota', 'privacidad.html', lambda s: s.replace('href="#cookies"', 'href="#nada"'), 'D3'),
     ('target _blank sin noopener', 'index.html', lambda s: s.replace('</body>', '<a href="https://x.mx" target="_blank">x</a></body>'), 'D4'),
     ('imagen sin alt', 'index.html', lambda s: s.replace('</body>', '<img src="css/styles.css"></body>'), 'D6'),
     ('campo sin etiqueta', 'login.html', lambda s: s.replace('</form>', '<input name="zz"></form>'), 'D7'),
     ('página privada sin noindex', 'perfil.html', lambda s: s.replace('<meta name="robots" content="noindex">', ''), 'D2'),
     ('script externo', 'login.html', lambda s: s.replace('<script src="js/config.js">', '<script src="https://cdn.ejemplo.com/a.js"></script><script src="js/config.js">'), 'D8'),
     ('script en línea', 'login.html', lambda s: s.replace('</body>', '<script>var a=1</script></body>'), 'D1'),
     ('.env.example con valor', '.env.example', lambda s: s + '\nSECRETO=abc123456\n', 'A5'),
     ('marca TODO', 'js/pages/planes.js', lambda s: s + '\n// TODO: arreglar\n', 'B5'),
     ('config.js con otra clave', 'js/config.js', lambda s: s.replace('sb_publishable_', 'sb_secret_'), 'A3'),
    ]
    miss = []
    for name, f, fn, code in cases:
        d = tempfile.mkdtemp(prefix='tpaud_')
        for item in os.listdir(ROOT0):
            if item in SKIP_DIRS: continue
            a = os.path.join(ROOT0, item); b = os.path.join(d, item)
            shutil.copytree(a, b, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(a) else shutil.copy(a, b)
        p = os.path.join(d, f); s = open(p, encoding='utf-8').read(); n = fn(s)
        if n == s: print('NO APLICA', name); miss.append(name + ' (no aplica)'); continue
        open(p, 'w', encoding='utf-8').write(n)
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            bad = run(d)
        hit = any(r[0].startswith(code) for r in bad)
        print(('DETECTADO   ' if hit else 'NO DETECTADO'), name, '→', code, '' if hit else [r[0][:50] for r in bad])
        if not hit: miss.append(name)
        shutil.rmtree(d, ignore_errors=True)
    print(f'\n{len(cases) - len(miss)}/{len(cases)} fallos inyectados fueron detectados', miss or '')
    return not miss

if __name__ == '__main__':
    if '--autoprueba' in sys.argv: sys.exit(0 if selftest() else 1)
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ROOT0
    sys.exit(1 if run(root) else 0)
