/*
  Atención al cliente (Etapa 7).
  · Conversaciones y mensajes de la propia persona (RLS: nadie más los ve; no hay mensajes entre usuarios).
  · Mensajes nuevos al instante con Supabase Realtime (js/tp-realtime.js). Si la conexión en vivo falla, la página consulta
    cada 15 s por su cuenta: el chat funciona igual, solo que con unos segundos de retraso.
  · Todo texto que viene del servidor se escribe como TEXTO (textContent mediante UI.el): jamás se interpreta como HTML.
  · Los límites (20 mensajes/10 min, 100/24 h, 10 conversaciones abiertas) los aplica el servidor; aquí solo se muestran sus avisos.
*/
(()=>{
const TP=window.TP,UI=window.TPUI,RT=window.TPRT;
if(!TP||!UI)return;
const $=id=>document.getElementById(id),el=UI.el;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE=50,POLL_MS=15000,MAX_TEXT=2000;
const LIST_COLS='id,user_id,subject,status,last_sender,last_message_at,created_at';
const MSG_COLS='id,conversation_id,sender_role,body,created_at';
const box=$('ch-msg');
const cp=v=>Array.from(v).length;                          // caracteres reales (un emoji cuenta 1), igual que char_length en el servidor

let me=null,convs=[],byId=new Map(),openId=null,msgs=[],msgIds=new Set(),hasMore=false,loadedList=false,listError=false;
let rtStatus='connecting',pollTimer=null,syncing=false,again=false,sending=false,creating=false,closing=false,confirmTimer=null,seen={},sub=null,listTimer=null;

/* ---------- «Visto»: solo para marcar «Nuevo» en tu propio navegador ---------- */
const seenKey=()=>'tp-chat-seen-v1:'+me.user.id;
function loadSeen(){try{const v=JSON.parse(localStorage.getItem(seenKey())||'{}');seen=v&&typeof v==='object'&&!Array.isArray(v)?v:{}}catch{seen={}}}
function saveSeen(){try{localStorage.setItem(seenKey(),JSON.stringify(seen))}catch{/* modo privado */}}
const ms=v=>Date.parse(v)||0;
const viewing=c=>c.id===openId&&!document.hidden;
const unread=c=>c.last_sender==='staff'&&!viewing(c)&&ms(c.last_message_at)>ms(seen[c.id]);
function touchSeen(){
  const c=openId&&byId.get(openId);
  if(c&&!document.hidden&&ms(c.last_message_at)>ms(seen[c.id])){seen[c.id]=c.last_message_at;saveSeen()}
}

/* ---------- Lista de conversaciones ---------- */
function stateOf(c){
  if(c.status==='cerrada')return ['Cerrada','mute'];
  return c.last_sender==='staff'?['Respondida','ok']:['Esperando respuesta','info'];
}
function sortConvs(){convs.sort((a,b)=>ms(b.last_message_at)-ms(a.last_message_at))}
function renderList(){
  const keep=document.activeElement&&document.activeElement.closest&&document.activeElement.closest('#ch-list')?document.activeElement.dataset.id:null;
  UI.put($('ch-list'),convs.map(c=>{
    const [lab,kind]=stateOf(c);
    return el('li',{},el('button',{type:'button',class:'chat-item',dataset:{id:c.id},'aria-current':c.id===openId?'true':null,onclick:()=>openConversation(c.id,true)},
      el('span',{class:'chat-item-top'},el('b',{text:c.subject}),unread(c)?el('span',{class:'badge warn',text:'Nuevo'}):null),
      el('span',{class:'chat-item-sub'},el('span',{class:'badge '+kind,text:lab}),el('small',{class:'mut',text:UI.dateTimeEs(c.last_message_at)}))));
  }));
  if(keep){const b=$('ch-list').querySelector('[data-id="'+keep+'"]');if(b)b.focus()}
  $('ch-loading').hidden=loadedList;
  $('ch-empty').hidden=!(loadedList&&convs.length===0);
}
function setConvs(rows){
  convs=rows.filter(r=>r&&UUID.test(r.id)&&typeof r.subject==='string').map(r=>({id:r.id,user_id:r.user_id,subject:r.subject,
    status:r.status==='cerrada'?'cerrada':'abierta',last_sender:r.last_sender==='staff'?'staff':'user',last_message_at:r.last_message_at,created_at:r.created_at}));
  sortConvs();byId=new Map(convs.map(c=>[c.id,c]));loadedList=true;
  for(const k of Object.keys(seen))if(!byId.has(k))delete seen[k];
}

/* ---------- Vistas (en el móvil se ve una sola columna a la vez) ---------- */
function show(kind){                                       // 'none' | 'new' | 'thread'
  $('ch-placeholder').hidden=kind!=='none';$('f-new').hidden=kind!=='new';$('ch-thread').hidden=kind!=='thread';
  $('chat').dataset.view=kind==='none'?'list':'thread';
}
function setUrl(id){try{history.replaceState(null,'',location.pathname+(id?'?c='+id:''))}catch{/* */}}
function goList(){openId=null;resetConfirm();setUrl(null);show('none');renderList();$('ch-list').querySelector('button')?.focus()}

/* ---------- Conversación abierta ---------- */
function renderHeader(){
  const c=byId.get(openId);if(!c)return;
  const [lab]=stateOf(c);
  $('th-asunto').textContent=c.subject;$('th-estado').textContent=lab;
  const closed=c.status==='cerrada',susp=!!me.suspended;
  $('f-send').hidden=closed;$('th-cerrar').hidden=closed||susp;
  $('s-texto').disabled=susp;$('s-enviar').disabled=susp||sending;
  const aviso=$('th-aviso');
  aviso.hidden=!(closed||susp);
  aviso.textContent=susp?'Tu cuenta está suspendida: puedes leer tus mensajes, pero no enviar nuevos.':'Esta conversación está cerrada. Si necesitas algo más, abre una nueva.';
  renderLive();
}
function renderLive(){
  const t=$('ch-live');
  t.textContent=rtStatus==='live'?'● En vivo: los mensajes nuevos aparecen solos.':
    rtStatus==='connecting'?'':'Sin conexión en vivo. Revisamos si hay mensajes nuevos cada 15 segundos.';
  t.classList.toggle('on',rtStatus==='live');
}
const cmpMsg=(a,b)=>ms(a.created_at)-ms(b.created_at)||(a.id<b.id?-1:a.id>b.id?1:0);
function bubble(m){
  const staff=m.sender_role==='staff';
  return el('div',{class:'bubble '+(staff?'staff':'mine')},
    el('span',{class:'who',text:staff?'Equipo TECNOPATITAS':'Tú'}),
    el('p',{class:'txt',text:m.body}),
    el('time',{class:'when',datetime:m.created_at,text:UI.dateTimeEs(m.created_at)}));
}
function renderLog(mode){                                   // mode: 'first' | 'older' | undefined
  const log=$('th-log'),prevH=log.scrollHeight,prevTop=log.scrollTop,near=prevH-prevTop-log.clientHeight<80;
  UI.put(log,msgs.length?msgs.map(bubble):el('p',{class:'mut',text:'Todavía no hay mensajes en esta conversación.'}));
  if(mode==='older')log.scrollTop=prevTop+(log.scrollHeight-prevH);
  else if(mode==='first'||near)log.scrollTop=log.scrollHeight;
  $('th-mas-wrap').hidden=!hasMore;
}
function addMessages(rows){                                 // → cuántos mensajes nuevos entraron (sin repetidos)
  let n=0;
  for(const r of rows||[]){
    if(!r||!UUID.test(r.id)||r.conversation_id!==openId||msgIds.has(r.id)||typeof r.body!=='string')continue;
    msgIds.add(r.id);n++;
    msgs.push({id:r.id,conversation_id:r.conversation_id,sender_role:r.sender_role==='staff'?'staff':'user',body:r.body,created_at:r.created_at});
  }
  if(n)msgs.sort(cmpMsg);
  return n;
}
function bump(c,row){                                       // actualiza la lista con un mensaje nuevo
  if(row.sender_role!=='staff'&&row.sender_role!=='user')return;
  if(ms(row.created_at)>=ms(c.last_message_at)){c.last_message_at=row.created_at;c.last_sender=row.sender_role;if(row.sender_role==='staff')c.status='abierta'}
  sortConvs();
}
async function loadLatest(first){
  const id=openId;if(!id)return;
  const rows=await TP.rest('/messages',{query:'select='+MSG_COLS+'&conversation_id=eq.'+id+'&order=created_at.desc,id.desc&limit='+PAGE});
  if(id!==openId)return;
  const n=addMessages(rows);
  if(first)hasMore=Array.isArray(rows)&&rows.length>=PAGE;
  if(first||n){renderLog(first?'first':undefined);touchSeen();renderList()}
}
async function loadOlder(){
  const id=openId,first=msgs[0],btn=$('th-mas');
  if(!id||!first||!UUID.test(first.id)||btn.disabled)return;
  btn.disabled=true;
  try{
    const t=encodeURIComponent(first.created_at);
    const rows=await TP.rest('/messages',{query:'select='+MSG_COLS+'&conversation_id=eq.'+id+'&or=(created_at.lt.'+t+',and(created_at.eq.'+t+',id.lt.'+first.id+'))&order=created_at.desc,id.desc&limit='+PAGE});
    if(id!==openId)return;
    addMessages(rows);hasMore=Array.isArray(rows)&&rows.length>=PAGE;renderLog('older');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{btn.disabled=false}
}
async function openConversation(id,byUser){
  const c=byId.get(id);if(!c)return;
  openId=id;msgs=[];msgIds=new Set();hasMore=false;resetConfirm();
  $('s-texto').value='';countOf($('s-texto'),$('s-cuenta'));
  show('thread');renderHeader();renderLog('first');touchSeen();renderList();setUrl(id);
  if(byUser)$('th-asunto').focus();
  UI.msg(box,null);
  try{await loadLatest(true)}catch(ex){if(id===openId)UI.msg(box,'err',TP.errorMessage(ex))}
}

/* ---------- Sincronizar con el servidor ---------- */
async function refreshList(){
  const rows=await TP.rest('/conversations',{query:'select='+LIST_COLS+'&user_id=eq.'+me.user.id+'&order=last_message_at.desc&limit=100'});
  setConvs(Array.isArray(rows)?rows:[]);
  if(openId&&!byId.has(openId)){openId=null;show('none');setUrl(null)}
  renderList();if(openId){renderHeader();touchSeen()}
  if(listError){listError=false;UI.msg(box,null)}
}
async function queueSync(){
  if(syncing){again=true;return}
  syncing=true;
  try{
    do{again=false;await refreshList();if(openId)await loadLatest(false)}while(again);
  }catch(ex){
    if(!loadedList){listError=true;UI.msg(box,'err',TP.errorMessage(ex));renderList();startPoll()}   // sin datos todavía: se reintenta solo
  }finally{syncing=false}
}
function scheduleListRefresh(){clearTimeout(listTimer);listTimer=setTimeout(queueSync,1500)}
function startPoll(){if(!pollTimer)pollTimer=setInterval(()=>{if(!document.hidden)queueSync()},POLL_MS)}
function stopPoll(){clearInterval(pollTimer);pollTimer=null}
function onStatus(s){
  rtStatus=s;renderLive();
  if(s==='live'){stopPoll();queueSync()}
  else if(s==='down')startPoll();
  else if(s==='paused')stopPoll();
}
function onChange(ch){
  if(!loadedList)return;
  const r=ch.record||{};
  if(ch.table==='messages'&&ch.type==='INSERT'){
    if(!UUID.test(r.conversation_id||''))return;
    const c=byId.get(r.conversation_id);
    if(!c){if(!me.isAdmin)scheduleListRefresh();return}      // conversación abierta desde otra pestaña
    bump(c,r);
    if(r.conversation_id===openId){const n=addMessages([r]);if(n){renderLog();touchSeen();renderHeader()}}
    renderList();
  }else if(ch.table==='conversations'){
    if(r.user_id!==me.user.id||!UUID.test(r.id||''))return;
    const c=byId.get(r.id);
    if(!c){scheduleListRefresh();return}
    if(r.status==='abierta'||r.status==='cerrada')c.status=r.status;
    if(r.last_sender==='user'||r.last_sender==='staff')c.last_sender=r.last_sender;
    if(r.last_message_at&&ms(r.last_message_at)>=ms(c.last_message_at))c.last_message_at=r.last_message_at;
    sortConvs();renderList();if(r.id===openId)renderHeader();
  }
}

/* ---------- Escribir ---------- */
function countOf(input,out){const n=cp(input.value);out.textContent=n.toLocaleString('es-MX')+' / '+MAX_TEXT.toLocaleString('es-MX');out.classList.toggle('over',n>MAX_TEXT)}
function linkCounter(input,out){input.addEventListener('input',()=>countOf(input,out));countOf(input,out)}
function ctrlEnter(input,form){input.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();form.requestSubmit()}})}

