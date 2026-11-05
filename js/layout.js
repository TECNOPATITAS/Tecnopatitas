/* Cabecera, pie y avisos compartidos por todas las páginas. Muestra el estado de la sesión (Etapa 3). */
(()=>{
const k=document.body.dataset.page;
const NAV=[['index','Inicio','index.html'],['guias','Guías','guias.html'],['directorio','Directorio','directorio.html'],['denuncias','Denuncias','denuncias.html'],['planes','Suscripciones','planes.html'],['sobre-nosotros','Sobre nosotros','sobre-nosotros.html']];
const paw='<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true"><circle cx="5" cy="10" r="2.2"/><circle cx="9.5" cy="5.5" r="2.2"/><circle cx="14.5" cy="5.5" r="2.2"/><circle cx="19" cy="10" r="2.2"/><path d="M12 11c-3 0-6 3.5-6 6 0 2 1.8 2.5 3 2.2 1.2-.3 2-.7 3-.7s1.8.4 3 .7c1.2.3 3-.2 3-2.2 0-2.5-3-6-6-6z"/></svg>';
const bellSvg='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>';
const TP=window.TP;
const actsGuest='<a class="btn ghost sm" href="login.html">Iniciar sesión</a><a class="btn coral sm" href="registro.html">Crear cuenta</a>';
const actsUser=(href,label)=>`<a class="btn ghost sm" id="acct" href="${href}">${label}</a><button class="btn coral sm" id="logout" type="button">Salir</button>`;
document.getElementById('site-header').innerHTML=`<header class="nav"><div class="wrap bar"><a class="logo" href="index.html">${paw}TECNOPATITAS</a><button id="mbtn" aria-label="Abrir menú" aria-expanded="false">☰</button><div class="panel" id="mp"><nav class="links" aria-label="Principal">${NAV.map(n=>`<a href="${n[2]}"${n[0]===k?' aria-current="page"':''}>${n[1]}</a>`).join('')}</nav><div class="acts" id="acts">${TP&&TP.hasSession()?actsUser('perfil.html','Mi cuenta'):actsGuest}</div></div><a class="bell" id="bell" href="notificaciones.html" aria-label="Notificaciones"${TP&&TP.hasSession()?'':' hidden'}>${bellSvg}<span class="bell-n" id="bell-n" hidden></span></a></div></header>`;
document.getElementById('site-footer').innerHTML=`<footer class="foot"><div class="wrap fg"><div><b>TECNOPATITAS</b><p>Cuidado, protección y bienestar de las mascotas.</p><p>Aún no hay pagos ni cobros: la contratación de planes de pago no está habilitada.</p></div><div><b>Explorar</b><ul>${NAV.map(n=>`<li><a href="${n[2]}">${n[1]}</a></li>`).join('')}</ul></div><div><b>Tu cuenta</b><ul><li><a href="login.html">Iniciar sesión</a></li><li><a href="registro.html">Crear cuenta</a></li><li><a href="recuperar.html">Recuperar contraseña</a></li><li><a href="perfil.html">Perfil</a></li></ul><b class="lg-h">Legal</b><ul><li><a href="privacidad.html">Aviso de privacidad</a></li><li><a href="terminos.html">Términos y condiciones</a></li></ul></div></div></footer>`;
const mb=document.getElementById('mbtn'),mp=document.getElementById('mp');
mb.onclick=()=>{mb.setAttribute('aria-expanded',mp.classList.toggle('open'))};

/* ---- Estado de la sesión en la cabecera y elementos por rol ---- */
if(!TP)return;
const acts=document.getElementById('acts');
function bindLogout(){const b=document.getElementById('logout');if(b)b.onclick=async()=>{b.disabled=true;await TP.signOut();location.href='index.html'}}
function guest(){acts.innerHTML=actsGuest;document.querySelectorAll('[data-only]').forEach(el=>{el.hidden=true});stopBell()}

/* ---- Campana de notificaciones (Etapa 8) ----
   · Consulta cuántas notificaciones sin leer hay: una vez al abrir la página, cada 60 s mientras la pestaña esté visible y al volver a ella.
     Usa consultas normales y NO una conexión en vivo: así cada pestaña abierta no gasta una de las ~200 conexiones simultáneas del plan gratuito.
   · Una vez al día por navegador (hora de México) pide al servidor que genere los recordatorios de vacunas, desparasitaciones y citas y los avisos de vencimiento de tu plan (también para cuentas de aliado);
     no hay ningún proceso programado, por eso se hace al visitar la página. La pantalla de Notificaciones lo hace por su cuenta.
   · El número solo es comodidad: lo que cada persona puede leer lo decide RLS en el servidor. */
const BELL_MS=60000,REM_KEY='tp-rem-v1:';
let bellTimer=null,bellUid=null,bellBusy=false,bellAgain=false,remTried=false;
function paintBell(n){
  const b=document.getElementById('bell'),c=document.getElementById('bell-n');
  if(!b||!c)return;
  c.hidden=!(n>0);c.textContent=n>99?'99+':n>0?String(n):'';
  b.setAttribute('aria-label',n>0?'Notificaciones: '+(n>99?'más de 99':n)+' sin leer':'Notificaciones: ninguna sin leer');
  b.classList.toggle('has',n>0);
}
async function pollBell(){
  if(!TP.hasSession())return;
  if(bellBusy){bellAgain=true;return}
  bellBusy=true;
  try{
    const rows=await TP.rest('/notifications',{query:'select=id&is_read=eq.false&limit=100'});
    if(Array.isArray(rows))paintBell(rows.length);
  }catch{/* sin conexión o sesión vencida: se conserva el número anterior (la guarda de la página se encarga de la sesión) */}
  finally{bellBusy=false;if(bellAgain){bellAgain=false;pollBell()}}
}
function stopBell(){
  clearInterval(bellTimer);bellTimer=null;bellUid=null;
  const b=document.getElementById('bell');if(b)b.hidden=true;
  paintBell(0);
}
async function dailyReminders(m){
  if(remTried||k==='notificaciones')return;   // la pantalla de Notificaciones los pide por su cuenta
  remTried=true;
  const day=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Mexico_City',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const key=REM_KEY+m.user.id;
  try{if(localStorage.getItem(key)===day)return}catch{/* modo privado: se pedirá una vez por página */}
  try{
    const n=await TP.rpc('generate_my_reminders');
    try{localStorage.setItem(key,day)}catch{/* */}
    if(n>0)pollBell();
  }catch{/* se reintenta al abrir otra página; no es grave */}
}
function startBell(m){
  const b=document.getElementById('bell');if(!b||!m.user)return;
  b.hidden=false;
  if(bellTimer&&bellUid===m.user.id)return;
  clearInterval(bellTimer);bellUid=m.user.id;
  pollBell();
  bellTimer=setInterval(()=>{if(!document.hidden)pollBell()},BELL_MS);
  dailyReminders(m);
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&bellTimer)pollBell()});
window.addEventListener('online',()=>{if(bellTimer)pollBell()});
window.addEventListener('tp-notifs',()=>{if(bellTimer)pollBell()});   // la pantalla de Notificaciones avisa cuando marca o borra algo
async function refresh(){
  if(!TP.hasSession()){guest();return}
  try{
    const m=await TP.me();
    if(!m){guest();return}
    const label=m.isAdmin?'Administración':m.accountType==='business'?'Mi negocio':'Mi cuenta';
    acts.innerHTML=actsUser(TP.homeFor(m),label);bindLogout();
    const roles=[m.isAdmin?'admin':null,m.accountType].filter(Boolean);
    document.querySelectorAll('[data-only]').forEach(el=>{el.hidden=!roles.includes(el.dataset.only)});
    startBell(m);
  }catch(e){
    if(e&&(e.code==='session_expired'))guest();   // si es un fallo de red se conserva la sesión y se reintenta al recargar
  }
}
bindLogout();
TP.ready.then(refresh);
TP.onAuthChange(()=>refresh());
})();
