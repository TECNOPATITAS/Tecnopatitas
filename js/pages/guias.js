/* Guías de cuidado (público, Etapa 10): lista con búsqueda y categoría, y lectura de una guía (guias.html?g=direccion).
   · Solo se leen guías PUBLICADAS (lo impone la política de la base de datos; un borrador no se puede leer ni adivinando la dirección).
   · El contenido es texto plano: se dibuja con textContent (TPGuides.blocks), nunca como HTML.
   · Es información general; no sustituye a un veterinario. */
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, G = window.TPGuides;
if (!TP || !UI || !G || !document.getElementById('gd-lista')) return;
const el = UI.el, $ = id => document.getElementById(id);
const LIST_COLS = 'slug,title,summary,category,author_source,published_at';
const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
let all = [];

function estado(kind, text, retry) {
  const box = $('gd-estado');
  if (!kind) { box.hidden = true; box.textContent = ''; return; }
  box.className = 'msg ' + kind; box.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  UI.put(box, text, retry ? [' ', el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: retry })] : null);
  box.hidden = false;
}
const fail = (ex, retry) => estado('err', TP.errorMessage ? TP.errorMessage(ex) : 'No se pudo cargar.', retry);

function card(g) {
  return el('div', { class: 'card gd-card', dataset: { slug: g.slug } },
    el('span', { class: 'badge info', text: G.CATEGORIES[g.category] || g.category }),
    el('h3', null, el('a', { href: 'guias.html?g=' + encodeURIComponent(g.slug), text: g.title })),
    g.summary ? el('p', { text: g.summary }) : null,
    g.author_source ? el('small', { class: 'gd-src', text: g.author_source }) : null);
}

function paintList() {
  const q = norm($('gd-q').value.trim()), cat = $('gd-cat').value;
  const rows = all.filter(g => (!cat || g.category === cat) && (!q || norm(g.title).includes(q) || norm(g.summary).includes(q)));
  $('gd-count').textContent = all.length ? (rows.length === 1 ? '1 guía' : rows.length + ' guías') : '';
  UI.put($('gd-lista'), rows.map(card));
  if (!all.length) estado('info', 'Aún no hay guías publicadas. Cuando existan, aparecerán aquí.');
  else if (!rows.length) estado('info', 'No hay guías que coincidan con tu búsqueda.');
  else estado(null);
}

async function loadList() {
  estado('info', 'Cargando guías…');
  try { all = await TP.rest('/care_guides', { query: 'select=' + LIST_COLS + '&is_published=eq.true&order=published_at.desc,title.asc&limit=200', anon: true }); }
  catch (ex) { fail(ex, loadList); return; }
  if (!Array.isArray(all)) all = [];
  paintList();
}

async function loadOne(slug) {
  $('gd-lista-vista').hidden = true; const art = $('gd-articulo'); art.hidden = false;
  UI.put(art, el('p', { class: 'mut', role: 'status', text: 'Cargando…' }));
  let rows;
  try { rows = await TP.rest('/care_guides', { query: 'select=' + LIST_COLS + ',content&slug=eq.' + encodeURIComponent(slug) + '&is_published=eq.true&limit=1', anon: true }); }
  catch (ex) { UI.put(art, el('div', { class: 'msg err', role: 'alert' }, TP.errorMessage ? TP.errorMessage(ex) : 'No se pudo cargar.', ' ', el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: () => loadOne(slug) }))); return; }
  const g = Array.isArray(rows) ? rows[0] : null;
  const back = el('p', null, el('a', { class: 'btn ghost sm', href: 'guias.html', text: '← Todas las guías' }));
  if (!g) { document.title = 'Guía no encontrada · TECNOPATITAS'; UI.put(art, back, el('div', { class: 'empty' }, el('span', { text: '📚' }), el('h3', { text: 'No encontramos esa guía' }), el('p', { text: 'Puede que ya no esté publicada o que la dirección esté mal escrita.' }))); return; }
  document.title = g.title + ' · Guías · TECNOPATITAS';
  UI.put(art, back, el('span', { class: 'badge info', text: G.CATEGORIES[g.category] || g.category }), el('h2', { id: 'gd-titulo', tabindex: '-1', text: g.title }),
    g.summary ? el('p', { class: 'lead', text: g.summary }) : null, G.blocks(g.content),
    g.author_source ? el('p', { class: 'gd-src', text: 'Fuente: ' + g.author_source }) : null,
    el('p', { class: 'note', text: 'Esta guía es información general y no sustituye la consulta con un veterinario.' }));
  $('gd-titulo').focus({ preventScroll: false });
}

let started = false;
async function start() {
  if (started) return; started = true;
  try { await TP.ready; } catch { /* config incompleta: layout.js lo explica */ }
  if (TP.configError) return;
  const slug = new URLSearchParams(location.search).get('g');
  if (slug !== null) {
    if (!G.SLUG_RE.test(slug) || slug.length > 120) { $('gd-lista-vista').hidden = true; $('gd-articulo').hidden = false; loadOne('no-existe-esa-guia'); return; }
    loadOne(slug); return;
  }
  $('gd-cat').append(...Object.keys(G.CATEGORIES).map(k => el('option', { value: k, text: G.CATEGORIES[k] })));
  $('gd-form').addEventListener('submit', e => { e.preventDefault(); paintList(); });
  $('gd-cat').addEventListener('change', paintList);
  $('gd-q').addEventListener('input', paintList);
  loadList();
}
document.addEventListener('DOMContentLoaded', start);
if (document.readyState !== 'loading') start();
})();
