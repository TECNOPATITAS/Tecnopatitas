/*
  Panel de aliados · Horarios (Etapa 5).
  El horario se guarda en businesses.hours como { lun: '09:00-18:00', dom: 'Cerrado', … }. Los días sin indicar no se guardan.
  El servidor valida la forma del objeto (máximo 10 días, textos cortos); aquí solo se ayuda a capturarlo bien.
  Con plan Plata u Oro el directorio muestra el horario en la ficha.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, B = window.TPBiz, P = window.TPPets;
if (!TP || !UI || !B || !P) return;
const el = UI.el;
const MODS = (window.TPPanelMods = window.TPPanelMods || {});
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

function render(host, ctx) {
  const biz = ctx.biz, cur = (biz.hours && typeof biz.hours === 'object' && !Array.isArray(biz.hours)) ? biz.hours : {};
  const disabled = ctx.suspended;
  const box = el('div', { class: 'msg', hidden: true });
  let legacy = false;                                           // valores guardados con otro formato (se reemplazan al guardar)
  const rows = B.DAYS.map(([key, label]) => {
    const p = B.parseHour(cur[key]);
    if (cur[key] !== undefined && !p) legacy = true;
    const mode = el('select', { 'aria-label': 'Estado del ' + label.toLowerCase() },
      el('option', { value: '', text: 'Sin indicar' }), el('option', { value: 'open', text: 'Abierto' }), el('option', { value: 'closed', text: 'Cerrado' }));
    const from = el('input', { type: 'time', 'aria-label': label + ': abre', value: p && p.open ? p.from : '09:00' });
    const to = el('input', { type: 'time', 'aria-label': label + ': cierra', value: p && p.open ? p.to : '18:00' });
    mode.value = p ? (p.open ? 'open' : 'closed') : '';
    const sync = () => { const o = mode.value === 'open'; from.disabled = to.disabled = disabled || !o; };
    mode.addEventListener('change', sync);
    mode.disabled = disabled; sync();
    return { key, label, mode, from, to, sync, tr: el('tr', {}, el('th', { scope: 'row', text: label }), el('td', {}, mode), el('td', {}, from), el('td', {}, to)) };
  });
  if (Object.keys(cur).some(k => !B.DAYS.some(d => d[0] === k))) legacy = true;

  const copyBtn = el('button', { class: 'btn ghost sm', type: 'button', text: 'Copiar el lunes a lunes–viernes', disabled, onclick: () => {
    const mon = rows[0];
    rows.slice(1, 5).forEach(r => { r.mode.value = mon.mode.value; r.from.value = mon.from.value; r.to.value = mon.to.value; r.sync(); });
    UI.msg(box, 'info', 'Listo: revisa los días y pulsa «Guardar horario».');
  } });

  const save = el('button', { class: 'btn coral', type: 'submit', text: 'Guardar horario', disabled });
  const form = el('form', { novalidate: true },
    el('div', { class: 'tablewrap' }, el('table', { class: 'hours edit' },
      el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Día' }), el('th', { scope: 'col', text: 'Estado' }), el('th', { scope: 'col', text: 'Abre' }), el('th', { scope: 'col', text: 'Cierra' }))),
      el('tbody', {}, rows.map(r => r.tr)))),
    box, el('div', { class: 'row' }, save, copyBtn));

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const hours = {};
    for (const r of rows) {
      if (r.mode.value === 'closed') hours[r.key] = 'Cerrado';
      else if (r.mode.value === 'open') {
        if (!TIME_RE.test(r.from.value) || !TIME_RE.test(r.to.value)) { UI.msg(box, 'err', r.label + ': escribe la hora de apertura y la de cierre.'); return; }
        if (r.from.value === r.to.value) { UI.msg(box, 'err', r.label + ': la hora de apertura y la de cierre no pueden ser iguales.'); return; }
        hours[r.key] = r.from.value + '-' + r.to.value;
      }
    }
    UI.msg(box, null); UI.busy(save, true, 'Guardando…');
    try {
      const r = await TP.rest('/businesses', { method: 'PATCH', query: 'id=eq.' + biz.id, body: { hours }, prefer: 'return=representation' });
      if (!Array.isArray(r) || !r.length) throw P.notSaved();
      ctx.updated(r[0]);
      render(host, ctx);
      UI.msg(host.querySelector('.msg'), 'ok', 'Horario guardado.');
    } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); UI.busy(save, false); }
  });

  const hasPlan = !!(ctx.plan && ctx.plan.audience === 'business');
  UI.put(host,
    el('h3', { text: '🕘 Horarios de atención' }),
    el('p', { class: 'mut', text: 'Marca cada día como abierto (con su hora de apertura y cierre), cerrado o sin indicar. Los días sin indicar no se muestran.' }),
    hasPlan ? null : el('p', { class: 'stage', text: 'Con tu plan actual el directorio todavía no muestra el horario. Puedes dejarlo listo desde ahora.' }),
    legacy ? el('p', { class: 'note', text: 'Tu horario anterior tenía un formato distinto: al guardar se reemplazará por el de esta tabla.' }) : null,
    form);
}

MODS.horarios = { render };
})();
