/* Panel · Guías: editor de las guías de cuidado.
   · Una guía nueva queda como BORRADOR; publicar es una decisión explícita (casilla «Publicar»). Solo las publicadas las ve el público.
   · El contenido es texto: párrafos separados por una línea en blanco; «## » al inicio de un párrafo es un subtítulo. No se acepta HTML.
   · Las guías son información general: no diagnostican ni sustituyen a un veterinario, y deben revisarse con un profesional antes de publicarse.
   · Cada creación, publicación, despublicación, edición o borrado queda en la bitácora (sin guardar el contenido). */
(() => {
const R = window.TPAdmin; if (!R) return;
R.register({
  id: 'guias', label: '📚 Guías', title: 'Guías de cuidado',
  async open(A, host) {
    const E = A.E, UI = window.TPUI, LIM = A.LIMIT, G = window.TPGuides;
    if (!G) { UI.put(host, E('p', { class: 'msg err', role: 'alert', text: 'No se pudo cargar el editor de guías. Recarga la página.' })); return; }
    const st = { q: A.params.q || '', state: A.params.state || '', offset: 0 };
    const body = E('div');
    UI.put(host, body);

    async function list() {
      A.loading(body);
      let rows;
      try { rows = await A.rpc('admin_list_guides', { p_search: st.q || null, p_state: st.state || null, p_limit: LIM, p_offset: st.offset }); }
      catch (ex) { if (A.alive(host)) A.fail(body, ex, list); return; }
      if (!A.alive(host)) return;
      rows = Array.isArray(rows) ? rows : [];
      if (!rows.length && st.offset > 0) { st.offset = 0; return list(); }
      const total = rows.length ? Number(rows[0].total_count) || rows.length : 0;
      const sel = E('select', { id: 'gu-estado' }, A.options([['', 'Todas'], ['published', 'Publicadas'], ['draft', 'Borradores']], st.state));
      const q = E('input', { type: 'search', id: 'gu-q', maxlength: '80', value: st.q, autocomplete: 'off' });
      UI.put(body,
        E('form', { class: 'adm-tools', role: 'search', onsubmit: e => { e.preventDefault(); st.state = sel.value; st.q = q.value.trim(); st.offset = 0; list(); } },
          A.field('Estado', sel), A.field('Buscar por título o dirección', q), E('button', { class: 'btn coral sm', type: 'submit', text: 'Filtrar' })),
        E('p', null, E('button', { class: 'btn mint sm', type: 'button', id: 'gu-nueva', text: '＋ Nueva guía', onclick: () => edit(null) })),
        rows.length ? E('ul', { class: 'adm-list' }, rows.map(g => E('li', { class: 'adm-row', dataset: { id: g.id, slug: g.slug } },
          E('div', { class: 'adm-main-line' }, E('b', { text: g.title }), ' ', g.is_published ? A.badge('Publicada', 'ok') : A.badge('Borrador', 'warn')),
          E('small', { class: 'mut', text: [G.CATEGORIES[g.category] || g.category, 'dirección: ' + g.slug, g.author_source || null,
              g.is_published && g.published_at ? 'publicada ' + A.d(g.published_at) : null, 'editada ' + A.d(g.updated_at)].filter(Boolean).join(' · ') }),
          E('div', { class: 'adm-actions' }, E('button', { class: 'btn ghost sm', type: 'button', text: 'Editar', 'aria-label': 'Editar ' + g.title, onclick: () => edit(g.id) }),
            g.is_published ? E('a', { class: 'btn ghost sm', href: 'guias.html?g=' + encodeURIComponent(g.slug), target: '_blank', rel: 'noopener', text: 'Ver publicada', 'aria-label': 'Ver publicada: ' + g.title }) : null))))
        : A.empty('No hay guías con ese filtro. Crea la primera con «Nueva guía».'),
        A.pager({ total, limit: LIM, offset: st.offset, go: o => { st.offset = o; list(); } }));
    }

    async function edit(id, keep) {
      if (!keep) A.say(null);
      let g = { slug: '', title: '', summary: '', content: '', category: 'perros', author_source: '', is_published: false };
      if (id) {
        A.loading(body);
        try { g = await A.rpc('admin_get_guide', { p_id: id }); }
        catch (ex) { if (A.alive(host)) A.fail(body, ex, () => edit(id, keep)); return; }
        if (!A.alive(host)) return;
      }
      let slugTouched = !!id;
      const title = E('input', { type: 'text', id: 'gu-titulo', maxlength: '160', autocomplete: 'off', value: g.title, required: true });
      const slug = E('input', { type: 'text', id: 'gu-slug', maxlength: '120', autocomplete: 'off', value: g.slug, required: true, spellcheck: 'false' });
      const cat = E('select', { id: 'gu-categoria' }, A.options(Object.keys(G.CATEGORIES).map(k => [k, G.CATEGORIES[k]]), g.category));
      const summary = E('textarea', { id: 'gu-resumen', rows: '2', maxlength: '300' }); summary.value = g.summary || '';
      const content = E('textarea', { id: 'gu-contenido', rows: '14', maxlength: '20000' }); content.value = g.content || '';
      const source = E('input', { type: 'text', id: 'gu-fuente', maxlength: '200', autocomplete: 'off', value: g.author_source || '' });
      const pub = E('input', { type: 'checkbox', id: 'gu-publicar', checked: g.is_published ? true : null });
      const count = E('small', { class: 'mut', id: 'gu-cuenta' });
      const prev = E('div', { class: 'adm-preview', id: 'gu-prev', hidden: true });
      const upd = () => { count.textContent = content.value.length + ' de 20000 caracteres'; };
      content.addEventListener('input', upd); upd();
      title.addEventListener('input', () => { if (!slugTouched) slug.value = G.slugify(title.value); });
      slug.addEventListener('input', () => { slugTouched = true; });

      function check() {
        const t = title.value.trim(), s = slug.value.trim().toLowerCase(), c = content.value.trim();
        if (t.length < 3 || t.length > 160) return [title, 'El título debe tener entre 3 y 160 caracteres.'];
        if (!G.SLUG_RE.test(s) || s.length > 120) return [slug, 'La dirección solo admite minúsculas, números y guiones (por ejemplo: cuidados-del-gato).'];
        if (summary.value.trim().length > 300) return [summary, 'El resumen admite hasta 300 caracteres.'];
        if (!c || c.length > 20000) return [content, 'El contenido debe tener entre 1 y 20000 caracteres.'];
        if (source.value.trim().length > 200) return [source, 'La fuente admite hasta 200 caracteres.'];
        return null;
      }
      const form = E('form', { class: 'adm-form', 'aria-label': id ? 'Editar guía' : 'Nueva guía', novalidate: true, onsubmit: e => {
        e.preventDefault();
        const bad = check();
        if (bad) { A.say('err', bad[1]); bad[0].focus(); return; }
        let savedId = id;
        A.run(e.currentTarget.querySelector('button[type=submit]'), 'Guardando…', async () => {
          const r = await A.rpc('admin_save_guide', { p_id: id || null, p_slug: slug.value.trim().toLowerCase(), p_title: title.value.trim(),
            p_summary: summary.value.trim(), p_content: content.value.trim(), p_category: cat.value, p_author_source: source.value.trim(), p_publish: pub.checked });
          if (typeof r === 'string' && r) savedId = r;
        }, pub.checked ? 'Guía guardada y publicada.' : 'Guía guardada como borrador: el público no la ve.').then(ok => { if (ok) edit(savedId, true); });
      } },
        A.field('Título', title), A.field('Dirección de la guía (en la web)', slug, 'Solo minúsculas, números y guiones. Si cambias la dirección de una guía publicada, los enlaces anteriores dejan de funcionar.'),
        A.field('Categoría', cat), A.field('Resumen (máx. 300)', summary),
        E('div', null, A.field('Contenido', content, 'Párrafos separados por una línea en blanco. Una línea que empieza con «## » es un subtítulo. No se acepta HTML.'), count),
        A.field('Fuente o autoría (opcional)', source, 'Por ejemplo: «Revisada por MVZ Nombre Apellido, cédula …». Si el contenido aún no lo revisa un veterinario, dilo aquí.'),
        E('label', { class: 'adm-f adm-check' }, pub, E('span', { text: 'Publicar (visible para todo el público)' })),
        E('div', { class: 'adm-actions' },
          E('button', { class: 'btn coral', type: 'submit', text: 'Guardar guía' }),
          E('button', { class: 'btn ghost', type: 'button', id: 'gu-vista', text: 'Vista previa', onclick: () => {
            prev.hidden = !prev.hidden;
            if (!prev.hidden) UI.put(prev, E('h3', { text: title.value.trim() || '(sin título)' }), summary.value.trim() ? E('p', { class: 'mut', text: summary.value.trim() }) : null, G.blocks(content.value));
          } }),
          E('button', { class: 'btn ghost', type: 'button', text: 'Cancelar', onclick: () => { A.say(null); list(); } })));
      UI.put(body,
        E('p', null, E('button', { class: 'btn ghost sm', type: 'button', text: '← Volver a la lista', onclick: () => { A.say(null); list(); } })),
        E('div', { class: 'card adm-card' }, E('h3', { text: id ? 'Editar guía' : 'Nueva guía' }),
          id ? E('p', null, g.is_published ? A.badge('Publicada', 'ok') : A.badge('Borrador', 'warn'), ' ', g.is_published && g.published_at ? E('small', { class: 'mut', text: 'desde ' + A.d(g.published_at) }) : null) : null,
          E('p', { class: 'mut', text: 'Las guías son información general: no diagnostican ni sustituyen la consulta con un veterinario. Revisa el contenido con un profesional antes de publicarlo.' }),
          form, prev),
        id ? E('div', { class: 'card adm-card' }, E('h3', { text: 'Eliminar guía' }),
          E('p', { class: 'mut', text: 'Borra la guía para siempre. Si solo quieres que el público deje de verla, desmarca «Publicar» y guarda.' }),
          A.confirm('Eliminar guía', '¿Eliminar esta guía para siempre?', btn => A.run(btn, 'Eliminando…', () => A.rpc('admin_delete_guide', { p_id: id }), 'Guía eliminada.').then(ok => { if (ok) list(); }), 'btn coral sm')) : null);
      title.focus();
    }

    if (A.params.id) await edit(A.params.id); else await list();
  }
});
})();
