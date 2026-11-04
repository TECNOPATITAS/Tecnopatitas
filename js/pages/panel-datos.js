/*
  Panel de aliados · Datos comerciales (Etapa 5): alta de un establecimiento, edición y eliminación.
  La seguridad real la dan las políticas RLS y los disparadores del servidor: aquí solo se ayuda a escribir datos válidos.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, B = window.TPBiz;
if (!TP || !UI || !B) return;
const el = UI.el;
const MODS = (window.TPPanelMods = window.TPPanelMods || {});

/* Controles del formulario (sirven para el alta y para la edición) */
function build(v, opts) {
  const c = {
    name: el('input', { type: 'text', maxlength: 100, required: true, autocomplete: 'off', value: v.name || '' }),
    category: el('select', { required: true }, el('option', { value: '', text: 'Selecciona una opción' }),
      Object.entries(B.CATEGORIES).map(([k, t]) => el('option', { value: k, text: t }))),
    description: el('textarea', { rows: 3, maxlength: 1000, value: v.description || '' }),
    address: el('input', { type: 'text', maxlength: 200, autocomplete: 'off', value: v.address || '' }),
    state: el('input', { type: 'text', maxlength: 80, autocomplete: 'off', value: v.state || '' }),
    municipality: el('input', { type: 'text', maxlength: 80, autocomplete: 'off', value: v.municipality || '' }),
    phone: el('input', { type: 'tel', maxlength: 20, inputmode: 'tel', autocomplete: 'off', value: v.phone || '' }),
    maps_query: el('input', { type: 'text', maxlength: 200, autocomplete: 'off', value: v.maps_query || '' }),
    whatsapp: el('input', { type: 'tel', maxlength: 20, inputmode: 'tel', autocomplete: 'off', value: B.waToInput(v.whatsapp_url) })
  };
  c.category.value = v.category || '';
  const waOk = !!(opts.plan && opts.plan.whatsapp_button);
  c.whatsapp.disabled = !waOk;
  const nodes = [
    el('div', { class: 'fgrid' },
      el('label', {}, 'Nombre del establecimiento', c.name),
      el('label', {}, 'Categoría', c.category)),
    el('label', {}, 'Descripción (opcional)', c.description, el('small', { text: 'Qué ofreces, servicios principales… (hasta 1000 caracteres).' })),
    el('label', {}, 'Dirección del local (opcional)', c.address),
    el('div', { class: 'fgrid' },
      el('label', {}, 'Municipio o alcaldía', c.municipality),
      el('label', {}, 'Estado', c.state)),
    el('div', { class: 'fgrid' },
      el('label', {}, 'Teléfono del negocio (opcional)', c.phone, el('small', { text: 'Se muestra en tu ficha con plan Plata u Oro.' })),
      el('label', {}, 'Texto para Google Maps (opcional)', c.maps_query, el('small', { text: 'Si lo dejas vacío se busca por nombre y dirección. Puedes escribir el nombre del lugar tal como aparece en Google Maps.' })))
  ];
  if (opts.withWhatsapp) {
    nodes.push(el('label', {}, 'WhatsApp del negocio (10 dígitos)', c.whatsapp,
      el('small', { text: waOk ? 'Se mostrará un botón directo a WhatsApp en tu ficha. Escribe solo el número, por ejemplo 55 1234 5678.'
                               : 'El botón directo a WhatsApp es un beneficio de Huellita de Oro. Con tu plan actual no se puede activar.' })));
  }
  return { c, nodes, waOk };
}

function read(c, withWhatsapp) {
  const v = {
    name: c.name.value.trim(), category: c.category.value, description: c.description.value.trim() || null,
    address: c.address.value.trim() || null, state: c.state.value.trim() || null, municipality: c.municipality.value.trim() || null,
    phone: c.phone.value.trim() || null, maps_query: c.maps_query.value.trim() || null
  };
  let err = null, wa;
  if (v.name.length < 2 || v.name.length > 100) err = 'Escribe el nombre del establecimiento (entre 2 y 100 caracteres).';
  else if (!B.CATEGORIES[v.category]) err = 'Elige la categoría.';
  else if (v.description && v.description.length > 1000) err = 'La descripción admite hasta 1000 caracteres.';
  else if (v.address && v.address.length > 200) err = 'La dirección admite hasta 200 caracteres.';
  else if (v.state && v.state.length > 80) err = 'El estado admite hasta 80 caracteres.';
  else if (v.municipality && v.municipality.length > 80) err = 'El municipio admite hasta 80 caracteres.';
  else if (v.phone && !B.PHONE_RE.test(v.phone)) err = 'El teléfono solo puede llevar números, espacios, guiones, paréntesis y «+» (de 7 a 20 caracteres).';
  else if (v.maps_query && v.maps_query.length > 200) err = 'El texto para Google Maps admite hasta 200 caracteres.';
  if (!err && withWhatsapp) { wa = B.waFromInput(c.whatsapp.value); if (wa.error) err = wa.error; }
  return { v, err, wa };
}

