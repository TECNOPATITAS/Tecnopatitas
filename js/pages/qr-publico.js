/*
  Página pública de una placa QR (Etapa 4). Cualquiera con el enlace la ve, SIN iniciar sesión.
  Solo muestra lo que el servidor devuelve (función get_public_pet_profile): lo que el dueño decidió publicar.
  Si el enlace no existe o la placa está desactivada se muestra el mismo aviso, sin dar pistas.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI, P = window.TPPets;
if (!TP || !UI) return;
const el = UI.el, host = document.getElementById('q-contenido');
const TOKEN_RE = /^[0-9a-f]{64}$/, PHONE_RE = /^[0-9+() .-]{7,20}$/;
const SPECIES = { perro: 'Perro', gato: 'Gato', ave: 'Ave', conejo: 'Conejo', pequeno_mamifero: 'Pequeño mamífero', otro: 'Otro' };

function invalid(text) {
  host.replaceChildren(el('div', { class: 'card pubcard' }, el('h1', { style: 'font-size:1.8rem', text: 'Enlace no disponible' }),
    el('p', { text: text || 'Este enlace no es válido o la placa fue desactivada por su responsable.' }),
    el('a', { class: 'btn ghost sm', href: 'index.html', text: 'Ir al inicio' })));
}
function show(d) {
  const photo = d.photo_path ? TP.storage.publicUrl('qr-photos', d.photo_path) : null;
  const facts = [SPECIES[d.species] || '', d.breed].filter(Boolean).join(' · ');
  const phone = d.contact_phone && PHONE_RE.test(d.contact_phone) ? d.contact_phone : null;
  const card = el('div', { class: 'card pubcard' },
    el('span', { class: 'tag', text: 'Mascota registrada en TECNOPATITAS' }),
    photo ? el('img', { class: 'pic', src: photo, alt: 'Foto de la mascota', decoding: 'async' }) : null,
    el('h1', { style: 'font-size:2rem', text: d.name || 'Mascota' }),
    facts ? el('p', { class: 'mut', text: facts }) : null,
    d.message ? el('blockquote', { class: 'pubmsg', text: d.message }) : null,
    phone ? el('div', {},
      d.contact_name ? el('p', {}, el('b', { text: 'Contacto: ' }), d.contact_name) : null,
      el('a', { class: 'btn coral', href: 'tel:' + phone.replace(/[^0-9+]/g, ''), text: 'Llamar al ' + phone }))
      : el('p', { class: 'note', text: 'Su responsable no publicó un teléfono de contacto. Si la encontraste, ofrécele agua, mantenla en un lugar seguro y llévala a un veterinario cercano para que revisen si tiene microchip o identificación.' }),
    el('p', { class: 'mut', style: 'font-size:.85rem', text: 'TECNOPATITAS no comparte direcciones ni correos de sus usuarios: solo se muestra lo que el responsable decidió publicar.' }));
  host.replaceChildren(card);
}

(async () => {
  const t = new URLSearchParams(location.search).get('t') || '';
  if (!TOKEN_RE.test(t)) { invalid(); return; }
  try {
    const d = await TP.rpc('get_public_pet_profile', { p_token: t }, { anon: true });
    if (!d || typeof d !== 'object') invalid(); else show(d);
  } catch (ex) { invalid(ex && ex.code === 'network' ? 'No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.' : 'No se pudo cargar la información en este momento. Inténtalo de nuevo en unos minutos.'); }
})();
})();
