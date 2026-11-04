/* Utilidades compartidas de mascotas (Etapa 4): especies, lectura de fichas, fotos privadas con URL firmada y plan vigente. */
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI;
if (!TP || !UI) return;
const SPECIES = { perro: 'Perro', gato: 'Gato', ave: 'Ave', conejo: 'Conejo', pequeno_mamifero: 'Pequeño mamífero', otro: 'Otro' };
const EMOJI = { perro: '🐕', gato: '🐈', ave: '🐦', conejo: '🐇', pequeno_mamifero: '🐹', otro: '🐾' };
const SEX = { macho: 'Macho', hembra: 'Hembra' };
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PET_COLS = 'id,name,photo_path,species,breed,sex,birth_date,weight_kg,description,vet_info,created_at';

const listPets = () => TP.rest('/pets', { query: 'select=' + PET_COLS + '&order=created_at.asc&limit=100' });

/* { ruta: urlFirmada } para las fotos de las mascotas indicadas (si falla, devuelve {} y se muestran los iconos) */
async function photoUrls(pets) {
  const paths = pets.map(p => p.photo_path).filter(Boolean);
  if (!paths.length) return {};
  try { return await TP.storage.sign('pet-photos', paths, 3600); } catch { return {}; }
}
function thumb(pet, urls, cls) {
  const u = pet.photo_path && urls[pet.photo_path];
  return u ? UI.el('img', { class: cls, src: u, alt: 'Foto de ' + pet.name, loading: 'lazy', decoding: 'async' })
           : UI.el('div', { class: cls + ' ph-emoji', 'aria-hidden': 'true', text: EMOJI[pet.species] || '🐾' });
}
/* Plan vigente de la persona (null = sin plan: se trata como Básica) */
async function plan() {
  try { const e = await TP.rpc('my_entitlements'); return (e && e.plan) || null; } catch { return null; }
}
const healthLimit = p => !p ? 0 : (p.health_card_pet_limit === null || p.health_card_pet_limit === undefined) ? Infinity : p.health_card_pet_limit;

/* Nombre de archivo aleatorio para las imágenes que se suben */
function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
  return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
}
const notSaved = () => new TP.TPError('not_saved', 'not_saved', 0);

window.TPPets = Object.freeze({ SPECIES, EMOJI, SEX, UUID_RE, listPets, photoUrls, thumb, plan, healthLimit, uuid, notSaved });
})();
