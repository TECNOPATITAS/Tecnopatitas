/* Páginas legales (Etapa 11): rellena fecha, versión y datos de contacto. Todo se escribe como TEXTO (nunca como HTML).
   · Si faltan los datos de quien responde por el sitio, se muestra un aviso visible: el texto está incompleto y no debe publicarse así. */
(() => {
const L = window.TP_LEGAL || {};
const C = (window.TP_CONFIG && window.TP_CONFIG.LEGAL) || {};
const clean = v => (typeof v === 'string' ? v.trim().slice(0, 300) : '');
const set = (key, text) => document.querySelectorAll('[data-lg="' + key + '"]').forEach(el => { el.textContent = text; });
set('fecha', L.FECHA || ''); set('version', L.VERSION || '');
const data = { responsable: clean(C.RESPONSABLE), domicilio: clean(C.DOMICILIO), contacto: clean(C.CONTACTO) };
const missing = [];
if (!data.responsable) missing.push('nombre de quien responde por el sitio');
if (!data.domicilio) missing.push('domicilio');
if (!data.contacto) missing.push('medio de contacto');
['responsable', 'domicilio'].forEach(k => set(k, data[k] || '(pendiente de completar)'));
document.querySelectorAll('[data-lg="contacto"]').forEach(el => {
  const v = data.contacto;
  if (/^[^\s@<>"']+@[^\s@<>"']+\.[A-Za-z]{2,}$/.test(v)) {   // un correo: se ofrece como enlace
    const a = document.createElement('a'); a.href = 'mailto:' + v; a.textContent = v; el.textContent = ''; el.appendChild(a);
  } else el.textContent = v || '(pendiente de completar)';
});
const box = document.getElementById('lg-falta');
if (box && missing.length) {
  box.textContent = 'Aviso para quien administra el sitio: faltan datos en js/config.js (' + missing.join(', ') + '). Mientras no se completen, este texto está incompleto y el sitio no debe recibir datos de personas reales.';
  box.hidden = false;
}
})();
