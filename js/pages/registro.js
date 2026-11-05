/* Registro de cuenta (Etapa 3). El tipo de cuenta solo puede ser dueño o aliado; el servidor lo vuelve a sanear. */
(()=>{
const TP=window.TP,UI=window.TPUI,f=document.getElementById('f-registro'),box=document.getElementById('msg'),btn=f.querySelector('button[type=submit]');
if(!TP||TP.configError){UI.msg(box,'err',TP?TP.errorMessage({code:'config'}):'El sitio no está configurado correctamente.');btn.disabled=true;return}
const CAP=window.TPCaptcha;let cap=null;                    // anti-robots (Turnstile): solo si hay «site key» en config.js
if(CAP&&CAP.configured)cap=CAP.mount(document.getElementById('captcha-host'),{onStatus:(k,m)=>{if(k==='error')UI.msg(box,'err',m)}});
TP.ready.then(async()=>{                                    // si ya hay sesión, no tiene caso registrarse
  if(TP.hasSession()){try{const m=await TP.me();if(m)location.replace(TP.homeFor(m))}catch{}}
});
f.addEventListener('submit',async e=>{
  e.preventDefault();
  if(btn.disabled)return;
  const name=f.nombre.value.trim(),email=f.email.value.trim().toLowerCase(),pw=f.pw.value,pw2=f.pw2.value,tipo=f.tipo.value;
  let err=null;
  if(name.length<2||name.length>80)err='Escribe tu nombre (entre 2 y 80 caracteres).';
  else if((err=TP.checkEmail(email)));
  else if(!['owner','business'].includes(tipo))err='Selecciona el tipo de cuenta.';
  else if((err=TP.checkPassword(pw,email)));
  else if(pw!==pw2)err='Las contraseñas no coinciden.';
  else if(!f.consent.checked)err='Debes aceptar el uso de tus datos para crear la cuenta.';
  if(!err&&cap&&!cap.token()){err='Completa la verificación anti-robots antes de continuar.';cap.retry()}
  if(err){UI.msg(box,'err',err);return}
  UI.msg(box,null);UI.busy(btn,true,'Creando cuenta…');
  try{
    const r=await TP.signUp({email,password:pw,displayName:name,accountType:tipo,redirectTo:new URL('login.html?confirmado=1',location.href).href,captchaToken:cap?cap.token():undefined});
    if(r.session){const m=await TP.me(true);location.replace(TP.homeFor(m));return}
    f.reset();
    UI.msg(box,'ok','Recibimos tu registro. Para activar la cuenta, confirma tu correo con el mensaje que te enviaremos (revisa también spam). Mientras no lo confirmes no podrás iniciar sesión. Si no llega en unos minutos, inténtalo de nuevo más tarde.');
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{UI.busy(btn,false);if(cap)cap.reset()}              // cada verificación sirve una sola vez
});
})();
