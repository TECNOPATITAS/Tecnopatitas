/*
  TECNOPATITAS · Cliente mínimo de Supabase Realtime (Etapa 7)

  Escucha cambios de tablas ("postgres_changes") por WebSocket, sin librerías de terceros.
  Supabase Realtime SÍ respeta las políticas RLS: cada persona solo recibe las filas que ya puede leer.
  Aun así, este archivo solo es comodidad (avisos al instante): lo que protege los datos es RLS en el servidor.

  Protocolo (Phoenix Channels v2, el mismo que usa el SDK oficial):
    URL      wss://<proyecto>.supabase.co/realtime/v1/websocket?apikey=<clave pública>&vsn=2.0.0
    Mensaje  [join_ref, ref, tema, evento, carga]
    Unirse   evento «phx_join» con { config: { postgres_changes: [...] }, access_token }
    Latido   [null, ref, 'phoenix', 'heartbeat', {}] cada 25 s
    Cambios  evento «postgres_changes» con { data: { type, table, record, old_record } }

  Qué hace por ti:
    · reconecta solo (espera 1, 2, 4… hasta 30 s, con un poco de azar) y detecta conexiones "muertas" con el latido;
    · renueva el token de sesión antes de que venza (si no, Realtime cierra el canal);
    · si la pestaña lleva mucho oculta, cierra la conexión para no gastar el límite de conexiones del plan gratuito;
    · avisa el estado: 'connecting' | 'live' | 'down' | 'paused' (la página usa consultas periódicas si no está 'live').
*/
(() => {
'use strict';
const CFG = window.TP_CONFIG || {};
const BASE = String(CFG.SUPABASE_URL || '').replace(/\/+$/, '');
const KEY = String(CFG.SUPABASE_PUBLISHABLE_KEY || '');
const HEARTBEAT_MS = 25000;
const PAUSE_HIDDEN_MS = 5 * 60 * 1000;                  // pestaña oculta más de 5 min → se cierra la conexión
const BACKOFF = [1000, 2000, 4000, 8000, 15000, 30000];
const JOIN_TIMEOUT_MS = 10000;                          // si el servidor acepta la conexión pero no confirma la unión, se reintenta
const TABLE_RE = /^[a-z_][a-z0-9_]{0,62}$/;
const EVENTS = ['INSERT', 'UPDATE', 'DELETE', '*'];

function wsUrl() {
  if (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(BASE) || !KEY || /^sb_secret_/.test(KEY)) return null;
  return 'wss://' + BASE.slice('https://'.length) + '/realtime/v1/websocket?apikey=' + encodeURIComponent(KEY) + '&vsn=2.0.0';
}

/*
  subscribe({ name, changes: [{ event, schema, table, filter? }], onChange(c), onStatus(s, detail) }) → { close(), status() }
  c = { table, type: 'INSERT'|'UPDATE'|'DELETE', record, old }
*/
function subscribe(opts) {
  const TP = window.TP;
  const url = wsUrl();
  const changes = (opts.changes || []).filter(c => c && EVENTS.includes(c.event) && TABLE_RE.test(c.table || '') && TABLE_RE.test(c.schema || 'public'))
    .map(c => { const o = { event: c.event, schema: c.schema || 'public', table: c.table }; if (typeof c.filter === 'string' && c.filter.length < 200) o.filter = c.filter; return o; });
  const topic = 'realtime:' + String(opts.name || 'tp').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40);
  let ws = null, status = 'connecting', closed = false, attempt = 0, seq = 0, starting = false;
  let joinRef = null, joinMsgRef = null, hbRef = null, hbTimer = null, retryTimer = null, tokTimer = null, pauseTimer = null, stableTimer = null, joinTimer = null, lastToken = null;

  const setStatus = (s, detail) => {
    if (closed || (s === status && s !== 'down')) return;
    status = s;
    try { opts.onStatus && opts.onStatus(s, detail); } catch { /* una página con error no debe tumbar la conexión */ }
  };
  const nextRef = () => String(++seq);
  const send = (ref, ev, payload, topicName, jr) => { if (ws && ws.readyState === 1) ws.send(JSON.stringify([jr === undefined ? joinRef : jr, ref, topicName || topic, ev, payload])); };

  function clearTimers() { clearInterval(hbTimer); clearTimeout(retryTimer); clearTimeout(tokTimer); clearTimeout(stableTimer); clearTimeout(joinTimer); hbTimer = retryTimer = tokTimer = stableTimer = joinTimer = null; }
  function teardownSocket() {
    clearInterval(hbTimer); clearTimeout(tokTimer); clearTimeout(stableTimer); clearTimeout(joinTimer); hbTimer = tokTimer = stableTimer = joinTimer = null; hbRef = null;
    if (ws) { const w = ws; ws = null; w.onopen = w.onmessage = w.onerror = w.onclose = null; try { w.close(); } catch { /* */ } }
  }
  function scheduleRetry(detail) {
    teardownSocket();
    if (closed || status === 'paused') return;
    setStatus('down', detail);
    const base = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
    attempt++;
    clearTimeout(retryTimer);
    retryTimer = setTimeout(connect, base + Math.floor(Math.random() * base * 0.3));
  }

  async function getSess() {
    try { const s = TP && await TP.getSession(); return s || null; } catch { return null; }
  }

  async function connect() {
    if (closed) return;
    clearTimeout(retryTimer);
    if (!url || !changes.length) { setStatus('down', 'config'); return; }
    if (document.hidden && status === 'paused') return;
    if (ws || starting) return;                                        // ya hay una conexión (o se está abriendo): nunca dos a la vez
    starting = true;
    let s;
    try { s = await getSess(); } finally { starting = false; }
    if (closed || ws) return;
    if (!s) { scheduleRetry('sin_sesion'); return; }
    if (status === 'down' || status === 'paused') setStatus('connecting');
    let sock;
    try { sock = new WebSocket(url); } catch { scheduleRetry('ws'); return; }
    ws = sock;
    joinTimer = setTimeout(() => { if (ws === sock && status !== 'live') scheduleRetry('sin_respuesta'); }, JOIN_TIMEOUT_MS);
    sock.onopen = () => {
      if (ws !== sock) return;
      joinRef = nextRef(); joinMsgRef = joinRef; lastToken = s.access_token;
      send(joinMsgRef, 'phx_join', {
        config: { broadcast: { ack: false, self: false }, presence: { key: '' }, postgres_changes: changes, private: false },
        access_token: s.access_token
      });
      hbTimer = setInterval(heartbeat, HEARTBEAT_MS);
      scheduleTokenPush(s);
    };
    sock.onmessage = ev => { if (ws === sock) onFrame(ev.data); };
    sock.onerror = () => { /* el cierre posterior dispara la reconexión */ };
    sock.onclose = () => { if (ws === sock) scheduleRetry('cerrado'); };
  }

  function heartbeat() {
    if (!ws || ws.readyState !== 1) return;
    if (hbRef !== null) { scheduleRetry('sin_latido'); return; }      // el latido anterior no tuvo respuesta: la conexión murió en silencio
    hbRef = nextRef();
    send(hbRef, 'heartbeat', {}, 'phoenix', null);
  }

  function onFrame(raw) {
    let f; try { f = JSON.parse(raw); } catch { return; }
    if (!Array.isArray(f) || f.length < 5) return;
    const [, ref, top, ev, payload] = f;
    if (top === 'phoenix' && ev === 'phx_reply') { if (ref === hbRef) hbRef = null; return; }
    if (top !== topic) return;
    if (ev === 'phx_reply') {
      if (ref !== joinMsgRef) return;                                  // respuestas a otros mensajes (p. ej. access_token)
      const pc = payload && payload.response && payload.response.postgres_changes;
      if (!payload || payload.status !== 'ok' || (Array.isArray(pc) && pc.length !== changes.length)) { scheduleRetry('rechazado'); return; }
      clearTimeout(joinTimer);
      setStatus('live');
      clearTimeout(stableTimer);
      stableTimer = setTimeout(() => { attempt = 0; }, 10000);        // el retroceso solo se reinicia si la conexión aguanta; así un error repetido no genera un bucle
    } else if (ev === 'postgres_changes') {
      const d = payload && payload.data;
      if (!d || !TABLE_RE.test(String(d.table || '')) || !['INSERT', 'UPDATE', 'DELETE'].includes(d.type)) return;
      try { opts.onChange && opts.onChange({ table: d.table, type: d.type, record: d.record || {}, old: d.old_record || {} }); } catch { /* una página con error no debe tumbar la conexión */ }
    } else if (ev === 'system') {
      if (payload && payload.status === 'error') scheduleRetry('sistema');   // p. ej. la tabla no está en la publicación de Realtime
    } else if (ev === 'phx_error' || ev === 'phx_close') {
      scheduleRetry('canal');
    }
  }

  // ---- Renovar el token antes de que venza (Realtime cierra el canal si el token caduca) ----
  function scheduleTokenPush(s) {
    clearTimeout(tokTimer);
    const secs = (s && s.expires_at ? s.expires_at : 0) - Math.floor(Date.now() / 1000);
    const wait = Math.max(5000, (secs - 45) * 1000);
    tokTimer = setTimeout(pushToken, Math.min(wait, 20 * 60 * 1000));
  }
  async function pushToken() {
    if (closed || !ws) return;
    const s = await getSess();
    if (closed || !ws) return;
    if (!s) { scheduleRetry('sin_sesion'); return; }
    if (s.access_token !== lastToken) { lastToken = s.access_token; send(nextRef(), 'access_token', { access_token: s.access_token }); }
    scheduleTokenPush(s);
  }
  const offAuth = TP && TP.onAuthChange ? TP.onAuthChange(ev => {
    if (closed) return;
    if (ev === 'SIGNED_OUT') { close(); return; }
    if (ev === 'TOKEN_REFRESHED' || ev === 'SIGNED_IN') pushToken();
  }) : null;

  // ---- Pestaña oculta mucho tiempo → pausa; al volver, se reconecta ----
  function onVisibility() {
    if (closed) return;
    if (document.hidden) {
      clearTimeout(pauseTimer);
      pauseTimer = setTimeout(() => { if (document.hidden && !closed) { teardownSocket(); clearTimeout(retryTimer); setStatus('paused'); } }, PAUSE_HIDDEN_MS);
    } else {
      clearTimeout(pauseTimer);
      if (status === 'paused' || status === 'down') { attempt = 0; connect(); }
    }
  }
  function onOnline() { if (!closed && status !== 'live') { attempt = 0; connect(); } }
  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('online', onOnline);

  function close() {
    if (closed) return;
    try { if (ws && ws.readyState === 1) send(nextRef(), 'phx_leave', {}); } catch { /* */ }
    closed = true; clearTimers(); clearTimeout(pauseTimer); teardownSocket();
    document.removeEventListener('visibilitychange', onVisibility); window.removeEventListener('online', onOnline);
    if (offAuth) offAuth();
  }

  connect();
  return Object.freeze({ close, status: () => status });
}

window.TPRT = Object.freeze({ subscribe, HEARTBEAT_MS, PAUSE_HIDDEN_MS });
})();
