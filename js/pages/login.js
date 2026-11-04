/* Inicio de sesión (Etapa 3). El parámetro ?next= solo acepta páginas internas conocidas (sin redirecciones externas). */
(()=>{
const TP=window.TP,UI=window.TPUI,f=document.getElementById('f-login'),box=document.getElementById('msg'),btn=f.querySelector('button[type=submit]');
if(!TP||TP.configError){UI.msg(box,'err',TP?TP.errorMessage({code:'config'}):'El sitio no está configurado correctamente.');btn.disabled=true;return}
const q=new URLSearchParams(location.search);
function go(m){const n=TP.safeNext(q.get('next'));location.replace(n&&UI.canOpen(n,m)?n:TP.homeFor(m))}
(async()=>{
  await TP.ready;
  if(TP.callback.error)UI.msg(box,'err','El enlace venció o ya se usó. Si ya confirmaste tu correo, inicia sesión; si no, solicita ayuda o regístrate de nuevo.');
  if(TP.hasSession()){try{const m=await TP.me();if(m){go(m);return}}catch{}}
  if(q.get('confirmado')&&!TP.callback.error)UI.msg(box,'info','Si ya confirmaste tu correo, inicia sesión para continuar.');
})();
f.addEventListener('submit',async e=>{
  e.preventDefault();
  if(btn.disabled)return;
  const email=f.email.value.trim().toLowerCase(),pw=f.pw.value;
  if(TP.checkEmail(email)){UI.msg(box,'err','Escribe un correo electrónico válido.');return}
  if(!pw){UI.msg(box,'err','Escribe tu contraseña.');return}
  UI.msg(box,null);UI.busy(btn,true,'Entrando…');
  try{await TP.signIn(email,pw);const m=await TP.me(true);if(!m)throw new TP.TPError('session_expired');go(m)}
  catch(ex){UI.msg(box,'err',TP.errorMessage(ex));UI.busy(btn,false)}
});
})();
