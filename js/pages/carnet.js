/*
  Carnet digital (Etapa 4): vacunas, desparasitación y citas/consultas por mascota.
  Los límites del plan (cuántas mascotas con carnet) los aplica el SERVIDOR; aquí solo se muestran avisos claros.
  Los recordatorios de próximas fechas y citas aparecen en Notificaciones (Etapa 8, dentro de la plataforma; todavía no por correo ni WhatsApp).
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, P = window.TPPets;
if (!TP || !UI || !P) return;
const $ = id => document.getElementById(id), el = UI.el;
const MX_OFFSET = '-06:00';                                   // Ciudad de México usa UTC-6 todo el año desde 2022
let me = null, pets = [], current = null, plan = null, suspended = false, canAdd = false;
const sections = [];

// ---------- Utilidades de fecha ----------
function localInputFromIso(iso) {                             // ISO → 'AAAA-MM-DDTHH:mm' en hora de Ciudad de México
  const d = new Date(iso); if (isNaN(d)) return '';
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d).map(p => [p.type, p.value]));
  return parts.year + '-' + parts.month + '-' + parts.day + 'T' + parts.hour + ':' + parts.minute;
}
const isoFromLocalInput = v => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v) ? new Date(v + ':00' + MX_OFFSET).toISOString() : null;

// ---------- Sección genérica (lista + formulario) ----------
function makeSection(cfg, host) {
  const state = { petId: null, rows: [], editing: null };
  const id = n => cfg.key + '-' + n;
  const msg = el('div', { class: 'msg', hidden: true, id: id('msg') });
  const list = el('ul', { class: 'recs', 'aria-live': 'polite' });
  const addBtn = el('button', { class: 'btn coral sm', type: 'button', text: '＋ ' + cfg.addLabel, onclick: () => openForm(null) });
  const note = el('p', { class: 'note', hidden: true });
  const fields = {};
  const form = el('form', { novalidate: true, hidden: true, class: 'recform' });
  const fieldsBox = el('div', { class: 'fgrid' });
  cfg.fields.forEach(f => {
    let input;
    if (f.type === 'select') input = el('select', { id: id(f.name) }, f.options.map(([v, l]) => el('option', { value: v, text: l })));
    else if (f.type === 'textarea') input = el('textarea', { id: id(f.name), rows: 2, maxlength: f.max });
    else input = el('input', { id: id(f.name), type: f.type === 'datetime' ? 'datetime-local' : f.type === 'date' ? 'date' : 'text', maxlength: f.max, min: f.type === 'date' ? '1990-01-01' : null });
    fields[f.name] = input;
    fieldsBox.append(el('label', { class: f.type === 'textarea' ? 'wide' : '' }, f.label + (f.required ? '' : ' (opcional)'), input));
  });
  const saveBtn = el('button', { class: 'btn coral sm', type: 'submit', text: 'Guardar' });
  const cancelBtn = el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: closeForm });
  form.append(fieldsBox, el('div', { class: 'row' }, saveBtn, cancelBtn));
  host.replaceChildren(el('h3', { text: cfg.title }), el('p', { class: 'mut', text: cfg.hint }), list, note, msg, el('div', { class: 'row' }, addBtn), form);

  function closeForm() { form.hidden = true; state.editing = null; addBtn.hidden = !canAdd; }
  function openForm(row) {
    state.editing = row; UI.msg(msg, null);
    cfg.fields.forEach(f => {
      const v = row ? row[f.name] : (f.def !== undefined ? f.def : '');
      fields[f.name].value = row && f.type === 'datetime' ? localInputFromIso(v) : (v == null ? '' : v);
    });
    form.hidden = false; addBtn.hidden = true;
    const first = form.querySelector('input,select,textarea'); if (first) first.focus();
  }
  function read() {
    const values = {}, today = UI.todayLocal();
    for (const f of cfg.fields) {
      const raw = fields[f.name].value.trim();
      if (!raw) { if (f.required) return { err: 'Completa «' + f.label + '».' }; values[f.name] = null; continue; }
      if (f.type === 'select') { if (!f.options.some(o => o[0] === raw)) return { err: 'Elige un valor válido en «' + f.label + '».' }; values[f.name] = raw; }
      else if (f.type === 'date') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(raw) || raw < '1990-01-01') return { err: 'La fecha de «' + f.label + '» no es válida.' };
        if (!f.future && raw > today) return { err: '«' + f.label + '» no puede estar en el futuro.' };
        values[f.name] = raw;
      } else if (f.type === 'datetime') {
        const iso = isoFromLocalInput(raw); if (!iso) return { err: 'La fecha y hora de «' + f.label + '» no son válidas.' };
        values[f.name] = iso;
      } else {
        if (raw.length > f.max) return { err: '«' + f.label + '» admite hasta ' + f.max + ' caracteres.' };
        values[f.name] = raw;
      }
    }
    const e2 = cfg.validate && cfg.validate(values);
    return e2 ? { err: e2 } : { values };
  }
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const { values, err } = read();
    if (err) { UI.msg(msg, 'err', err); return; }
    UI.msg(msg, null); UI.busy(saveBtn, true, 'Guardando…');
    try {
      if (state.editing) {
        const r = await TP.rest('/' + cfg.table, { method: 'PATCH', query: 'id=eq.' + state.editing.id, body: values, prefer: 'return=representation' });
        if (!Array.isArray(r) || !r.length) throw P.notSaved();
      } else {
        await TP.rest('/' + cfg.table, { method: 'POST', body: Object.assign({ pet_id: state.petId }, values), prefer: 'return=minimal' });
      }
      const wasEdit = !!state.editing;
      closeForm(); await load(state.petId);
      UI.msg(msg, 'ok', wasEdit ? 'Cambios guardados.' : 'Registro agregado.');
    } catch (ex) { UI.msg(msg, 'err', TP.errorMessage(ex)); }
    finally { UI.busy(saveBtn, false); }
  });

  function renderRows() {
    list.replaceChildren();
    if (!state.rows.length) { list.append(el('li', { class: 'empty-li', text: cfg.empty })); return; }
    state.rows.forEach(row => {
      const actions = el('div', { class: 'row' });
      actions.append(
        el('button', { class: 'btn ghost sm', type: 'button', text: 'Editar', disabled: suspended, onclick: () => openForm(row) }),
        el('button', { class: 'btn ghost sm', type: 'button', text: 'Eliminar', disabled: suspended, onclick: () => ask(row, actions) }));
      list.append(el('li', {}, el('div', { class: 'recbody' }, cfg.summary(row)), actions));
    });
  }
  function ask(row, actions) {
    actions.replaceChildren(el('span', { class: 'mut', text: '¿Eliminar este registro?' }),
      el('button', { class: 'btn coral sm', type: 'button', text: 'Sí, eliminar', onclick: async () => {
        try {
          const r = await TP.rest('/' + cfg.table, { method: 'DELETE', query: 'id=eq.' + row.id, prefer: 'return=representation' });
          if (!Array.isArray(r) || !r.length) throw P.notSaved();
          await load(state.petId); UI.msg(msg, 'ok', 'Registro eliminado.');
        } catch (ex) { UI.msg(msg, 'err', TP.errorMessage(ex)); renderRows(); }
      } }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: renderRows }));
  }
  async function load(petId) {
    state.petId = petId;
    state.rows = await TP.rest('/' + cfg.table, { query: 'select=' + cfg.select + '&pet_id=eq.' + petId + '&order=' + cfg.order + '&limit=200' });
    renderRows();
  }
  function refreshAccess() {
    addBtn.hidden = !canAdd || !form.hidden;
    note.hidden = canAdd || suspended;
    note.textContent = canAdd ? '' : 'Tu plan actual no permite agregar registros al carnet. Puedes consultar y editar los que ya existan.';
    renderRows();
  }
  return { load, refreshAccess, reset() { closeForm(); UI.msg(msg, null); } };
}

// ---------- Definición de las tres secciones ----------
const line = t => el('div', { class: 'mut', text: t });
const dueLine = d => {
  const late = d < UI.todayLocal();
  return el('div', { class: 'mut' }, 'Próxima: ' + UI.dateEs(d) + ' ', late ? el('span', { class: 'badge warn', text: 'Vencida' }) : null);
};
const KIND_DEW = { interna: 'Interna', externa: 'Externa', ambas: 'Interna y externa' };
const KIND_APPT = { consulta: 'Consulta', vacunacion: 'Vacunación', desparasitacion: 'Desparasitación', estetica: 'Estética', otra: 'Otra' };
const STATUS = { programada: 'Programada', realizada: 'Realizada', cancelada: 'Cancelada' };
const opts = o => Object.entries(o);
const nextAfter = v => (v.next_due_on && v.applied_on && v.next_due_on < v.applied_on) ? 'La próxima fecha no puede ser anterior a la fecha de aplicación.' : null;

const DEFS = [
  { key: 'vac', host: 'sec-vac', table: 'pet_vaccinations', title: '💉 Vacunas', addLabel: 'Agregar vacuna', empty: 'Sin vacunas registradas.',
    hint: 'Fecha de cada vacuna y la próxima fecha recomendada.',
    select: 'id,vaccine_name,applied_on,next_due_on,veterinarian,notes', order: 'applied_on.desc,created_at.desc',
    fields: [
      { name: 'vaccine_name', label: 'Vacuna', type: 'text', required: true, max: 100 },
      { name: 'applied_on', label: 'Fecha de aplicación', type: 'date', required: true },
      { name: 'next_due_on', label: 'Próxima fecha recomendada', type: 'date', future: true },
      { name: 'veterinarian', label: 'Veterinario o clínica', type: 'text', max: 100 },
      { name: 'notes', label: 'Notas', type: 'textarea', max: 1000 }],
    validate: nextAfter,
    summary: r => [el('b', { text: r.vaccine_name }), line('Aplicada: ' + UI.dateEs(r.applied_on)), r.next_due_on && dueLine(r.next_due_on),
      r.veterinarian && line('Veterinario: ' + r.veterinarian), r.notes && line(r.notes)] },
  { key: 'des', host: 'sec-des', table: 'pet_deworming', title: '🪱 Desparasitación', addLabel: 'Agregar desparasitación', empty: 'Sin desparasitaciones registradas.',
    hint: 'Historial de desparasitación interna y externa.',
    select: 'id,product_name,kind,applied_on,next_due_on,notes', order: 'applied_on.desc,created_at.desc',
    fields: [
      { name: 'product_name', label: 'Producto', type: 'text', required: true, max: 100 },
      { name: 'kind', label: 'Tipo', type: 'select', required: true, options: opts(KIND_DEW), def: 'interna' },
      { name: 'applied_on', label: 'Fecha de aplicación', type: 'date', required: true },
      { name: 'next_due_on', label: 'Próxima fecha recomendada', type: 'date', future: true },
      { name: 'notes', label: 'Notas', type: 'textarea', max: 1000 }],
    validate: nextAfter,
    summary: r => [el('b', { text: r.product_name }), line(KIND_DEW[r.kind] || r.kind), line('Aplicada: ' + UI.dateEs(r.applied_on)), r.next_due_on && dueLine(r.next_due_on), r.notes && line(r.notes)] },
  { key: 'cit', host: 'sec-cit', table: 'pet_appointments', title: '🩺 Citas y consultas', addLabel: 'Agregar cita o consulta', empty: 'Sin citas ni consultas registradas.',
    hint: 'Citas por venir y consultas realizadas (cambia el estado a «Realizada» cuando ocurra).',
    select: 'id,kind,scheduled_at,status,clinic,reason,notes', order: 'scheduled_at.desc',
    fields: [
      { name: 'kind', label: 'Tipo', type: 'select', required: true, options: opts(KIND_APPT), def: 'consulta' },
      { name: 'scheduled_at', label: 'Fecha y hora (hora de Ciudad de México)', type: 'datetime', required: true },
      { name: 'status', label: 'Estado', type: 'select', required: true, options: opts(STATUS), def: 'programada' },
      { name: 'clinic', label: 'Clínica o veterinario', type: 'text', max: 120 },
      { name: 'reason', label: 'Motivo', type: 'text', max: 300 },
      { name: 'notes', label: 'Notas', type: 'textarea', max: 1000 }],
    summary: r => [el('b', { text: (KIND_APPT[r.kind] || r.kind) + ' · ' + UI.dateTimeEs(r.scheduled_at) }), ' ',
      el('span', { class: 'badge' + (r.status === 'cancelada' ? ' mute' : r.status === 'realizada' ? ' ok' : ''), text: STATUS[r.status] || r.status }),
      r.clinic && line(r.clinic), r.reason && line('Motivo: ' + r.reason), r.notes && line(r.notes)] }
];

// ---------- Mascota seleccionada ----------
function planNote() {
  const lim = P.healthLimit(plan), name = plan ? plan.name : 'Huellita Básica';
  const box = $('c-plan');
  box.textContent = lim === 0 ? 'Tu plan (' + name + ') no incluye el carnet de salud digital: se incluye desde Huellita Pro (2 mascotas) y Huellita VIP (ilimitado). Todavía no hay pagos en línea: puedes pedir un plan en Mi suscripción y el equipo lo activa a mano, sin cargos.'
    : lim === Infinity ? 'Tu plan (' + name + ') incluye carnet de salud para todas tus mascotas.'
    : 'Tu plan (' + name + ') permite carnet de salud para ' + lim + ' mascota' + (lim === 1 ? '' : 's') + '. Si ya llegaste al límite, el servidor te lo avisará al agregar un registro.';
}
async function showPet(p) {
  current = p;
  try { history.replaceState(null, '', 'carnet.html?pet=' + p.id); } catch { /* */ }
  sections.forEach(s => s.reset());
  UI.msg($('msg-global'), null);
  try { await Promise.all(sections.map(s => s.load(p.id))); }
  catch (ex) { UI.msg($('msg-global'), 'err', 'No se pudo cargar el carnet. ' + TP.errorMessage(ex)); }
  if (window.TPPlaca) window.TPPlaca.mount($('sec-qr'), { pet: p, plan, me, suspended });
}

