/*
  Directorio público de aliados (Etapa 5). Cualquiera lo ve, sin iniciar sesión.
  Solo muestra lo que devuelven directory_search / directory_get: establecimientos aprobados y, según el plan del aliado,
  teléfono, horario, logotipo, fotos y promociones. Nunca se muestra quién es el dueño.
  Los mapas son enlaces directos a Google Maps (sin API de pago ni claves).
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, B = window.TPBiz;
if (!TP || !UI || !B) return;
const $ = id => document.getElementById(id), el = UI.el;
const PAGE = 12;
let seq = 0, shown = 0, total = 0;
const viewed = new Set();

const badge = (text, cls) => el('span', { class: 'badge ' + (cls || ''), text });

function actions(b, extra) {
  const row = el('div', { class: 'row' }, extra);
  if (!b.is_demo) {
    row.append(
      el('a', { class: 'btn ghost sm', href: B.mapsSearchUrl(b), target: '_blank', rel: 'noopener noreferrer', text: 'Ver ubicación', onclick: () => B.track(b.id, 'map') }),
      el('a', { class: 'btn sm', href: B.mapsRouteUrl(b), target: '_blank', rel: 'noopener noreferrer', text: 'Cómo llegar', onclick: () => B.track(b.id, 'map') }));
  }
  const wa = B.waHref(b.whatsapp_url);
  if (wa) row.append(el('a', { class: 'btn coral sm', href: wa, target: '_blank', rel: 'noopener noreferrer', text: 'WhatsApp' }));
  return row;
}

function renderDetail(box, d) {
  const parts = [];
  if (d.description) parts.push(el('p', { class: 'biz-full', text: d.description }));
  const photos = (Array.isArray(d.photo_paths) ? d.photo_paths : []).map(B.imgUrl).filter(Boolean);
  if (photos.length) {
    parts.push(el('div', { class: 'gallery' }, photos.map((u, i) =>
      el('a', { href: u, target: '_blank', rel: 'noopener noreferrer', 'aria-label': 'Abrir foto ' + (i + 1) + ' en una pestaña nueva' },
        el('img', { src: u, alt: 'Foto ' + (i + 1) + ' de ' + d.name, loading: 'lazy', decoding: 'async' })))));
  }
  const hrs = B.hoursList(d.hours);
  if (hrs.length) {
    parts.push(el('h4', { text: 'Horario' }),
      el('table', { class: 'hours' }, el('tbody', {}, hrs.map(([day, text]) => el('tr', {}, el('th', { scope: 'row', text: day }), el('td', { text }))))));
  }
  const tel = B.telHref(d.phone);
  if (tel) parts.push(el('p', {}, el('b', { text: 'Teléfono: ' }), el('a', { href: tel, text: d.phone })));
  const promos = Array.isArray(d.promotions) ? d.promotions : [];
  if (promos.length) {
    parts.push(el('h4', { text: 'Promociones vigentes' }),
      el('ul', { class: 'promos' }, promos.map(p => el('li', {},
        el('b', { text: p.title }), p.description ? el('span', { text: ' · ' + p.description }) : null,
        el('small', { text: ' (hasta el ' + UI.dateEs(p.ends_on) + ')' })))));
  }
  if (!parts.length) parts.push(el('p', { class: 'mut', text: 'Este establecimiento todavía no publicó más información.' }));
  box.replaceChildren(...parts);
}

async function toggleDetail(b, btn, box) {
  if (!box.hidden) { box.hidden = true; btn.textContent = 'Ver ficha'; btn.setAttribute('aria-expanded', 'false'); return; }
  btn.disabled = true; btn.textContent = 'Cargando…';
  try {
    const d = await TP.rpc('directory_get', { p_id: b.id }, { anon: true });
    if (!d || typeof d !== 'object') throw new Error('empty');
    renderDetail(box, d);
    if (!viewed.has(b.id)) { viewed.add(b.id); B.track(b.id, 'view'); }          // una visita por ficha y por carga de página
    box.hidden = false; btn.textContent = 'Ocultar ficha'; btn.setAttribute('aria-expanded', 'true');
  } catch {
    box.replaceChildren(el('p', { class: 'msg err', role: 'alert', text: 'No se pudo cargar la ficha. Inténtalo de nuevo.' }));
    box.hidden = false; btn.textContent = 'Ver ficha';
  } finally { btn.disabled = false; }
}

function card(b) {
  const full = !!b.full_listing, logo = full ? B.imgUrl(b.logo_path) : null;
  const place = [b.address, b.municipality, b.state].filter(Boolean).join(', ');
  const tel = full ? B.telHref(b.phone) : null;
  const box = el('div', { class: 'bizdetail', hidden: true });
  const tags = el('div', { class: 'tags' },
    el('span', { class: 'tag', text: B.CATEGORIES[b.category] || 'Otro servicio' }),
    b.verified ? badge('✔ Aliado verificado', 'ok') : null,
    b.is_priority ? badge('Destacado', 'mute') : null,
    b.has_promotion ? badge('🏷️ Promoción vigente', 'warn') : null,
    b.is_demo ? badge('Ejemplo de demostración', 'mute') : null);
  const head = el('div', { class: 'bizhead' },
    logo ? el('img', { class: 'bizlogo', src: logo, alt: 'Logotipo de ' + b.name, loading: 'lazy', decoding: 'async' })
         : el('div', { class: 'bizlogo ph-emoji', 'aria-hidden': 'true', text: B.ICONS[b.category] || '🐾' }),
    el('div', { class: 'bizname' }, el('h3', { text: b.name }), tags));
  const toggle = full ? el('button', { class: 'btn ghost sm', type: 'button', 'aria-expanded': 'false', text: 'Ver ficha' }) : null;
  if (toggle) toggle.addEventListener('click', () => toggleDetail(b, toggle, box));
  return el('article', { class: 'card biz' }, head,
    b.description ? el('p', { class: 'biz-desc', text: b.description }) : null,
    place ? el('p', { class: 'biz-place', text: '📍 ' + place }) : null,
    tel ? el('p', { class: 'biz-place' }, '📞 ', el('a', { href: tel, text: b.phone })) : null,
    b.is_demo ? el('small', {}, el('b', { text: 'Ficha de demostración: no es un establecimiento real.' })) : null,
    actions(b, toggle), box);
}

/* ---------- búsqueda y paginación ---------- */
const list = $('d-lista'), more = $('d-mas'), count = $('d-count'), state = $('d-estado');
const filters = () => ({ q: $('d-q').value.trim().slice(0, 80), cat: $('d-cat').value, ord: $('d-orden').value });

