/*
  Panel de aliados · Promociones (Etapa 5).
  Plata: 1 promoción nueva al mes; Oro: ilimitadas (el límite lo aplica el SERVIDOR con un disparador; aquí solo se avisa).
  Una promoción se muestra en el directorio mientras esté activa, dentro de sus fechas, y la ficha esté aprobada con plan Plata u Oro.
  No hay cobros ni cupones: es solo un anuncio de texto.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, P = window.TPPets;
if (!TP || !UI || !P) return;
const el = UI.el;
const MODS = (window.TPPanelMods = window.TPPanelMods || {});
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const COLS = 'id,business_id,title,description,starts_on,ends_on,is_active,created_at';

const monthStartIso = () => UI.todayMx().slice(0, 7) + '-01T00:00:00-06:00';        // Ciudad de México usa UTC-6 todo el año

function statusOf(p, today) {
  if (!p.is_active) return ['Pausada', 'mute'];
  if (today < p.starts_on) return ['Programada', 'warn'];
  if (today > p.ends_on) return ['Vencida', 'mute'];
  return ['Vigente', 'ok'];
}

async function render(host, ctx, keepMsg) {
  const biz = ctx.biz, today = UI.todayMx();
  const box = el('div', { class: 'msg', hidden: true });
  host.replaceChildren(el('h3', { text: '🏷️ Promociones' }), el('p', { class: 'mut', text: 'Cargando…' }));
  let promos, usedThisMonth;
  try {
    promos = await TP.rest('/business_promotions', { query: 'select=' + COLS + '&business_id=eq.' + biz.id + '&order=created_at.desc&limit=100' });
    const cnt = await TP.rest('/business_promotions', { query: 'select=id&created_at=gte.' + encodeURIComponent(monthStartIso()) + '&limit=1000' });
    usedThisMonth = Array.isArray(cnt) ? cnt.length : 0;
    if (!Array.isArray(promos)) throw new Error('bad');
  } catch (ex) {
    host.replaceChildren(el('h3', { text: '🏷️ Promociones' }), el('p', { class: 'msg err', role: 'alert', text: TP.errorMessage(ex) }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: () => render(host, ctx) }));
    return;
  }

  const plan = ctx.plan, isBiz = !!(plan && plan.audience === 'business');
  const limit = isBiz ? plan.max_promotions_per_month : 0;                          // null = ilimitadas
  const unlimited = isBiz && (limit === null || limit === undefined);
  const left = unlimited ? Infinity : Math.max(0, (limit || 0) - usedThisMonth);
  const canCreate = !ctx.suspended && isBiz && left > 0;

  let quota;
  if (!isBiz) quota = 'Necesitas un plan de aliado (Huellita de Plata u Oro) para publicar promociones. Por ahora los planes los asigna un administrador: la contratación y los cobros todavía no están habilitados.';
  else if (unlimited) quota = 'Tu plan permite promociones ilimitadas.';
  else quota = 'Tu plan permite ' + limit + (limit === 1 ? ' promoción nueva al mes' : ' promociones nuevas al mes') + '. Este mes llevas ' + usedThisMonth + (left > 0 ? ' (te queda ' + left + ').' : ' y ya no te quedan.');

  /* ---- Formulario (alta y edición) ---- */
  const f = {
    title: el('input', { type: 'text', maxlength: 100, required: true, autocomplete: 'off' }),
    description: el('textarea', { rows: 2, maxlength: 500 }),
    starts: el('input', { type: 'date', required: true, min: today }),
    ends: el('input', { type: 'date', required: true, min: today })
  };
  let editing = null;
  const save = el('button', { class: 'btn coral sm', type: 'submit', text: 'Publicar promoción' });
  const cancel = el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar' });
  const form = el('form', { novalidate: true, hidden: true, class: 'recform' },
    el('label', {}, 'Título de la promoción', f.title),
    el('label', {}, 'Detalle (opcional)', f.description, el('small', { text: 'Condiciones, horarios, productos incluidos… (hasta 500 caracteres). No pidas pagos ni datos personales aquí.' })),
    el('div', { class: 'fgrid' }, el('label', {}, 'Empieza', f.starts), el('label', {}, 'Termina', f.ends)),
    box, el('div', { class: 'row' }, save, cancel));
  const addBtn = el('button', { class: 'btn coral sm', type: 'button', text: '＋ Nueva promoción', disabled: !canCreate, onclick: () => open(null) });

  function open(p) {
    editing = p; UI.msg(box, null);
    f.title.value = p ? p.title : ''; f.description.value = p && p.description ? p.description : '';
    f.starts.value = p ? p.starts_on : today; f.ends.value = p ? p.ends_on : UI.addDays(today, 30);
    f.starts.min = p ? '' : today; f.ends.min = '';
    save.textContent = p ? 'Guardar cambios' : 'Publicar promoción';
    form.hidden = false; addBtn.hidden = true; f.title.focus();
  }
  cancel.addEventListener('click', () => { form.hidden = true; editing = null; addBtn.hidden = false; UI.msg(box, null); });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const title = f.title.value.trim(), description = f.description.value.trim() || null, starts_on = f.starts.value, ends_on = f.ends.value;
    let err = null;
    if (title.length < 3 || title.length > 100) err = 'El título debe tener entre 3 y 100 caracteres.';
    else if (description && description.length > 500) err = 'El detalle admite hasta 500 caracteres.';
    else if (!DATE_RE.test(starts_on) || !DATE_RE.test(ends_on)) err = 'Elige la fecha de inicio y la de término.';
    else if (ends_on < starts_on) err = 'La fecha de término no puede ser anterior a la de inicio.';
    else if (ends_on > UI.addDays(starts_on, 366)) err = 'Una promoción puede durar como máximo un año.';
    else if (ends_on < today) err = 'La fecha de término ya pasó.';
    if (err) { UI.msg(box, 'err', err); return; }
    UI.msg(box, null); UI.busy(save, true, 'Guardando…');
    try {
      if (editing) {
        const r = await TP.rest('/business_promotions', { method: 'PATCH', query: 'id=eq.' + editing.id, body: { title, description, starts_on, ends_on }, prefer: 'return=representation' });
        if (!Array.isArray(r) || !r.length) throw P.notSaved();
      } else {
        await TP.rest('/business_promotions', { method: 'POST', body: { business_id: biz.id, title, description, starts_on, ends_on, is_active: true }, prefer: 'return=minimal' });
      }
      const wasEdit = !!editing;
      await render(host, ctx, wasEdit ? 'Cambios guardados.' : 'Promoción publicada.');
    } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); UI.busy(save, false); }
  });

  /* ---- Lista ---- */
  const list = el('ul', { class: 'recs', 'aria-live': 'polite' });
  const listMsg = el('div', { class: 'msg', hidden: true });
  async function toggle(p) {
    try {
      const r = await TP.rest('/business_promotions', { method: 'PATCH', query: 'id=eq.' + p.id, body: { is_active: !p.is_active }, prefer: 'return=representation' });
      if (!Array.isArray(r) || !r.length) throw P.notSaved();
      await render(host, ctx, p.is_active ? 'Promoción pausada: ya no se muestra.' : 'Promoción activada.');
    } catch (ex) { UI.msg(listMsg, 'err', TP.errorMessage(ex)); }
  }
  function ask(p, actions) {
    actions.replaceChildren(el('span', { class: 'mut', text: '¿Eliminar esta promoción?' }),
      el('button', { class: 'btn coral sm', type: 'button', text: 'Sí, eliminar', onclick: async () => {
        try {
          const r = await TP.rest('/business_promotions', { method: 'DELETE', query: 'id=eq.' + p.id, prefer: 'return=representation' });
          if (!Array.isArray(r) || !r.length) throw P.notSaved();
          await render(host, ctx, 'Promoción eliminada.');
        } catch (ex) { UI.msg(listMsg, 'err', TP.errorMessage(ex)); paint(); }
      } }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: paint }));
  }
  function paint() {
    list.replaceChildren();
    if (!promos.length) { list.append(el('li', { class: 'empty-li', text: 'Todavía no has publicado promociones.' })); return; }
    promos.forEach(p => {
      const [label, cls] = statusOf(p, today);
      const actions = el('div', { class: 'row' },
        el('button', { class: 'btn ghost sm', type: 'button', text: 'Editar', disabled: ctx.suspended, onclick: () => open(p) }),
        el('button', { class: 'btn ghost sm', type: 'button', text: p.is_active ? 'Pausar' : 'Activar', disabled: ctx.suspended, onclick: () => toggle(p) }),
        el('button', { class: 'btn ghost sm', type: 'button', text: 'Eliminar', disabled: ctx.suspended, onclick: () => ask(p, actions) }));
      list.append(el('li', {},
        el('div', { class: 'recbody' }, el('b', { text: p.title }), ' ', el('span', { class: 'badge ' + cls, text: label }),
          p.description ? el('div', { text: p.description }) : null,
          el('small', { text: 'Del ' + UI.dateEs(p.starts_on) + ' al ' + UI.dateEs(p.ends_on) })),
        actions));
    });
  }
  paint();

  const approved = biz.status === 'approved';
  UI.put(host,
    el('h3', { text: '🏷️ Promociones' }),
    el('p', { class: 'mut', text: 'Anuncia ofertas o servicios destacados en la ficha de tu negocio. Se muestran mientras estén activas y dentro de sus fechas.' }),
    el('p', { class: isBiz ? 'note' : 'stage', text: quota }),
    approved ? null : el('p', { class: 'note', text: 'Tu ficha todavía no está aprobada: puedes dejar listas tus promociones, pero no se verán en el directorio hasta que se apruebe.' }),
    list, listMsg, el('div', { class: 'row' }, addBtn), form);
  if (keepMsg) UI.msg(listMsg, 'ok', keepMsg);
}

MODS.promos = { render };
})();
