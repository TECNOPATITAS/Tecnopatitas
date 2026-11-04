/* Mis mascotas (Etapa 4): fichas con foto, crear / editar / eliminar. La seguridad real la dan las políticas RLS del servidor. */
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, P = window.TPPets, MEDIA = window.TPMedia;
if (!TP || !UI || !P || !MEDIA) return;
const $ = id => document.getElementById(id), el = UI.el;
const MAX_PETS = 30;
let me = null, pets = [], urls = {}, editing = null, suspended = false;

function applyFormState() {
  const off = suspended || (!editing && pets.length >= MAX_PETS);
  document.querySelectorAll('#f-mascota input,#f-mascota select,#f-mascota textarea,#f-mascota button').forEach(x => { x.disabled = off; });
  const lim = $('m-limite');
  lim.hidden = !off;
  lim.textContent = suspended ? 'Tu cuenta está suspendida: puedes consultar tus mascotas, pero no modificarlas.'
    : 'Llegaste al límite de ' + MAX_PETS + ' mascotas por cuenta. Elimina alguna para agregar otra.';
}

function readForm() {
  const v = {
    name: $('m-nombre').value.trim(), species: $('m-especie').value, breed: $('m-raza').value.trim() || null,
    sex: $('m-sexo').value || null, birth_date: $('m-nac').value || null, weight_kg: null,
    description: $('m-desc').value.trim() || null, vet_info: $('m-vet').value.trim() || null
  };
  const w = $('m-peso').value.trim();
  let err = null;
  if (v.name.length < 1 || v.name.length > 60) err = 'Escribe el nombre de tu mascota (hasta 60 caracteres).';
  else if (!P.SPECIES[v.species]) err = 'Elige la especie.';
  else if (v.breed && v.breed.length > 80) err = 'La raza admite hasta 80 caracteres.';
  else if (v.sex && !P.SEX[v.sex]) err = 'El sexo no es válido.';
  else if (v.birth_date && (!/^\d{4}-\d{2}-\d{2}$/.test(v.birth_date) || v.birth_date < '1990-01-01' || v.birth_date > UI.todayLocal())) err = 'La fecha de nacimiento debe estar entre 1990 y hoy.';
  else if (w !== '') {
    const n = Number(w.replace(',', '.'));
    if (!isFinite(n) || n <= 0 || n > 200) err = 'El peso debe ser mayor que 0 y de hasta 200 kg.';
    else v.weight_kg = Math.round(n * 100) / 100;
  }
  if (!err && v.description && v.description.length > 1000) err = 'La descripción admite hasta 1000 caracteres.';
  if (!err && v.vet_info && v.vet_info.length > 2000) err = 'La información veterinaria admite hasta 2000 caracteres.';
  return { v, err };
}

async function changePhoto(pet, blob) {                       // blob = foto nueva; null = quitar la foto
  const old = pet.photo_path;
  let path = null;
  if (blob) { path = me.user.id + '/' + P.uuid() + '.jpg'; await TP.storage.upload('pet-photos', path, blob); }
  try {
    const r = await TP.rest('/pets', { method: 'PATCH', query: 'id=eq.' + pet.id, body: { photo_path: path }, prefer: 'return=representation' });
    if (!Array.isArray(r) || !r.length) throw P.notSaved();
  } catch (ex) { if (path) TP.storage.remove('pet-photos', [path]).catch(() => {}); throw ex; }
  if (old) TP.storage.remove('pet-photos', [old]).catch(() => {});   // limpieza; si falla, solo queda un archivo huérfano
}

async function save(e) {
  e.preventDefault();
  const box = $('msg-form'), btn = $('m-guardar');
  const { v, err } = readForm();
  if (err) { UI.msg(box, 'err', err); return; }
  const file = $('m-foto').files[0] || null, removePhoto = !!editing && $('m-quitar').checked && !file;
  const wasEditing = !!editing;
  UI.msg(box, null); UI.busy(btn, true, 'Guardando…');
  try {
    let blob = null;
    if (file) {
      try { blob = await MEDIA.prepareImage(file, { maxSide: 1600, quality: 0.85 }); }
      catch (ex) { if (ex instanceof MEDIA.MediaError) { UI.msg(box, 'err', ex.message); return; } throw ex; }
    }
    let pet;
    if (editing) {
      const r = await TP.rest('/pets', { method: 'PATCH', query: 'id=eq.' + editing.id, body: v, prefer: 'return=representation' });
      if (!Array.isArray(r) || !r.length) throw P.notSaved();
      pet = r[0];
    } else {
      const r = await TP.rest('/pets', { method: 'POST', body: v, prefer: 'return=representation' });
      pet = Array.isArray(r) ? r[0] : r;
    }
    let note = null;
    if (blob || removePhoto) {
      try { await changePhoto(pet, blob); }
      catch (ex) { note = 'La mascota se guardó, pero la foto no se pudo actualizar. ' + TP.errorMessage(ex); }
    }
    resetForm();
    await render();
    UI.msg(box, note ? 'err' : 'ok', note || (wasEditing ? 'Cambios guardados.' : 'Mascota agregada.'));
  } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); }
  finally { UI.busy(btn, false); applyFormState(); }
}

