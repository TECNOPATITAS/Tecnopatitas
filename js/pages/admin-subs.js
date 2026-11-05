/* Panel · Suscripciones: solicitudes de plan y suscripciones vigentes. SIN COBROS.
   · Aprobar una solicitud asigna el plan a mano (un mes o un año, o la fecha que indiques). No se cobra nada ni se guardan datos de pago.
   · Renovar, cancelar y cambiar el vencimiento también son manuales. Cada acción avisa a la persona y queda en la bitácora.
   · Las acciones sobre una suscripción las valida el servidor (p. ej. un plan de aliado no se puede dar a una cuenta de dueño). */
(() => {
const R = window.TPAdmin; if (!R) return;
const RSTATUS = { pending: ['Pendiente', 'warn'], approved: ['Aprobada', 'ok'], rejected: ['Rechazada', 'mute'], cancelled: ['Cancelada por la persona', 'mute'] };
const SSTATUS = { active: ['Activa', 'ok'], expired: ['Vencida', 'warn'], cancelled: ['Cancelada', 'mute'], replaced: ['Reemplazada', 'mute'] };
R.register({
  id: 'subs', label: '⭐ Suscripciones', title: 'Suscripciones y solicitudes de plan',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT;
    const st = { tab: A.params.tab === 'subs' ? 'subs' : 'requests', rStatus: 'pending', sStatus: 'active', q: A.params.tab === 'subs' ? (A.params.q || '') : '', offset: 0 };
    const tabs = E('nav', { class: 'tabs', 'aria-label': 'Solicitudes o suscripciones' });
    const body = E('div');
    UI.put(host, tabs, body);

    function paintTabs() {
      UI.put(tabs, [['requests', 'Solicitudes de plan'], ['subs', 'Suscripciones']].map(([k, t]) =>
        E('button', { type: 'button', text: t, dataset: { tab: k }, 'aria-current': st.tab === k ? 'page' : null, onclick: () => { st.tab = k; st.offset = 0; paintTabs(); load(); } })));
    }
    const load = () => st.tab === 'requests' ? requests() : subs();

    /* ---------- Solicitudes ---------- */
    async function requests() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_plan_requests', { p_status: st.rStatus || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, requests); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return requests(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'su-rstatus', onchange: () => { st.rStatus = sel.value; st.offset = 0; requests(); } },
        A.options([['pending', 'Pendientes'], ['approved', 'Aprobadas'], ['rejected', 'Rechazadas'], ['cancelled', 'Canceladas por la persona'], ['', 'Todas']], st.rStatus));
      UI.put(body,
        E('p', { class: 'mut', text: 'Aprobar asigna el plan a mano. No se cobra nada: el acuerdo con la persona se hace fuera de la plataforma.' }),
        E('div', { class: 'adm-tools' }, A.field('Mostrar', sel)),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(requestRow)) : A.empty(st.rStatus === 'pending' ? 'No hay solicitudes pendientes.' : 'No hay solicitudes con ese estado.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; requests(); } }));
    }

    function requestRow(r) {
      const x = RSTATUS[r.status] || [r.status, 'mute'];
      const kids = [
        E('div', { class: 'adm-main-line' }, E('b', { text: 'Solicitud ' + r.code }), ' ', A.badge(x[0], x[1])),
        E('small', { class: 'mut', text: [(r.display_name || '(sin nombre)') + ' · ' + r.email, A.TYPE[r.account_type] || r.account_type,
            'pide ' + (r.plan_name || A.PLAN[r.plan_id] || r.plan_id) + ' (' + (A.PERIOD[r.billing_period] || '') + ')', 'el ' + A.d(r.created_at)].join(' · ') }),
        E('small', { class: 'mut', text: 'Plan actual: ' + (r.current_plan_id ? A.PLAN[r.current_plan_id] || r.current_plan_id : 'sin plan') +
            (r.current_ends_at ? ' (vence ' + A.d(r.current_ends_at) + ')' : '') }),
        r.user_note ? E('p', { class: 'adm-text', text: 'Mensaje de la persona: ' + r.user_note }) : null
      ];
      if (r.status !== 'pending') {
        kids.push(E('small', { class: 'mut', text: 'Resuelta ' + A.dt(r.resolved_at) + (r.admin_note ? ' · Nota: ' + r.admin_note : '') }));
      } else {
        const note = E('input', { type: 'text', maxlength: '500', 'aria-label': 'Nota para la persona (solicitud ' + r.code + ')', placeholder: 'Nota para la persona (opcional)' });
        const ends = E('input', { type: 'date', 'aria-label': 'Vence el (solicitud ' + r.code + ')' });
        const resolve = (approve, okText) => btn => A.run(btn, 'Guardando…', () => A.rpc('admin_resolve_plan_request',
          { p_request: r.id, p_approve: approve, p_note: note.value.trim() || null, p_ends: approve ? A.endOfDay(ends.value) : null }), okText).then(ok => { if (ok) requests(); });
        kids.push(E('div', { class: 'adm-form' },
          A.field('Nota para la persona', note, 'Los primeros 300 caracteres se muestran en su aviso.'),
          A.field('Vence el (solo al aprobar, opcional)', ends, 'Vacío: ' + (r.billing_period === 'yearly' ? '1 año' : '1 mes') + ' desde hoy.'),
          E('div', { class: 'adm-actions' },
            A.confirm('Aprobar y activar plan', '¿Activar este plan sin cobro?', resolve(true, 'Solicitud aprobada: el plan quedó activo y la persona recibió un aviso.'), 'btn mint sm'),
            A.confirm('Rechazar', '¿Rechazar la solicitud?', resolve(false, 'Solicitud rechazada. La persona recibió un aviso.'), 'btn ghost sm'))));
      }
      kids.push(E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver cuenta', onclick: () => A.go('usuarios', { id: r.user_id }) })));
      return E('li', { class: 'adm-row', dataset: { id: r.id, code: r.code } }, kids);
    }

    /* ---------- Suscripciones ---------- */
    async function subs() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_subscriptions', { p_status: st.sStatus || null, p_search: st.q || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, subs); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return subs(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'su-sstatus' }, A.options([['active', 'Activas'], ['expiring', 'Por vencer (15 días o menos)'], ['expired', 'Vencidas'], ['cancelled', 'Canceladas'], ['replaced', 'Reemplazadas'], ['', 'Todas']], st.sStatus));
      const q = E('input', { type: 'search', id: 'su-q', maxlength: '80', value: st.q, autocomplete: 'off' });
      UI.put(body,
        E('form', { class: 'adm-tools', role: 'search', onsubmit: e => { e.preventDefault(); st.sStatus = sel.value; st.q = q.value.trim(); st.offset = 0; subs(); } },
          A.field('Estado', sel), A.field('Buscar por nombre o correo', q), E('button', { class: 'btn coral sm', type: 'submit', text: 'Filtrar' })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(subRow)) : A.empty('No hay suscripciones con ese filtro.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; subs(); } }));
    }

    function subRow(s) {
      const x = SSTATUS[s.status] || [s.status, 'mute'];
      const left = s.days_left == null ? null : (s.days_left < 0 ? 'venció hace ' + Math.abs(s.days_left) + ' día(s)' : s.days_left === 0 ? 'vence hoy' : 'quedan ' + s.days_left + ' día(s)');
      const kids = [
        E('div', { class: 'adm-main-line' }, E('b', { text: s.plan_name || A.PLAN[s.plan_id] || s.plan_id }), ' ', A.badge(x[0], x[1]), ' ',
          s.status === 'active' && s.days_left != null && s.days_left <= 15 ? A.badge('Por vencer', 'warn') : null),
        E('small', { class: 'mut', text: [(s.display_name || '(sin nombre)') + ' · ' + s.email, A.PERIOD[s.billing_period] || '', 'desde ' + A.d(s.starts_at),
            s.ends_at ? 'hasta ' + A.d(s.ends_at) : 'sin vencimiento', s.status === 'active' ? left : null].filter(Boolean).join(' · ') }),
        s.note ? E('small', { class: 'mut', text: 'Nota: ' + s.note }) : null
      ];
      if (s.status === 'active' || s.status === 'expired') {
        const date = E('input', { type: 'date', 'aria-label': 'Nuevo vencimiento de ' + s.email });
        const act = (btn, label, fn, okText) => A.run(btn, label, fn, okText).then(ok => { if (ok) subs(); });
        kids.push(E('div', { class: 'adm-actions' },
          A.confirm('Renovar un periodo', '¿Extender el vencimiento un periodo (' + (A.PERIOD[s.billing_period] || '') + ')?', btn => act(btn, 'Renovando…',
            () => A.rpc('admin_renew_subscription', { p_subscription: s.id, p_note: null }), 'Suscripción renovada. La persona recibió un aviso.'), 'btn mint sm'),
          s.status === 'active' ? A.confirm('Cancelar suscripción', '¿Cancelar la suscripción?', btn => act(btn, 'Cancelando…',
            () => A.rpc('admin_cancel_subscription', { p_user: s.user_id, p_note: null }), 'Suscripción cancelada. La persona recibió un aviso.'), 'btn coral sm') : null),
          E('form', { class: 'adm-form adm-inline', 'aria-label': 'Cambiar vencimiento de ' + s.email, onsubmit: e => {
            e.preventDefault();
            if (!date.value) { A.say('err', 'Elige la nueva fecha de vencimiento.'); date.focus(); return; }
            act(e.currentTarget.querySelector('button[type=submit]'), 'Guardando…',
              () => A.rpc('admin_set_subscription_dates', { p_subscription: s.id, p_starts: null, p_ends: A.endOfDay(date.value) }), 'Vencimiento actualizado.');
          } }, A.field('Nuevo vencimiento', date), E('button', { class: 'btn ghost sm', type: 'submit', text: 'Cambiar fecha' })));
      }
      kids.push(E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver cuenta', onclick: () => A.go('usuarios', { id: s.user_id }) })));
      return E('li', { class: 'adm-row', dataset: { id: s.id } }, kids);
    }

    paintTabs();
    await load();
  }
});
})();
