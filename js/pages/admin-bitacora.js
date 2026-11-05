/* Panel · Bitácora: historial de las acciones de administración (solo lectura).
   · Cada cambio hecho desde el panel (o desde el SQL Editor con una sesión de administración) deja una línea: quién, qué y sobre qué.
   · No guarda contenidos (ni el texto de las guías, ni los mensajes, ni las notas internas): solo datos mínimos del cambio.
   · No se puede borrar ni editar desde aquí. Crece con el tiempo; hoy no se limpia sola. */
(() => {
const R = window.TPAdmin; if (!R) return;
const ACTION = {
  user_suspend: 'Usuario suspendido', user_reactivate: 'Usuario reactivado',
  business_status: 'Estado de aliado', business_verify: 'Verificación de aliado', promotion_delete: 'Promoción retirada',
  complaint_update: 'Denuncia actualizada',
  guide_create: 'Guía creada', guide_publish: 'Guía publicada', guide_unpublish: 'Guía despublicada', guide_update: 'Guía editada', guide_delete: 'Guía eliminada',
  subscription_assign: 'Plan asignado', subscription_renew: 'Suscripción renovada', subscription_cancel: 'Suscripción cancelada', subscription_dates: 'Fechas de suscripción',
  plan_request_approve: 'Solicitud de plan aprobada', plan_request_reject: 'Solicitud de plan rechazada',
  conversation_status: 'Estado de conversación'
};
const GROUPS = [['', 'Todas las acciones'], ['user_', 'Usuarios'], ['business_', 'Aliados'], ['promotion_', 'Promociones'], ['complaint_', 'Denuncias'],
                ['guide_', 'Guías'], ['subscription_', 'Suscripciones'], ['plan_request_', 'Solicitudes de plan'], ['conversation_', 'Conversaciones']];
const LIMIT = 50;
/* details (jsonb) → «clave: valor · …» en texto plano y acotado */
function detailsText(d) {
  if (!d || typeof d !== 'object' || Array.isArray(d)) return '';
  return Object.keys(d).slice(0, 8).map(k => {
    const v = d[k];
    const t = v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);
    return k + ': ' + (t.length > 80 ? t.slice(0, 80) + '…' : t);
  }).join(' · ');
}
R.register({
  id: 'bitacora', label: '📜 Bitácora', title: 'Bitácora de administración',
  async open(A, host) {
    const E = A.E, UI = window.TPUI;
    const st = { prefix: '', offset: 0 };
    const body = E('div');
    UI.put(host, body);

    async function load() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_audit', { p_prefix: st.prefix || null, p_limit: LIMIT, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, load); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return load(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'bi-filtro', onchange: () => { st.prefix = sel.value; st.offset = 0; load(); } }, A.options(GROUPS, st.prefix));
      UI.put(body,
        E('p', { class: 'mut', text: 'Solo lectura. Aquí queda constancia de quién hizo cada cambio; no se guardan contenidos (mensajes, notas ni textos de guías).' }),
        E('div', { class: 'adm-tools' }, A.field('Mostrar', sel), E('button', { class: 'btn ghost sm', type: 'button', text: 'Actualizar', onclick: load })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(r => E('li', { class: 'adm-row', dataset: { id: String(r.id), action: r.action } },
          E('div', { class: 'adm-main-line' }, E('b', { text: ACTION[r.action] || r.action }), ' ', E('small', { class: 'mut', text: A.dt(r.created_at) })),
          E('small', { class: 'mut', text: 'Por: ' + (r.admin_id ? (r.admin_name || '(sin nombre)') + ' · ' + (r.admin_email || '') : 'SQL Editor (sin sesión)') +
              (r.target_table ? ' · sobre ' + r.target_table + (r.target_id ? ' ' + String(r.target_id).slice(0, 8) : '') : '') }),
          detailsText(r.details) ? E('small', { class: 'mut adm-details', text: detailsText(r.details) }) : null)))
        : A.empty('Todavía no hay acciones registradas con ese filtro.'),
        A.pager({ total, limit: LIMIT, offset: st.offset, go: o => { st.offset = o; load(); } }));
    }
    await load();
  }
});
})();
