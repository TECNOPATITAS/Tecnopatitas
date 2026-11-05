/*
  TECNOPATITAS · Función segura «submit-complaint» (Etapa 6)
  Supabase Edge Function (Deno). Es la ÚNICA puerta por la que entra una denuncia anónima.

  Qué hace, en este orden (si algo falla, se detiene y no se guarda nada):
    1. Lee el formulario (campos + hasta 3 fotos) y lo valida. Si el campo trampa «website» viene lleno es un robot:
       se le responde «éxito» con un código falso y no se guarda nada.
    2. Comprueba Cloudflare Turnstile con la clave SECRETA del servidor (TURNSTILE_SECRET_KEY). Sin esa clave, o si
       Cloudflare no responde, NO se acepta el reporte (falla cerrado).
    3. Aplica los límites por visitante y globales (SQL: complaint_precheck) ANTES de subir archivos.
    4. Revisa cada foto: debe ser un JPEG válido; se le quitan TODOS los metadatos (EXIF, GPS, comentarios, miniaturas)
       y todo lo que haya después del final de la imagen. Se guarda en el bucket PRIVADO «complaint-evidence».
    5. Registra la denuncia (SQL: submit_complaint) y devuelve su código de seguimiento.
       Si el paso 5 falla, borra las fotos que ya había subido.

  Anonimato: no se guarda la IP (solo un hash con sal que cambia cada día, y dentro de la base de datos); esta función no
  escribe en los registros ni el texto del reporte ni la IP. La clave secreta del servidor solo se lee de las variables
  de entorno de la función: NUNCA va en el navegador ni en el repositorio.

  Variables de entorno (las pone Supabase o tú en el panel; ver GUIA_ETAPA_6.md):
    SUPABASE_URL, SUPABASE_SECRET_KEYS (o SUPABASE_SERVICE_ROLE_KEY)   → las inyecta Supabase automáticamente
    TURNSTILE_SECRET_KEY                                               → la pegas tú en «Edge Functions → Secrets»

  Este archivo no importa nada externo a propósito: se pega tal cual en el editor del panel de Supabase.
*/

declare const Deno: any;

const BUCKET = 'complaint-evidence';
const MAX_PHOTOS = 3;
const MAX_PHOTO_BYTES = 2 * 1024 * 1024;          // por foto, YA reducida por el navegador (normalmente pesa unos 300 KB)
const MAX_BODY_BYTES = 8 * 1024 * 1024;
const MAX_SIDE_PX = 4096;                         // el navegador envía como máximo 1280 px
const TYPES = ['maltrato_fisico', 'abandono', 'sin_agua_alimento_refugio', 'hacinamiento_insalubre', 'comercio_ilegal', 'otra'];
const TURNSTILE_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

const MSG = {
  notConfigured: 'El envío de reportes todavía no está configurado. Inténtalo más tarde.',
  tooBig: 'Los datos enviados son demasiado grandes.',
  badForm: 'No se pudo leer el formulario. Inténtalo de nuevo.',
  type: 'Selecciona el tipo de situación.',
  description: 'La descripción debe tener entre 30 y 4000 caracteres.',
  date: 'La fecha aproximada no es válida.',
  place: 'Indica el estado y el municipio (entre 2 y 80 caracteres).',
  reference: 'La referencia del lugar admite hasta 300 caracteres.',
  photos: 'Máximo 3 fotografías.',
  photoSize: 'Una de las fotos pesa demasiado. Elige una más pequeña.',
  photoType: 'Una de las fotos no es una imagen JPEG válida.',
  captcha: 'No se pudo comprobar que eres una persona. Inténtalo de nuevo.',
  captchaDown: 'No pudimos comprobar la verificación anti-robots. Inténtalo de nuevo en unos minutos.',
  rate: 'Demasiadas solicitudes. Intenta de nuevo más tarde.',
  upload: 'No se pudieron guardar las fotos. Inténtalo de nuevo o envía el reporte sin fotos.',
  failed: 'No se pudo registrar el reporte. Inténtalo de nuevo en unos minutos.'
};

/* ------------------------------------------------------------------ utilidades */
const CORS: Record<string, string> = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'apikey, content-type, x-client-info',
  'access-control-allow-methods': 'POST, OPTIONS',
  'access-control-max-age': '86400'
};
function reply(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status, headers: { ...CORS, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }
  });
}
const fail = (status: number, error: string, code?: string) => reply(status, { ok: false, error, code });

