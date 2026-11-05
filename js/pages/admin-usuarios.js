/* Panel · Usuarios: buscar cuentas, ver su ficha (solo datos de la cuenta y conteos), suspender/reactivar y asignar un plan a mano.
   Las funciones admin_* del servidor vuelven a comprobar el rol; un administrador no puede suspender a otro. Sin pagos. */
(() => {
const R = window.TPAdmin; if (!R) return;
R.register({
  id: 'usuarios', label: '👥 Usuarios', title: 'Usuarios',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT;
    const st = { q: A.params.q || '', offset: 0, id: null };
    const PLANS_BY_TYPE = { owner: ['pro', 'vip'], business: ['plata', 'oro'] };
    const body = E('div');
    UI.put(host, body);

    async function list() {
      st.id = null; A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_users', { p_search: st.q || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, list); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return list(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const q = E('input', { type: 'search', id: 'us-q', name: 'q', value: st.q, maxlength: '80', autocomplete: 'off' });
      UI.put(body,
        E('form', { class: 'adm-tools', role: 'search', onsubmit: e => { e.preventDefault(); st.q = q.value.trim(); st.offset = 0; list(); } },
          A.field('Buscar por nombre o correo', q), E('button', { class: 'btn coral sm', type: 'submit', text: 'Buscar' })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(u => E('li', { class: 'adm-row', dataset: { id: u.id } },
          E('div', { class: 'adm-main-line' },
            E('b', { text: u.display_name || '(sin nombre)' }), ' ',
            u.is_admin ? A.badge('Administrador', 'info') : null, ' ',
            u.is_suspended ? A.badge('Suspendida', 'warn') : null),
          E('small', { class: 'mut', text: u.email + ' · ' + (A.TYPE[u.account_type] || u.account_type) + ' · ' + (u.plan_id ? A.PLAN[u.plan_id] || u.plan_id : 'Sin plan') + ' · registro ' + A.d(u.created_at) }),
          E('div', { class: 'adm-actions' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver ficha', 'aria-label': 'Ver ficha de ' + u.email, onclick: () => detail(u.id) }))))
        ) : A.empty('No hay cuentas que coincidan con la búsqueda.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; list(); } }));
    }

    async function detail(id, keep) {
      st.id = id; if (!keep) A.say(null); A.loading(body);
      let u;
      try { u = await A.rpc('admin_get_user', { p_user: id }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, () => detail(id, keep)); return; }
      if (!A.alive(host)) return;
      const sub = u.subscription;
      const reason = E('textarea', { id: 'us-reason', rows: '2', maxlength: '300' });
      const afterChange = () => detail(id, true);
      const suspendBox = u.is_admin
        ? E('p', { class: 'mut', text: 'Las cuentas de administración no se pueden suspender desde el panel.' })
        : E('div', { class: 'adm-form' },
            A.field(u.is_suspended ? 'Motivo de la reactivación (la persona lo verá en su aviso, opcional)' : 'Motivo de la suspensión (la persona lo verá en su aviso, opcional)', reason, 'Hasta 300 caracteres. No escribas datos personales de terceros.'),
            A.confirm(u.is_suspended ? 'Reactivar cuenta' : 'Suspender cuenta', u.is_suspended ? '¿Reactivar esta cuenta?' : '¿Suspender esta cuenta?',
              btn => A.run(btn, 'Guardando…', () => A.rpc('admin_set_user_suspended', { p_user: id, p_suspended: !u.is_suspended, p_reason: reason.value.trim() || null }),
                u.is_suspended ? 'Cuenta reactivada.' : 'Cuenta suspendida. Podrá consultar su información, pero no modificarla.').then(ok => { if (ok) afterChange(); }),
              u.is_suspended ? 'btn mint sm' : 'btn coral sm'));
      const plans = PLANS_BY_TYPE[u.account_type] || [];
      const pSel = E('select', { id: 'us-plan' }, A.options(plans.map(p => [p, A.PLAN[p]]), plans[0]));
      const perSel = E('select', { id: 'us-period' }, A.options([['monthly', 'Mensual'], ['yearly', 'Anual']], 'monthly'));
      const endIn = E('input', { type: 'date', id: 'us-end' });
      const noteIn = E('input', { type: 'text', id: 'us-note', maxlength: '500' });
      const assign = E('form', { class: 'adm-form', 'aria-label': 'Asignar un plan', onsubmit: e => {
        e.preventDefault();
        A.run(e.currentTarget.querySelector('button[type=submit]'), 'Asignando…',
          () => A.rpc('admin_assign_subscription', { p_user: id, p_plan: pSel.value, p_period: perSel.value, p_starts: null, p_ends: A.endOfDay(endIn.value), p_note: noteIn.value.trim() || null }),
          'Plan asignado sin ningún cobro. La persona recibió un aviso.').then(ok => { if (ok) afterChange(); });
      } },
        A.field('Plan', pSel), A.field('Periodo', perSel),
        A.field('Vence el (opcional)', endIn, 'Si lo dejas vacío: 1 mes o 1 año desde hoy.'),
        A.field('Nota interna (opcional)', noteIn),
        E('button', { class: 'btn coral sm', type: 'submit', text: 'Asignar plan' }));
      UI.put(body,
        E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: '← Volver a la lista', onclick: () => { A.say(null); list(); } })),
        E('div', { class: 'card adm-card' },
          E('h3', { text: u.display_name || '(sin nombre)' }),
          E('p', null, u.is_admin ? A.badge('Administrador', 'info') : null, ' ', u.is_suspended ? A.badge('Suspendida', 'warn') : A.badge('Activa', 'ok')),
          A.dl([
            ['Correo', u.email], ['Tipo de cuenta', A.TYPE[u.account_type] || u.account_type], ['Registro', A.dt(u.created_at)],
            ['Último acceso', u.last_sign_in_at ? A.dt(u.last_sign_in_at) : 'Sin registro'],
            ['Plan vigente', u.plan_id ? A.PLAN[u.plan_id] || u.plan_id : 'Sin plan'],
            ['Vigencia', sub ? (sub.ends_at ? 'hasta el ' + A.d(sub.ends_at) : 'sin vencimiento') + ' (' + (A.PERIOD[sub.billing_period] || '') + ')' : 'Sin suscripción de pago'],
            ['Solicitud de plan', u.pending_request ? (A.PLAN[u.pending_request.plan_id] || u.pending_request.plan_id) + ' · ' + (A.PERIOD[u.pending_request.billing_period] || '') + ' · pedida el ' + A.d(u.pending_request.created_at) : 'Ninguna en revisión'],
            ['Mascotas', u.pets], ['Establecimientos', u.businesses], ['Conversaciones abiertas', u.open_conversations]
          ]),
          E('p', { class: 'mut', text: 'Por privacidad, aquí solo ves datos de la cuenta y conteos; no el contenido de sus mascotas ni de sus conversaciones.' }),
          sub || u.pending_request ? E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver en Suscripciones', onclick: () => A.go('subs', { tab: sub ? 'subs' : 'requests', q: u.email }) })) : null),
        E('div', { class: 'card adm-card' }, E('h3', { text: u.is_suspended ? 'Cuenta suspendida' : 'Suspender o reactivar' }), suspendBox),
        plans.length ? E('div', { class: 'card adm-card' }, E('h3', { text: 'Asignar un plan a mano' }),
          E('p', { class: 'mut', text: 'No se cobra nada ni se guardan datos de pago. Reemplaza el plan vigente.' }), assign) : null);
    }

    if (A.params.id) await detail(A.params.id); else await list();
  }
});
})();
