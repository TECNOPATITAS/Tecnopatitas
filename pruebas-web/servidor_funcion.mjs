/*
  Puente de pruebas para la función segura «submit-complaint» (Etapa 6). SOLO para desarrollo.

  Ejecuta el CÓDIGO REAL de supabase/functions/submit-complaint/index.ts (con Node, que tiene las mismas funciones web que Deno:
  fetch, Request, FormData, crypto) y le conecta, en lugar de los servicios reales:
    · una base PostgreSQL LOCAL con el esquema REAL de database/ (las funciones SQL submit_complaint y complaint_precheck se
      ejecutan de verdad, con el rol service_role, y la restricción de permisos es la real);
    · un Storage simulado en memoria (y registrado en storage.objects para que cuente la cuota);
    · un Cloudflare Turnstile simulado: «ok.*» es un token válido que solo sirve una vez; cualquier otro es inválido.

  Uso:  node pruebas-web/servidor_funcion.mjs <puerto>      (variables PG* y TP_WEB_DB para elegir la base)
  Control para las pruebas:  POST /__config  ·  GET /__state  ·  GET /__object?path=  ·  POST /__reset
*/
import http from 'node:http';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

globalThis.__TP_TEST__ = true;                        // la función no arranca su servidor al importarla
const HERE = path.dirname(fileURLToPath(import.meta.url));
const mod = await import(pathToFileURL(process.env.TP_FN_FILE || path.join(HERE, '../supabase/functions/submit-complaint/index.ts')).href);   // TP_FN_FILE: versión «saboteada» (prueba de las pruebas)

const PORT = Number(process.argv[2] || 8799);
const DB = process.env.TP_WEB_DB || 'tp_web';
const SUPA = 'https://mtkbxnhsjqqdbrjeaslo.supabase.co';
const SECRET = 'sb_' + 'secret_PRUEBA_LOCAL_no_es_real';          // partida a propósito: no es una clave real y así ningún escáner de secretos la confunde con una
const LEGACY = 'eyJ.clave-anterior-service_role.de-prueba';       // formato anterior (JWT): va en «apikey» Y en «Authorization»
const TS_SECRET = '1x0000000000000000000000000000000AA-prueba';
const BUCKET = 'complaint-evidence';

const defaults = () => ({
  env: { SUPABASE_URL: SUPA, SUPABASE_SECRET_KEYS: JSON.stringify({ default: SECRET }), TURNSTILE_SECRET_KEY: TS_SECRET },
  turnstile: 'normal',        // normal | down (error de red) | http500
  failUploadAt: 0,            // N>0: la subida número N falla
  failRpc: null,              // 'complaint_precheck' | 'submit_complaint': devuelve 500
  today: null                 // fecha simulada (ISO) o null
});
let cfg = defaults();
let objects = new Map();      // ruta -> Buffer
let spent = new Set();        // tokens de Turnstile ya usados
let log = [];                 // llamadas a servicios (sin datos personales)
let uploads = 0;