/* Quita caracteres de control (menos salto de línea y tabulador) y los que cambian el sentido de lectura del texto. */
function clean(v: unknown, max: number): string | null {
  if (typeof v !== 'string') return null;
  const s = v.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '').trim();
  return s.length <= max ? s : null;
}
function todayMx(now: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}
function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return t.getUTCFullYear() + '-' + String(t.getUTCMonth() + 1).padStart(2, '0') + '-' + String(t.getUTCDate()).padStart(2, '0');
}
function validDate(s: string, now: Date): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const t = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if (t.getUTCFullYear() !== +m[1] || t.getUTCMonth() !== +m[2] - 1 || t.getUTCDate() !== +m[3]) return false;
  return s >= '2000-01-01' && s <= addDays(todayMx(now), 1);
}
function fakeCode(): string {
  const a = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789', r = new Uint8Array(8);
  crypto.getRandomValues(r);
  const s = Array.from(r, b => a[b % 32]).join('');
  return 'TP-' + s.slice(0, 4) + '-' + s.slice(4);
}

/* ------------------------------------------------------------------ fotos: JPEG válido y SIN metadatos */
/*
  Recorre los segmentos del JPEG y conserva solo los necesarios para mostrarlo (tablas, tamaño, datos de imagen).
  Se descartan: APP0–APP15 (JFIF, EXIF con GPS y fecha, XMP, perfiles, miniaturas), comentarios y cualquier cosa después
  del marcador de fin. No decodifica la imagen. Devuelve null si el archivo no es un JPEG bien formado.
*/
function sanitizeJpeg(src: Uint8Array): { bytes: Uint8Array; width: number; height: number } | null {
  const n = src.length;
  if (n < 30 || src[0] !== 0xFF || src[1] !== 0xD8) return null;
  const chunks: Uint8Array[] = [src.subarray(0, 2)];
  let i = 2, sof = false, sos = false, width = 0, height = 0;
  while (i < n) {
    if (src[i] !== 0xFF) return null;
    while (i < n && src[i] === 0xFF) i++;                         // relleno entre marcadores
    if (i >= n) return null;
    const m = src[i++];
    if (m === 0xD9) {                                              // fin de la imagen
      if (!sos || !sof) return null;
      chunks.push(Uint8Array.of(0xFF, 0xD9));
      const total = chunks.reduce((a, c) => a + c.length, 0), out = new Uint8Array(total);
      let o = 0; for (const c of chunks) { out.set(c, o); o += c.length; }
      return { bytes: out, width, height };
    }
    const isSof = m >= 0xC0 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC;
    const keep = isSof || m === 0xC4 || m === 0xCC || m === 0xDB || m === 0xDD || m === 0xDA;
    const drop = (m >= 0xE0 && m <= 0xEF) || m === 0xFE || (m >= 0xF0 && m <= 0xFD);
    if (!keep && !drop) return null;                               // marcador fuera de lugar o no admitido
    if (i + 2 > n) return null;
    const len = (src[i] << 8) | src[i + 1];
    if (len < 2 || i + len > n) return null;
    const start = i - 2, end = i + len;                            // «FF xx» + longitud + datos
    if (isSof) {
      if (len < 8) return null;
      height = (src[i + 3] << 8) | src[i + 4]; width = (src[i + 5] << 8) | src[i + 6];
      if (!width || !height) return null;
      sof = true;
    }
    if (keep) chunks.push(src.subarray(start, end));
    if (m !== 0xDA) { i = end; continue; }
    sos = true;                                                    // datos de imagen: hasta el siguiente marcador de verdad
    let j = end;
    while (j < n) {
      if (src[j] === 0xFF) {
        let k = j + 1;
        while (k < n && src[k] === 0xFF) k++;
        if (k >= n) return null;
        const b = src[k];
        if (b === 0x00 || (b >= 0xD0 && b <= 0xD7)) { j = k + 1; continue; }
        break;
      }
      j++;
    }
    if (j >= n) return null;
    chunks.push(src.subarray(end, j));
    i = j;
  }
  return null;
}

