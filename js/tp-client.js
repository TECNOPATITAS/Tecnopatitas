/*
  TECNOPATITAS · Cliente de Supabase (Etapa 3)

  Cliente mínimo y auditable (sin librerías de terceros) para:
    · Supabase Auth (GoTrue): registro, inicio de sesión, cierre, recuperación y cambio de contraseña
    · Base de datos (PostgREST): consultas y funciones RPC con la sesión de la persona

  Reglas de seguridad:
    · Solo usa la clave pública (publishable). Se niega a arrancar si detecta una clave secreta.
    · La sesión vive en localStorage (el sitio no tiene scripts de terceros: ver CSP en _headers).
    · Todo texto que venga del servidor debe mostrarse con textContent, nunca con innerHTML.
    · Que una página oculte contenido es solo comodidad: la protección real es RLS en el servidor.
*/
(() => {
'use strict';

const CFG = window.TP_CONFIG || {};
const BASE = String(CFG.SUPABASE_URL || '').replace(/\/+$/, '');
const KEY = String(CFG.SUPABASE_PUBLISHABLE_KEY || '');
const STORE_KEY = 'tp-auth-v1';

// ---------- Comprobaciones de arranque ----------
function jwtRole(k) {
  try { return JSON.parse(atob(k.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).role; } catch { return null; }
}
let configError = null;
if (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(BASE)) configError = 'SUPABASE_URL no es válida (config.js).';
else if (!KEY) configError = 'Falta la clave pública (config.js).';
else if (/^sb_secret_/.test(KEY) || jwtRole(KEY) === 'service_role') configError = 'config.js contiene una clave SECRETA. Retírala de inmediato: solo se permite la clave publishable.';
if (configError) console.error('[TECNOPATITAS] ' + configError);

// ---------- Errores ----------
class TPError extends Error {
  constructor(code, message, status, raw) { super(message || code); this.name = 'TPError'; this.code = code; this.status = status || 0; this.raw = raw; }
}
const MESSAGES = {
  network: 'No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.',
  config: 'El sitio no está configurado correctamente. Avisa al administrador.',
  invalid_credentials: 'Correo o contraseña incorrectos.',
  email_not_confirmed: 'Todavía no confirmas tu correo. Revisa tu bandeja de entrada y la carpeta de spam.',
  weak_password: 'La contraseña es demasiado débil. Usa al menos 10 caracteres y evita contraseñas comunes.',
  over_email_send_rate_limit: 'Se alcanzó el límite de correos por hora del servicio gratuito. Inténtalo de nuevo en una hora.',
  over_request_rate_limit: 'Demasiados intentos. Espera unos minutos antes de volver a intentarlo.',
  email_address_not_authorized: 'Por ahora el servicio de correo solo envía mensajes a cuentas de prueba autorizadas. Estamos configurando el envío para todo el público.',
  signup_disabled: 'El registro está desactivado temporalmente.',
  user_already_exists: 'No pudimos crear la cuenta con esos datos. Si ya tienes una, inicia sesión.',
  email_exists: 'No pudimos crear la cuenta con esos datos. Si ya tienes una, inicia sesión.',
  same_password: 'La nueva contraseña debe ser distinta de la actual.',
  otp_expired: 'El enlace venció o ya se usó. Solicita uno nuevo.',
  flow_state_expired: 'El enlace venció o ya se usó. Solicita uno nuevo.',
  validation_failed: 'Revisa los datos que escribiste.',
  captcha_failed: 'No se pudo comprobar que eres una persona. Inténtalo de nuevo.',
  session_expired: 'Tu sesión expiró. Inicia sesión de nuevo.',
  forbidden: 'No tienes permiso para hacer esto.',
  not_saved: 'No se pudo guardar. Si tu cuenta está suspendida, contacta al administrador.'
};
function errorMessage(e) {
  if (!e) return MESSAGES.network;
  const code = e.code || '';
  if (MESSAGES[code]) return MESSAGES[code];
  if (e.status === 429) return MESSAGES.over_request_rate_limit;
  if (e.status === 401) return MESSAGES.session_expired;
  if (e.status === 403) return MESSAGES.forbidden;
  return 'Ocurrió un error inesperado. Inténtalo de nuevo en unos minutos.';
}

// ---------- Almacenamiento de la sesión ----------
let memSession = null;
let cache = null;                                             // perfil/rol de esta carga de página
function readSession() {
  try { const raw = localStorage.getItem(STORE_KEY); if (raw) { const s = JSON.parse(raw); if (s && s.access_token && s.refresh_token) return s; } return null; }
  catch { return memSession; }
}
function writeSession(s) {
  memSession = s;
  try { if (s) localStorage.setItem(STORE_KEY, JSON.stringify(s)); else localStorage.removeItem(STORE_KEY); } catch { /* modo privado: queda en memoria */ }
}
const nowSec = () => Math.floor(Date.now() / 1000);
function toSession(r) {
  return { access_token: r.access_token, refresh_token: r.refresh_token,
           expires_at: r.expires_at || (nowSec() + (r.expires_in || 3600)),
           user: r.user ? { id: r.user.id, email: r.user.email, email_confirmed_at: r.user.email_confirmed_at || r.user.confirmed_at || null } : null };
}

// ---------- Eventos ----------
const listeners = new Set();
function emit(event, meta) { listeners.forEach(fn => { try { setTimeout(() => fn(event, readSession(), meta || {}), 0); } catch { /* */ } }); }
function onAuthChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }
window.addEventListener('storage', e => { if (e.key === STORE_KEY) { cache = null; emit(readSession() ? 'SIGNED_IN' : 'SIGNED_OUT', { remote: true }); } });

// ---------- HTTP ----------
async function http(path, { method = 'GET', query, body, token, headers, signal } = {}) {
  if (configError) throw new TPError('config', configError);
  const url = BASE + path + (query ? '?' + query : '');
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 20000);
  let res;
  try {
    res = await fetch(url, {
      method, credentials: 'omit', cache: 'no-store', signal: signal || ctl.signal,
      headers: Object.assign({ apikey: KEY, Accept: 'application/json' },
        body !== undefined ? { 'Content-Type': 'application/json' } : {},
        token ? { Authorization: 'Bearer ' + token } : {}, headers || {}),
      body: body !== undefined ? JSON.stringify(body) : undefined
    });
  } catch (e) {
    throw new TPError('network', 'network', 0, e);
  } finally { clearTimeout(timer); }
  let data = null;
  const text = await res.text().catch(() => '');
  if (text) { try { data = JSON.parse(text); } catch { data = null; } }
  if (!res.ok) {
    const code = (data && (data.error_code || data.code || data.error)) || 'http_' + res.status;
    const msg = (data && (data.msg || data.message || data.error_description)) || ('HTTP ' + res.status);
    throw new TPError(String(code), msg, res.status, data);
  }
  return data;
}

// ---------- Sesión ----------
let refreshing = null;
async function refreshSession() {
  if (refreshing) return refreshing;
  const run = async () => {
    const cur = readSession();
    if (!cur) return null;
    if (cur.expires_at - nowSec() > 60) return cur;           // otra pestaña ya la renovó
    let r;
    try {
      r = await http('/auth/v1/token', { method: 'POST', query: 'grant_type=refresh_token', body: { refresh_token: cur.refresh_token } });
    } catch (e) {
      if (e.status === 400 || e.status === 401 || e.status === 403 || e.status === 422) { writeSession(null); cache = null; emit('SIGNED_OUT'); return null; }
      throw e;                                                // sin red: no cerramos la sesión
    }
    const ns = toSession(r);
    if (!ns.user) ns.user = cur.user;
    writeSession(ns); emit('TOKEN_REFRESHED');
    return ns;
  };
  refreshing = (async () => {
    try { return navigator.locks ? await navigator.locks.request('tp-refresh', run) : await run(); }
    finally { refreshing = null; }
  })();
  return refreshing;
}
async function getSession() {
  const s = readSession();
  if (!s) return null;
  if (s.expires_at - nowSec() > 60) return s;
  return refreshSession();
}
function hasSession() { return !!readSession(); }

// ---------- Retorno desde enlaces de correo (flujo implícito) ----------
const callback = { type: null, error: null };
async function consumeUrlCallback() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ''));
  const q = new URLSearchParams(location.search);
  const err = h.get('error_code') || h.get('error') || q.get('error_code') || q.get('error');
  const hasTokens = h.get('access_token') && h.get('refresh_token');
  if (!err && !hasTokens) return;
  const clean = () => {                                       // deja la URL sin tokens ni errores
    ['error', 'error_code', 'error_description'].forEach(k => q.delete(k));
    const qs = q.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch { /* */ }
  };
  if (err) {
    callback.error = { code: h.get('error_code') || q.get('error_code') || err };
    clean(); return;
  }
  const type = h.get('type');
  if (!['signup', 'recovery', 'magiclink', 'invite', 'email_change'].includes(type)) { clean(); return; }
  const token = h.get('access_token');
  clean();                                                    // quita los tokens de la barra de direcciones cuanto antes
  try {
    const user = await http('/auth/v1/user', { token });
    const s = toSession({ access_token: token, refresh_token: h.get('refresh_token'), expires_at: Number(h.get('expires_at')) || undefined,
                          expires_in: Number(h.get('expires_in')) || 3600, user });
    writeSession(s); cache = null;
    callback.type = type;
    emit(type === 'recovery' ? 'PASSWORD_RECOVERY' : 'SIGNED_IN');
  } catch (e) { callback.error = { code: e.code || 'otp_expired' }; }
}
const ready = consumeUrlCallback().catch(() => {});

