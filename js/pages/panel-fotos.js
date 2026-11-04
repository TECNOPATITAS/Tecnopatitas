/*
  Panel de aliados · Logotipo y fotos (Etapa 5).
  Las imágenes se reducen y se recodifican como JPEG en el navegador (se eliminan los datos ocultos, como la ubicación) y se
  suben al bucket público «business-media», carpeta <id de la cuenta>/. El servidor limita 30 archivos de 5 MB por cuenta
  y solo cuentas de aliado pueden subir. Con plan Plata u Oro el directorio muestra el logotipo y hasta 6 fotos.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, B = window.TPBiz, MEDIA = window.TPMedia, P = window.TPPets;
if (!TP || !UI || !B || !MEDIA || !P) return;
const el = UI.el;
const MAX_PHOTOS = 6;
const MODS = (window.TPPanelMods = window.TPPanelMods || {});

function render(host, ctx) {
  const biz = ctx.biz, uid = ctx.me.user.id;
  const box = el('div', { class: 'msg', hidden: true });
  const disabled = ctx.suspended;
  const hasPlan = !!(ctx.plan && ctx.plan.audience === 'business');

  async function patch(body) {
    const r = await TP.rest('/businesses', { method: 'PATCH', query: 'id=eq.' + ctx.biz.id, body, prefer: 'return=representation' });
    if (!Array.isArray(r) || !r.length) throw P.notSaved();
    ctx.updated(r[0]);
    return r[0];
  }
  const cleanup = paths => { const ok = paths.filter(Boolean); if (ok.length) TP.storage.remove('business-media', ok).catch(() => {}); };   // si falla, queda un archivo huérfano sin consecuencias
  async function run(label, fn) {
    UI.msg(box, 'info', label);
    try { await fn(); UI.msg(box, 'ok', 'Listo.'); }
    catch (ex) { UI.msg(box, 'err', ex instanceof MEDIA.MediaError ? ex.message : TP.errorMessage(ex)); }
    render(host, ctx);                                                                // redibuja con los datos nuevos (conserva el mensaje)
    UI.msg(host.querySelector('.msg'), box.className.includes('err') ? 'err' : 'ok', box.textContent);
  }

  async function setLogo(file) {
    const blob = file ? await MEDIA.prepareImage(file, { maxSide: 512, quality: 0.85 }) : null;
    const old = ctx.biz.logo_path;
    let path = null;
    if (blob) { path = uid + '/' + P.uuid() + '.jpg'; await TP.storage.upload('business-media', path, blob); }
    try { await patch({ logo_path: path }); } catch (ex) { cleanup([path]); throw ex; }
    cleanup([old]);
  }
  async function addPhoto(file) {
    const cur = Array.isArray(ctx.biz.photo_paths) ? ctx.biz.photo_paths : [];
    if (cur.length >= MAX_PHOTOS) throw new TP.TPError('too_many', 'Ya tienes ' + MAX_PHOTOS + ' fotos. Quita alguna para agregar otra.', 0);
    const blob = await MEDIA.prepareImage(file, { maxSide: 1280, quality: 0.82 });
    const path = uid + '/' + P.uuid() + '.jpg';
    await TP.storage.upload('business-media', path, blob);
    try { await patch({ photo_paths: cur.concat([path]) }); } catch (ex) { cleanup([path]); throw ex; }
  }
  async function removePhoto(path) {
    const cur = Array.isArray(ctx.biz.photo_paths) ? ctx.biz.photo_paths : [];
    await patch({ photo_paths: cur.filter(p => p !== path) });
    cleanup([path]);
  }

  /* ---- Logotipo ---- */
  const logoUrl = B.imgUrl(biz.logo_path);
  const logoInput = el('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp', disabled });
  logoInput.addEventListener('change', () => { const f = logoInput.files[0]; logoInput.value = ''; if (f) run('Subiendo logotipo…', () => setLogo(f)); });
  const logoRow = el('div', { class: 'avatarrow' },
    logoUrl ? el('img', { class: 'avatar', src: logoUrl, alt: 'Logotipo actual de ' + biz.name })
            : el('div', { class: 'avatar ph-emoji', 'aria-hidden': 'true', text: B.ICONS[biz.category] || '🐾' }),
    el('div', { class: 'avatarctl' },
      el('label', {}, 'Logotipo', logoInput, el('small', { text: 'Cuadrado o redondo se ve mejor. JPG, PNG o WebP.' })),
      biz.logo_path ? el('button', { class: 'btn ghost sm', type: 'button', text: 'Quitar logotipo', disabled, onclick: () => run('Quitando logotipo…', () => setLogo(null)) }) : null));

  /* ---- Fotos ---- */
  const photos = Array.isArray(biz.photo_paths) ? biz.photo_paths : [];
  const photoInput = el('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp', disabled: disabled || photos.length >= MAX_PHOTOS });
  photoInput.addEventListener('change', () => { const f = photoInput.files[0]; photoInput.value = ''; if (f) run('Subiendo foto…', () => addPhoto(f)); });
  const gallery = photos.length
    ? el('div', { class: 'gallery editable' }, photos.map((p, i) => {
        const u = B.imgUrl(p);
        return el('figure', {}, u ? el('img', { src: u, alt: 'Foto ' + (i + 1) + ' de tu negocio', loading: 'lazy', decoding: 'async' }) : el('div', { class: 'ph-emoji', text: '🖼️' }),
          el('button', { class: 'btn ghost sm', type: 'button', text: 'Quitar', disabled, 'aria-label': 'Quitar la foto ' + (i + 1), onclick: () => run('Quitando foto…', () => removePhoto(p)) }));
      }))
    : el('p', { class: 'mut', text: 'Todavía no hay fotos.' });

  UI.put(host,
    el('h3', { text: '🖼️ Logotipo y fotos' }),
    el('p', { class: 'note', text: 'Las imágenes de tu negocio son PÚBLICAS: cualquier persona con su dirección exacta puede verlas, y se muestran en el directorio cuando tu ficha está aprobada y tu plan es Plata u Oro. No subas imágenes con datos personales. Al subirlas se reducen de tamaño y se borran sus datos ocultos (como la ubicación).' }),
    hasPlan ? null : el('p', { class: 'stage', text: 'Con tu plan actual el directorio todavía no muestra logotipo ni fotos. Puedes dejarlas listas desde ahora.' }),
    box, logoRow,
    el('h4', { text: 'Fotos del establecimiento (' + photos.length + ' de ' + MAX_PHOTOS + ')' }), gallery,
    el('label', {}, 'Agregar foto', photoInput, el('small', { text: photos.length >= MAX_PHOTOS ? 'Llegaste al máximo de fotos.' : 'Una a la vez. JPG, PNG o WebP.' })));
}

MODS.fotos = { render };
})();
