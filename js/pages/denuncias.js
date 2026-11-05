/*
  Denuncias anónimas (Etapa 6).
  - El reporte NO lleva ningún dato de quien lo envía: no se pide ni se manda nombre, correo, teléfono ni sesión.
    (Se envía SIN la sesión aunque la persona tenga una cuenta abierta: TP.fn solo manda la clave pública.)
  - Las fotos se reducen y se re-codifican en el navegador (se pierde el EXIF/GPS); el servidor vuelve a revisarlas y a limpiarlas.
  - El envío pasa por la función segura «submit-complaint» (Cloudflare Turnstile + límites + subida privada).
  - La plataforma REGISTRA el reporte; no lo presenta ante ninguna autoridad. Aquí no se promete nada más que eso.
  - Todo lo que viene del servidor se muestra con textContent.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, M = window.TPMedia, C = window.TPCaptcha;
const form = document.getElementById('f-denuncia');
if (!form) return;
const el = UI.el, $ = id => document.getElementById(id);
const aviso = $('dn-aviso'), msg = $('dn-msg'), send = $('dn-enviar'), thumbs = $('dn-thumbs'), listo = $('dn-listo'), fotos = $('dn-fotos');
const MAX_PHOTOS = 3, MAX_PHOTO_BYTES = Math.round(1.8 * 1024 * 1024);          // el servidor acepta hasta 2 MB por foto ya reducida
const CODE_RE = /^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$/;
const ESTADOS = ['Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche', 'Chiapas', 'Chihuahua', 'Ciudad de México', 'Coahuila', 'Colima', 'Durango',
  'Estado de México', 'Guanajuato', 'Guerrero', 'Hidalgo', 'Jalisco', 'Michoacán', 'Morelos', 'Nayarit', 'Nuevo León', 'Oaxaca', 'Puebla', 'Querétaro', 'Quintana Roo',
  'San Luis Potosí', 'Sinaloa', 'Sonora', 'Tabasco', 'Tamaulipas', 'Tlaxcala', 'Veracruz', 'Yucatán', 'Zacatecas'];
const TIPOS = ['maltrato_fisico', 'abandono', 'sin_agua_alimento_refugio', 'hacinamiento_insalubre', 'comercio_ilegal', 'otra'];
const STATUS = {
  recibida: ['Recibida', 'info', 'Recibimos tu reporte. Todavía no lo revisa el equipo.'],
  en_revision: ['En revisión', 'info', 'El equipo está revisando tu reporte.'],
  en_proceso: ['En proceso', 'ok', 'El equipo está dando seguimiento a tu reporte.'],
  canalizada: ['Canalizada', 'ok', 'El equipo orientó el caso hacia la instancia que puede atenderlo. TECNOPATITAS no sustituye una denuncia oficial.'],
  cerrada: ['Cerrada', 'mute', 'El equipo cerró el seguimiento de este reporte.']
};

$('dn-estados').append(...ESTADOS.map(s => el('option', { value: s })));
const today = UI.todayMx();
$('dn-fecha').max = today;

/* ---------- Estado de la verificación anti-robots ---------- */
let captcha = null, blocked = false;
function showNotice(text, retry) {
  UI.put(aviso, text, retry ? ' ' : null, retry ? el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: () => { aviso.hidden = true; UI.msg(msg, null); captcha && captcha.retry(); } }) : null);
  aviso.hidden = false;
}
if (!TP || TP.configError) {
  blocked = true; showNotice('El sitio no está configurado correctamente. Avisa al administrador.');
} else if (C.configError) {
  blocked = true; showNotice(C.configError);
} else if (!C.enabled) {
  blocked = true;
  showNotice('El envío de reportes todavía no está activado en este sitio: falta configurar la verificación anti-robots (Cloudflare Turnstile). Cuando se active podrás enviar tu reporte aquí. Si hay un peligro inmediato, llama al 911.');
} else {
  captcha = C.mount($('dn-captcha'), {
    onStatus: (k, m) => { if (k === 'error') showNotice(m, true); else aviso.hidden = true; }
  });
}
send.disabled = blocked;
if (blocked) form.querySelectorAll('input,select,textarea,button').forEach(x => { x.disabled = true; });

/* ---------- Contador de la descripción ---------- */
const desc = $('dn-desc');
desc.addEventListener('input', () => { $('dn-cuenta').textContent = Array.from(desc.value).length + ' / 4000'; });

