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
  /* Crea un elemento sin innerHTML. props: class, text, dataset, onclick…(funciones) y atributos (se escriben con setAttribute).
     NUNCA pases datos del servidor a href/src: usa solo valores validados. */
  el(tag,props,...kids){
    const e=document.createElement(tag);
    for(const [k,v] of Object.entries(props||{})){
      if(v==null||v===false)continue;
      if(k==='class')e.className=v;
      else if(k==='text')e.textContent=v;
      else if(k==='dataset')Object.assign(e.dataset,v);
      else if(k.startsWith('on')){if(typeof v==='function')e.addEventListener(k.slice(2),v)}
      else if(k==='value'||k==='checked'||k==='disabled'||k==='hidden')e[k]=v;
      else e.setAttribute(k,v===true?'':String(v));
    }
    kids.flat().forEach(c=>{if(c==null||c===false)return;e.append(c&&c.nodeType?c:document.createTextNode(String(c)))});
    return e;
  },
  MESES:['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'],
  /* 'AAAA-MM-DD' → '4 nov 2026' (sin convertir zonas horarias) */
  dateEs(d){const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(d||'');return m?(+m[3])+' '+this.MESES[+m[2]-1]+' '+m[1]:''},
  /* Fecha y hora en horario de Ciudad de México */
  dateTimeEs(iso){
    const d=new Date(iso);if(isNaN(d))return '';
    return new Intl.DateTimeFormat('es-MX',{timeZone:'America/Mexico_City',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(d);
  },
  /* Edad aproximada a partir de la fecha de nacimiento */
  ageEs(birth){
    const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(birth||'');if(!m)return '';
    const now=new Date();let months=(now.getFullYear()-(+m[1]))*12+(now.getMonth()+1-(+m[2]));if(now.getDate()<(+m[3]))months--;
    if(months<0)return '';
    if(months<1)return 'menos de 1 mes';
    if(months<12)return months+(months===1?' mes':' meses');
    const y=Math.floor(months/12),r=months%12;
    return y+(y===1?' año':' años')+(r?' y '+r+(r===1?' mes':' meses'):'');
  },
  todayLocal(){const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')},
  /* A qué página puede ir esta persona según su rol (para respetar ?next= sin mandarla a una pantalla que la rechace). */
  canOpen(page,m){
    if(page==='admin.html')return !!m.isAdmin;
    if(page==='panel-aliado.html')return m.accountType==='business';
    if(page==='mascota.html'||page==='carnet.html')return m.accountType==='owner';
    return true;
  }
});
