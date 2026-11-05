/*
  Notificaciones (Etapa 8).
  · Lista las notificaciones de la propia persona (RLS: nadie más las ve), las marca como leídas, las borra y guarda las preferencias.
  · Notificaciones nuevas al instante con Supabase Realtime (js/tp-realtime.js), filtradas a las de esta persona. Si la conexión en vivo
    falla, la página consulta cada 20 s por su cuenta: funciona igual, solo que con unos segundos de retraso.
  · Al abrir la pantalla se piden al servidor los recordatorios de vacunas, desparasitaciones y citas (no hay proceso programado).
  · Todo texto que viene del servidor se escribe como TEXTO (textContent mediante UI.el): jamás se interpreta como HTML.
    Los enlaces se aceptan solo si son páginas conocidas de este mismo sitio (nunca «//otro-sitio», «javascript:» ni direcciones externas).
  · Por ahora no se envía ningún correo: el interruptor de correo aparece apagado y bloqueado.
*/
(()=>{
const TP=window.TP,UI=window.TPUI,RT=window.TPRT;
if(!TP||!UI)return;
const $=id=>document.getElementById(id),el=UI.el;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE=50,POLL_MS=20000;
const COLS='id,type,title,body,link,is_read,read_at,created_at';
const TYPES={
  vacuna:['💉','Vacuna','ok'],desparasitacion:['💊','Desparasitación','ok'],cita:['📅','Cita','info'],
  promocion:['🏷️','Promoción','mute'],suscripcion:['⭐','Suscripción','mute'],mensaje:['💬','Mensaje','info'],aviso:['📢','Aviso','warn']
};
const PAGES=['index','guias','directorio','denuncias','planes','sobre-nosotros','perfil','mascota','carnet','qr','chat','notificaciones','panel-aliado','admin'];
const LINK_RE=/^([a-z0-9-]{1,40})\.html(\?[a-z0-9._=&-]{1,100})?(#[a-z0-9._-]{1,60})?$/;
const PREF_KEYS=['vacuna','desparasitacion','cita','promocion','suscripcion','mensaje'];
const box=$('nt-msg'),pbox=$('p-msg');

let me=null,items=new Map(),hasMore=false,loaded=false,filter='all',rtStatus='connecting',pollTimer=null,sub=null;
let syncing=false,again=false,loadingMore=false,bulk=false,confirmTimer=null,remBusy=false,savedPrefs={};
const pending=new Set();
const ms=v=>Date.parse(v)||0;

/* ---------- Validación de lo que llega del servidor ---------- */
function safeLink(l){
  if(typeof l!=='string'||l.length>200)return null;
  const m=LINK_RE.exec(l);
  return m&&PAGES.includes(m[1])?l:null;
}
function clean(r){
  if(!r||typeof r!=='object'||!UUID.test(r.id||'')||!TYPES[r.type]||typeof r.title!=='string'||!r.title||typeof r.created_at!=='string'||!ms(r.created_at))return null;
  return {id:r.id,type:r.type,title:r.title,body:typeof r.body==='string'&&r.body?r.body:null,link:safeLink(r.link),is_read:r.is_read===true,created_at:r.created_at};
}
const cmp=(a,b)=>ms(b.created_at)-ms(a.created_at)||(a.id<b.id?1:a.id>b.id?-1:0);   // más nueva primero
const sorted=()=>Array.from(items.values()).sort(cmp);
const announce=t=>{$('nt-announce').textContent='';setTimeout(()=>{$('nt-announce').textContent=t},30)};
const tell=()=>window.dispatchEvent(new Event('tp-notifs'));            // avisa a la campana de la cabecera

/* ---------- Dibujar ---------- */
function focusKey(){
  const a=document.activeElement;
  if(a&&a.closest&&a.closest('#nt-list')&&a.dataset&&a.dataset.act){const li=a.closest('li');return {id:li&&li.dataset.id,act:a.dataset.act}}
  return null;
}
function restoreFocus(k,neighbours){
  if(!k)return;
  const list=$('nt-list');
  let b=list.querySelector('li[data-id="'+k.id+'"] [data-act="'+k.act+'"]');
  if(!b)for(const id of neighbours){b=list.querySelector('li[data-id="'+id+'"] [data-act]');if(b)break}
  if(b)b.focus();
  else{const h=$('nt-h');h.tabIndex=-1;h.focus()}            // no queda nada que enfocar: el foco va al título de la sección
}
const shownIds=()=>{const all=sorted();return (filter==='unread'?all.filter(n=>!n.is_read):all).map(n=>n.id)};
/* Qué enfocar si la fila desaparece: primero las que estaban debajo, luego las de arriba */
function neighboursOf(id){const ids=shownIds(),i=ids.indexOf(id);return i<0?ids:ids.slice(i+1).concat(ids.slice(0,i).reverse())}
function itemEl(n){
  const [ic,lab,kind]=TYPES[n.type];
  const busy=pending.has(n.id)?'true':null;
  return el('li',{class:'nt-item'+(n.is_read?'':' unread'),dataset:{id:n.id},'aria-busy':busy},
    el('span',{class:'nt-ic','aria-hidden':'true',text:ic}),
    el('div',{class:'nt-body'},
      el('div',{class:'nt-top'},
        el('b',{class:'nt-title',text:n.title}),
        n.is_read?null:el('span',{class:'badge warn',text:'Nueva'}),
        el('span',{class:'badge '+kind,text:lab})),
      n.body?el('p',{class:'nt-txt',text:n.body}):null,
      el('time',{class:'when',datetime:n.created_at,text:UI.dateTimeEs(n.created_at)}),
      el('div',{class:'nt-actions'},
        n.link?el('a',{class:'btn sm',href:n.link,'aria-label':'Ver: '+n.title,text:'Ver',onclick:e=>followLink(e,n)}):null,
        el('button',{class:'btn ghost sm',type:'button',dataset:{act:'toggle'},'aria-disabled':busy,'aria-label':(n.is_read?'Marcar como no leída: ':'Marcar como leída: ')+n.title,
          text:n.is_read?'Marcar como no leída':'Marcar como leída',onclick:()=>{if(!pending.has(n.id))toggleRead(n.id)}}),
        el('button',{class:'btn ghost sm',type:'button',dataset:{act:'del'},'aria-disabled':busy,'aria-label':'Borrar: '+n.title,text:'Borrar',onclick:()=>{if(!pending.has(n.id))deleteOne(n.id)}}))));
}
function render(keep){
  const fk=(keep&&keep.fk)||focusKey(),near=(keep&&keep.near)||null,all=sorted(),shown=filter==='unread'?all.filter(n=>!n.is_read):all;
  const unread=all.filter(n=>!n.is_read).length,read=all.length-unread;
  $('nt-loading').hidden=loaded;
  UI.put($('nt-list'),shown.map(itemEl));
  const empty=loaded&&shown.length===0;
  $('nt-empty').hidden=!empty;
  if(empty){
    const f=filter==='unread'&&all.length>0;
    $('nt-empty-h').textContent=f?'No tienes notificaciones sin leer':'No tienes notificaciones';
    $('nt-empty-p').textContent=f?'Estás al día. Pulsa «Todas» para ver las que ya leíste.':'Aquí verás los recordatorios de vacunas, desparasitaciones y citas, las respuestas de atención al cliente y los avisos importantes.';
  }
  $('nt-count').hidden=!loaded||all.length===0;
  $('nt-count').textContent=(unread?unread+' sin leer':'Todo al día: no tienes notificaciones sin leer')+' · '+all.length+(all.length===1?' notificación':' notificaciones')+(hasMore?' cargadas (hay más antiguas)':'');
  $('nt-more-wrap').hidden=!(loaded&&hasMore);
  $('nt-readall').disabled=!loaded||bulk||(unread===0&&!hasMore);
  $('nt-delread').disabled=!loaded||bulk||(read===0&&!hasMore);
  const f1=$('nt-f-all'),f2=$('nt-f-unread');
  f1.setAttribute('aria-pressed',String(filter==='all'));f2.setAttribute('aria-pressed',String(filter==='unread'));
  renderLive();
  restoreFocus(fk,near||shown.map(n=>n.id));
}
function renderLive(){
  const t=$('nt-live');
  t.textContent=rtStatus==='live'?'● En vivo: las notificaciones nuevas aparecen solas.':
    rtStatus==='connecting'||!loaded?'':'Sin conexión en vivo. Revisamos si hay notificaciones nuevas cada 20 segundos.';
  t.classList.toggle('on',rtStatus==='live');
}

/* ---------- Cargar y sincronizar ---------- */
function addRows(rows){
  let n=0;
  for(const raw of rows||[]){const r=clean(raw);if(!r)continue;if(!items.has(r.id))n++;items.set(r.id,r)}
  return n;
}
async function loadFirst(){
  const rows=await TP.rest('/notifications',{query:'select='+COLS+'&order=created_at.desc,id.desc&limit='+PAGE});
  const arr=Array.isArray(rows)?rows:[];
  items=new Map();addRows(arr);hasMore=arr.length>=PAGE;loaded=true;render();
}
/* Une la primera página con lo que ya se ve: añade lo nuevo, actualiza «leída» y quita lo que ya no existe (borrado en otra pestaña). */
async function syncOnce(){
  const rows=await TP.rest('/notifications',{query:'select='+COLS+'&order=created_at.desc,id.desc&limit='+PAGE});
  const arr=Array.isArray(rows)?rows:[];
  const got=new Set();let added=0,first=null;
  for(const raw of arr){
    const r=clean(raw);if(!r)continue;got.add(r.id);
    if(!items.has(r.id)){added++;if(!first)first=r}
    items.set(r.id,r);
  }
  const full=arr.length>=PAGE,last=arr.length?clean(arr[arr.length-1]):null;
  for(const [id,n] of Array.from(items)){
    if(got.has(id))continue;
    if(!full||(last&&cmp(n,last)<0))items.delete(id);        // está dentro del tramo que acabamos de leer y no vino: ya no existe
  }
  if(!hasMore&&full)hasMore=true;
  if(!loaded){loaded=true;UI.msg(box,null)}
  render();
  if(added&&first)announce('Nueva notificación: '+first.title);
}
const signature=()=>sorted().map(n=>n.id+(n.is_read?'1':'0')).join(',');
async function queueSync(){
  if(syncing){again=true;return}
  syncing=true;
  const before=signature();
  try{do{again=false;await syncOnce()}while(again);if(signature()!==before)tell()}
  catch(ex){if(!loaded){UI.msg(box,'err',TP.errorMessage(ex));startPoll()}}
  finally{syncing=false}
}
async function loadMore(){
  const all=sorted(),oldest=all[all.length-1],btn=$('nt-more');
  if(loadingMore||!oldest)return;
  loadingMore=true;btn.disabled=true;
  try{
    const t=encodeURIComponent(oldest.created_at);
    const rows=await TP.rest('/notifications',{query:'select='+COLS+'&or=(created_at.lt.'+t+',and(created_at.eq.'+t+',id.lt.'+oldest.id+'))&order=created_at.desc,id.desc&limit='+PAGE});
    const arr=Array.isArray(rows)?rows:[];
    addRows(arr);hasMore=arr.length>=PAGE;render();
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{loadingMore=false;btn.disabled=false}
}

/* ---------- Acciones ---------- */
function drop(id){items.delete(id)}
function markBusy(id,on){
  const li=$('nt-list').querySelector('li[data-id="'+id+'"]');if(!li)return;
  if(on)li.setAttribute('aria-busy','true');else li.removeAttribute('aria-busy');
  li.querySelectorAll('[data-act]').forEach(b=>{if(on)b.setAttribute('aria-disabled','true');else b.removeAttribute('aria-disabled')});
}
async function setRead(id,val){
  const n=items.get(id);if(!n||pending.has(id))return false;
  const keep={fk:focusKey(),near:neighboursOf(id)};
  pending.add(id);markBusy(id,true);
  try{
    const r=await TP.rest('/notifications',{method:'PATCH',query:'id=eq.'+id+'&select=id,is_read',body:{is_read:val},prefer:'return=representation'});
    const row=Array.isArray(r)?r[0]:null;
    if(!row)drop(id);                                       // ya no existe (se borró desde otra pestaña)
    else{const cur=items.get(id);if(cur)cur.is_read=row.is_read===true}
    return !!row;
  }finally{pending.delete(id);render(keep);tell()}
}
async function toggleRead(id){
  const n=items.get(id);if(!n)return;
  UI.msg(box,null);
  try{
    const ok=await setRead(id,!n.is_read);
    if(!ok)UI.msg(box,'info','Esa notificación ya no existe.');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
}
async function deleteOne(id){
  const n=items.get(id);if(!n||pending.has(id))return;
  const keep={fk:focusKey(),near:neighboursOf(id)};
  UI.msg(box,null);pending.add(id);markBusy(id,true);
  try{
    await TP.rest('/notifications',{method:'DELETE',query:'id=eq.'+id+'&select=id',prefer:'return=representation'});
    drop(id);announce('Notificación borrada.');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{pending.delete(id);render(keep);tell()}
}
async function followLink(e,n){
  if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||n.is_read||!n.link)return;
  e.preventDefault();
  const href=n.link;
  try{await Promise.race([setRead(n.id,true),new Promise(r=>setTimeout(r,1500))])}catch{/* igual se abre la página */}
  location.href=href;
}
async function markAllRead(){
  if(bulk)return;
  bulk=true;UI.msg(box,null);UI.busy($('nt-readall'),true,'Marcando…');
  try{
    const r=await TP.rest('/notifications',{method:'PATCH',query:'is_read=eq.false&select=id',body:{is_read:true},prefer:'return=representation'});
    const n=Array.isArray(r)?r.length:0;
    for(const v of items.values())v.is_read=true;
    UI.msg(box,'ok',n?(n===1?'Listo: 1 notificación marcada como leída.':'Listo: '+n+' notificaciones marcadas como leídas.'):'No había notificaciones sin leer.');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{bulk=false;UI.busy($('nt-readall'),false);render();tell()}
}
function resetConfirm(){clearTimeout(confirmTimer);const b=$('nt-delread');b.dataset.confirm='';b.textContent='Borrar las leídas'}
async function deleteRead(){
  const b=$('nt-delread');
  if(bulk)return;
  if(b.dataset.confirm!=='1'){                              // primer clic: pide confirmar (sin ventanas emergentes)
    b.dataset.confirm='1';b.textContent='Confirmar: borrar las leídas';
    UI.msg(box,'info','¿Borrar todas las notificaciones que ya leíste? No se puede deshacer. Pulsa «Confirmar: borrar las leídas».');
    clearTimeout(confirmTimer);confirmTimer=setTimeout(()=>{resetConfirm();UI.msg(box,null)},6000);return;
  }
  resetConfirm();bulk=true;UI.busy(b,true,'Borrando…');
  try{
    const r=await TP.rest('/notifications',{method:'DELETE',query:'is_read=eq.true&select=id',prefer:'return=representation'});
    const n=Array.isArray(r)?r.length:0;
    for(const [id,v] of Array.from(items))if(v.is_read)items.delete(id);
    UI.msg(box,'ok',n?(n===1?'Listo: 1 notificación borrada.':'Listo: '+n+' notificaciones borradas.'):'No había notificaciones leídas.');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{bulk=false;UI.busy(b,false);render();tell();if(hasMore)queueSync()}
}
function setFilter(f){filter=f;resetConfirm();render()}

/* ---------- Recordatorios (vacunas, desparasitaciones y citas) y avisos de vencimiento del plan ---------- */
function markDay(){
  try{localStorage.setItem('tp-rem-v1:'+me.user.id,new Intl.DateTimeFormat('en-CA',{timeZone:'America/Mexico_City',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()))}catch{/* */}
}
async function runReminders(){
  if(remBusy||!me)return;
  remBusy=true;
  try{
    const n=await TP.rpc('generate_my_reminders');
    markDay();
    if(n>0)await queueSync();
  }catch{/* los recordatorios no son esenciales: si falla (p. ej. demasiadas solicitudes), la lista sigue funcionando */}
  finally{remBusy=false}
}

/* ---------- Tiempo real y respaldo por consulta ---------- */
function startPoll(){if(!pollTimer)pollTimer=setInterval(()=>{if(!document.hidden)queueSync()},POLL_MS)}
function stopPoll(){clearInterval(pollTimer);pollTimer=null}
function onStatus(s){
  rtStatus=s;renderLive();
  if(s==='live'){stopPoll();queueSync()}
  else if(s==='down')startPoll();
  else if(s==='paused')stopPoll();
}
function onChange(ch){
  if(!loaded||ch.table!=='notifications')return;
  const raw=ch.record||{};
  if(raw.user_id!==me.user.id)return;                       // el servidor ya filtra; esto es solo una segunda barrera
  const r=clean(raw);if(!r)return;
  if(ch.type==='INSERT'){
    if(items.has(r.id))return;
    items.set(r.id,r);render();announce('Nueva notificación: '+r.title);tell();
  }else if(ch.type==='UPDATE'){
    const cur=items.get(r.id);
    if(cur){cur.is_read=r.is_read;render();tell()}
    else queueSync();
  }
}

/* ---------- Preferencias ---------- */
function paintPrefs(prefs){
  for(const k of PREF_KEYS){
    const input=document.querySelector('#f-prefs [name="'+k+'"]');
    if(input)input.checked=!(prefs&&prefs[k]===false);
  }
}
async function loadPrefs(){
  try{
    const p=await TP.rest('/profiles',{query:'select=notification_prefs&id=eq.'+me.user.id,single:true});
    savedPrefs=p&&p.notification_prefs&&typeof p.notification_prefs==='object'&&!Array.isArray(p.notification_prefs)?p.notification_prefs:{};
    paintPrefs(savedPrefs);
    $('p-set').disabled=false;$('p-save').disabled=false;
  }catch(ex){UI.msg(pbox,'err','No pudimos cargar tus preferencias. '+TP.errorMessage(ex))}
}
async function savePrefs(e){
  e.preventDefault();
  const btn=$('p-save');
  if(btn.disabled)return;
  const prefs={aviso:true};
  for(const k of PREF_KEYS){prefs[k]=document.querySelector('#f-prefs [name="'+k+'"]').checked}
  UI.msg(pbox,null);UI.busy(btn,true,'Guardando…');
  try{
    await TP.updateProfile(me.user.id,{notification_prefs:prefs});
    const reenabled=PREF_KEYS.some(k=>savedPrefs[k]===false&&prefs[k]);
    savedPrefs=prefs;
    UI.msg(pbox,'ok','Preferencias guardadas.');
    if(reenabled)runReminders();                            // al reactivar un tipo, aparecen los recordatorios que estaban pendientes
  }catch(ex){UI.msg(pbox,'err',TP.errorMessage(ex))}
  finally{UI.busy(btn,false)}
}

/* ---------- Arranque ---------- */
(async()=>{
  await TP.ready;
  try{me=await TP.me()}catch{return}                        // la guarda (guard.js) muestra el error o redirige
  if(!me||!me.user||!UUID.test(me.user.id||''))return;
  $('nt-f-all').addEventListener('click',()=>setFilter('all'));
  $('nt-f-unread').addEventListener('click',()=>setFilter('unread'));
  $('nt-readall').addEventListener('click',markAllRead);
  $('nt-delread').addEventListener('click',deleteRead);
  $('nt-more').addEventListener('click',loadMore);
  $('f-prefs').addEventListener('submit',savePrefs);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&loaded)queueSync()});
  window.addEventListener('online',()=>{if(loaded)queueSync()});
  window.addEventListener('pagehide',()=>{if(sub)sub.close();stopPoll()});
  render();
  loadPrefs();
  if(RT){sub=RT.subscribe({name:'tp-notifs',changes:[
    {event:'INSERT',schema:'public',table:'notifications',filter:'user_id=eq.'+me.user.id},
    {event:'UPDATE',schema:'public',table:'notifications',filter:'user_id=eq.'+me.user.id}],onChange,onStatus})}
  else startPoll();
  try{await loadFirst()}catch(ex){
    UI.msg(box,'err',TP.errorMessage(ex));$('nt-loading').textContent='No pudimos cargar tus notificaciones. Lo intentaremos de nuevo en unos segundos.';startPoll();return}
  runReminders();
})();
})();
