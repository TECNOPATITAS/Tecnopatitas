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
  (async()=>{                                                  // sin await: los formularios de abajo deben responder desde el primer momento
    try{
      const ent=await TP.rpc('my_entitlements');
      const plan=ent&&ent.plan;
      $('p-plan').textContent=plan?plan.name+(plan.tagline?' · '+plan.tagline:''):
        (m.accountType==='business'?'Sin plan de aliado todavía (puedes pedirlo en Mi suscripción; no hay cobros)':'Huellita Básica');
    }catch{$('p-plan').textContent='No se pudo consultar tu plan en este momento.'}
  })();
  /* ---- Foto de perfil (bucket privado «avatars»: se ve con una URL firmada temporal) ---- */
  const MEDIA=window.TPMedia,P=window.TPPets;
  let avatarPath=m.profile.avatar_path||null;
  async function showAvatar(){
    let url=null;
    if(avatarPath){try{const u=await TP.storage.sign('avatars',[avatarPath],3600);url=u[avatarPath]||null}catch{url=null}}
    const img=$('p-avatar');
    if(url){img.src=url;img.hidden=false}else{img.removeAttribute('src');img.hidden=true}
    $('p-avatar-ph').hidden=!!url;$('p-foto-quitar').hidden=!avatarPath||m.suspended;
  }
  async function setAvatar(blob){
    const old=avatarPath;let path=null;
    if(blob){path=m.user.id+'/'+P.uuid()+'.jpg';await TP.storage.upload('avatars',path,blob)}
    try{await TP.updateProfile(m.user.id,{avatar_path:path})}
    catch(ex){if(path)TP.storage.remove('avatars',[path]).catch(()=>{});throw ex}
    avatarPath=path;
    if(old)TP.storage.remove('avatars',[old]).catch(()=>{});
  }
  if(MEDIA&&P){
    showAvatar();
    if(m.suspended)$('p-foto').disabled=true;
    $('p-foto').addEventListener('change',async e=>{
      const file=e.target.files[0],box=$('msg-foto');if(!file)return;
      UI.msg(box,'info','Subiendo foto…');
      try{
        const blob=await MEDIA.prepareImage(file,{maxSide:512,quality:0.85});
        await setAvatar(blob);await showAvatar();UI.msg(box,'ok','Foto actualizada.');
      }catch(ex){UI.msg(box,'err',ex instanceof MEDIA.MediaError?ex.message:TP.errorMessage(ex))}
      finally{e.target.value=''}
    });
    $('p-foto-quitar').addEventListener('click',async()=>{
      const box=$('msg-foto');
      try{await setAvatar(null);await showAvatar();UI.msg(box,'ok','Foto eliminada.')}catch(ex){UI.msg(box,'err',TP.errorMessage(ex))}
    });
  }
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
  const capPw=(window.TPCaptcha&&window.TPCaptcha.configured)?window.TPCaptcha.mount($('pw-captcha'),{onStatus:(k,t)=>{if(k==='error')UI.msg($('msg-pw'),'err',t)}}):null;
  $('f-pw').addEventListener('submit',async e=>{
    e.preventDefault();
    const box=$('msg-pw'),btn=e.target.querySelector('button'),cur=$('pw-actual').value,pw=$('pw-nueva').value,pw2=$('pw-repetir').value;
    let err=null;
    if(!cur)err='Escribe tu contraseña actual.';
    else if((err=TP.checkPassword(pw,m.user.email)));
    else if(pw!==pw2)err='Las contraseñas no coinciden.';
    else if(pw===cur)err='La nueva contraseña debe ser distinta de la actual.';
    if(err){UI.msg(box,'err',err);return}
    if(capPw&&!capPw.token()){UI.msg(box,'err','Completa la verificación anti-robots antes de continuar.');capPw.retry();return}
    UI.msg(box,null);UI.busy(btn,true,'Guardando…');
    try{
      try{await TP.signIn(m.user.email,cur,capPw?capPw.token():undefined)}   // confirma que quien teclea conoce la contraseña actual
      catch(ex){if(ex.code==='invalid_credentials')throw new TP.TPError('bad_current','');throw ex}
      await TP.updatePassword(pw);
      e.target.reset();UI.msg(box,'ok','Contraseña actualizada.');
    }catch(ex){UI.msg(box,'err',ex.code==='bad_current'?'La contraseña actual no es correcta.':TP.errorMessage(ex))}
    finally{UI.busy(btn,false);if(capPw)capPw.reset()}           // cada verificación sirve una sola vez
  });

  /* ---- Eliminar mi cuenta (Etapa 11) ----
     Orden: 1) confirmar contraseña (+ anti-robots si está activo) y la frase exacta; 2) borrar los archivos propios por la API de Storage
     (borrarlos con SQL dejaría los archivos huérfanos); 3) pedir al servidor que borre la cuenta (delete_my_account vuelve a comprobar
     frase, rol y que no queden archivos); 4) cerrar sesión local y volver al inicio de sesión. Las cuentas de administración no pasan por aquí. */
  const FRASE='ELIMINAR MI CUENTA',CARPETAS=['avatars','pet-photos','qr-photos','business-media'];
  const fb=$('f-borrar'),ab=$('del-abrir');
  let capDel=null;
  if(m.isAdmin){$('del-admin').hidden=false;ab.hidden=true}
  else{
    const closeForm=()=>{fb.hidden=true;ab.hidden=false;ab.setAttribute('aria-expanded','false');fb.reset();UI.msg($('msg-borrar'),null);if(capDel){capDel.destroy();capDel=null}};
    ab.addEventListener('click',()=>{
      fb.hidden=false;ab.hidden=true;ab.setAttribute('aria-expanded','true');
      if(window.TPCaptcha&&window.TPCaptcha.configured&&!capDel)capDel=window.TPCaptcha.mount($('del-captcha'),{onStatus:(k,t)=>{if(k==='error')UI.msg($('msg-borrar'),'err',t)}});
      $('del-pw').focus();
    });
    $('del-cancelar').addEventListener('click',()=>{closeForm();ab.focus()});
    fb.addEventListener('submit',async e=>{
      e.preventDefault();
      const box=$('msg-borrar'),btn=$('del-ok'),cancel=$('del-cancelar'),pw=$('del-pw').value,frase=$('del-frase').value.trim();
      if(btn.disabled)return;
      let err=null;
      if(!pw)err='Escribe tu contraseña.';
      else if(frase!==FRASE)err='Para confirmar, escribe exactamente: '+FRASE;
      else if(capDel&&!capDel.token()){err='Completa la verificación anti-robots antes de continuar.';capDel.retry()}
      if(err){UI.msg(box,'err',err);return}
      UI.msg(box,null);UI.busy(btn,true,'Eliminando…');cancel.disabled=true;
      let deleted=false;
      try{
        try{await TP.signIn(m.user.email,pw,capDel?capDel.token():undefined)}
        catch(ex){if(ex.code==='invalid_credentials')throw new TP.TPError('bad_current','');throw ex}
        UI.msg(box,'info','Borrando tus archivos…');
        for(const b of CARPETAS){
          const files=await TP.storage.listFolder(b,m.user.id);
          for(let i=0;i<files.length;i+=50)await TP.storage.remove(b,files.slice(i,i+50));
        }
        UI.msg(box,'info','Eliminando tu cuenta…');
        await TP.rpc('delete_my_account',{p_confirm:FRASE});
        deleted=true;
        await TP.signOut();
        location.replace('login.html?eliminada=1');
      }catch(ex){
        UI.msg(box,'err',ex.code==='bad_current'?'La contraseña no es correcta.':TP.errorMessage(ex));
        if(!deleted){UI.busy(btn,false);cancel.disabled=false}
      }
      finally{if(capDel&&!deleted)capDel.reset()}
    });
  }
  $('p-salir').addEventListener('click',async()=>{$('p-salir').disabled=true;await TP.signOut();location.href='index.html'});
})();
})();
