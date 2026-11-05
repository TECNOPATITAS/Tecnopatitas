/*
  Anti-robots con Cloudflare Turnstile (Etapa 6). Gratuito, sin cuenta de pago.

  - La «site key» (clave de sitio) es PÚBLICA y se lee de js/config.js (TURNSTILE_SITE_KEY). La clave SECRETA nunca está aquí.
  - Si no hay site key, no se muestra nada y las páginas siguen funcionando como antes (excepto las denuncias, que la exigen).
  - El script de Cloudflare solo se descarga cuando una página pide la verificación (CSP: challenges.cloudflare.com).
  - Cada token sirve UNA sola vez y vence a los 5 minutos: después de cada intento hay que llamar a reset().
  - La comprobación de verdad la hace el servidor (la función segura de denuncias o Supabase Auth); esto solo obtiene el token.
*/
(() => {
'use strict';
const KEY = String((window.TP_CONFIG && window.TP_CONFIG.TURNSTILE_SITE_KEY) || '').trim();
const KEY_RE = /^[0-9A-Za-z_-]{10,32}$/;
const SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

// Una «site key» mide unos 22–25 caracteres; la secreta unos 35. Si es más larga, casi seguro se pegó la clave equivocada.
const configError = !KEY ? null
  : KEY.length > 32 ? 'La clave de Turnstile de config.js parece ser la SECRETA (es demasiado larga). Retírala de inmediato y pon la «Site Key».'
  : !KEY_RE.test(KEY) ? 'La clave de Turnstile de config.js no tiene un formato válido.' : null;
const enabled = !!KEY && !configError;
if (configError) console.error('[TECNOPATITAS] ' + configError);

let loading = null;
function loadScript() {
  if (window.turnstile && typeof window.turnstile.render === 'function') return Promise.resolve();
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SRC; s.async = true; s.defer = true;
    s.onload = () => (window.turnstile && typeof window.turnstile.render === 'function') ? resolve() : reject(new Error('turnstile'));
    s.onerror = () => reject(new Error('blocked'));
    document.head.appendChild(s);
  }).catch(e => { loading = null; throw e; });                  // permite reintentar
  return loading;
}

/*
  mount(host, { onChange(tieneToken), onStatus('loading'|'ready'|'error', mensaje) })
  → { token(), reset(), destroy(), retry() }
*/
function mount(host, opts) {
  const o = opts || {};
  let id = null, tok = null, dead = false, starting = false, errored = false;
  const status = (k, m) => { try { o.onStatus && o.onStatus(k, m); } catch { /* */ } };
  const change = () => { try { o.onChange && o.onChange(!!tok); } catch { /* */ } };
  const box = document.createElement('div'); box.className = 'captcha'; host.replaceChildren(box);

  async function start() {
    if (starting || id !== null) return;                        // evita dibujar dos verificaciones si se pide reintentar mientras carga
    if (!enabled) { status('error', configError || 'La verificación anti-robots no está configurada.'); return; }
    starting = true; status('loading');
    try { await loadScript(); }
    catch { starting = false; if (!dead) status('error', 'No se pudo cargar la verificación anti-robots. Revisa tu conexión o desactiva el bloqueador de contenido en este sitio y vuelve a intentarlo.'); return; }
    starting = false;
    if (dead) return;
    try {
      id = window.turnstile.render(box, {
        sitekey: KEY, theme: 'auto', language: 'es',
        callback: t => { errored = false; tok = typeof t === 'string' && t ? t : null; change(); },
        'expired-callback': () => { tok = null; change(); },
        'timeout-callback': () => { tok = null; change(); },
        'error-callback': () => { tok = null; errored = true; change(); status('error', 'La verificación anti-robots falló. Recarga la página e inténtalo de nuevo.'); return true; }
      });
      status('ready');
    } catch { status('error', 'No se pudo iniciar la verificación anti-robots.'); }
  }
  start();
  return {
    token: () => tok,
    reset() { tok = null; errored = false; change(); try { if (id !== null && window.turnstile) window.turnstile.reset(id); } catch { /* */ } },
    retry() {                                                  // si el script no cargó, lo intenta de nuevo; si el desafío falló, lo reinicia (no toca uno en curso)
      if (id === null) start();
      else if (errored) { errored = false; try { window.turnstile.reset(id); } catch { /* */ } }
    },
    destroy() { dead = true; try { if (id !== null && window.turnstile) window.turnstile.remove(id); } catch { /* */ } box.remove(); }
  };
}

window.TPCaptcha = Object.freeze({ enabled, configured: !!KEY, configError, mount });
})();