/* ------------------------------------------------------------------ servicios externos */
type Deps = { fetch: typeof fetch; env: (k: string) => string | undefined; now: () => Date; uuid: () => string };
const realDeps = (): Deps => ({ fetch: (u, o) => fetch(u, o), env: k => Deno.env.get(k), now: () => new Date(), uuid: () => crypto.randomUUID() });

function serverKey(d: Deps): string {
  const multi = d.env('SUPABASE_SECRET_KEYS');
  if (multi) {
    try {
      const o = JSON.parse(multi);
      if (o && typeof o.default === 'string' && o.default) return o.default;
      const first = o && Object.values(o).find(v => typeof v === 'string' && v);
      if (first) return first as string;
    } catch { /* se prueba la clave anterior */ }
  }
  return d.env('SUPABASE_SERVICE_ROLE_KEY') || '';
}
function srvHeaders(key: string): Record<string, string> {
  return key.startsWith('sb_secret_') ? { apikey: key } : { apikey: key, Authorization: 'Bearer ' + key };
}
async function api(d: Deps, base: string, key: string, path: string, init: { method?: string; json?: unknown; bytes?: Uint8Array; headers?: Record<string, string> }) {
  const headers: Record<string, string> = { ...srvHeaders(key), ...(init.headers || {}) };
  let body: BodyInit | undefined;
  if (init.json !== undefined) { headers['content-type'] = 'application/json'; body = JSON.stringify(init.json); }
  else if (init.bytes) body = init.bytes;
  const res = await d.fetch(base + path, { method: init.method || 'POST', headers, body, signal: AbortSignal.timeout(20000) });
  const text = await res.text().catch(() => '');
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  return { ok: res.ok, status: res.status, data };
}
async function turnstileOk(d: Deps, secret: string, token: string): Promise<'ok' | 'bad' | 'down'> {
  try {
    const res = await d.fetch(TURNSTILE_URL, { method: 'POST', body: new URLSearchParams({ secret, response: token }), signal: AbortSignal.timeout(8000) });
    if (res.status >= 500) return 'down';
    const j: any = await res.json().catch(() => null);
    if (!j) return 'down';
    if (j.success === true) return 'ok';
    const codes: string[] = Array.isArray(j['error-codes']) ? j['error-codes'] : [];
    return codes.some(c => c === 'internal-error' || c === 'invalid-input-secret' || c === 'missing-input-secret') ? 'down' : 'bad';
  } catch { return 'down'; }
}
function clientIp(req: Request): string {
  const h = req.headers;
  return (h.get('cf-connecting-ip') || h.get('x-real-ip') || (h.get('x-forwarded-for') || '').split(',')[0] || '').trim().slice(0, 64);
}

