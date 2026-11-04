"""
Valida js/qr.js: genera muchos códigos QR (todas las versiones 1-10 y los 4 niveles de corrección, texto UTF-8)
y los DECODIFICA con un lector independiente (OpenCV). Si un solo código no se lee exactamente igual, falla.
Uso:  python3 pruebas-web/probar_qr.py      (requiere node, numpy, opencv-python-headless)
"""
import json, os, random, subprocess, sys
import numpy as np, cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
random.seed(4)
URL = 'https://tecnopatitas.pages.dev/qr.html?t=' + ''.join(random.choice('0123456789abcdef') for _ in range(64))
cases = []
for level in 'LMQH':
    for n in (1, 5, 17, 20, 32, 40, 60, 78, 106, 134, 154, 178, 200, 230, 255, 271):
        cases.append((level, ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789:/.?=-_') for _ in range(n))))
    cases.append((level, URL))
    cases.append((level, 'Ñandú pequeño · mascota perdida: ¡llámanos! 🐕'))
for n in range(1, 120, 7):
    cases.append(('M', ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(n))))

js = r"""
global.window = {};
require(%s);
const cases = JSON.parse(process.argv[1]);
const out = cases.map(([level, text]) => {
  try { const q = window.TPQR.encode(text, level); return { ok: true, version: q.version, size: q.size, rows: q.modules.map(r => Array.from(r).join('')) }; }
  catch (e) { return { ok: false, error: String(e.message) }; }
});
console.log(JSON.stringify(out));
""" % json.dumps(os.path.join(ROOT, 'js/qr.js'))
res = json.loads(subprocess.run(['node', '-e', js, json.dumps(cases)], capture_output=True, text=True, check=True).stdout)

det = cv2.QRCodeDetector()
aru = cv2.QRCodeDetectorAruco()                  # segundo detector de OpenCV (localiza mejor algunos patrones); ambos usan el mismo decodificador de datos
def picture(rows, scale=8, border=4):
    m = np.array([[int(c) for c in row] for row in rows], dtype=np.uint8)
    im = np.pad(np.where(m == 1, 0, 255).astype(np.uint8), border, constant_values=255)
    return cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
total = bad = skipped = second = 0
versions = set()
for (level, text), r in zip(cases, res):
    total += 1
    if not r['ok']:
        skipped += 1                                   # texto demasiado largo para ese nivel: debe rechazarse con error, no generar basura
        assert 'demasiado largo' in r['error'], r
        continue
    versions.add((r['version'], level))
    got, _, _ = det.detectAndDecode(picture(r['rows']))
    if got != text:
        got, _, _ = aru.detectAndDecode(picture(r['rows']))
        second += 1
    if got != text:
        bad += 1; print(f'  FALLA nivel {level} v{r["version"]} len={len(text.encode())}: leído {got!r}')
print(f'códigos: {total - skipped} generados y leídos ({second} necesitaron el segundo detector), {skipped} rechazados por tamaño, {bad} con error')
print(f'combinaciones versión/nivel cubiertas: {len(versions)}  (versiones {sorted({v for v, _ in versions})})')
# La dirección real de la placa debe caber y leerse
real = [r for (l, t), r in zip(cases, res) if t == URL and l == 'M'][0]
print('dirección de la placa (nivel M): versión', real['version'], f'({real["size"]}×{real["size"]} módulos)')
sys.exit(1 if bad else 0)
