/* Panel de administración (Etapa 10): controlador y ayudas compartidas. Los módulos admin-*.js se registran con TPAdmin.register().
   · Esta página es solo comodidad: la protección real está en el servidor. Cada función admin_* vuelve a comprobar que quien llama es
     administrador (is_admin()) y deja constancia en la bitácora. Ocultar o deshabilitar un botón nunca es la protección.
   · Todo lo que viene del servidor (nombres, mensajes, descripciones de denuncias…) se escribe como texto (textContent), nunca como HTML.
   · No hay pagos: los planes se asignan a mano. Los roles de administrador NO se gestionan desde aquí (solo desde el SQL Editor). */
(() => {
'use strict';
const mods = [];
const TP = window.TP, UI = window.TPUI;
const A = window.TPAdmin = { mods, register: m => mods.push(m), params: {}, LIMIT: 25 };
if (!TP || !UI) return;
const E = UI.el, $ = id => document.getElementById(id);
A.E = E;
A.PLAN = { basica: 'Huellita Básica', pro: 'Huellita Pro', vip: 'Huellita VIP', plata: 'Huellita de Plata', oro: 'Huellita de Oro' };
A.PERIOD = { monthly: 'mensual', yearly: 'anual' };
A.TYPE = { owner: 'Dueño de mascota', business: 'Aliado comercial' };

let busy = false, timers = [], current = null, shown = 0, keepParams = false;

/* ---------- Ayudas ---------- */
A.say = (kind, text) => UI.msg($('ad-msg'), kind, text);
A.d = iso => iso ? UI.dateMx(iso) : '';                 // instante → fecha en horario de México
A.dd = ymd => ymd ? UI.dateEs(ymd) : '';                // 'AAAA-MM-DD' (sin hora) → «4 dic 2026»
A.dt = iso => iso ? UI.dateTimeEs(iso) : '';
A.badge = (text, kind) => E('span', { class: 'badge ' + (kind || 'mute'), text });
A.rpc = (fn, args) => TP.rpc(fn, args || {});
A.err = ex => TP.hasSession() ? TP.errorMessage(ex) : 'Tu sesión expiró. Inicia sesión de nuevo.';
A.loading = host => UI.put(host, E('p', { class: 'mut', role: 'status', text: 'Cargando…' }));
A.empty = text => E('p', { class: 'mut adm-empty', text });
A.fail = (host, ex, retry) => UI.put(host, E('div', { class: 'msg err', role: 'alert' }, A.err(ex), ' ',
  retry ? E('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: retry }) : null));
/* Un campo con etiqueta visible; devuelve {box, input}. */
A.field = (label, input, hint) => E('label', { class: 'adm-f' }, E('span', { text: label }), input, hint ? E('small', { class: 'mut', text: hint }) : null);
A.options = (pairs, selected) => pairs.map(([v, t]) => E('option', { value: v, text: t, selected: String(v) === String(selected) ? true : null }));
/* Fecha 'AAAA-MM-DD' (hora de México, sin horario de verano) → instante al final de ese día. */
A.endOfDay = ymd => /^\d{4}-\d{2}-\d{2}$/.test(ymd || '') ? ymd + 'T23:59:59-06:00' : null;
A.go = (id, params) => { A.params = params || {}; if (location.hash === '#' + id) show(id); else { keepParams = true; location.hash = '#' + id; } };
/* Temporizadores de la sección abierta: se cancelan al cambiar de sección y se pausan con la pestaña oculta. */
A.every = (ms, fn) => { timers.push(setInterval(() => { if (!document.hidden) fn(); }, ms)); };
A.alive = host => !!host && host.isConnected;

/* Ejecuta una acción del servidor sin dobles envíos. Devuelve true si salió bien. */
A.run = async (btn, busyLabel, fn, okText) => {
  if (busy) return false;
  busy = true; UI.busy(btn, true, busyLabel); A.say(null);
  let ok = false;
  try { await fn(); ok = true; } catch (ex) { A.say('err', A.err(ex)); }
  busy = false; UI.busy(btn, false);
  if (ok && okText) A.say('ok', okText);
  return ok;
};

/* Botón de dos pasos: «Cancelar…» → «¿Seguro? Sí / No». */
A.confirm = (label, question, onYes, cls) => {
  const box = E('span', { class: 'adm-confirm' });
  const idle = () => UI.put(box, E('button', { class: cls || 'btn ghost sm', type: 'button', text: label, onclick: ask }));
  function ask() {
    UI.put(box, E('span', { class: 'adm-ask', role: 'group', 'aria-label': question },
      E('span', { text: question + ' ' }),
      E('button', { class: 'btn coral sm', type: 'button', text: 'Sí', onclick: e => onYes(e.currentTarget) }),
      E('button', { class: 'btn ghost sm', type: 'button', text: 'No', dataset: { no: '1' }, onclick: () => { idle(); box.querySelector('button').focus(); } })));
    box.querySelector('[data-no]').focus();
  }
  idle();
  return box;
};

A.pager = ({ total, limit, offset, go }) => {
  const to = Math.min(offset + limit, total);
  return E('div', { class: 'adm-pager' },
    E('span', { class: 'mut', text: total ? 'Mostrando ' + (offset + 1) + '–' + to + ' de ' + total : 'Sin resultados' }),
    E('div', { class: 'row' },
      E('button', { class: 'btn ghost sm', type: 'button', text: '← Anterior', disabled: offset <= 0, onclick: () => go(Math.max(0, offset - limit)) }),
      E('button', { class: 'btn ghost sm', type: 'button', text: 'Siguiente →', disabled: offset + limit >= total, onclick: () => go(offset + limit) })));
};

/* Pares «etiqueta: valor» para fichas. */
A.dl = pairs => E('dl', { class: 'adm-dl' }, pairs.filter(Boolean).flatMap(([k, v]) => [E('dt', { text: k }), E('dd', { text: v == null || v === '' ? '—' : String(v) })]));

/* ---------- Navegación ---------- */
const ORDER = ['dash', 'usuarios', 'aliados', 'denuncias', 'guias', 'subs', 'atencion', 'bitacora'];
function paintNav() {
  const nav = $('ad-nav');
  const list = ORDER.map(id => id === 'dash' ? { id, label: '📈 Panel' } : mods.find(m => m.id === id)).filter(Boolean);
  /* Pulsar la sección donde ya estás vuelve a su lista (el cambio de dirección no se dispara si es la misma) */
  UI.put(nav, list.map(m => E('a', { href: '#' + m.id, text: m.label, dataset: { sec: m.id }, 'aria-current': current === m.id ? 'page' : null,
    onclick: e => { if ((location.hash || '#dash') === '#' + m.id) { e.preventDefault(); A.params = {}; show(m.id); } } })));
}

function clearTimers() { timers.forEach(clearInterval); timers = []; }

async function show(id) {
  const m = id === 'dash' ? dash : mods.find(x => x.id === id);
  if (!m) { A.go('dash'); return; }
  clearTimers(); A.say(null);
  current = m.id; const my = ++shown;
  document.querySelectorAll('#ad-nav a').forEach(a => { if (a.dataset.sec === m.id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const head = E('h2', { id: 'ad-h', tabindex: '-1', text: m.title });
  const host = E('div', { class: 'adm-sec', dataset: { sec: m.id } });
  UI.put($('ad-view'), head, host);
  document.title = m.title + ' · Administración · TECNOPATITAS';
  try { await m.open(A, host); } catch (ex) { if (my === shown) A.fail(host, ex, () => show(m.id)); }
  if (my === shown && !host.contains(document.activeElement)) head.focus({ preventScroll: false });
}

/* ---------- Panel (resumen) ---------- */
const CARDS = [
  ['users', 'Usuarios', 'usuarios', null], ['suspended_users', 'Cuentas suspendidas', 'usuarios', null],
  ['businesses_pending', 'Aliados en revisión', 'aliados', { status: 'pending' }], ['businesses', 'Aliados registrados', 'aliados', { status: '' }],
  ['complaints_pending', 'Denuncias pendientes', 'denuncias', { status: 'pendientes' }], ['complaints', 'Denuncias en total', 'denuncias', { status: '' }],
  ['conversations_unanswered', 'Conversaciones sin responder', 'atencion', { filter: 'pending' }], ['conversations_open', 'Conversaciones abiertas', 'atencion', { filter: 'open' }],
  ['plan_requests_pending', 'Solicitudes de plan', 'subs', { tab: 'requests' }], ['active_subscriptions', 'Suscripciones activas', 'subs', { tab: 'subs' }],
  ['pets', 'Mascotas registradas', null, null]
];
const TODO = new Set(['businesses_pending', 'complaints_pending', 'conversations_unanswered', 'plan_requests_pending']);
const dash = {
  id: 'dash', title: 'Resumen',
  async open(_A, host) {
    A.loading(host);
    const load = async () => {
      let s;
      try { s = await A.rpc('admin_dashboard_stats'); } catch (ex) { if (A.alive(host)) A.fail(host, ex, load); return; }
      if (!A.alive(host)) return;
      UI.put(host,
        E('p', { class: 'mut', text: 'Lo que espera atención aparece resaltado. Pulsa una tarjeta para ir a la sección.' }),
        E('div', { class: 'adm-stats' }, CARDS.map(([k, label, sec, par]) => {
          const n = Number(s[k]) || 0;
          const kids = [E('span', { class: 'stat', text: String(n) }), E('small', { text: label })];
          const cls = 'card statcard' + (TODO.has(k) && n > 0 ? ' adm-todo' : '');
          return sec ? E('a', { class: cls, href: '#' + sec, dataset: { stat: k }, onclick: e => { e.preventDefault(); A.go(sec, par || {}); } }, kids)
                     : E('div', { class: cls, dataset: { stat: k } }, kids);
        })),
        E('p', { class: 'mut', text: 'Las notificaciones del equipo (campana) abren directamente la sección correspondiente.' }),
        E('p', { class: 'row' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Actualizar cifras', onclick: () => { A.loading(host); load(); } })));
    };
    await load();
  }
};

/* ---------- Arranque ---------- */
function route() {
  const id = (location.hash || '#dash').slice(1);
  show(ORDER.includes(id) ? id : 'dash');
}
let started = false;
async function start() {
  if (started) return; started = true;
  try {
    await TP.ready;
    if (TP.configError || !$('ad-view')) return;
    const me = await TP.me();
    if (!me || !me.isAdmin) return;                           // guard.js ya explicó por qué no se entra
  } catch { return; }
  paintNav();
  window.addEventListener('hashchange', () => { if (keepParams) keepParams = false; else A.params = {}; route(); });
  route();
}
document.addEventListener('DOMContentLoaded', start);
if (document.readyState !== 'loading') start();
})();
