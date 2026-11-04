/*
  Placa QR (Etapa 4): enlace público por mascota. Solo se muestra lo que la persona decide mostrar.
  Crear la placa requiere un plan con QR (Huellita VIP): lo exige el servidor. Una placa ya creada se conserva si el plan vence.
  Nunca se muestran dirección, correo ni datos del dueño: solo los campos de este formulario.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, P = window.TPPets, MEDIA = window.TPMedia, QR = window.TPQR;
if (!TP || !UI || !P || !MEDIA || !QR) return;
const el = UI.el;
const TOKEN_RE = /^[0-9a-f]{64}$/;
const PHONE_RE = /^[0-9+() .-]{7,20}$/;
const COLS = 'id,pet_id,public_token,is_active,show_name,show_breed,show_photo,public_message,contact_name,contact_phone,show_phone,qr_photo_path';
let seq = 0;                                                  // descarta respuestas de una mascota anterior si la persona cambió de selección

async function mount(host, ctx) {
  const my = ++seq, { pet, plan, me, suspended } = ctx;
  host.replaceChildren(el('h3', { text: '🏷️ Placa QR de ' + pet.name }), el('p', { class: 'mut', text: 'Cargando…' }));
  let row;
  try {
    const r = await TP.rest('/pet_qr_profiles', { query: 'select=' + COLS + '&pet_id=eq.' + pet.id + '&limit=1' });
    row = r[0] || null;
  } catch (ex) { if (my === seq) host.replaceChildren(el('h3', { text: '🏷️ Placa QR de ' + pet.name }), el('div', { class: 'msg err', role: 'alert', text: 'No se pudo cargar la placa. ' + TP.errorMessage(ex) })); return; }
  if (my !== seq) return;
  render(host, { pet, plan, me, suspended }, row);
}

function intro() {
  return el('p', { class: 'mut', text: 'Imprime este código y ponlo en el collar. Quien lo escanee verá solo lo que tú elijas aquí. Nunca se muestra tu dirección ni tu correo.' });
}

function render(host, ctx, row) {
  const { pet, plan, me, suspended } = ctx;
  const title = el('h3', { text: '🏷️ Placa QR de ' + pet.name });
  const msg = el('div', { class: 'msg', hidden: true });
  const hasPlan = !!(plan && plan.qr_enabled);

  if (!row) {                                                 // todavía no existe la placa
    if (!hasPlan) {
      host.replaceChildren(title, intro(), el('p', { class: 'note' }, 'La placa QR se incluye en ', el('b', { text: 'Huellita VIP' }),
        '. Los planes de pago aún no se contratan en línea; por ahora los asigna un administrador. ', el('a', { href: 'planes.html', text: 'Ver planes' }), '.'));
      return;
    }
    const btn = el('button', { class: 'btn coral sm', type: 'button', text: 'Crear placa QR', disabled: suspended });
    btn.addEventListener('click', async () => {
      UI.busy(btn, true, 'Creando…'); UI.msg(msg, null);
      try {
        const r = await TP.rest('/pet_qr_profiles', { method: 'POST', body: { pet_id: pet.id }, prefer: 'return=representation' });
        const created = Array.isArray(r) ? r[0] : r;
        render(host, ctx, created);
      } catch (ex) { UI.msg(msg, 'err', TP.errorMessage(ex)); UI.busy(btn, false); }
    });
    host.replaceChildren(title, intro(), msg, el('div', { class: 'row' }, btn));
    return;
  }

  // ---- Existe la placa ----
  const f = {
    active: el('input', { type: 'checkbox', checked: !!row.is_active }),
    name: el('input', { type: 'checkbox', checked: !!row.show_name }),
    breed: el('input', { type: 'checkbox', checked: !!row.show_breed }),
    photo: el('input', { type: 'checkbox', checked: !!row.show_photo }),
    file: el('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp' }),
    removePhoto: el('input', { type: 'checkbox' }),
    message: el('textarea', { rows: 3, maxlength: 300 }),
    contact: el('input', { type: 'text', maxlength: 80, autocomplete: 'off' }),
    phone: el('input', { type: 'tel', maxlength: 20, autocomplete: 'off' }),
    showPhone: el('input', { type: 'checkbox', checked: !!row.show_phone })
  };
  f.message.value = row.public_message || ''; f.contact.value = row.contact_name || ''; f.phone.value = row.contact_phone || '';
  const ck = (input, text) => el('label', { class: 'ck' }, input, ' ' + text);

  const photoUrl = row.qr_photo_path ? TP.storage.publicUrl('qr-photos', row.qr_photo_path) : null;
  const photoBlock = el('div', { class: 'photoblock' },
    photoUrl ? el('img', { class: 'pic small', src: photoUrl, alt: 'Foto pública de la placa de ' + pet.name, loading: 'lazy' }) : el('p', { class: 'mut', text: 'Todavía no hay foto pública.' }),
    el('label', {}, 'Foto que se mostrará (opcional)', f.file, el('small', { text: 'Esta foto será PÚBLICA: cualquier persona con el enlace de la placa podrá verla. Es una copia aparte de la foto de la ficha, que sigue siendo privada.' })),
    row.qr_photo_path ? el('label', { class: 'ck' }, f.removePhoto, ' Quitar la foto pública actual (si no subes otra)') : null);

  const form = el('form', { novalidate: true, class: 'recform' },
    ck(f.active, 'Placa activa (si la desactivas, el enlace deja de mostrar datos)'),
    el('h4', { text: 'Qué verá quien escanee' }),
    ck(f.name, 'Mostrar el nombre'), ck(f.breed, 'Mostrar la raza'), ck(f.photo, 'Mostrar la foto pública (la de abajo)'), photoBlock,
    el('label', {}, 'Mensaje para quien la encuentre (opcional)', f.message),
    el('h4', { text: 'Contacto' }),
    el('div', { class: 'fgrid' }, el('label', {}, 'Nombre de contacto (opcional)', f.contact), el('label', {}, 'Teléfono de contacto (opcional)', f.phone)),
    ck(f.showPhone, 'Mostrar el teléfono públicamente'),
    el('p', { class: 'note', text: '⚠️ Si activas «Mostrar el teléfono», cualquier persona que escanee el QR o tenga el enlace verá ese número. Si no lo activas, no se muestra ningún dato de contacto.' }),
    msg);
  const save = el('button', { class: 'btn coral sm', type: 'submit', text: 'Guardar placa', disabled: suspended });
  form.append(el('div', { class: 'row' }, save));
  if (suspended) form.querySelectorAll('input,textarea').forEach(x => { x.disabled = true; });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const body = {
      is_active: f.active.checked, show_name: f.name.checked, show_breed: f.breed.checked, show_photo: f.photo.checked,
      public_message: f.message.value.trim() || null, contact_name: f.contact.value.trim() || null,
      contact_phone: f.phone.value.trim() || null, show_phone: f.showPhone.checked
    };
    const file = f.file.files[0] || null, removePhoto = f.removePhoto.checked && !file;
    let err = null;
    if (body.public_message && body.public_message.length > 300) err = 'El mensaje admite hasta 300 caracteres.';
    else if (body.contact_name && body.contact_name.length > 80) err = 'El nombre de contacto admite hasta 80 caracteres.';
    else if (body.contact_phone && !PHONE_RE.test(body.contact_phone)) err = 'El teléfono solo puede llevar números, espacios, + ( ) . - (7 a 20 caracteres).';
    else if (body.show_phone && !body.contact_phone) err = 'Para mostrar el teléfono, escríbelo primero.';
    else if (body.show_photo && removePhoto) err = 'Quitaste la foto pública: desmarca «Mostrar la foto pública» o sube otra.';
    else if (body.show_photo && !file && !row.qr_photo_path) err = 'Para mostrar la foto, sube primero la que quieres hacer pública.';
    if (err) { UI.msg(msg, 'err', err); return; }
    UI.msg(msg, null); UI.busy(save, true, 'Guardando…');
    let uploaded = null;
    try {
      if (file) {
        let blob;
        try { blob = await MEDIA.prepareImage(file, { maxSide: 800, quality: 0.8 }); }
        catch (ex) { if (ex instanceof MEDIA.MediaError) { UI.msg(msg, 'err', ex.message); return; } throw ex; }
        uploaded = me.user.id + '/' + P.uuid() + '.jpg';
        await TP.storage.upload('qr-photos', uploaded, blob);
        body.qr_photo_path = uploaded;
      } else if (removePhoto) body.qr_photo_path = null;
      const r = await TP.rest('/pet_qr_profiles', { method: 'PATCH', query: 'id=eq.' + row.id, body, prefer: 'return=representation' });
      if (!Array.isArray(r) || !r.length) throw P.notSaved();
      if ('qr_photo_path' in body && row.qr_photo_path && row.qr_photo_path !== body.qr_photo_path) TP.storage.remove('qr-photos', [row.qr_photo_path]).catch(() => {});
      render(host, ctx, Object.assign({}, row, r[0]));
      const all = host.querySelectorAll('.msg'), m2 = all[all.length - 1]; if (m2) UI.msg(m2, 'ok', 'Placa guardada.');   // el último aviso es el del formulario
    } catch (ex) {
      if (uploaded) TP.storage.remove('qr-photos', [uploaded]).catch(() => {});
      UI.msg(msg, 'err', TP.errorMessage(ex)); UI.busy(save, false);
    }
  });

  host.replaceChildren(title, intro(), qrBlock(row, pet, ctx, host), form);
}

function slug(s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase().slice(0, 30) || 'mascota'; }
function download(blob, name) {
  const u = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = u; a.download = name; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 2000);
}

function qrBlock(row, pet, ctx, host) {
  const box = el('div', { class: 'qrbox' });
  if (!TOKEN_RE.test(row.public_token || '')) { box.append(el('p', { class: 'msg err', text: 'La placa tiene un enlace no válido. Genera uno nuevo.' })); return box; }
  const url = location.origin + '/qr.html?t=' + row.public_token;
  let qr;
  try { qr = QR.encode(url, 'M'); } catch { box.append(el('p', { class: 'msg err', text: 'No se pudo generar el código QR.' })); return box; }
  const msg = el('div', { class: 'msg', hidden: true });
  const actions = el('div', { class: 'row' });
  const link = el('input', { type: 'text', readonly: true, value: url, 'aria-label': 'Enlace público de la placa' });
  const regen = el('button', { class: 'btn ghost sm', type: 'button', text: 'Generar enlace nuevo', disabled: ctx.suspended });
  regen.addEventListener('click', () => {
    regen.replaceWith(el('span', { class: 'mut', text: 'El enlace actual y los QR ya impresos dejarán de funcionar. ¿Continuar?' }),
      el('button', { class: 'btn coral sm', type: 'button', text: 'Sí, generar nuevo', onclick: async ev => {
        UI.busy(ev.target, true, 'Generando…');
        try {
          await TP.rpc('regenerate_pet_qr_token', { p_pet_id: pet.id });
          const r = await TP.rest('/pet_qr_profiles', { query: 'select=' + COLS + '&id=eq.' + row.id + '&limit=1' });
          render(host, ctx, r[0] || row);
          const m2 = host.querySelector('.msg'); if (m2) UI.msg(m2, 'ok', 'Enlace nuevo generado. Vuelve a descargar e imprimir tu QR.');
        } catch (ex) { UI.msg(msg, 'err', TP.errorMessage(ex)); render(host, ctx, row); }
      } }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Cancelar', onclick: () => render(host, ctx, row) }));
  });
  actions.append(
    el('button', { class: 'btn coral sm', type: 'button', text: 'Descargar PNG', onclick: async () => {
      try { download(await QR.toPngBlob(qr, 12), 'placa-qr-' + slug(pet.name) + '.png'); } catch { UI.msg(msg, 'err', 'No se pudo crear la imagen.'); } } }),
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Descargar SVG', onclick: () =>
      download(new Blob([QR.toSvg(qr, { label: 'Placa QR de ' + pet.name })], { type: 'image/svg+xml' }), 'placa-qr-' + slug(pet.name) + '.svg') }),
    el('button', { class: 'btn ghost sm', type: 'button', text: 'Copiar enlace', onclick: async () => {
      try { await navigator.clipboard.writeText(url); UI.msg(msg, 'ok', 'Enlace copiado.'); } catch { link.select(); UI.msg(msg, 'info', 'Selecciona el enlace y cópialo manualmente.'); } } }),
    el('a', { class: 'btn ghost sm', href: url, target: '_blank', rel: 'noopener noreferrer', text: 'Probar enlace' }), regen);
  const local = /^(localhost|127\.|\[::1\])/.test(location.hostname);
  box.append(
    el('div', { class: 'qrpic' }, QR.toSvgElement(qr, { label: 'Código QR de la placa de ' + pet.name })),
    el('div', { class: 'qrinfo' },
      el('p', { class: 'mut', text: row.is_active ? 'La placa está activa.' : 'La placa está desactivada: el enlace no muestra datos.' }),
      el('label', {}, 'Enlace público', link),
      local ? el('p', { class: 'msg info', text: 'Estás usando el sitio desde tu computadora (' + location.host + '). Este QR solo funcionaría aquí: descárgalo desde la dirección pública del sitio antes de imprimirlo.' }) : null,
      el('p', { class: 'note', text: 'Si algún día cambia la dirección del sitio, hay que descargar e imprimir el QR de nuevo.' }),
      actions, msg));
  return box;
}

window.TPPlaca = Object.freeze({ mount });
})();