// ---------- Autenticación ----------
async function signUp({ email, password, displayName, accountType, redirectTo }) {
  const data = { display_name: displayName, account_type: accountType === 'business' ? 'business' : 'owner' };
  const r = await http('/auth/v1/signup', { method: 'POST', query: redirectTo ? 'redirect_to=' + encodeURIComponent(redirectTo) : '', body: { email, password, data } });
  if (r && r.access_token) {                                  // la confirmación por correo está desactivada: entra directo
    writeSession(toSession(r)); cache = null; emit('SIGNED_IN');
    return { session: true };
  }
  return { session: false };                                  // pendiente de confirmar el correo (o correo ya existente: no se revela)
}
async function signIn(email, password) {
  const r = await http('/auth/v1/token', { method: 'POST', query: 'grant_type=password', body: { email, password } });
  writeSession(toSession(r)); cache = null; emit('SIGNED_IN');
}
async function signOut() {
  const s = readSession();
  writeSession(null); cache = null;
  emit('SIGNED_OUT', { manual: true });                       // cierre pedido por la persona (las páginas decidirán a dónde ir)
  if (s) { try { await http('/auth/v1/logout', { method: 'POST', query: 'scope=local', token: s.access_token }); } catch { /* ya cerrada localmente */ } }
}
async function resetPassword(email, redirectTo) {
  await http('/auth/v1/recover', { method: 'POST', query: redirectTo ? 'redirect_to=' + encodeURIComponent(redirectTo) : '', body: { email } });
}
async function updatePassword(newPassword) {
  const s = await getSession();
  if (!s) throw new TPError('session_expired', 'session_expired', 401);
  await http('/auth/v1/user', { method: 'PUT', token: s.access_token, body: { password: newPassword } });
}

