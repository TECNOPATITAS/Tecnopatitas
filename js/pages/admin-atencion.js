/* Panel · Atención al cliente: bandeja del chat y respuestas del equipo.
   · «Sin responder» = conversaciones abiertas cuyo último mensaje es de la persona (las más antiguas primero).
   · Responder envía el mensaje como «Equipo TECNOPATITAS» y avisa a la persona dentro de la plataforma; si estaba cerrada, se vuelve a abrir.
   · La bandeja se actualiza sola cada 30 s (y la conversación abierta cada 15 s) mientras la pestaña está visible. No usa Realtime en el panel.
   · Solo se ve el contenido de las conversaciones del chat de atención; nunca mascotas, carnet ni denuncias de la persona. */
(() => {
const R = window.TPAdmin; if (!R) return;
R.register({
  id: 'atencion', label: '💬 Atención', title: 'Atención al cliente',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT;
    const st = { filter: ['pending', 'open', 'closed', 'all'].includes(A.params.filter) ? A.params.filter : 'pending', offset: 0, view: 'list', sig: '', id: null, tsig: '' };
    const body = E('div');
    UI.put(host, body);
    const sig = rows => rows.map(r => [r.id, r.status, r.last_sender, r.last_message_at, r.message_count].join('|')).join(';');

    /* ---------- Bandeja ---------- */
    async function list(silent) {
      st.view = 'list'; st.id = null;
      if (!silent) A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_conversations', { p_filter: st.filter, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (!silent && A.alive(host)) A.fail(body, ex, () => list()); return; }
      if (!A.alive(host) || st.view !== 'list') return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return list(silent); }
      const s = st.filter + st.offset + sig(rows);
      if (silent && s === st.sig) return;                       // nada cambió: no se redibuja (conserva el foco)
      st.sig = s;
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'at-filtro', onchange: () => { st.filter = sel.value; st.offset = 0; list(); } },
        A.options([['pending', 'Sin responder'], ['open', 'Abiertas'], ['closed', 'Cerradas'], ['all', 'Todas']], st.filter));
      UI.put(body,
        E('div', { class: 'adm-tools' }, A.field('Mostrar', sel), E('button', { class: 'btn ghost sm', type: 'button', text: 'Actualizar', onclick: () => list() })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(c => E('li', { class: 'adm-row', dataset: { id: c.id } },
          E('div', { class: 'adm-main-line' }, E('b', { text: c.subject }), ' ',
            c.status === 'cerrada' ? A.badge('Cerrada', 'mute') : c.last_sender === 'user' ? A.badge('Sin responder', 'warn') : A.badge('Respondida', 'ok')),
          E('small', { class: 'mut', text: (c.display_name || '(sin nombre)') + ' · ' + c.email + ' · ' + c.message_count + ' mensaje(s) · último ' + A.dt(c.last_message_at) }),
          c.last_body ? E('p', { class: 'adm-excerpt', text: (c.last_sender === 'staff' ? 'Equipo: ' : 'Persona: ') + c.last_body }) : null,
          E('div', { class: 'adm-actions' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Abrir', 'aria-label': 'Abrir conversación: ' + c.subject, onclick: () => thread(c.id) }))))
        ) : A.empty(st.filter === 'pending' ? 'No hay conversaciones sin responder.' : 'No hay conversaciones con ese filtro.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; list(); } }));
    }

    /* ---------- Conversación ---------- */
    const bubble = m => E('div', { class: 'adm-bubble ' + (m.sender_role === 'staff' ? 'staff' : 'user'), dataset: { role: m.sender_role === 'staff' ? 'staff' : 'user' } },
      E('span', { class: 'who', text: m.sender_role === 'staff' ? 'Equipo TECNOPATITAS' : 'Persona' }),
      E('p', { class: 'txt', text: m.body }), E('span', { class: 'when', text: A.dt(m.created_at) }));

    async function thread(id, keep) {
      if (!keep) A.say(null);
      st.view = 'thread'; st.id = id; st.tsig = '';
      A.loading(body);
      let c;
      try { c = await A.rpc('admin_get_conversation', { p_id: id }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, () => thread(id, keep)); return; }
      if (!A.alive(host)) return;
      const log = E('div', { class: 'adm-thread', role: 'log', 'aria-label': 'Mensajes de la conversación', tabindex: '0' });
      const head = E('div');
      const reply = E('textarea', { id: 'at-respuesta', rows: '4', maxlength: '2000' });
      const count = E('small', { class: 'mut', id: 'at-cuenta' });
      const upd = () => { count.textContent = reply.value.length + ' de 2000 caracteres'; };
      reply.addEventListener('input', upd); upd();

      function paint(conv) {
        st.tsig = conv.messages.map(m => m.id).join(',') + '|' + conv.status;
        UI.put(head,
          E('h3', { text: conv.subject }),
          E('p', null, conv.status === 'cerrada' ? A.badge('Cerrada', 'mute') : A.badge('Abierta', 'ok'), ' ',
            E('small', { class: 'mut', text: conv.user.display_name + ' · ' + conv.user.email + (conv.user.is_suspended ? ' · cuenta suspendida' : '') + ' · iniciada ' + A.dt(conv.created_at) })),
          conv.total_messages > conv.messages.length ? E('p', { class: 'mut', text: 'Se muestran los últimos ' + conv.messages.length + ' mensajes de ' + conv.total_messages + '.' }) : null);
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        UI.put(log, conv.messages.length ? conv.messages.map(bubble) : E('p', { class: 'mut', text: 'Todavía no hay mensajes.' }));
        if (atBottom) log.scrollTop = log.scrollHeight;
        c = conv;
      }
      paint(c);
      const form = E('form', { class: 'adm-form', 'aria-label': 'Responder', onsubmit: e => {
        e.preventDefault();
        const text = reply.value.trim();
        if (!text) { A.say('err', 'Escribe tu respuesta antes de enviarla.'); reply.focus(); return; }
        if (text.length > 2000) { A.say('err', 'El mensaje puede tener hasta 2000 caracteres.'); reply.focus(); return; }
        A.run(e.currentTarget.querySelector('button[type=submit]'), 'Enviando…', () => A.rpc('admin_reply_conversation', { p_conversation: id, p_body: text }),
          'Respuesta enviada. La persona recibió un aviso.').then(ok => { if (ok) { reply.value = ''; upd(); thread(id, true); } });
      } },
        A.field('Tu respuesta', reply, c.status === 'cerrada' ? 'La conversación está cerrada: si respondes, se vuelve a abrir.' : 'Habla con claridad y respeto. Nunca pidas contraseñas ni datos de pago.'),
        count, E('div', { class: 'adm-actions' }, E('button', { class: 'btn coral', type: 'submit', text: 'Enviar respuesta' })));
      const toggle = c.status === 'cerrada'
        ? A.confirm('Reabrir conversación', '¿Reabrir la conversación?', btn => A.run(btn, 'Guardando…', () => A.rpc('admin_set_conversation_status', { p_conversation: id, p_status: 'abierta' }), 'Conversación reabierta.').then(ok => { if (ok) thread(id, true); }), 'btn ghost sm')
        : A.confirm('Cerrar conversación', '¿Cerrar la conversación?', btn => A.run(btn, 'Guardando…', () => A.rpc('admin_set_conversation_status', { p_conversation: id, p_status: 'cerrada' }), 'Conversación cerrada. Si la persona escribe de nuevo, se reabrirá.').then(ok => { if (ok) thread(id, true); }), 'btn ghost sm');
      UI.put(body,
        E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: '← Volver a la bandeja', onclick: () => { A.say(null); st.sig = ''; list(); } })),
        E('div', { class: 'card adm-card' }, head, log, form, E('div', { class: 'adm-actions' }, toggle, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver cuenta', onclick: () => A.go('usuarios', { id: c.user.id }) }))));
      log.scrollTop = log.scrollHeight;

      /* Actualiza solo los mensajes (no toca lo que estés escribiendo). Se detiene si cambias de vista. */
      st.refresh = async () => {
        if (st.view !== 'thread' || st.id !== id || !A.alive(log)) return;
        let n;
        try { n = await A.rpc('admin_get_conversation', { p_id: id }); } catch { return; }
        if (st.view !== 'thread' || st.id !== id || !A.alive(log)) return;
        if (n.messages.map(m => m.id).join(',') + '|' + n.status !== st.tsig) paint(n);
      };
    }

    A.every(30000, () => { if (st.view === 'list') list(true); });
    A.every(15000, () => { if (st.view === 'thread' && st.refresh) st.refresh(); });
    if (A.params.id) await thread(A.params.id); else await list();
  }
});
})();