async function sendMessage(e){
  e.preventDefault();
  if(sending||me.suspended)return;
  const id=openId,c=byId.get(id),input=$('s-texto'),btn=$('s-enviar'),text=input.value.trim();
  if(!c)return;
  if(!text){UI.msg(box,'err','Escribe un mensaje antes de enviar.');input.focus();return}
  if(cp(text)>MAX_TEXT){UI.msg(box,'err','El mensaje no puede tener más de 2000 caracteres.');return}
  sending=true;UI.busy(btn,true,'Enviando…');UI.msg(box,null);
  try{
    const r=await TP.rest('/messages',{method:'POST',body:{conversation_id:id,body:text},prefer:'return=representation'});
    const row=Array.isArray(r)?r[0]:null;
    input.value='';countOf(input,$('s-cuenta'));
    if(row){bump(c,row);if(id===openId){addMessages([row]);renderLog('first');touchSeen()}renderList();renderHeader()}
    else queueSync();
  }catch(ex){
    UI.msg(box,'err',TP.errorMessage(ex));
    queueSync();                                           // p. ej. el equipo cerró la conversación mientras escribías
  }finally{sending=false;UI.busy(btn,false);if(!c||c.status!=='cerrada')input.focus();renderHeader()}
}
async function createConversation(e){
  e.preventDefault();
  if(creating||me.suspended)return;
  const f=$('f-new'),subject=$('n-asunto').value.trim(),text=$('n-texto').value.trim(),btn=$('n-enviar');
  if(cp(subject)<3||cp(subject)>120){UI.msg(box,'err','El asunto debe tener entre 3 y 120 caracteres.');$('n-asunto').focus();return}
  if(!text){UI.msg(box,'err','Escribe tu mensaje antes de enviar.');$('n-texto').focus();return}
  if(cp(text)>MAX_TEXT){UI.msg(box,'err','El mensaje no puede tener más de 2000 caracteres.');return}
  creating=true;UI.busy(btn,true,'Enviando…');UI.msg(box,null);
  try{
    const id=await TP.rpc('start_conversation',{p_subject:subject,p_body:text});
    f.reset();countOf($('n-texto'),$('n-cuenta'));
    await refreshList();
    if(typeof id==='string'&&UUID.test(id)&&byId.has(id))await openConversation(id,true);else goList();
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{creating=false;UI.busy(btn,false)}
}
function resetConfirm(){clearTimeout(confirmTimer);const b=$('th-cerrar');b.dataset.confirm='';b.textContent='Cerrar conversación'}
async function closeConversation(){
  const b=$('th-cerrar'),id=openId,c=byId.get(id);
  if(closing||!c||me.suspended)return;
  if(b.dataset.confirm!=='1'){                              // primer clic: pide confirmar (sin ventanas emergentes)
    b.dataset.confirm='1';b.textContent='Confirmar cierre';
    UI.msg(box,'info','¿Cerrar esta conversación? Pulsa «Confirmar cierre». Para escribir de nuevo tendrás que abrir otra conversación.');
    clearTimeout(confirmTimer);confirmTimer=setTimeout(()=>{resetConfirm();UI.msg(box,null)},6000);return;
  }
  closing=true;resetConfirm();UI.busy(b,true,'Cerrando…');
  try{
    const r=await TP.rest('/conversations',{method:'PATCH',query:'id=eq.'+id,body:{status:'cerrada'},prefer:'return=representation'});
    if(!Array.isArray(r)||!r.length)throw new TP.TPError('not_saved','not_saved',0);
    c.status='cerrada';UI.msg(box,'ok','Conversación cerrada.');
    renderList();if(id===openId)renderHeader();
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{closing=false;UI.busy(b,false)}
}

/* ---------- Arranque ---------- */
(async()=>{
  await TP.ready;
  try{me=await TP.me()}catch{return}                        // la guarda (guard.js) muestra el error o redirige
  if(!me||!me.user||!UUID.test(me.user.id||''))return;
  loadSeen();
  $('ch-new').disabled=!!me.suspended;
  $('ch-new').addEventListener('click',()=>{openId=null;resetConfirm();setUrl(null);renderList();show('new');$('n-asunto').focus();UI.msg(box,null)});
  $('n-cancelar').addEventListener('click',goList);
  document.querySelectorAll('[data-back]').forEach(b=>b.addEventListener('click',goList));
  $('f-new').addEventListener('submit',createConversation);
  $('f-send').addEventListener('submit',sendMessage);
  $('th-cerrar').addEventListener('click',closeConversation);
  $('th-mas').addEventListener('click',loadOlder);
  linkCounter($('n-texto'),$('n-cuenta'));linkCounter($('s-texto'),$('s-cuenta'));
  ctrlEnter($('n-texto'),$('f-new'));ctrlEnter($('s-texto'),$('f-send'));
  show('none');
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&loadedList){touchSeen();renderList();queueSync()}});
  window.addEventListener('online',()=>{if(loadedList)queueSync()});
  window.addEventListener('pagehide',()=>{if(sub)sub.close();stopPoll()});
  if(RT){sub=RT.subscribe({name:'tp-chat',changes:[{event:'INSERT',schema:'public',table:'messages'},{event:'*',schema:'public',table:'conversations'}],onChange,onStatus})}
  else startPoll();
  await queueSync();
  const want=new URLSearchParams(location.search).get('c');
  if(want&&UUID.test(want)&&byId.has(want))await openConversation(want,false);
})();
})();