// ---------- Base de datos (PostgREST) ----------
async function rest(path, { method = 'GET', query, body, prefer, single } = {}) {
  const s = await getSession();
  const headers = {};
  if (prefer) headers.Prefer = prefer;
  if (single) headers.Accept = 'application/vnd.pgrst.object+json';
  try {
    return await http('/rest/v1' + path, { method, query, body, token: s && s.access_token, headers });
  } catch (e) {
    if (e.status === 401 && s) { writeSession(null); cache = null; emit('SIGNED_OUT'); throw new TPError('session_expired', 'session_expired', 401); }
    throw e;
  }
}
const rpc = (fn, args) => rest('/rpc/' + encodeURIComponent(fn), { method: 'POST', body: args || {} });

// ---------- Perfil y rol ----------
let meInflight = null;                                        // evita pedir lo mismo dos veces cuando cabecera y guarda lo piden a la vez
function me(force) {
  if (cache && !force) return Promise.resolve(cache);
  if (meInflight && !force) return meInflight;
  const p = loadMe().finally(() => { if (meInflight === p) meInflight = null; });
  meInflight = p;
  return p;
}
async function loadMe() {
  const s = await getSession();
  if (!s) return null;
  const uid = s.user && s.user.id;
  if (!uid) { await signOut(); return null; }
  const [prof, adm] = await Promise.all([
    rest('/profiles', { query: 'select=id,display_name,account_type,phone,is_suspended,created_at&id=eq.' + encodeURIComponent(uid), single: true })
      .catch(e => { if (e.status === 406 || e.code === 'PGRST116') return null; throw e; }),
    rpc('is_admin').then(v => v === true).catch(e => { if (e.status === 401) throw e; return false; })
  ]);
  if (!readSession()) return null;                            // se cerró la sesión mientras tanto
  const accountType = prof && prof.account_type === 'business' ? 'business' : 'owner';
  cache = { user: s.user, profile: prof || { display_name: '', phone: null, is_suspended: false }, accountType, isAdmin: adm === true,
            suspended: !!(prof && prof.is_suspended) };
  return cache;
}
const homeFor = m => !m ? 'login.html' : m.isAdmin ? 'admin.html' : m.accountType === 'business' ? 'panel-aliado.html' : 'perfil.html';
const PAGES = ['index', 'registro', 'login', 'recuperar', 'nueva-contrasena', 'guias', 'directorio', 'denuncias', 'planes', 'sobre-nosotros',
               'perfil', 'mascota', 'carnet', 'notificaciones', 'chat', 'panel-aliado', 'admin'];
