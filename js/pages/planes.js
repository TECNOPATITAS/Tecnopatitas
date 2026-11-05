/* Suscripciones con sesión iniciada (Etapa 9): tu plan y su vigencia, solicitar un plan, tu solicitud en revisión,
   historial con la respuesta del equipo y cancelar la suscripción.
   · NO hay pagos: «Solicitar» envía una petición al equipo; si la aprueba, el plan se activa a mano, sin cargos ni datos de pago.
   · Quien no ha iniciado sesión no entra aquí: la página queda como siempre y no se hace ninguna petición a Supabase.
   · Todo lo que se escribe aquí lo vuelve a comprobar el servidor (funciones request_plan, cancel_plan_request y cancel_my_subscription):
     deshabilitar un botón es comodidad, nunca la protección.
   · Los textos que vienen del servidor (mensajes, notas del equipo) se escriben con textContent. */
(()=>{
const TP=window.TP,UI=window.TPUI,PL=window.TPPlans;
if(!TP||!UI||!PL||!TP.hasSession())return;
const E=UI.el,$=id=>document.getElementById(id);
const DAY=864e5,RENEW_MS=15*DAY;
const NAME=Object.fromEntries(PL.PLANS.map(p=>[p.id,p.n]));
const PERIOD={monthly:'mensual',yearly:'anual'};
const STATUS={pending:['En revisión','pending'],approved:['Aprobada','ok'],rejected:['Rechazada','no'],cancelled:['Cancelada por ti','off']};
const st={m:null,ent:null,reqs:[],loaded:false,error:false,form:null,busy:false,confirmCancel:false,focus:null};
const code=id=>String(id||'').replace(/-/g,'').slice(0,8).toUpperCase();
const pending=()=>st.reqs.find(r=>r.status==='pending')||null;
const sub=()=>(st.ent&&st.ent.subscription)||null;
const renewable=s=>!!s&&!!s.ends_at&&(new Date(s.ends_at)-Date.now())<=RENEW_MS;
const daysLeft=s=>Math.max(0,Math.ceil((new Date(s.ends_at)-Date.now())/DAY));

/* ---------- Avisos de la pantalla ---------- */
function say(kind,text){UI.msg($('mine-msg'),kind,text)}

/* ---------- Botones de cada plan ---------- */
function openForm(p){
  st.form={plan:p.id,period:PL.yearly&&p.a?'yearly':'monthly',note:''};
  st.focus='form';say(null);paint();
}
function closeForm(){const id=st.form&&st.form.plan;st.form=null;st.focus=id?'open-'+id:null;paint()}

function formFor(p){
  const f=st.form;
  const radio=(v,label)=>E('label',{class:'ck rq-r'},E('input',{type:'radio',name:'rq-period',value:v,checked:f.period===v,dataset:v==='monthly'?{fx:'form'}:null,onchange:()=>{f.period=v}}),label);
  const nid='rq-note-'+p.id;
  return E('form',{class:'rq-form',novalidate:true,'aria-label':'Solicitar '+p.n,onsubmit:submit},
    E('fieldset',null,E('legend',{text:'Periodo que te interesa'}),
      radio('monthly','Mensual · '+PL.mxn(p.m)),
      p.a?radio('yearly','Anual · '+PL.mxn(p.a)):null),
    E('label',{for:nid},'Mensaje para el equipo (opcional)',
      E('textarea',{id:nid,rows:3,maxlength:300,value:f.note,placeholder:'Por ejemplo: cuántas mascotas tienes o qué necesitas.',oninput:e=>{f.note=e.target.value}})),
    E('p',{class:'note',text:'Enviar la solicitud no genera ningún cargo ni te pide tarjeta ni datos bancarios. El equipo la revisa y, si la aprueba, activa el plan manualmente.'}),
    E('div',{class:'row'},
      E('button',{class:'btn coral',type:'submit',text:'Enviar solicitud'}),
      E('button',{class:'btn ghost',type:'button',text:'Cancelar',onclick:closeForm})));
}

PL.cta=p=>{
  const m=st.m,aud=m&&m.accountType==='business'?1:0;
  if(!st.loaded&&!st.error)return E('button',{class:'btn',type:'button',disabled:true,text:'Cargando…'});
  if(st.error)return E('small',{class:'mut',text:'No pudimos consultar tu estado. Usa «Reintentar» arriba.'});
  if(p.g!==aud)return E('small',{class:'mut',text:p.g?'Este plan es para cuentas de aliado comercial.':'Este plan es para cuentas de dueño de mascota.'});
  const s=sub(),cur=!!s&&s.plan_id===p.id,pend=pending();
  if(p.m===0)return E('span',{class:'tag',text:s?'Plan gratuito':'Tu plan actual'});
  if(cur&&!renewable(s))return [E('span',{class:'tag',text:'Tu plan actual'}),s.ends_at?E('small',{text:'Vigente hasta el '+UI.dateMx(s.ends_at)}):null];
  if(pend)return pend.plan_id===p.id?E('span',{class:'tag pk',text:'Solicitud en revisión'})
    :E('button',{class:'btn',type:'button',disabled:true,text:'Hay una solicitud en revisión'});
  if(m.suspended)return E('button',{class:'btn',type:'button',disabled:true,text:'Cuenta suspendida'});
  if(st.form&&st.form.plan===p.id)return formFor(p);
  return E('button',{class:'btn coral',type:'button',text:cur?'Solicitar renovación':'Solicitar este plan','aria-label':(cur?'Solicitar renovación: ':'Solicitar este plan: ')+p.n,dataset:{fx:'open-'+p.id},onclick:()=>openForm(p)});
};

/* ---------- Envío y cancelaciones ---------- */
/* Ejecuta una acción del servidor sin dobles envíos: bloquea el botón, muestra el resultado y vuelve a pedir el estado real al servidor. */
async function act(btn,busyLabel,run,okText){
  if(st.busy)return;
  st.busy=true;UI.busy(btn,true,busyLabel);say(null);
  let ok=false,val;
  try{val=await run();ok=true}catch(ex){say('err',TP.hasSession()?TP.errorMessage(ex):'Tu sesión expiró. Inicia sesión de nuevo.')}   // sin sesión, el servidor responde «sin permiso»: lo correcto es decir que hay que volver a entrar
  try{await reload()}catch{/* sin conexión: se conserva lo que ya se veía */}
  if(ok){say('ok',okText(val));window.dispatchEvent(new Event('tp-notifs'))}
  st.busy=false;UI.busy(btn,false);
  st.focus=!ok&&st.form?'form':'head';applyFocus();
}
function submit(e){
  e.preventDefault();
  const f=st.form;if(!f||st.busy)return;
  if(f.note.trim().length>300){say('err','El mensaje puede tener hasta 300 caracteres.');return}
  return act(e.target.querySelector('button[type=submit]'),'Enviando…',async()=>{
    const id=await TP.rpc('request_plan',{p_plan:f.plan,p_period:f.period,p_note:f.note.trim()||null});
    st.form=null;return id;
  },id=>'Solicitud enviada (código '+code(id)+'). No se hizo ningún cargo. Te avisaremos en Notificaciones cuando el equipo responda.');
}
const cancelRequest=(r,btn)=>act(btn,'Cancelando…',()=>TP.rpc('cancel_plan_request',{p_request:r.id}),
  ()=>'Solicitud cancelada. Puedes hacer otra cuando quieras.');
const cancelSubscription=btn=>act(btn,'Cancelando…',async()=>{await TP.rpc('cancel_my_subscription');st.confirmCancel=false},
  ()=>'Suscripción cancelada. No hubo ningún cobro, así que no hay nada que reembolsar. Puedes solicitar un plan de nuevo cuando quieras.');

/* ---------- Panel «Tu plan» ---------- */
function reqItem(r){
  const [label,cls]=STATUS[r.status]||[r.status,'off'];
  const nm=NAME[r.plan_id]||r.plan_id;
  return E('li',{class:'rq-item',dataset:{status:r.status}},
    E('div',{class:'rq-top'},E('b',{text:nm}),E('span',{class:'rq-st '+cls,text:label})),
    E('small',{text:(PERIOD[r.billing_period]||'')+' · enviada el '+UI.dateMx(r.created_at)+(r.resolved_at&&r.status!=='cancelled'?' · respondida el '+UI.dateMx(r.resolved_at):'')+' · código '+code(r.id)}),
    r.user_note?E('p',{class:'rq-n'},E('b',{text:'Tu mensaje: '}),r.user_note):null,
    r.admin_note?E('p',{class:'rq-n'},E('b',{text:'Respuesta del equipo: '}),r.admin_note):null);
}
function planBox(){
  const s=sub(),pl=st.ent&&st.ent.plan,m=st.m;
  const head=E('p',{class:'mine-plan'},E('b',{text:pl?pl.name:'Sin plan'}),pl&&pl.tagline?E('small',{text:' · '+pl.tagline}):null);
  let vig;
  if(!pl)vig=E('p',{class:'mut',text:m.accountType==='business'?'Todavía no tienes un plan de aliado. Pide el que te interese más abajo.':'No pudimos determinar tu plan.'});
  else if(!s)vig=E('p',{class:'mut',text:m.accountType==='business'?'Sin vencimiento.':'Plan gratuito, sin vencimiento. Puedes pedir uno de pago más abajo; mientras no haya cobros, el equipo lo activa a mano.'});
  else if(!s.ends_at)vig=E('p',{class:'mut',text:'Sin fecha de vencimiento definida.'});
  else vig=E('p',{class:'mut'},'Vigente hasta el ',E('b',{text:UI.dateMx(s.ends_at)}),
    renewable(s)?' · te quedan '+daysLeft(s)+(daysLeft(s)===1?' día':' días')+': ya puedes solicitar la renovación.':'.');
  const kids=[head,vig];
  if(s){
    if(st.confirmCancel)kids.push(E('div',{class:'rq-confirm',role:'group','aria-label':'Confirmar cancelación'},
      E('p',{text:'¿Cancelar tu suscripción a '+(pl?pl.name:'este plan')+'? Perderás sus beneficios de inmediato. No hubo cobros, así que no hay nada que reembolsar.'}),
      E('div',{class:'row'},
        E('button',{class:'btn coral',type:'button',text:'Sí, cancelar mi suscripción',dataset:{fx:'cancel-yes'},onclick:e=>cancelSubscription(e.currentTarget)}),
        E('button',{class:'btn ghost',type:'button',text:'No, conservarla',onclick:()=>{st.confirmCancel=false;st.focus='cancel-ask';paint()}}))));
    else kids.push(E('div',{class:'row'},E('button',{class:'btn ghost sm',type:'button',text:'Cancelar mi suscripción',dataset:{fx:'cancel-ask'},onclick:()=>{st.confirmCancel=true;st.focus='cancel-yes';say(null);paint()}})));
  }
  return E('div',{class:'card mine-card'},kids);
}
function pendingBox(){
  const r=pending();if(!r)return null;
  return E('div',{class:'card mine-card rq-pend','aria-label':'Solicitud en revisión'},
    E('h3',{text:'Solicitud en revisión'}),
    E('p',null,E('b',{text:NAME[r.plan_id]||r.plan_id}),' · '+(PERIOD[r.billing_period]||'')+' · enviada el '+UI.dateMx(r.created_at)+' · código '+code(r.id)),
    r.user_note?E('p',{class:'rq-n'},E('b',{text:'Tu mensaje: '}),r.user_note):null,
    E('p',{class:'mut',text:'El equipo la revisará pronto. Mientras tanto no puedes enviar otra. No genera ningún cargo.'}),
    E('div',{class:'row'},E('button',{class:'btn ghost sm',type:'button',text:'Cancelar solicitud',dataset:{fx:'cancel-req'},onclick:e=>cancelRequest(r,e.currentTarget)})));
}
function renderMine(){
  const body=$('mine-body');if(!body)return;
  if(st.error){
    UI.put(body,E('div',{class:'card mine-card'},E('p',{text:'No pudimos consultar tu plan en este momento.'}),
      E('div',{class:'row'},E('button',{class:'btn coral sm',type:'button',text:'Reintentar',onclick:e=>{UI.busy(e.currentTarget,true,'Consultando…');st.error=false;boot()}}))));
    return;
  }
  if(!st.loaded){UI.put(body,E('p',{class:'mut',role:'status',text:'Cargando tu plan…'}));return}
  const done=st.reqs.filter(r=>r.status!=='pending');
  UI.put(body,planBox(),pendingBox(),
    done.length?E('div',{class:'mine-hist'},E('h3',{text:'Tus solicitudes anteriores'}),E('ul',{class:'rq-list'},done.map(reqItem))):null);
}

/* ---------- Carga y dibujo ---------- */
function applyFocus(){
  const k=st.focus;st.focus=null;if(!k)return;
  const t=k==='head'?$('mine-h'):document.querySelector('[data-fx="'+k+'"]');
  if(t&&t.focus)t.focus();
}
function paint(){PL.render();renderMine();applyFocus()}
async function reload(){
  const [ent,reqs]=await Promise.all([
    TP.rpc('my_entitlements'),
    TP.rest('/plan_requests',{query:'select=id,plan_id,billing_period,status,user_note,admin_note,created_at,resolved_at&user_id=eq.'+encodeURIComponent(st.m.user.id)+'&order=created_at.desc&limit=25'})]);   // el filtro importa: un administrador puede LEER las solicitudes de todos (RLS), pero aquí solo van las suyas
  st.ent=ent||{plan:null,subscription:null};st.reqs=Array.isArray(reqs)?reqs:[];st.loaded=true;st.error=false;
  paint();
}
function showAsVisitor(){PL.cta=null;st.m=null;$('mine').hidden=true;PL.render()}
async function boot(){
  let m=null;
  try{m=await TP.me()}catch(ex){
    if(ex&&ex.code==='session_expired'){showAsVisitor();return}
    st.error=true;st.loaded=false;paint();return                 // fallo de red: se puede reintentar
  }
  if(!m){showAsVisitor();return}                                   // sesión sin perfil: la página queda como la ve un visitante
  st.m=m;
  const note=$('stage-note');
  if(note)UI.put(note,E('b',{text:'La contratación y los cobros automáticos todavía no están habilitados.'}),' Puedes enviar una solicitud: el equipo la revisa y, si la aprueba, activa el plan manualmente, sin cargos ni datos de pago.');
  try{await reload()}catch(ex){
    if(ex&&ex.code==='session_expired'){showAsVisitor();return}
    st.error=true;st.loaded=false;paint();
  }
}

/* ---------- Arranque ---------- */
const mine=$('mine');
if(!mine)return;
mine.append(E('h2',{id:'mine-h',tabindex:'-1',text:'Tu plan'}),E('div',{id:'mine-msg',class:'msg',hidden:true}),E('div',{id:'mine-body'}));
mine.hidden=false;
renderMine();
TP.ready.then(boot);
})();
