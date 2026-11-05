/*
  Ayudas compartidas de las guías de cuidado (Etapa 10): la página pública (guias.html) y el editor del panel de administración.
  · El contenido de una guía es TEXTO: párrafos separados por una línea en blanco; una línea que empieza con «## » es un subtítulo.
    Nunca se interpreta como HTML ni como Markdown completo: cada bloque se escribe con textContent.
  · Las categorías son las mismas que permite la base de datos (restricción CHECK de care_guides.category).
*/
(() => {
'use strict';
const UI = window.TPUI;
if (!UI) return;
const CATEGORIES = { perros: 'Perros', gatos: 'Gatos', aves: 'Aves', conejos: 'Conejos', 'pequenos-mamiferos': 'Pequeños mamíferos',
                     alimentacion: 'Alimentación', higiene: 'Higiene', vacunacion: 'Vacunación', 'salud-preventiva': 'Salud preventiva', comportamiento: 'Comportamiento' };
const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/* «Cómo cuidar a tu gato» → «como-cuidar-a-tu-gato» (sin acentos, solo minúsculas, números y guiones; máx. 120) */
function slugify(text) {
  return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 120).replace(/-+$/g, '');
}

/* Texto de la guía → lista de elementos <h3>/<p> (todo con textContent) */
function blocks(content) {
  const out = [];
  String(content || '').replace(/\r\n?/g, '\n').split(/\n{2,}/).forEach(chunk => {
    const t = chunk.trim();
    if (!t) return;
    if (/^## /.test(t) && !t.includes('\n')) out.push(UI.el('h3', { text: t.slice(3).trim() }));
    else out.push(UI.el('p', { class: 'gd-p', text: t }));
  });
  return out;
}

window.TPGuides = Object.freeze({ CATEGORIES, SLUG_RE, slugify, blocks });
})();
