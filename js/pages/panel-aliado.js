/*
  Panel de aliados (Etapa 5): controlador. Une los módulos panel-datos, -fotos, -horarios, -promos y -stats.
  Cada aliado ve y edita únicamente SUS establecimientos: lo impone el servidor (RLS), no esta página.
  Un establecimiento nuevo queda «en revisión» hasta que un administrador lo apruebe. Los planes los asigna un administrador:
  todavía no hay contratación ni cobros.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, B = window.TPBiz, P = window.TPPets;
const MODS = window.TPPanelMods;
if (!TP || !UI || !B || !P || !MODS) return;
const $ = id => document.getElementById(id), el = UI.el;
const MAX_BIZ = 5;
const SECTIONS = [['datos', '🏪 Datos comerciales'], ['fotos', '🖼️ Fotos y logotipo'], ['horarios', '🕘 Horarios'], ['promos', '🏷️ Promociones'], ['stats', '📊 Estadísticas']];
const COLS = 'id,name,category,description,address,state,municipality,phone,whatsapp_url,maps_query,logo_path,photo_paths,hours,status,verified,is_demo,created_at';

const ctx = { me: null, list: [], biz: null, plan: null, suspended: false, added, updated, removed };
let section = 'datos', creating = false, flash = null;

const STATUS = {
  pending: ['En revisión', 'warn', 'Tu ficha todavía NO aparece en el directorio. Un administrador la revisará y, si todo está bien, la aprobará.'],
  approved: ['Aprobada', 'ok', 'Tu ficha ya aparece en el directorio.'],
  suspended: ['Suspendida', 'warn', 'Un administrador suspendió tu ficha: no aparece en el directorio. Si crees que es un error, escribe a atención al cliente desde el chat.'],
  rejected: ['No aprobada', 'warn', 'Tu ficha no fue aprobada y no aparece en el directorio. Revisa tus datos y escribe a atención al cliente desde el chat si necesitas más información.']
};

function renderStatus() {
  const host = $('pa-estado');
  const b = ctx.biz;
  if (!b) { host.replaceChildren(); return; }
  const [label, cls, text] = STATUS[b.status] || STATUS.pending;
  const plan = ctx.plan, isBiz = !!(plan && plan.audience === 'business');
  const planText = isBiz
    ? 'Tu plan: ' + plan.name + '. ' + (plan.whatsapp_button ? 'Tu ficha completa incluye teléfono, horario, logotipo, fotos, promociones y botón de WhatsApp.' : 'Tu ficha completa incluye teléfono, horario, logotipo, fotos y promociones.')
    : 'Todavía no tienes un plan de aliado: el directorio muestra de tu negocio solo nombre, categoría, descripción y dirección. La contratación y los cobros todavía no están habilitados; por ahora un administrador asigna los planes.';
  const verifiedText = b.verified
    ? (isBiz && plan.verified_badge_eligible ? '✔ Tu establecimiento es «Aliado verificado»: la etiqueta se muestra en tu ficha.' : 'Un administrador marcó tu establecimiento como verificado; la etiqueta «Aliado verificado» se muestra con el plan Huellita de Oro.')
    : 'La etiqueta «Aliado verificado» solo puede asignarla un administrador.';
  const link = b.status === 'approved' && !b.is_demo
    ? el('a', { class: 'btn ghost sm', href: 'directorio.html?q=' + encodeURIComponent(b.name.slice(0, 80)), text: 'Ver mi ficha en el directorio' }) : null;
  host.replaceChildren(el('div', { class: 'card bizstatus' },
    el('div', {}, el('b', { text: b.name }), ' ', el('span', { class: 'badge ' + cls, text: label })),
    el('p', { text }), el('p', { class: 'mut', text: planText }), el('p', { class: 'mut', text: verifiedText }), link));
}

function renderSelector() {
  const host = $('pa-selector');
  if (!ctx.list.length || creating) { host.replaceChildren(); return; }
  const kids = [];
  if (ctx.list.length > 1) {
    const sel = el('select', { id: 'pa-sel', 'aria-label': 'Establecimiento que estás administrando' }, ctx.list.map(b => el('option', { value: b.id, text: b.name })));
    sel.value = ctx.biz.id;
    sel.addEventListener('change', () => { ctx.biz = ctx.list.find(b => b.id === sel.value) || ctx.list[0]; refresh(); });
    kids.push(el('label', { class: 'inline' }, 'Establecimiento', sel));
  }
  if (ctx.list.length < MAX_BIZ && !ctx.suspended) {
    kids.push(el('button', { class: 'btn ghost sm', type: 'button', text: '＋ Registrar otro establecimiento', onclick: () => { creating = true; refresh(); } }));
  }
  host.replaceChildren(el('div', { class: 'row bizselect' }, kids));
}

function renderTabs() {
  const nav = $('pa-tabs');
  nav.hidden = !ctx.biz || creating;
  nav.replaceChildren(...SECTIONS.map(([k, label]) => {
    const a = el('a', { href: '#' + k, text: label, 'data-sec': k });
    if (k === section) a.setAttribute('aria-current', 'page');
    return a;
  }));
}

function renderModule() {
  const host = $('pa-modulo');
  if (creating || !ctx.biz) {
    MODS.datos.renderCreate(host, ctx, {
      title: ctx.list.length ? 'Registrar otro establecimiento' : 'Registra tu establecimiento',
      onCancel: ctx.list.length ? () => { creating = false; refresh(); } : null
    });
    return;
  }
  const mod = section === 'datos' ? { render: MODS.datos.renderEdit } : MODS[section];
  if (!mod) { host.replaceChildren(el('p', { class: 'msg err', role: 'alert', text: 'Esta sección no está disponible.' })); return; }
  mod.render(host, ctx);
}

function renderFlash() {
  const box = $('pa-msg');
  if (flash) { UI.msg(box, 'ok', flash); flash = null; } else UI.msg(box, null);
}

function refresh() { renderFlash(); renderStatus(); renderSelector(); renderTabs(); renderModule(); }

function added(row) {
  ctx.list.push(row); ctx.biz = row; creating = false; section = 'datos';
  flash = 'Establecimiento registrado. Quedó «en revisión»: aparecerá en el directorio cuando un administrador lo apruebe. Mientras tanto puedes completar tus datos, fotos, horario y promociones.';
  location.hash = '#datos';
  refresh();
}
function updated(row) {
  const i = ctx.list.findIndex(b => b.id === row.id);
  if (i >= 0) ctx.list[i] = row;
  if (ctx.biz && ctx.biz.id === row.id) ctx.biz = row;
  renderStatus();
  const sel = $('pa-sel'); if (sel) { const o = Array.from(sel.options).find(x => x.value === row.id); if (o) o.textContent = row.name; }
}
function removed(biz) {
  const paths = [biz.logo_path].concat(Array.isArray(biz.photo_paths) ? biz.photo_paths : []).filter(Boolean);
  if (paths.length) TP.storage.remove('business-media', paths).catch(() => {});         // limpieza; si falla solo queda un archivo huérfano
  ctx.list = ctx.list.filter(b => b.id !== biz.id);
  ctx.biz = ctx.list[0] || null; section = 'datos';
  flash = 'Establecimiento eliminado.';
  refresh();
}

function fromHash() {                                                  // una dirección desconocida o rara abre «Datos comerciales»
  const k = (location.hash || '').replace('#', '');
  section = SECTIONS.some(s => s[0] === k) ? k : 'datos';
}
window.addEventListener('hashchange', () => { if (!ctx.biz || creating) return; fromHash(); renderTabs(); renderModule(); });

async function start() {
  const root = $('pa-modulo');
  try {
    await TP.ready;
    if (TP.configError) return;
    const me = await TP.me();
    if (!me || me.accountType !== 'business') return;                 // guard.js ya mostró el aviso correspondiente
    ctx.me = me; ctx.suspended = !!me.suspended;
    const [rows, plan] = await Promise.all([
      TP.rest('/businesses', { query: 'select=' + COLS + '&owner_id=eq.' + me.user.id + '&order=created_at.asc&limit=20' }),
      P.plan()
    ]);
    ctx.list = Array.isArray(rows) ? rows : [];
    ctx.plan = plan; ctx.biz = ctx.list[0] || null;
    fromHash(); refresh();
  } catch (ex) {
    if (ex && ex.code === 'session_expired') return;
    root.replaceChildren(el('p', { class: 'msg err', role: 'alert', text: TP.errorMessage(ex) }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: () => { root.replaceChildren(el('p', { class: 'mut', text: 'Cargando…' })); start(); } }));
  }
}
start();
})();