function resetForm() {
  $('f-mascota').reset(); editing = null;
  $('m-form-title').textContent = 'Agregar mascota';
  $('m-cancelar').hidden = true; $('m-quitar-fila').hidden = true;
  $('m-foto-ayuda').textContent = 'JPG, PNG o WebP. Se reduce de tamaño automáticamente y se eliminan los datos ocultos de la foto (como la ubicación).';
}
function startEdit(p) {
  editing = p;
  $('m-nombre').value = p.name || ''; $('m-especie').value = p.species || ''; $('m-raza').value = p.breed || '';
  $('m-sexo').value = p.sex || ''; $('m-nac').value = p.birth_date || ''; $('m-peso').value = p.weight_kg != null ? String(Number(p.weight_kg)) : '';
  $('m-desc').value = p.description || ''; $('m-vet').value = p.vet_info || ''; $('m-foto').value = ''; $('m-quitar').checked = false;
  $('m-quitar-fila').hidden = !p.photo_path;
  $('m-form-title').textContent = 'Editar a ' + p.name;
  $('m-cancelar').hidden = false;
  UI.msg($('msg-form'), null); applyFormState();
  $('m-form-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('m-nombre').focus();
}

function askDelete(p, actions) {
  actions.replaceChildren(
    el('span', { class: 'mut', text: '¿Eliminar a ' + p.name + '? Se borrará también su carnet y su placa QR. No se puede deshacer.' }),
    el('button', { class: 'btn coral sm', type: 'button', text: 'Sí, eliminar', onclick: () => doDelete(p) }),
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: () => render() }));
}
async function doDelete(p) {
  const box = $('msg-global');
  UI.msg(box, null);
  try {
    let qrPhotos = [];
    try { const q = await TP.rest('/pet_qr_profiles', { query: 'select=qr_photo_path&pet_id=eq.' + p.id }); qrPhotos = q.map(x => x.qr_photo_path).filter(Boolean); } catch { /* sin fotos que limpiar */ }
    const r = await TP.rest('/pets', { method: 'DELETE', query: 'id=eq.' + p.id, prefer: 'return=representation' });
    if (!Array.isArray(r) || !r.length) throw P.notSaved();
    if (p.photo_path) TP.storage.remove('pet-photos', [p.photo_path]).catch(() => {});
    if (qrPhotos.length) TP.storage.remove('qr-photos', qrPhotos).catch(() => {});
    if (editing && editing.id === p.id) resetForm();
    await render();
    UI.msg(box, 'ok', p.name + ' fue eliminada.');
  } catch (ex) { UI.msg(box, 'err', TP.errorMessage(ex)); await render().catch(() => {}); }
}

function card(p) {
  const facts = [P.SPECIES[p.species] || '', p.breed, p.sex && P.SEX[p.sex]].filter(Boolean).join(' · ');
  const age = p.birth_date ? UI.ageEs(p.birth_date) : '';
  const meta = [age && 'Edad: ' + age, p.weight_kg != null && 'Peso: ' + Number(p.weight_kg) + ' kg'].filter(Boolean).join(' · ');
  const actions = el('div', { class: 'row' });
  actions.append(
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Editar', disabled: suspended, onclick: () => startEdit(p) }),
    P.UUID_RE.test(p.id) ? el('a', { class: 'btn sm', href: 'carnet.html?pet=' + p.id, text: 'Carnet y placa QR' }) : null,
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Eliminar', disabled: suspended, onclick: () => askDelete(p, actions) }));
  return el('article', { class: 'card pet' }, P.thumb(p, urls, 'pic'), el('h3', { text: p.name }),
    facts && el('p', { class: 'mut', text: facts }), meta && el('p', { text: meta }), p.description && el('p', { text: p.description }),
    p.vet_info && el('p', { class: 'note' }, el('b', { text: 'Info veterinaria: ' }), p.vet_info), actions);
}

async function render() {
  pets = await P.listPets();
  urls = await P.photoUrls(pets);
  const box = $('m-lista'); box.replaceChildren();
  if (!pets.length) box.append(el('div', { class: 'empty' }, el('span', { text: '🐕' }), el('h3', { text: 'Aún no registraste mascotas' }), el('p', { text: 'Agrega la primera con el formulario de abajo.' })));
  else pets.forEach(p => box.append(card(p)));
  $('m-contador').textContent = pets.length + ' de ' + MAX_PETS + ' mascotas';
  applyFormState();
}

(async () => {
  await TP.ready;
  try { me = await TP.me(); } catch { return; }              // guard.js muestra el error o redirige
  if (!me || me.accountType !== 'owner' || !$('f-mascota')) return;
  suspended = !!me.suspended;
  $('f-mascota').addEventListener('submit', save);
  $('m-cancelar').addEventListener('click', () => { resetForm(); UI.msg($('msg-form'), null); applyFormState(); });
  try { await render(); }
  catch (ex) { UI.msg($('msg-global'), 'err', 'No se pudieron cargar tus mascotas. ' + TP.errorMessage(ex)); }
})();
})();
