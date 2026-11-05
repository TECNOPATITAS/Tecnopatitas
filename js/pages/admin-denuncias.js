/* Panel · Denuncias: bandeja de reportes anónimos de maltrato animal.
   · Las denuncias NO están ligadas a ninguna cuenta ni dirección IP: aquí no hay datos de quien reporta.
   · El contenido original no se puede cambiar. Solo el estado, la prioridad, el seguimiento, la «actualización pública» (la ve quien
     tenga el código de seguimiento) y las notas internas (solo el equipo).
   · «Canalizada» significa que se orientó el caso a la instancia que puede atenderlo. NO significa que TECNOPATITAS haya presentado
     una denuncia oficial ante alguna autoridad, y así se dice en pantalla.
   · Las fotos están en un bucket privado: se piden con enlaces firmados de corta duración y solo las puede leer un administrador. */
(() => {
const R = window.TPAdmin; if (!R) return;
const TYPE = { maltrato_fisico: 'Maltrato físico', abandono: 'Abandono', sin_agua_alimento_refugio: 'Falta de agua, alimento o refugio',
               hacinamiento_insalubre: 'Hacinamiento o condiciones insalubres', comercio_ilegal: 'Venta o comercio ilegal', otra: 'Otra situación' };
const STATUS = { recibida: ['Recibida', 'info'], en_revision: ['En revisión', 'info'], en_proceso: ['En proceso', 'ok'], canalizada: ['Canalizada', 'ok'], cerrada: ['Cerrada', 'mute'] };
const PRIORITY = { baja: ['Baja', 'mute'], media: ['Media', 'info'], alta: ['Alta', 'warn'], urgente: ['Urgente', 'warn'] };
R.register({
  id: 'denuncias', label: '🚨 Denuncias', title: 'Denuncias',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT, TP = window.TP;
    const st = { status: A.params.status != null ? A.params.status : 'pendientes', offset: 0 };
    const body = E('div');
    UI.put(host, body);
    const sBadge = s => { const x = STATUS[s] || [s, 'mute']; return A.badge(x[0], x[1]); };
    const pBadge = p => { if (!p) return null; const x = PRIORITY[p] || [p, 'mute']; return A.badge('Prioridad ' + x[0].toLowerCase(), x[1]); };

    async function list() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_complaints', { p_status: st.status || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, list); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return list(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'dn-filtro', onchange: () => { st.status = sel.value; st.offset = 0; list(); } },
        A.options([['pendientes', 'Pendientes (recibidas y en revisión)'], ['recibida', 'Recibidas'], ['en_revision', 'En revisión'], ['en_proceso', 'En proceso'],
                   ['canalizada', 'Canalizadas'], ['cerrada', 'Cerradas'], ['', 'Todas']], st.status));
      UI.put(body,
        E('div', { class: 'adm-tools' }, A.field('Mostrar', sel)),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(c => E('li', { class: 'adm-row', dataset: { id: c.id, code: c.tracking_code } },
          E('div', { class: 'adm-main-line' }, E('b', { text: c.tracking_code }), ' ', sBadge(c.status), ' ', pBadge(c.priority), ' ',
            c.attended ? A.badge('Atendida', 'ok') : null),
          E('small', { class: 'mut', text: [TYPE[c.type] || c.type, [c.municipality, c.state].filter(Boolean).join(', '), 'hechos ~' + A.dd(c.approx_date),
              c.photos > 0 ? c.photos + ' foto(s)' : null, 'recibida ' + A.dt(c.created_at)].filter(Boolean).join(' · ') }),
          E('p', { class: 'adm-excerpt', text: c.excerpt + (c.excerpt && c.excerpt.length >= 160 ? '…' : '') }),
          E('div', { class: 'adm-actions' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Abrir', 'aria-label': 'Abrir denuncia ' + c.tracking_code, onclick: () => detail(c.id) }))))
        ) : A.empty(st.status === 'pendientes' ? 'No hay denuncias pendientes.' : 'No hay denuncias con ese estado.'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; list(); } }));
    }

    async function detail(id, keep) {
      if (!keep) A.say(null); A.loading(body);
      let c;
      try { c = await A.rpc('admin_get_complaint', { p_id: id }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, () => detail(id, keep)); return; }
      if (!A.alive(host)) return;
      const status = E('select', { id: 'dn-estado' }, A.options(Object.keys(STATUS).map(k => [k, STATUS[k][0]]), c.status));
      const prio = E('select', { id: 'dn-prio' }, A.options([['', 'Sin prioridad'], ...Object.keys(PRIORITY).map(k => [k, PRIORITY[k][0]])], c.priority || ''));
      const att = E('input', { type: 'checkbox', id: 'dn-atendida', checked: c.attended ? true : null });
      const pub = E('textarea', { id: 'dn-publica', rows: '3', maxlength: '500' }); pub.value = c.public_update || '';
      const internal = E('textarea', { id: 'dn-notas', rows: '5', maxlength: '4000' }); internal.value = c.internal_notes || '';
      const form = E('form', { class: 'adm-form', 'aria-label': 'Seguimiento de la denuncia', onsubmit: e => {
        e.preventDefault();
        A.run(e.currentTarget.querySelector('button[type=submit]'), 'Guardando…', () => A.rpc('admin_update_complaint', {
          p_id: id, p_status: status.value, p_priority: prio.value || null, p_attended: att.checked,
          p_public_update: pub.value.trim() || null, p_internal_notes: internal.value.trim() || null }),
          'Seguimiento guardado.').then(ok => { if (ok) detail(id, true); });
      } },
        A.field('Estado', status,
          '«Canalizada» = orientaste el caso a la instancia que puede atenderlo. No significa que TECNOPATITAS haya presentado una denuncia oficial.'),
        A.field('Prioridad', prio),
        E('label', { class: 'adm-f adm-check' }, att, E('span', { text: 'Ya fue atendida por el equipo' })),
        A.field('Actualización pública (máx. 500)', pub, 'La ve cualquier persona que tenga el código de seguimiento. No escribas nombres, teléfonos ni direcciones.'),
        A.field('Notas internas (máx. 4000)', internal, 'Solo las ve el equipo de administración.'),
        E('button', { class: 'btn coral', type: 'submit', text: 'Guardar seguimiento' }));
      const gallery = E('div', { class: 'adm-photos', role: 'group', 'aria-label': 'Fotos de evidencia' });
      UI.put(body,
        E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: '← Volver a la lista', onclick: () => { A.say(null); list(); } })),
        E('div', { class: 'card adm-card' },
          E('h3', { text: 'Denuncia ' + c.tracking_code }),
          E('p', null, sBadge(c.status), ' ', pBadge(c.priority), ' ', c.attended ? A.badge('Atendida', 'ok') : null),
          A.dl([['Tipo', TYPE[c.type] || c.type], ['Fecha aproximada de los hechos', A.dd(c.approx_date)],
                ['Lugar', [c.municipality, c.state].filter(Boolean).join(', ')], ['Referencia del lugar', c.location_reference],
                ['Recibida', A.dt(c.created_at)], ['Última actualización', A.dt(c.updated_at)], ['Atendida el', c.attended_at ? A.dt(c.attended_at) : '']]),
          E('h4', { text: 'Descripción' }), E('p', { class: 'adm-text', text: c.description }),
          c.extra_info ? [E('h4', { text: 'Información adicional' }), E('p', { class: 'adm-text', text: c.extra_info })] : null,
          E('p', { class: 'mut', text: 'La denuncia es anónima: no está ligada a ninguna cuenta ni a datos de contacto. El contenido original no se puede modificar.' }),
          E('h4', { text: 'Evidencia (' + (Array.isArray(c.photo_paths) ? c.photo_paths.length : 0) + ')' }), gallery),
        E('div', { class: 'card adm-card' }, E('h3', { text: 'Seguimiento' }), form));
      photos(c, gallery);
    }

    async function photos(c, gallery) {
      const paths = Array.isArray(c.photo_paths) ? c.photo_paths : [];
      if (!paths.length) { UI.put(gallery, E('p', { class: 'mut', text: 'Esta denuncia no incluye fotos.' })); return; }
      UI.put(gallery, E('p', { class: 'mut', role: 'status', text: 'Cargando fotos…' }));
      let urls;
      try { urls = await TP.storage.sign('complaint-evidence', paths, 600); }
      catch (ex) { if (A.alive(gallery)) UI.put(gallery, E('p', { class: 'msg err', role: 'alert', text: 'No se pudieron cargar las fotos. ' + A.err(ex) })); return; }
      if (!A.alive(gallery)) return;
      UI.put(gallery, paths.map((p, i) => urls[p]
        ? E('a', { href: urls[p], target: '_blank', rel: 'noopener noreferrer', 'aria-label': 'Abrir foto ' + (i + 1) + ' en una pestaña nueva' },
            E('img', { src: urls[p], alt: 'Foto de evidencia ' + (i + 1), loading: 'lazy', referrerpolicy: 'no-referrer' }))
        : E('p', { class: 'mut', text: 'La foto ' + (i + 1) + ' no está disponible.' })));
    }

    if (A.params.id) await detail(A.params.id); else await list();
  }
});
})();
