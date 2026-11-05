/* Panel · Aliados: revisión y moderación de establecimientos.
   · Aprobar / rechazar / suspender / volver a «en revisión» (avisa al dueño) y dar o quitar «Aliado verificado» (solo aprobados).
   · Retirar una promoción que no cumple las reglas (se borra; el dueño recibe el motivo).
   · El panel NO edita los datos del establecimiento: eso lo hace su dueño. Todo se escribe como texto. */
(() => {
const R = window.TPAdmin; if (!R) return;
const STATUS = { pending: ['En revisión', 'warn'], approved: ['Aprobado', 'ok'], rejected: ['Rechazado', 'mute'], suspended: ['Suspendido', 'warn'] };
R.register({
  id: 'aliados', label: '🏪 Aliados', title: 'Aliados',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT, B = window.TPBiz || { CATEGORIES: {}, hoursList: () => [], mapsSearchUrl: null };
    const st = { status: A.params.status != null ? A.params.status : 'pending', q: A.params.q || '', offset: 0 };
    const body = E('div');
    UI.put(host, body);
    const badge = s => { const x = STATUS[s] || [s, 'mute']; return A.badge(x[0], x[1]); };

    async function list() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_businesses', { p_status: st.status || null, p_search: st.q || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, list); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return list(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'al-status' }, A.options([['pending', 'En revisión'], ['approved', 'Aprobados'], ['suspended', 'Suspendidos'], ['rejected', 'Rechazados'], ['', 'Todos']], st.status));
      const q = E('input', { type: 'search', id: 'al-q', maxlength: '80', value: st.q, autocomplete: 'off' });
      UI.put(body,
        E('form', { class: 'adm-tools', role: 'search', onsubmit: e => { e.preventDefault(); st.status = sel.value; st.q = q.value.trim(); st.offset = 0; list(); } },
          A.field('Estado', sel), A.field('Buscar por nombre, municipio o correo', q), E('button', { class: 'btn coral sm', type: 'submit', text: 'Filtrar' })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(b => E('li', { class: 'adm-row', dataset: { id: b.id } },
          E('div', { class: 'adm-main-line' }, E('b', { text: b.name }), ' ', badge(b.status), ' ',
            b.verified ? A.badge('Verificado', 'info') : null, ' ', b.is_demo ? A.badge('Demostración', 'mute') : null),
          E('small', { class: 'mut', text: [B.CATEGORIES[b.category] || b.category, [b.municipality, b.state].filter(Boolean).join(', '),
              b.owner_email ? 'dueño: ' + b.owner_email : 'sin dueño', b.plan_id ? (A.PLAN[b.plan_id] || b.plan_id) : null,
              b.active_promotions > 0 ? b.active_promotions + ' promoción(es) vigente(s)' : null, 'alta ' + A.d(b.created_at)].filter(Boolean).join(' · ') }),
          E('div', { class: 'adm-actions' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Revisar', 'aria-label': 'Revisar ' + b.name, onclick: () => detail(b.id) }))))
        ) : A.empty(st.status === 'pending' && !st.q ? 'No hay establecimientos esperando revisión.' : 'No hay establecimientos con ese filtro.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; list(); } }));
    }

    async function detail(id, keep) {
      if (!keep) A.say(null); A.loading(body);
      let b;
      try { b = await A.rpc('admin_get_business', { p_id: id }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, () => detail(id, keep)); return; }
      if (!A.alive(host)) return;
      const again = () => detail(id, true);
      const setStatus = (status, okText) => btn => A.run(btn, 'Guardando…', () => A.rpc('admin_set_business_status', { p_business: id, p_status: status }), okText).then(ok => { if (ok) again(); });
      const acts = [];
      if (b.status !== 'approved') acts.push(A.confirm('Aprobar', '¿Aprobar y publicar en el directorio?', setStatus('approved', 'Establecimiento aprobado. Su dueño recibió un aviso.'), 'btn mint sm'));
      if (b.status === 'pending') acts.push(A.confirm('Rechazar', '¿Rechazar este establecimiento?', setStatus('rejected', 'Establecimiento rechazado. Su dueño recibió un aviso.'), 'btn ghost sm'));
      if (b.status === 'approved') acts.push(A.confirm('Suspender', '¿Quitarlo del directorio?', setStatus('suspended', 'Establecimiento suspendido y retirado del directorio.'), 'btn coral sm'));
      if (b.status === 'approved' || b.status === 'suspended' || b.status === 'rejected') acts.push(A.confirm('Regresar a revisión', '¿Regresarlo a «en revisión»?', setStatus('pending', 'Establecimiento en revisión.'), 'btn ghost sm'));
      const canVerify = b.status === 'approved';
      const eligible = b.plan && b.plan.verified_badge_eligible;
      const verify = !canVerify ? E('p', { class: 'mut', text: 'La etiqueta «Aliado verificado» solo se puede dar a establecimientos aprobados.' })
        : E('div', { class: 'adm-form' },
            !b.verified && !eligible ? E('p', { class: 'mut', text: 'Su plan actual no incluye la etiqueta de verificado: aunque la asignes, no se mostrará hasta que tenga un plan que la incluya.' }) : null,
            A.confirm(b.verified ? 'Quitar verificación' : 'Marcar como verificado', b.verified ? '¿Quitar la etiqueta?' : '¿Dar la etiqueta «Aliado verificado»?',
              btn => A.run(btn, 'Guardando…', () => A.rpc('admin_set_business_verified', { p_business: id, p_verified: !b.verified }),
                b.verified ? 'Verificación retirada.' : 'Etiqueta «Aliado verificado» asignada.').then(ok => { if (ok) again(); }), 'btn ghost sm'));
      const hours = B.hoursList(b.hours);
      const promos = Array.isArray(b.promotions) ? b.promotions : [];
      const mapUrl = typeof B.mapsSearchUrl === 'function' ? B.mapsSearchUrl(b) : null;
      UI.put(body,
        E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: '← Volver a la lista', onclick: () => { A.say(null); list(); } })),
        E('div', { class: 'card adm-card' },
          E('h3', { text: b.name }),
          E('p', null, badge(b.status), ' ', b.verified ? A.badge('Verificado', 'info') : null, ' ', b.is_demo ? A.badge('Demostración', 'mute') : null),
          A.dl([
            ['Categoría', B.CATEGORIES[b.category] || b.category], ['Descripción', b.description], ['Dirección', b.address],
            ['Municipio y estado', [b.municipality, b.state].filter(Boolean).join(', ')], ['Teléfono', b.phone], ['WhatsApp', b.whatsapp_url],
            ['Texto para Google Maps', b.maps_query], ['Logotipo', b.has_logo ? 'Sí' : 'No'], ['Fotos', b.photos],
            ['Horario', hours.length ? hours.map(h => h[0] + ': ' + h[1]).join(' · ') : 'Sin horario'],
            ['Alta', A.dt(b.created_at)], ['Última actualización', A.dt(b.updated_at)],
            ['Dueño', b.owner ? (b.owner.display_name || '(sin nombre)') + ' · ' + b.owner.email + (b.owner.is_suspended ? ' (cuenta suspendida)' : '') : 'Sin dueño'],
            ['Plan del dueño', b.plan ? b.plan.name : 'Sin plan']
          ]),
          mapUrl ? E('p', null, E('a', { class: 'btn ghost sm', href: mapUrl, target: '_blank', rel: 'noopener noreferrer', text: 'Ver ubicación en Google Maps' })) : null,
          b.owner ? E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: 'Ver cuenta del dueño', onclick: () => A.go('usuarios', { id: b.owner.id }) })) : null),
        E('div', { class: 'card adm-card' }, E('h3', { text: 'Estado en el directorio' }),
          E('p', { class: 'mut', text: 'Solo los establecimientos aprobados aparecen en el directorio. Cada cambio avisa al dueño y queda en la bitácora.' }),
          E('div', { class: 'adm-actions' }, acts), E('h4', { text: 'Aliado verificado' }), verify),
        E('div', { class: 'card adm-card' }, E('h3', { text: 'Promociones (' + promos.length + ')' }),
          promos.length ? E('ul', { class: 'adm-list' }, promos.map(p => promoRow(p))) : A.empty('Este establecimiento no tiene promociones.')));

      function promoRow(p) {
        const why = E('input', { type: 'text', maxlength: '300', 'aria-label': 'Motivo del retiro de «' + p.title + '»', placeholder: 'Motivo (se lo mostramos al dueño)' });
        return E('li', { class: 'adm-row', dataset: { promo: p.id } },
          E('div', { class: 'adm-main-line' }, E('b', { text: p.title }), ' ', p.is_active ? A.badge('Activa', 'ok') : A.badge('Inactiva', 'mute')),
          p.description ? E('p', { text: p.description }) : null,
          E('small', { class: 'mut', text: 'Del ' + A.dd(p.starts_on) + ' al ' + A.dd(p.ends_on) }),
          E('div', { class: 'adm-form' }, E('label', { class: 'adm-f' }, E('span', { text: 'Motivo del retiro' }), why),
            A.confirm('Retirar promoción', '¿Borrar esta promoción?', btn => A.run(btn, 'Retirando…',
              () => A.rpc('admin_delete_promotion', { p_promo: p.id, p_reason: why.value.trim() || null }), 'Promoción retirada. Su dueño recibió el motivo.').then(ok => { if (ok) again(); }), 'btn coral sm')));
      }
    }

    if (A.params.id) await detail(A.params.id); else await list();
  }
});
})();