(async () => {
  await TP.ready;
  try { me = await TP.me(); } catch { return; }
  if (!me || me.accountType !== 'owner' || !$('c-mascota')) return;
  suspended = !!me.suspended;
  try { [pets, plan] = await Promise.all([P.listPets(), P.plan()]); }
  catch (ex) { UI.msg($('msg-global'), 'err', 'No se pudieron cargar tus mascotas. ' + TP.errorMessage(ex)); return; }
  canAdd = P.healthLimit(plan) !== 0 && !suspended;
  planNote();
  if (!pets.length) { $('c-vacio').hidden = false; $('c-selector').hidden = true; return; }
  DEFS.forEach(d => sections.push(makeSection(d, $(d.host))));
  sections.forEach(s => s.refreshAccess());
  const sel = $('c-mascota');
  pets.forEach(p => sel.append(el('option', { value: p.id, text: p.name + ' (' + (P.SPECIES[p.species] || '') + ')' })));
  const want = new URLSearchParams(location.search).get('pet');
  const start = pets.find(p => p.id === want) || pets[0];
  sel.value = start.id;
  sel.addEventListener('change', () => { const p = pets.find(x => x.id === sel.value); if (p) showPet(p); });
  $('c-contenido').hidden = false;
  await showPet(start);
})();
})();
