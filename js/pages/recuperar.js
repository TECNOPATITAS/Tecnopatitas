/* Recuperar contraseña (Etapa 3). No revela si el correo existe y no promete un envío que no puede confirmar. */
(()=>{
const TP=window.TP,UI=window.TPUI,f=document.getElementById('f-recuperar'),box=document.getElementById('msg'),btn=f.querySelector('button[type=submit]');
if(!TP||TP.configError){UI.msg(box,'err',TP?TP.errorMessage({code:'config'}):'El sitio no está configurado correctamente.');btn.disabled=true;return}
f.addEventListener('submit',async e=>{
  e.preventDefault();
  if(btn.disabled)return;
  const email=f.email.value.trim().toLowerCase();
  if(TP.checkEmail(email)){UI.msg(box,'err','Escribe un correo electrónico válido.');return}
  UI.msg(box,null);UI.busy(btn,true,'Enviando…');
  try{
    await TP.resetPassword(email,new URL('nueva-contrasena.html',location.href).href);
    UI.msg(box,'ok','Solicitud recibida. Si existe una cuenta con ese correo, recibirás un enlace para elegir una nueva contraseña (puede tardar unos minutos; revisa también spam). El enlace vence en poco tiempo y solo sirve una vez.');
    f.reset();
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
  finally{UI.busy(btn,false)}
});
})();
