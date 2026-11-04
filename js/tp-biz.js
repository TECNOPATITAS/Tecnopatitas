/*
  Ayudas compartidas del directorio y del panel de aliados (Etapa 5).
  Todo lo que viene del servidor se muestra como TEXTO. Los enlaces (mapas, teléfono, WhatsApp) se construyen aquí con
  direcciones de dominios fijos y partes validadas o codificadas; nunca se usa un enlace guardado tal cual.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI;
if (!TP || !UI) return;

const CATEGORIES = { veterinaria: 'Veterinaria', estetica_canina: 'Estética canina', estetica_felina: 'Estética felina',
                     tienda: 'Tienda de mascotas', adiestramiento: 'Adiestramiento', otro: 'Otro servicio' };
const ICONS = { veterinaria: '🩺', estetica_canina: '✂️', estetica_felina: '🐈', tienda: '🛍️', adiestramiento: '🎓', otro: '🐾' };
const DAYS = [['lun', 'Lunes'], ['mar', 'Martes'], ['mie', 'Miércoles'], ['jue', 'Jueves'], ['vie', 'Viernes'], ['sab', 'Sábado'], ['dom', 'Domingo']];
const DAY_NAME = Object.fromEntries(DAYS);
const DAY_ORDER = DAYS.map(d => d[0]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PHONE_RE = /^[0-9+() .-]{7,20}$/;
const WA_RE = /^https:\/\/wa\.me\/[0-9]{8,15}(\?text=[A-Za-z0-9%._~+-]{1,255})?$/;   // el mismo formato que exige la base de datos

/* Texto que Google Maps buscará: el que escribió el aliado o, si no, nombre + dirección + municipio + estado */
function mapsQuery(b) {
  const own = (b.maps_query || '').trim();
  return (own || [b.name, b.address, b.municipality, b.state].filter(Boolean).join(', ')).slice(0, 200);
}
const mapsSearchUrl = b => 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(mapsQuery(b));
const mapsRouteUrl = b => 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(mapsQuery(b));
const telHref = phone => (typeof phone === 'string' && PHONE_RE.test(phone)) ? 'tel:' + phone.replace(/[^0-9+]/g, '') : null;
const waHref = url => (typeof url === 'string' && WA_RE.test(url)) ? url : null;
/* Los logotipos y fotos del aliado están en un bucket público; la ruta se valida antes de armar la dirección */
const imgUrl = path => (typeof path === 'string' && path) ? TP.storage.publicUrl('business-media', path) : null;

/* Horario guardado → [[«Lunes», «09:00-18:00»], …] en orden de semana (las claves desconocidas, como «lun-vie», al final) */
function hoursList(h) {
  if (!h || typeof h !== 'object' || Array.isArray(h)) return [];
  const keys = Object.keys(h).filter(k => typeof h[k] === 'string' && h[k].trim() !== '');
  keys.sort((a, b) => { const ia = DAY_ORDER.indexOf(a), ib = DAY_ORDER.indexOf(b); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib); });
  return keys.map(k => [DAY_NAME[k] || k, h[k].trim()]);
}
/* '09:00-18:00' → {open:true, from, to}; 'Cerrado' → {open:false}; otro formato → null */
function parseHour(v) {
  if (typeof v !== 'string') return null;
  const m = /^(\d{2}:\d{2})-(\d{2}:\d{2})$/.exec(v.trim());
  if (m) return { open: true, from: m[1], to: m[2] };
  return /^cerrado$/i.test(v.trim()) ? { open: false } : null;
}

/* Número de WhatsApp escrito por una persona → enlace wa.me (solo números de México: 10 dígitos, con o sin 52 / 521) */
function waFromInput(raw) {
  const t = String(raw || '').trim();
  if (!t) return { url: null };
  const d = t.replace(/[\s().+-]/g, '');
  if (!/^\d+$/.test(d)) return { error: 'El número de WhatsApp solo puede llevar dígitos, espacios, guiones o paréntesis.' };
  let n = d;
  if (n.length === 12 && n.startsWith('52')) n = n.slice(2);
  else if (n.length === 13 && n.startsWith('521')) n = n.slice(3);
  if (n.length !== 10) return { error: 'Escribe el WhatsApp a 10 dígitos (lada + número), por ejemplo 55 1234 5678.' };
  return { url: 'https://wa.me/52' + n };
}
/* Enlace guardado → los 10 dígitos para mostrarlos en el formulario */
function waToInput(url) {
  const m = /^https:\/\/wa\.me\/(\d{8,15})/.exec(url || '');
  if (!m) return '';
  const d = m[1];
  if (d.length === 12 && d.startsWith('52')) return d.slice(2);
  if (d.length === 13 && d.startsWith('521')) return d.slice(3);
  return d;
}

/* Registra una visita o un clic (contador anónimo por día). Nunca interrumpe al visitante. */
function track(id, event) {
  if (!UUID_RE.test(id || '')) return;
  try { TP.rpc('directory_track', { p_id: id, p_event: event }).catch(() => {}); } catch { /* sin conexión: no se cuenta */ }
}

window.TPBiz = Object.freeze({ CATEGORIES, ICONS, DAYS, UUID_RE, PHONE_RE, WA_RE, mapsQuery, mapsSearchUrl, mapsRouteUrl, telHref, waHref, imgUrl,
                               hoursList, parseHour, waFromInput, waToInput, track });
})();