/* ---------- Fotos ---------- */
const photos = [];                                              // { blob, url (data:), id }
let photoSeq = 0;
function renderThumbs() {
  UI.put(thumbs, photos.map((p, i) => el('li', {},
    el('img', { src: p.url, alt: 'Vista previa de la foto ' + (i + 1), width: 96, height: 96 }),
    el('span', { class: 'mut', text: Math.max(1, Math.round(p.blob.size / 1024)) + ' KB' }),
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Quitar', 'aria-label': 'Quitar la foto ' + (i + 1), onclick: () => { const k = photos.findIndex(x => x.id === p.id); if (k >= 0) photos.splice(k, 1); renderThumbs(); } }))));
  fotos.disabled = blocked || photos.length >= MAX_PHOTOS;
}
const readUrl = blob => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = () => rej(new Error('lectura')); r.readAsDataURL(blob); });
async function shrink(file) {
  for (const [side, q] of [[1280, 0.82], [1100, 0.7], [900, 0.6]]) {
    const b = await M.prepareImage(file, { maxSide: side, quality: q });
    if (b.size <= MAX_PHOTO_BYTES) return b;
  }
  throw new M.MediaError('Una foto pesa demasiado incluso reducida. Prueba con otra.');
}
fotos.addEventListener('change', async () => {
  const files = Array.from(fotos.files || []); fotos.value = '';
  if (!files.length) return;
  UI.msg(msg, null);
  const room = MAX_PHOTOS - photos.length, take = files.slice(0, Math.max(0, room));
  let problem = files.length > take.length ? 'Máximo ' + MAX_PHOTOS + ' fotografías: se tomaron solo las primeras.' : null;
  fotos.disabled = true;
  for (const f of take) {
    try { const blob = await shrink(f); photos.push({ blob, url: await readUrl(blob), id: ++photoSeq }); }
    catch (ex) { problem = ex instanceof M.MediaError ? f.name.slice(0, 60) + ': ' + ex.message : 'No se pudo preparar una de las fotos.'; }
  }
  renderThumbs();
  if (problem) UI.msg(msg, 'err', problem);
});

/* ---------- Envío ---------- */
function check() {
  const tipo = form.tipo.value, d = desc.value.trim(), f = form.f.value, e = form.e.value.trim(), m = form.m.value.trim();
  if (!TIPOS.includes(tipo)) return 'Selecciona el tipo de situación.';
  if (Array.from(d).length < 30) return 'La descripción debe tener al menos 30 caracteres.';
  if (Array.from(d).length > 4000) return 'La descripción admite hasta 4000 caracteres.';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f) || f < '2000-01-01' || f > UI.addDays(today, 1)) return 'Indica una fecha aproximada válida (no puede ser futura).';
  if (Array.from(e).length < 2 || Array.from(e).length > 80) return 'Indica el estado.';
  if (Array.from(m).length < 2 || Array.from(m).length > 80) return 'Indica el municipio o alcaldía.';
  if (form.l.value.length > 300) return 'La referencia del lugar admite hasta 300 caracteres.';
  if (!$('dn-acepto').checked) return 'Marca la casilla para confirmar que entiendes cómo se maneja tu reporte.';
  if (!captcha || !captcha.token()) return 'Completa la verificación anti-robots antes de enviar.';
  return null;
}
form.addEventListener('submit', async ev => {
  ev.preventDefault();
  if (blocked || send.disabled) return;
  const err = check();
  if (err) { UI.msg(msg, 'err', err); return; }
  UI.msg(msg, null); UI.busy(send, true, 'Enviando…');
  const fd = new FormData();
  fd.append('type', form.tipo.value); fd.append('description', desc.value.trim()); fd.append('approx_date', form.f.value);
  fd.append('state', form.e.value.trim()); fd.append('municipality', form.m.value.trim()); fd.append('location_reference', form.l.value.trim());
  fd.append('website', $('dn-web').value); fd.append('cf-turnstile-response', captcha.token());
  photos.forEach((p, i) => fd.append('photos', p.blob, 'foto' + (i + 1) + '.jpg'));
  try {
    const r = await TP.fn('submit-complaint', fd);
    if (!r || r.ok !== true || typeof r.code !== 'string' || !CODE_RE.test(r.code)) throw new TP.TPError('bad_reply', 'bad_reply', 0);
    done(r.code);
  } catch (ex) {
    UI.msg(msg, 'err', TP.errorMessage(ex));
    UI.busy(send, false);
  } finally { captcha.reset(); }                               // cada token sirve una sola vez
});

