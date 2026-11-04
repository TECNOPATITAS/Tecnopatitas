/* Ayudas de interfaz compartidas (Etapa 3). Todo texto se escribe con textContent: nunca innerHTML. */
window.TPUI=Object.freeze({
  msg(box,kind,text){            /* kind: 'err' | 'ok' | 'info' | null (ocultar) */
    if(!box)return;
    if(!kind){box.hidden=true;box.textContent='';return}
    box.className='msg '+kind;box.setAttribute('role',kind==='err'?'alert':'status');
    box.textContent=text;box.hidden=false;
  },
  busy(btn,on,label){
    if(!btn)return;
    if(on){btn.dataset.label=btn.textContent;btn.disabled=true;btn.textContent=label||'Un momento…'}
    else{btn.disabled=false;if(btn.dataset.label)btn.textContent=btn.dataset.label}
  },
  /* A qué página puede ir esta persona según su rol (para respetar ?next= sin mandarla a una pantalla que la rechace). */
  canOpen(page,m){
    if(page==='admin.html')return !!m.isAdmin;
    if(page==='panel-aliado.html')return m.accountType==='business';
    if(page==='mascota.html'||page==='carnet.html')return m.accountType==='owner';
    return true;
  }
});
