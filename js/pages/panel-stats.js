/*
  Panel de aliados · Estadísticas básicas (Etapa 5): visitas a la ficha y clics en «Ver ubicación» / «Cómo llegar».
  Son contadores anónimos por día (no se guarda quién visitó). Son aproximados: una persona cuenta una vez al día por ficha,
  tus propias visitas no cuentan y solo se cuentan fichas aprobadas.
*/
(() => {
'use strict';
const TP = window.TP, UI = window.TPUI;
if (!TP || !UI) return;
const el = UI.el;
const MODS = (window.TPPanelMods = window.TPPanelMods || {});
const DAYS_SHOWN = 14, DAYS_TOTAL = 30;

async function render(host, ctx) {
  const biz = ctx.biz, today = UI.todayMx(), from = UI.addDays(today, -(DAYS_TOTAL - 1));
  host.replaceChildren(el('h3', { text: '📊 Estadísticas básicas' }), el('p', { class: 'mut', text: 'Cargando…' }));
  let rows;
  try {
    rows = await TP.rest('/business_daily_stats', { query: 'select=day,views,map_clicks&business_id=eq.' + biz.id + '&day=gte.' + from + '&order=day.asc&limit=60' });
    if (!Array.isArray(rows)) throw new Error('bad');
  } catch (ex) {
    host.replaceChildren(el('h3', { text: '📊 Estadísticas básicas' }), el('p', { class: 'msg err', role: 'alert', text: TP.errorMessage(ex) }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Reintentar', onclick: () => render(host, ctx) }));
    return;
  }
  const byDay = new Map(rows.map(r => [r.day, r]));
  const sum = (days, key) => { let t = 0; for (let i = 0; i < days; i++) { const r = byDay.get(UI.addDays(today, -i)); if (r) t += Number(r[key]) || 0; } return t; };
  const tile = (value, label) => el('div', { class: 'card statcard' }, el('div', { class: 'big', text: String(value) }), el('small', { text: label }));

  const recent = [];
  for (let i = 0; i < DAYS_SHOWN; i++) { const d = UI.addDays(today, -i); const r = byDay.get(d); recent.push({ d, v: r ? Number(r.views) || 0 : 0, m: r ? Number(r.map_clicks) || 0 : 0 }); }
  const max = Math.max(1, ...recent.map(x => Math.max(x.v, x.m)));
  const bar = (n, cls) => { const s = el('span', { class: 'fill ' + cls }); s.style.width = Math.round((n / max) * 100) + '%'; return el('div', { class: 'sbar' }, s); };
  const empty = sum(DAYS_TOTAL, 'views') + sum(DAYS_TOTAL, 'map_clicks') === 0;

  UI.put(host,
    el('h3', { text: '📊 Estadísticas básicas' }),
    el('p', { class: 'mut', text: 'Cuántas personas abrieron la ficha de «' + biz.name + '» y cuántas tocaron «Ver ubicación» o «Cómo llegar».' }),
    biz.status === 'approved' ? null : el('p', { class: 'note', text: 'Las visitas se empiezan a contar cuando tu ficha está aprobada.' }),
    el('div', { class: 'cards statrow' }, tile(sum(7, 'views'), 'visitas a la ficha · 7 días'), tile(sum(30, 'views'), 'visitas a la ficha · 30 días'),
      tile(sum(7, 'map_clicks'), 'clics en el mapa · 7 días'), tile(sum(30, 'map_clicks'), 'clics en el mapa · 30 días')),
    empty ? el('p', { class: 'mut', text: 'Todavía no hay datos. Aparecerán aquí cuando las personas empiecen a visitar tu ficha.' })
          : el('div', { class: 'tablewrap' }, el('table', { class: 'statsday' },
              el('caption', { text: 'Últimos ' + DAYS_SHOWN + ' días' }),
              el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Día' }), el('th', { scope: 'col', text: 'Visitas' }), el('th', { scope: 'col', text: 'Clics en el mapa' }))),
              el('tbody', {}, recent.map(x => el('tr', {}, el('th', { scope: 'row', text: UI.dateEs(x.d) }),
                el('td', {}, bar(x.v, 'v'), el('span', { class: 'n', text: String(x.v) })),
                el('td', {}, bar(x.m, 'm'), el('span', { class: 'n', text: String(x.m) }))))))),
    el('p', { class: 'note', text: 'Son cifras aproximadas y anónimas: no se guarda quién visitó tu ficha. Cada persona cuenta una sola vez al día; tus propias visitas y las de fichas de demostración no se cuentan.' }));
}

MODS.stats = { render };
})();
