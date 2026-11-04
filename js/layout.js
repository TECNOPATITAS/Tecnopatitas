/* Cabecera, pie y avisos compartidos por todas las páginas. */
(()=>{
const k=document.body.dataset.page;
const NAV=[['index','Inicio','index.html'],['guias','Guías','guias.html'],['directorio','Directorio','directorio.html'],['denuncias','Denuncias','denuncias.html'],['planes','Suscripciones','planes.html'],['sobre-nosotros','Sobre nosotros','sobre-nosotros.html']];
const paw='<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true"><circle cx="5" cy="10" r="2.2"/><circle cx="9.5" cy="5.5" r="2.2"/><circle cx="14.5" cy="5.5" r="2.2"/><circle cx="19" cy="10" r="2.2"/><path d="M12 11c-3 0-6 3.5-6 6 0 2 1.8 2.5 3 2.2 1.2-.3 2-.7 3-.7s1.8.4 3 .7c1.2.3 3-.2 3-2.2 0-2.5-3-6-6-6z"/></svg>';
document.getElementById('site-header').innerHTML=`<header class="nav"><div class="wrap bar"><a class="logo" href="index.html">${paw}TECNOPATITAS</a><button id="mbtn" aria-label="Abrir menú" aria-expanded="false">☰</button><div class="panel" id="mp"><nav class="links" aria-label="Principal">${NAV.map(n=>`<a href="${n[2]}"${n[0]===k?' aria-current="page"':''}>${n[1]}</a>`).join('')}</nav><div class="acts"><a class="btn ghost sm" href="login.html">Iniciar sesión</a><a class="btn coral sm" href="registro.html">Crear cuenta</a></div></div></div></header>`;
document.getElementById('site-footer').innerHTML=`<footer class="foot"><div class="wrap fg"><div><b>TECNOPATITAS</b><p>Cuidado, protección y bienestar de las mascotas.</p><p>Plataforma en desarrollo por etapas. Aún no hay pagos ni cobros: la contratación de planes todavía no está habilitada.</p></div><div><b>Explorar</b><ul>${NAV.map(n=>`<li><a href="${n[2]}">${n[1]}</a></li>`).join('')}</ul></div><div><b>Tu cuenta</b><ul><li><a href="login.html">Iniciar sesión</a></li><li><a href="registro.html">Crear cuenta</a></li><li><a href="recuperar.html">Recuperar contraseña</a></li><li><a href="perfil.html">Perfil</a></li></ul></div></div></footer>`;
const mb=document.getElementById('mbtn'),mp=document.getElementById('mp');
mb.onclick=()=>{mb.setAttribute('aria-expanded',mp.classList.toggle('open'))};
const t=document.getElementById('toast');let tm;
document.addEventListener('submit',e=>{const f=e.target.closest('form[data-stage]');if(!f)return;e.preventDefault();
t.textContent='Todavía no está conectado: esta función se activa en la Etapa '+f.dataset.stage+'. No se envió ni se guardó nada.';t.classList.add('on');clearTimeout(tm);tm=setTimeout(()=>t.classList.remove('on'),4500)});
})();