function showState(kind, text, retry) {
  if (!kind) { state.hidden = true; state.replaceChildren(); return; }
  const box = kind === 'empty'
    ? el('div', { class: 'empty' }, el('span', { text: '📍' }), el('h3', { text: text[0] }), el('p', { text: text[1] }))
    : el('div', { class: 'msg ' + (kind === 'err' ? 'err' : 'info'), role: kind === 'err' ? 'alert' : 'status', text });
  if (retry) box.append(el('p', {}, el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: retry })));
  state.replaceChildren(box); state.hidden = false;
}

async function load(reset) {
  const my = ++seq, f = filters();
  if (reset) { shown = 0; total = 0; list.replaceChildren(); more.hidden = true; count.textContent = ''; }
  showState('info', 'Buscando…');
  more.disabled = true;
  try {
    const rows = await TP.rpc('directory_search', { p_query: f.q || null, p_category: f.cat || null, p_order: f.ord, p_limit: PAGE, p_offset: shown }, { anon: true });
    if (my !== seq) return;
    const items = Array.isArray(rows) ? rows : [];
    if (items.length) total = Number(items[0].total_count) || items.length;
    items.forEach(b => { if (b && TPBizOk(b)) list.append(card(b)); });
    shown += items.length;
    showState(null);
    if (!shown) {
      const filtered = f.q || f.cat;
      showState('empty', filtered ? ['No encontramos establecimientos', 'Prueba con otra palabra o quita el filtro de categoría.']
                                  : ['Aún no hay aliados publicados', 'Los establecimientos aparecerán aquí cuando se registren y un administrador los apruebe.']);
      count.textContent = '';
    } else {
      count.textContent = total + (total === 1 ? ' establecimiento' : ' establecimientos');
    }
    more.hidden = shown >= total; more.textContent = 'Mostrar más (' + (total - shown) + ' restantes)';
  } catch (ex) {
    if (my !== seq) return;
    showState('err', TP.errorMessage(ex), () => load(reset));
  } finally { if (my === seq) more.disabled = false; }
}
const TPBizOk = b => typeof b.name === 'string' && B.UUID_RE.test(b.id || '');

let timer;
$('d-form').addEventListener('submit', e => { e.preventDefault(); clearTimeout(timer); load(true); });
$('d-q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => load(true), 350); });
$('d-cat').addEventListener('change', () => load(true));
$('d-orden').addEventListener('change', () => load(true));
more.addEventListener('click', () => load(false));

/* Opciones de categoría y parámetros de la dirección (?q=nombre&cat=veterinaria) */
Object.entries(B.CATEGORIES).forEach(([k, v]) => $('d-cat').append(el('option', { value: k, text: v })));
const params = new URLSearchParams(location.search);
const q0 = (params.get('q') || '').slice(0, 80), c0 = params.get('cat') || '';
if (q0) $('d-q').value = q0;
if (B.CATEGORIES[c0]) $('d-cat').value = c0;

TP.ready.then(() => { if (TP.configError) { showState('err', 'El sitio no está configurado todavía. Avisa al administrador.'); return; } load(true); });
})();