/* ------------------------------------------------------------------ atención de la petición */
export async function handle(req: Request, deps?: Deps): Promise<Response> {
  const d = deps || realDeps();
  if (req.method === 'OPTIONS') return reply(204, null);
  if (req.method !== 'POST') return fail(405, 'Método no permitido.');

  const base = (d.env('SUPABASE_URL') || '').replace(/\/+$/, ''), key = serverKey(d), tsSecret = d.env('TURNSTILE_SECRET_KEY') || '';
  if (!base || !key || !tsSecret) return fail(503, MSG.notConfigured, 'not_configured');           // falla cerrado

  const len = Number(req.headers.get('content-length') || 0);
  if (len > MAX_BODY_BYTES) return fail(413, MSG.tooBig);
  let form: FormData;
  try { form = await req.formData(); } catch { return fail(400, MSG.badForm); }

  /* 1. Campo trampa: los humanos no lo ven. Un robot recibe «éxito» y no se guarda nada. */
  const trap = form.get('website');
  if (typeof trap === 'string' && trap.trim() !== '') return reply(200, { ok: true, code: fakeCode() });

  /* 2. Validación de los datos (sin gastar el token de Turnstile, que solo sirve una vez). */
  const now = d.now();
  const type = clean(form.get('type'), 40), description = clean(form.get('description'), 4000);
  const date = clean(form.get('approx_date'), 10), state = clean(form.get('state'), 80), muni = clean(form.get('municipality'), 80);
  const ref = form.get('location_reference') == null || form.get('location_reference') === '' ? '' : clean(form.get('location_reference'), 300);
  if (!type || !TYPES.includes(type)) return fail(400, MSG.type);
  if (description === null || Array.from(description).length < 30) return fail(400, MSG.description);   // se cuentan caracteres, no unidades UTF-16 (igual que la base de datos)
  if (!date || !validDate(date, now)) return fail(400, MSG.date);
  if (!state || Array.from(state).length < 2 || !muni || Array.from(muni).length < 2) return fail(400, MSG.place);
  if (ref === null) return fail(400, MSG.reference);

  const files = form.getAll('photos').filter(f => typeof f !== 'string') as File[];
  if (form.getAll('photos').some(f => typeof f === 'string' && f !== '')) return fail(400, MSG.photoType);
  if (files.length > MAX_PHOTOS) return fail(400, MSG.photos);
  const photos: Uint8Array[] = [];
  for (const f of files) {
    if (f.size < 1) continue;
    if (f.size > MAX_PHOTO_BYTES) return fail(413, MSG.photoSize);
    const jpg = sanitizeJpeg(new Uint8Array(await f.arrayBuffer()));
    if (!jpg) return fail(415, MSG.photoType);
    if (jpg.width > MAX_SIDE_PX || jpg.height > MAX_SIDE_PX) return fail(413, MSG.photoSize);
    photos.push(jpg.bytes);
  }

  /* 3. Anti-robots (Cloudflare Turnstile), con la clave secreta. */
  const token = form.get('cf-turnstile-response');
  if (typeof token !== 'string' || token.length < 1 || token.length > 2048) return fail(403, MSG.captcha, 'captcha');
  const ts = await turnstileOk(d, tsSecret, token);
  if (ts === 'bad') return fail(403, MSG.captcha, 'captcha');
  if (ts === 'down') return fail(503, MSG.captchaDown, 'captcha_unavailable');

  /* 4. Límites por visitante y globales, antes de gastar espacio de archivos. */
  const pre = await api(d, base, key, '/rest/v1/rpc/complaint_precheck', { json: { p_client_ip: clientIp(req), p_photos: photos.length } });
  if (!pre.ok) return dbError(pre.data);

  /* 5. Fotos (sin metadatos) al espacio privado. Nombre al azar: no tiene relación con nada del reporte. */
  const folder = d.uuid(), paths: string[] = [];
  const undo = async () => { if (paths.length) await api(d, base, key, '/storage/v1/object/' + BUCKET, { method: 'DELETE', json: { prefixes: paths } }).catch(() => null); };
  for (let i = 0; i < photos.length; i++) {
    const path = folder + '/' + (i + 1) + '.jpg';
    const up = await api(d, base, key, '/storage/v1/object/' + BUCKET + '/' + path, { bytes: photos[i], headers: { 'content-type': 'image/jpeg', 'x-upsert': 'false', 'cache-control': 'max-age=3600' } }).catch(() => null);
    if (!up || !up.ok) { await undo(); return fail(502, MSG.upload, 'upload'); }
    paths.push(path);
  }

  /* 6. Registro de la denuncia. */
  const res = await api(d, base, key, '/rest/v1/rpc/submit_complaint', {
    json: { p_type: type, p_description: description, p_approx_date: date, p_state: state, p_municipality: muni,
            p_location_reference: ref || null, p_extra_info: null, p_photo_paths: paths }
  }).catch(() => null);
  if (!res || !res.ok || typeof res.data !== 'string' || !/^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(res.data)) {
    await undo();
    return res && !res.ok ? dbError(res.data) : fail(500, MSG.failed);
  }
  return reply(200, { ok: true, code: res.data });
}

/* Traduce un error de la base de datos: los mensajes propios (P0001 y 22023) ya vienen en español; el resto no se muestra. */
function dbError(data: any): Response {
  const code = data && typeof data.code === 'string' ? data.code : '', msg = data && typeof data.message === 'string' ? data.message : '';
  if (code === 'P0001' && msg.startsWith('Demasiadas')) return fail(429, MSG.rate, 'rate');
  if (code === 'P0001' && msg.length < 200) return fail(503, msg, 'unavailable');
  if (code === '22023' && msg.length < 200) return fail(400, msg);
  return fail(500, MSG.failed);
}

export { sanitizeJpeg };
if (!(globalThis as any).__TP_TEST__) Deno.serve((req: Request) => handle(req));