function safeNext(v) {                                        // evita redirecciones a otros sitios
  if (typeof v !== 'string') return null;
  const m = /^([a-z-]+)\.html$/.exec(v);
  return m && PAGES.includes(m[1]) ? v : null;
}
async function updateProfile(uid, values) {
  const r = await rest('/profiles', { method: 'PATCH', query: 'id=eq.' + encodeURIComponent(uid), body: values, prefer: 'return=representation' });
  if (!Array.isArray(r) || r.length === 0) throw new TPError('not_saved', 'not_saved', 0);
  cache = null; return r[0];
}

// ---------- Validaciones (solo comodidad: el servidor vuelve a validar) ----------
const COMMON = ['1234567890', '0123456789', 'contrasena1', 'contraseña1', 'password12', 'password123', 'qwertyuiop', 'abcdefghij', 'tecnopatitas', 'mascotas123', '1q2w3e4r5t'];
function checkPassword(pw, email) {
  if (typeof pw !== 'string' || pw.length < 10) return 'La contraseña debe tener al menos 10 caracteres.';
  if (pw.length > 72) return 'La contraseña no puede tener más de 72 caracteres.';
  if (/^(.)\1+$/.test(pw)) return 'Elige una contraseña menos repetitiva.';
  const low = pw.toLowerCase();
  if (COMMON.some(c => low.includes(c))) return 'Esa contraseña es demasiado común. Elige otra.';
  const local = String(email || '').split('@')[0].toLowerCase();
  if (local.length >= 4 && low.includes(local)) return 'La contraseña no debe contener tu correo.';
  return null;
}
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const checkEmail = e => (typeof e === 'string' && e.length <= 254 && EMAIL_RE.test(e)) ? null : 'Escribe un correo electrónico válido.';

window.TP = Object.freeze({
  ready, callback, onAuthChange, hasSession, getSession, me, homeFor, safeNext, errorMessage, TPError,
  signUp, signIn, signOut, resetPassword, updatePassword, updateProfile, rest, rpc,
  checkPassword, checkEmail, configError
});
})();
