/* Elegir nueva contraseña desde el enlace del correo (Etapa 3). Solo funciona si se llegó por un enlace de recuperación. */
(()=>{
const TP=window.TP,UI=window.TPUI,f=document.getElementById('f-nueva'),box=document.getElementById('msg'),btn=f.querySelector('button[type=submit]');
if(!TP||TP.configError){UI.msg(box,'err',TP?TP.errorMessage({code:'config'}):'El sitio no está configurado correctamente.');f.hidden=true;return}
(async()=>{
  await TP.ready;
  if(TP.callback.type!=='recovery'){
    f.hidden=true;
    UI.msg(box,'err',TP.callback.error?TP.errorMessage({code:'otp_expired'}):'Abre esta página desde el enlace que te enviamos por correo. Si no lo tienes, solicita uno nuevo.');
    document.getElementById('again').hidden=false;
  }
})();
f.addEventListener('submit',async e=>{
  e.preventDefault();
  if(btn.disabled)return;
  const pw=f.pw.value,pw2=f.pw2.value,s=await TP.getSession();
  let err=TP.checkPassword(pw,s&&s.user&&s.user.email);
  if(!err&&pw!==pw2)err='Las contraseñas no coinciden.';
  if(err){UI.msg(box,'err',err);return}
  UI.msg(box,null);UI.busy(btn,true,'Guardando…');
  try{
    await TP.updatePassword(pw);
    UI.msg(box,'ok','Contraseña actualizada. Te llevamos a tu cuenta…');
    f.hidden=true;
    const m=await TP.me(true);setTimeout(()=>location.replace(TP.homeFor(m)),1200);
  }catch(ex){UI.msg(box,'err',TP.errorMessage(ex));UI.busy(btn,false)}
});
})();