/* ---- psql como service_role / anon ---- */
function psql(role, headers, sql, vars) {
  const args = ['-X', '-q', '-t', '-A', '-v', 'ON_ERROR_STOP=1', '-d', DB];
  for (const [k, v] of Object.entries(vars || {})) args.push('-v', k + '=' + v);
  const input = `\\set VERBOSITY verbose\nbegin;\nset local role ${role};\n` +
    (headers ? `select set_config('request.headers', '${headers.replace(/'/g, "''")}', true);\n` : '') + sql + '\ncommit;\n';
  try {
    const out = execFileSync('psql', args, { input, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
    const lines = out.split('\n').filter(l => l !== '' && l !== 'BEGIN' && l !== 'SET' && l !== 'COMMIT' && !/^set_config/.test(l));
    return { ok: true, out: lines.filter(l => l !== 'on' && !/^\{.*"(?:sub|role)"/.test(l)).pop() ?? '' };
  } catch (e) {
    const err = String(e.stderr || e.message);
    const m = /ERROR:\s+([0-9A-Z]{5}):\s+(.*)/.exec(err);
    return { ok: false, code: m ? m[1] : 'XX000', message: m ? m[2].trim() : err.slice(0, 200) };
  }
}
function rpc(name, body) {
  if (cfg.failRpc === name) return json(500, { code: 'XX000', message: 'fallo simulado' });
  if (name === 'complaint_precheck') {
    const r = psql('service_role', null, "select public.complaint_precheck(:'ip', :'n'::int);", { ip: body.p_client_ip ?? '', n: String(body.p_photos ?? 0) });
    return r.ok ? json(204, null) : json(400, { code: r.code, message: r.message });
  }
  if (name === 'submit_complaint') {
    const paths = (body.p_photo_paths || []).join(',');
    const r = psql('service_role', null,
      "select to_json(public.submit_complaint(:'t', :'d', :'f'::date, :'e', :'m', nullif(:'l', ''), nullif(:'x', ''), case when :'p' = '' then '{}'::text[] else string_to_array(:'p', ',') end));",
      { t: body.p_type ?? '', d: body.p_description ?? '', f: body.p_approx_date ?? '', e: body.p_state ?? '', m: body.p_municipality ?? '', l: body.p_location_reference ?? '', x: body.p_extra_info ?? '', p: paths });
    return r.ok ? json(200, JSON.parse(r.out)) : json(400, { code: r.code, message: r.message });
  }
  return json(404, { code: 'PGRST202', message: 'función desconocida' });
}
function track(code, ip) {
  const hdr = JSON.stringify({ 'cf-connecting-ip': ip || '203.0.113.7' });
  const r = psql('anon', hdr, "select coalesce(public.track_complaint(:'c')::text, 'null');", { c: code });
  return r.ok ? json(200, JSON.parse(r.out)) : json(400, { code: r.code, message: r.message });
}
const json = (status, body) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

/* ---- «fetch» que la función usa en lugar de la red ---- */
async function fakeFetch(url, opts = {}) {
  url = String(url);
  const hdr = Object.fromEntries(Object.entries(opts.headers || {}).map(([k, v]) => [k.toLowerCase(), v]));
  if (url.startsWith('https://challenges.cloudflare.com/turnstile/v0/siteverify')) {
    const p = new URLSearchParams(String(opts.body));
    log.push({ svc: 'turnstile', secretOk: p.get('secret') === TS_SECRET });
    if (cfg.turnstile === 'down') throw new Error('sin red');
    if (cfg.turnstile === 'http500') return json(500, {});
    if (p.get('secret') !== TS_SECRET) return json(200, { success: false, 'error-codes': ['invalid-input-secret'] });
    const t = p.get('response') || '';
    if (!t.startsWith('ok.')) return json(200, { success: false, 'error-codes': ['invalid-input-response'] });
    if (spent.has(t)) return json(200, { success: false, 'error-codes': ['timeout-or-duplicate'] });
    spent.add(t);
    return json(200, { success: true, hostname: 'localhost', challenge_ts: new Date().toISOString() });
  }
  if (!url.startsWith(SUPA)) throw new Error('URL inesperada en la prueba: ' + url);
  if (hdr.apikey !== SECRET && hdr.apikey !== LEGACY) return json(401, { message: 'No API key found in request' });
  if (hdr.apikey === SECRET && hdr.authorization) return json(401, { message: 'Invalid JWT' });      // una clave sb_secret_ solo va en «apikey»
  if (hdr.apikey === LEGACY && hdr.authorization !== 'Bearer ' + LEGACY) return json(401, { message: 'Missing authorization' });
  const rest = url.slice(SUPA.length);
  let m;
  if ((m = /^\/rest\/v1\/rpc\/([a-z_]+)$/.exec(rest))) { log.push({ svc: 'rpc', name: m[1] }); return rpc(m[1], JSON.parse(String(opts.body))); }
  if ((m = /^\/storage\/v1\/object\/complaint-evidence\/(.+)$/.exec(rest)) && opts.method === 'POST') {
    uploads++;
    log.push({ svc: 'upload', path: m[1], type: hdr['content-type'], size: opts.body.length });
    if (cfg.failUploadAt && uploads === cfg.failUploadAt) return json(500, { message: 'fallo simulado' });
    if (hdr['content-type'] !== 'image/jpeg') return json(415, { message: 'tipo no permitido' });
    objects.set(m[1], Buffer.from(opts.body));
    psql('postgres', null, "insert into storage.objects (bucket_id, name, metadata) values ('complaint-evidence', :'n', jsonb_build_object('size', :'s'::bigint));", { n: m[1], s: String(opts.body.length) });
    return json(200, { Key: BUCKET + '/' + m[1] });
  }
  if (rest === '/storage/v1/object/' + BUCKET && opts.method === 'DELETE') {
    const prefixes = JSON.parse(String(opts.body)).prefixes || [];
    log.push({ svc: 'delete', prefixes });
    for (const p of prefixes) { objects.delete(p); psql('postgres', null, "delete from storage.objects where bucket_id = 'complaint-evidence' and name = :'n';", { n: p }); }
    return json(200, prefixes.map(name => ({ name })));
  }
  return json(404, { message: 'ruta desconocida ' + rest });
}

/* ---- Servidor HTTP ---- */
const readBody = req => new Promise(res => { const c = []; req.on('data', d => c.push(d)); req.on('end', () => res(Buffer.concat(c))); });
const send = async (res, r) => { const buf = Buffer.from(await r.arrayBuffer()); const h = Object.fromEntries(r.headers); res.writeHead(r.status, h); res.end(buf); };
const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' };

http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  try {
    if (u.pathname === '/__reset') { cfg = defaults(); objects = new Map(); spent = new Set(); log = []; uploads = 0; psql('postgres', null, "delete from storage.objects where bucket_id = 'complaint-evidence';"); res.writeHead(204); return res.end(); }
    if (u.pathname === '/__config') { Object.assign(cfg, JSON.parse((await readBody(req)).toString() || '{}')); res.writeHead(204); return res.end(); }
    if (u.pathname === '/__state') { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify({ objects: [...objects.keys()], log, uploads })); }
    if (u.pathname === '/__object') { const b = objects.get(u.searchParams.get('path')); res.writeHead(b ? 200 : 404, { 'content-type': 'image/jpeg' }); return res.end(b || ''); }
    if (u.pathname === '/__corrupt_env') { cfg.env = Object.assign({}, cfg.env, JSON.parse((await readBody(req)).toString() || '{}')); res.writeHead(204); return res.end(); }
    if (u.pathname === '/rest/v1/rpc/track_complaint') {
      const b = JSON.parse((await readBody(req)).toString() || '{}');
      return send(res, track(b.p_code, req.headers['x-test-ip']));
    }
    if (u.pathname === '/functions/v1/submit-complaint') {
      const body = await readBody(req);
      const hdr = { ...req.headers }; delete hdr['transfer-encoding'];
      const request = new Request('http://localhost/functions/v1/submit-complaint', { method: req.method, headers: hdr, body: ['GET', 'HEAD', 'OPTIONS'].includes(req.method) ? undefined : body });
      const now = cfg.today ? new Date(cfg.today + 'T18:00:00Z') : new Date();
      const env = k => cfg.env[k];
      const out = await mod.handle(request, { fetch: fakeFetch, env, now: () => now, uuid: () => crypto.randomUUID() });
      return send(res, out);
    }
    res.writeHead(404, CORS); res.end('no existe');
  } catch (e) {
    res.writeHead(500, { 'content-type': 'text/plain' }); res.end('ERROR DEL PUENTE: ' + (e && e.stack || e));
  }
}).listen(PORT, '127.0.0.1', () => console.log('listo en ' + PORT));
