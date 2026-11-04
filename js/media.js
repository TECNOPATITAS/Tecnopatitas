/*
  Preparación de imágenes en el navegador (Etapa 4).
  - Solo JPG, PNG o WebP; se rechaza cualquier otro archivo aunque cambie la extensión (la imagen debe poder decodificarse).
  - Se reduce el tamaño y se RE-CODIFICA siempre como JPEG: así se eliminan los metadatos (EXIF, incluida la ubicación GPS)
    y las fotos pesan poco (el plan gratuito tiene 1 GB de archivos en total).
  - El servidor vuelve a validar tipo y tamaño (buckets de Supabase); esto es comodidad y ahorro de espacio.
*/
(() => {
'use strict';
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_INPUT = 15 * 1024 * 1024;                           // lo que se acepta del dispositivo (antes de reducir)
const MAX_PIXELS = 100e6;                                     // evita imágenes diseñadas para agotar la memoria
class MediaError extends Error { constructor(message) { super(message); this.name = 'MediaError'; } }

async function prepareImage(file, opts) {
  const o = Object.assign({ maxSide: 1600, quality: 0.85 }, opts);
  if (!file || typeof file.type !== 'string' || !ALLOWED.includes(file.type)) throw new MediaError('Elige una imagen JPG, PNG o WebP.');
  if (file.size > MAX_INPUT) throw new MediaError('La imagen pesa demasiado (máximo 15 MB).');
  if (file.size === 0) throw new MediaError('El archivo está vacío.');
  let bmp;
  try { bmp = await createImageBitmap(file); }
  catch { throw new MediaError('No se pudo leer la imagen. Prueba con otra.'); }
  try {
    if (bmp.width * bmp.height > MAX_PIXELS) throw new MediaError('La imagen es demasiado grande en píxeles.');
    const k = Math.min(1, o.maxSide / Math.max(bmp.width, bmp.height));
    const w = Math.max(1, Math.round(bmp.width * k)), h = Math.max(1, Math.round(bmp.height * k));
    const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);      // las transparencias de un PNG quedan sobre blanco
    ctx.drawImage(bmp, 0, 0, w, h);
    const blob = await new Promise(res => cv.toBlob(res, 'image/jpeg', o.quality));
    if (!blob || blob.type !== 'image/jpeg') throw new MediaError('No se pudo preparar la imagen.');
    return blob;
  } finally { if (bmp && bmp.close) bmp.close(); }
}
window.TPMedia = Object.freeze({ prepareImage, MediaError, ALLOWED });
})();
