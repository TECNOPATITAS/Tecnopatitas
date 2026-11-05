/* Planes del modelo de negocio (Etapa 9).
   · El catálogo se muestra a todo el mundo sin consultar Supabase (los visitantes no hacen peticiones solo por mirar los planes).
     Lo que SÍ se aplica en el servidor (límites, permisos) sale de la tabla subscription_plans; una prueba automática
     comprueba que este catálogo coincide con ella (identificador, nombre, precios y beneficios).
   · Con sesión iniciada, js/pages/planes.js añade tu plan actual, tus solicitudes y los botones «Solicitar» (TPPlans.cta). */
const PLANS=[
{id:'basica',g:0,n:'Huellita Básica',s:'Plan Comunidad',m:0,a:0,t:'Comenzar gratis',b:['Acceso ilimitado a guías informativas de cuidados principales','Acceso al módulo de denuncias de maltrato animal, diseñado para permitir reportes anónimos','Consulta del directorio general de aliados locales con nombre y dirección']},
{id:'pro',g:0,n:'Huellita Pro',s:'Plan Cuidadores',m:29,a:290,pop:1,t:'Elegir Huellita Pro',b:['Todos los beneficios del plan gratuito','Carnet de Salud Digital interactivo para hasta 2 mascotas, con vacunas, desparasitaciones y citas','Recordatorios automáticos previstos por WhatsApp o correo electrónico','Descuentos exclusivos del 5 % al 10 % en la red de aliados locales']},
{id:'vip',g:0,n:'Huellita VIP',s:'Plan Familia',m:59,a:590,t:'Elegir Huellita VIP',b:['Todos los beneficios del plan Huellita Pro','Carnet de Salud Digital ilimitado para familias con 3 o más mascotas','Generador de placa QR digital con acceso al perfil de contacto de la mascota en caso de extravío','Cupones de descuento acumulables','Acceso prioritario a talleres y materiales PDF de nutrición y adiestramiento']},
{id:'plata',g:1,n:'Huellita de Plata',s:'Plan Aliado Inicial',m:149,a:1490,t:'Registrar mi negocio',b:['Ficha completa en el directorio con nombre, dirección, teléfono, horario y logotipo','Ubicación mediante mapa interactivo','Publicación de hasta una promoción o servicio destacado al mes']},
{id:'oro',g:1,n:'Huellita de Oro',s:'Plan Aliado Premium',m:299,a:2990,t:'Elegir plan Premium',b:['Todos los beneficios del directorio comercial','Posicionamiento prioritario','Etiqueta «Aliado Verificado / Recomendado», cuando corresponda','Botón directo a WhatsApp','Publicación ilimitada de promociones','Difusión mensual en las redes sociales oficiales de TECNOPATITAS']}];
const mxn=n=>'$'+n.toLocaleString('es-MX')+' MXN';
const TPPlans={PLANS,mxn,yearly:false,cta:null,render(){
  const E=window.TPUI&&window.TPUI.el;
  [['#pu',0],['#pb',1]].forEach(([sel,g])=>{
    const host=document.querySelector(sel);if(!host||!E)return;
    host.replaceChildren(...PLANS.filter(p=>p.g===g).map(p=>{
      const yearly=TPPlans.yearly,pr=yearly?p.a:p.m,ah=p.m*12-p.a,q=g?'tipo=aliado&':'';
      const custom=TPPlans.cta?TPPlans.cta(p,yearly):null;
      return E('article',{class:'card'+(p.pop?' pop':''),dataset:{plan:p.id}},
        p.pop?E('span',{class:'tag pk',text:'Más popular'}):null,
        E('h3',{text:p.n}),E('small',{text:p.s}),
        E('div',{class:'price'},mxn(pr),E('small',{text:pr?(yearly?' /año':' /mes'):' · gratis'})),
        ah?E('small',{text:'Anual: '+mxn(p.a)+' · ahorras '+mxn(ah)+' al año frente a 12 pagos mensuales'}):null,
        E('ul',null,...p.b.map(x=>E('li',{text:x}))),
        E('div',{class:'row'},custom||E('a',{class:'btn coral',href:'registro.html?'+q+'plan='+p.id,text:p.t})));
    }));
  });
}};
window.TPPlans=TPPlans;
function init(){
  const mini=document.querySelector('#plans-mini'),E=window.TPUI&&window.TPUI.el;
  if(mini&&E)mini.replaceChildren(...PLANS.map(p=>E('a',{class:'card',href:'planes.html'},E('h3',{text:p.n}),E('small',{text:p.g?'Aliados comerciales':'Dueños de mascotas'}),E('div',{class:'price'},mxn(p.m),E('small',{text:p.m?' /mes':' · gratis'})))));
  if(document.querySelector('#pu')){
    TPPlans.render();
    document.querySelectorAll('[data-bill]').forEach(b=>b.onclick=()=>{TPPlans.yearly=b.dataset.bill==='y';document.querySelectorAll('[data-bill]').forEach(x=>x.setAttribute('aria-pressed',x===b));TPPlans.render()});
  }
}
/* Se dibuja cuando termina de cargar la página, para que planes.js (con sesión) pueda poner sus botones antes del primer dibujo. */
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