/* ---------- Reporte recibido ---------- */
function done(code) {
  form.hidden = true;
  const codeEl = el('code', { id: 'dn-codigo', class: 'codebig', text: code });
  const copyMsg = el('span', { class: 'mut', role: 'status', 'aria-live': 'polite' });
  const h = el('h2', { text: 'Recibimos tu reporte', tabindex: -1 });
  UI.put(listo,
    h,
    el('p', { text: 'Este es tu código de seguimiento. Guárdalo en un lugar seguro: es la única forma de consultar el estado de tu reporte y no podemos recuperarlo ni saber quién lo envió.' }),
    el('div', { class: 'codebox' }, codeEl,
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Copiar código', onclick: async () => {
        try { await navigator.clipboard.writeText(code); copyMsg.textContent = 'Copiado.'; }
        catch { const r = document.createRange(); r.selectNodeContents(codeEl); const s = getSelection(); s.removeAllRanges(); s.addRange(r); copyMsg.textContent = 'Selecciona y copia el código.'; }
      } }), copyMsg),
    el('p', { class: 'note', text: 'Tu reporte quedó registrado en la plataforma para su revisión por el equipo. TECNOPATITAS no lo presentó ante ninguna autoridad. Si hay un peligro inmediato, llama al 911.' }),
    el('div', { class: 'row' },
      el('button', { class: 'btn coral sm', type: 'button', text: 'Consultar este código', onclick: () => { $('sg-codigo').value = code; lookup(); $('sg-codigo').scrollIntoView({ block: 'center' }); } }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Hacer otro reporte', onclick: again })));
  listo.hidden = false; h.focus();
}
function again() {
  form.reset(); photos.length = 0; renderThumbs(); $('dn-cuenta').textContent = '0 / 4000';
  UI.msg(msg, null); UI.busy(send, false); listo.hidden = true; UI.put(listo); form.hidden = false; form.tipo.focus();
}

/* ---------- Seguimiento ---------- */
const sf = $('f-seguimiento'), smsg = $('sg-msg'), sbtn = $('sg-boton'), sres = $('sg-resultado');
function normCode(v) {
  const s = String(v || '').toUpperCase().replace(/[^A-Z0-9]/g, ''), m = /^TP([A-Z2-9]{4})([A-Z2-9]{4})$/.exec(s);
  return m ? 'TP-' + m[1] + '-' + m[2] : null;
}
async function lookup() {
  UI.msg(smsg, null); UI.put(sres);
  const code = normCode($('sg-codigo').value);
  if (!code) { UI.msg(smsg, 'err', 'El código tiene el formato TP-XXXX-XXXX (letras y números, sin I, O, 0 ni 1).'); return; }
  if (!TP || TP.configError) { UI.msg(smsg, 'err', 'El sitio no está configurado correctamente. Avisa al administrador.'); return; }
  $('sg-codigo').value = code; UI.busy(sbtn, true, 'Consultando…');
  try {
    const r = await TP.rpc('track_complaint', { p_code: code }, { anon: true });
    if (r === null || r === undefined) { UI.msg(smsg, 'err', 'No encontramos ese código. Revisa que esté bien escrito.'); return; }
    if (typeof r !== 'object' || !STATUS[r.status]) throw new TP.TPError('bad_reply', 'bad_reply', 0);
    const [label, cls, text] = STATUS[r.status];
    UI.put(sres, el('div', { class: 'trackres' },
      el('p', {}, el('span', { class: 'badge ' + cls, text: label }), ' ', text),
      el('small', { class: 'mut', text: 'Recibido: ' + UI.dateTimeEs(r.received_at) + (r.updated_at && r.updated_at !== r.received_at ? ' · Última actualización: ' + UI.dateTimeEs(r.updated_at) : '') }),
      typeof r.public_update === 'string' && r.public_update ? el('div', { class: 'note' }, el('b', { text: 'Mensaje del equipo: ' }), r.public_update) : null));
  } catch (ex) { UI.msg(smsg, 'err', TP.errorMessage(ex)); }
  finally { UI.busy(sbtn, false); }
}
sf.addEventListener('submit', e => { e.preventDefault(); if (!sbtn.disabled) lookup(); });
renderThumbs();
})();
