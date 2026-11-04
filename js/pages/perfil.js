/* Perfil de la cuenta (Etapa 3): datos básicos, plan vigente, cambio de contraseña y cierre de sesión. */
(()=>{
const TP=window.TP,UI=window.TPUI;
if(!TP)return;
const $=id=>document.getElementById(id);
const TIPOS={owner:'Dueño de mascota',business:'Aliado comercial'};
(async()=>{
  await TP.ready;
  let m;try{m=await TP.me()}catch{return}                    // la guarda (guard.js) ya muestra el error o redirige
  if(!m)return;
  $('p-nombre').value=m.profile.display_name||'';
  $('p-email').value=(m.user&&m.user.email)||'';
  $('p-tel').value=m.profile.phone||'';
  $('p-tipo').textContent=(m.isAdmin?'Administración · ':'')+TIPOS[m.accountType];
  if(m.suspended)document.querySelectorAll('#f-datos input:not([disabled]),#f-datos button,#f-pw input,#f-pw button').forEach(el=>{el.disabled=true});
  try{
    const ent=await TP.rpc('my_entitlements');
    const plan=ent&&ent.plan;
    $('p-plan').textContent=plan?plan.name+(plan.tagline?' · '+plan.tagline:''):
      (m.accountType==='business'?'Sin plan de aliado (lo asigna un administrador; la contratación aún no está habilitada)':'Huellita Básica');
  }catch{$('p-plan').textContent='No se pudo consultar tu plan en este momento.'}
  $('f-datos').addEventListener('submit',async e=>{
    e.preventDefault();
    const box=$('msg-datos'),btn=e.target.querySelector('button'),name=$('p-nombre').value.trim(),tel=$('p-tel').value.trim();
    if(name.length<2||name.length>80){UI.msg(box,'err','Escribe tu nombre (entre 2 y 80 caracteres).');return}
    if(tel&&!/^[0-9+() .-]{7,20}$/.test(tel)){UI.msg(box,'err','El teléfono solo puede llevar números, espacios, + ( ) . - (7 a 20 caracteres).');return}
    UI.msg(box,null);UI.busy(btn,true,'Guardando…');
    try{await TP.updateProfile(m.user.id,{display_name:name,phone:tel||null});UI.msg(box,'ok','Cambios guardados.')}
    catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
    finally{UI.busy(btn,false)}
  });
  $('f-pw').addEventListener('submit',async e=>{
    e.preventDefault();
    const box=$('msg-pw'),btn=e.target.querySelector('button'),cur=$('pw-actual').value,pw=$('pw-nueva').value,pw2=$('pw-repetir').value;
    let err=null;
    if(!cur)err='Escribe tu contraseña actual.';
    else if((err=TP.checkPassword(pw,m.user.email)));
    else if(pw!==pw2)err='Las contraseñas no coinciden.';
    else if(pw===cur)err='La nueva contraseña debe ser distinta de la actual.';
    if(err){UI.msg(box,'err',err);return}
    UI.msg(box,null);UI.busy(btn,true,'Guardando…');
    try{
      try{await TP.signIn(m.user.email,cur)}                   // confirma que quien teclea conoce la contraseña actual
      catch(ex){if(ex.code==='invalid_credentials')throw new TP.TPError('bad_current','');throw ex}
      await TP.updatePassword(pw);
      e.target.reset();UI.msg(box,'ok','Contraseña actualizada.');
    }catch(ex){UI.msg(box,'err',ex.code==='bad_current'?'La contraseña actual no es correcta.':TP.errorMessage(ex))}
    finally{UI.busy(btn,false)}
  });
  $('p-salir').addEventListener('click',async()=>{$('p-salir').disabled=true;await TP.signOut();location.href='index.html'});
})();
})();
