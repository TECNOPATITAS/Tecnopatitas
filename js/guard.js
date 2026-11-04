/*
  Protección de páginas privadas (Etapa 3).
  Uso: <body data-guard="any|owner|business|admin">

  IMPORTANTE: esto es solo experiencia de usuario. Ocultar una página en el navegador NO protege datos:
  lo que protege son las políticas RLS y las funciones del servidor (Etapa 2), que se aplican igual
  aunque alguien salte este archivo. El rol de administrador se comprueba SIEMPRE en el servidor (is_admin()).
*/
(()=>{
const need=document.body.dataset.guard;
if(!need||!window.TP)return;
const TP=window.TP,main=document.getElementById('main'),page=(document.body.dataset.page||'index')+'.html';

function panel(title,text,links){
  main.replaceChildren();
  const s=document.createElement('section'),c=document.createElement('div'),h=document.createElement('h1'),p=document.createElement('p'),w=document.createElement('p');
  s.className='authwrap';s.style.gridTemplateColumns='1fr';c.className='card authcard';
  h.textContent=title;h.style.fontSize='1.8rem';p.textContent=text;c.append(h,p);
  (links||[]).forEach(([href,label,cls])=>{const a=document.createElement('a');a.href=href;a.className='btn '+(cls||'ghost')+' sm';a.textContent=label;a.style.marginRight='8px';w.append(a)});
  c.append(w);s.append(c);main.append(s);document.body.classList.add('tp-ok');
}
function suspendedBanner(){
  const d=document.createElement('p');d.className='stage';d.setAttribute('role','status');
  d.textContent='Tu cuenta está suspendida. Puedes consultar tu información, pero no modificarla. Si crees que es un error, contacta al administrador.';
  main.prepend(d);
}
/* Si la sesión se cierra o caduca (en otra pestaña, o por expiración), se vuelve a pedir inicio de sesión. */
TP.onAuthChange((ev,_s,meta)=>{if(ev==='SIGNED_OUT'&&!(meta&&meta.manual))location.replace('login.html?next='+encodeURIComponent(page))});
(async()=>{
  try{
    await TP.ready;
    if(TP.configError){panel('Sitio sin configurar','Falta configurar la conexión con el servidor. Avisa al administrador.');return}
    const m=await TP.me();
    if(!m){location.replace('login.html?next='+encodeURIComponent(page));return}
    const home=TP.homeFor(m);
    if(need==='admin'&&!m.isAdmin){panel('Acceso restringido','Esta sección es solo para administradores.',[[home,'Ir a mi cuenta','coral']]);return}
    if(need==='business'&&m.accountType!=='business'){panel('Solo para aliados comerciales','Esta sección es para cuentas de aliado comercial.',[[home,'Ir a mi cuenta','coral']]);return}
    if(need==='owner'&&m.accountType!=='owner'){panel('Solo para dueños de mascotas','Esta sección es para cuentas de dueño de mascota.',[[home,'Ir a mi panel','coral']]);return}
    if(m.suspended)suspendedBanner();
    document.body.classList.add('tp-ok');
  }catch(e){
    if(e&&e.code==='session_expired'){location.replace('login.html?next='+encodeURIComponent(page));return}
    panel('No se pudo verificar tu sesión',TP.errorMessage(e),[[page,'Reintentar','coral']]);
  }
})();
})();