/* ---- Alta ---- */
function renderCreate(host, ctx, opts) {
  const f = build({}, { plan: ctx.plan, withWhatsapp: false });
  const box = el('div', { class: 'msg', hidden: true });
  const save = el('button', { class: 'btn coral', type: 'submit', text: 'Registrar establecimiento', disabled: ctx.suspended });
  const row = el('div', { class: 'row' }, save, opts && opts.onCancel ? el('button', { class: 'btn ghost', type: 'button', text: 'Cancelar', onclick: opts.onCancel }) : null);
  const form = el('form', { novalidate: true }, ...f.nodes, box, row);
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const { v, err } = read(f.c, false);
    if (err) { UI.msg(box, 'err', err); return; }
    UI.msg(box, null); UI.busy(save, true, 'Registrando…');
    try {
      const r = await TP.rest('/businesses', { method: 'POST', body: v, prefer: 'return=representation' });
      const row0 = Array.isArray(r) ? r[0] : r;
      if (!row0 || !row0.id) throw new TP.TPError('not_saved', 'not_saved', 0);
      ctx.added(row0);
    } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); }
    finally { UI.busy(save, false); }
  });
  UI.put(host,
    el('h3', { text: opts && opts.title || 'Registra tu establecimiento' }),
    el('p', { class: 'mut', text: 'Tu ficha quedará «en revisión» y no aparecerá en el directorio hasta que un administrador la apruebe. Escribe solo datos del negocio (no personales): lo que captures aquí se publica cuando tu ficha sea aprobada.' }),
    ctx.suspended ? el('p', { class: 'note', text: 'Tu cuenta está suspendida: no puedes registrar establecimientos.' }) : null, form);
}

/* ---- Edición ---- */
function renderEdit(host, ctx) {
  const biz = ctx.biz;
  const f = build(biz, { plan: ctx.plan, withWhatsapp: true });
  const box = el('div', { class: 'msg', hidden: true });
  const save = el('button', { class: 'btn coral', type: 'submit', text: 'Guardar cambios', disabled: ctx.suspended });
  const form = el('form', { novalidate: true }, ...f.nodes, box, el('div', { class: 'row' }, save));
  if (ctx.suspended) form.querySelectorAll('input,select,textarea').forEach(x => { x.disabled = true; });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const { v, err, wa } = read(f.c, true);
    if (err) { UI.msg(box, 'err', err); return; }
    const body = Object.assign({}, v);
    const newWa = wa && wa.url ? wa.url : null;
    if (f.waOk && newWa !== (ctx.biz.whatsapp_url || null)) body.whatsapp_url = newWa;      // solo se envía si cambió (el plan lo comprueba el servidor)
    UI.msg(box, null); UI.busy(save, true, 'Guardando…');
    try {
      const r = await TP.rest('/businesses', { method: 'PATCH', query: 'id=eq.' + biz.id, body, prefer: 'return=representation' });
      if (!Array.isArray(r) || !r.length) throw new TP.TPError('not_saved', 'not_saved', 0);
      ctx.updated(r[0]);
      UI.msg(box, 'ok', ctx.biz.status === 'approved' ? 'Cambios guardados. Como tu ficha ya está aprobada, se publican de inmediato.' : 'Cambios guardados.');
    } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); }
    finally { UI.busy(save, false); }
  });

  /* Eliminar establecimiento (pide confirmación) */
  const delHost = el('div', { class: 'recform' });
  const askDelete = () => {
    const msg = el('div', { class: 'msg', hidden: true });
    const yes = el('button', { class: 'btn coral sm', type: 'button', text: 'Sí, eliminar todo', onclick: async () => {
      UI.busy(yes, true, 'Eliminando…');
      try {
        const r = await TP.rest('/businesses', { method: 'DELETE', query: 'id=eq.' + biz.id, prefer: 'return=representation' });
        if (!Array.isArray(r) || !r.length) throw new TP.TPError('not_saved', 'not_saved', 0);
        ctx.removed(biz);
      } catch (ex) { UI.msg(msg, 'err', TP.errorMessage(ex)); UI.busy(yes, false); }
    } });
    delHost.replaceChildren(
      el('p', { class: 'note', text: 'Se borrarán el establecimiento, sus promociones, sus estadísticas y sus imágenes. Esto no se puede deshacer.' }),
      msg, el('div', { class: 'row' }, yes, el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: showDelete })));
  };
  const showDelete = () => delHost.replaceChildren(el('button', { class: 'btn ghost sm', type: 'button', text: 'Eliminar este establecimiento', disabled: ctx.suspended, onclick: askDelete }));
  showDelete();

  UI.put(host, el('h3', { text: '🏪 Datos comerciales' }),
    el('p', { class: 'mut', text: 'Lo que escribas aquí es público cuando tu ficha está aprobada (según tu plan: nombre, categoría, descripción y dirección siempre; teléfono, horario, logotipo, fotos y promociones con plan Plata u Oro; WhatsApp con Oro).' }),
    form, delHost);
}

MODS.datos = { renderCreate, renderEdit };
})();
