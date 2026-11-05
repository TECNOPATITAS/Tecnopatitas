# Etapa 11 · Seguridad final, textos legales, eliminar cuenta y publicación: lo que tienes que hacer tú

Esta es la **última etapa**. Añade lo que faltaba para abrir el sitio a personas reales: **Aviso de privacidad** y **Términos y condiciones** (con aceptación al registrarse), **eliminar la cuenta**, una página 404, la limpieza de los datos de demostración, una auditoría de seguridad del sitio y la lista de pendientes antes de publicar.

> Los menús de Supabase, GitHub y Cloudflare cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 45–60 minutos, más el tiempo que tarde la revisión de los textos legales y de las guías.

**Reglas que siguen vigentes:**

- **No hay pagos.** Ninguna pantalla pide tarjeta ni datos financieros, no hay pruebas gratuitas que se vuelvan de pago ni cargos automáticos. **Contratar y cobrar suscripciones no está habilitado** (queda para más adelante, si tú lo decides).
- **Nadie se vuelve administrador desde el navegador.** El rol solo se da desde el SQL Editor (`GUIA_ETAPA_10.md`).
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase, la contraseña de la base de datos ni la *Secret Key* de Turnstile.

---

## Lo que cambia en esta etapa

1. **`privacidad.html` y `terminos.html`** (públicas, enlazadas en el pie de todas las páginas). Dicen qué datos se recaban, para qué, qué es público y qué no, con quién se comparten (Supabase, Cloudflare, Google Fonts), cómo ejercer los derechos de acceso, rectificación, cancelación y oposición (ARCO), cuánto se conservan y cómo se eliminan, menores de edad, cookies y almacenamiento del navegador, y las reglas de uso (aliados, reportes, planes sin cobros). **Los datos de quien responde (responsable, domicilio, contacto) los pones tú en `js/config.js`** (Paso 3): si faltan, las páginas muestran un cuadro de aviso con la lista de lo que falta, en lugar de inventarlo.
2. **Aceptación al registrarse.** `registro.html` tiene una casilla obligatoria («He leído y acepto el Aviso de privacidad y los Términos y condiciones, y el uso de mis datos para gestionar mi cuenta. Declaro tener 18 años o más (o contar con la autorización de mi madre, padre o tutor)»). La base guarda **qué versión** aceptó la persona y **cuándo** (`profiles.terms_version` y `terms_accepted_at`). Esa constancia **no se puede cambiar desde el navegador**, ni siquiera con permisos de columna: la escribe solo el servidor al crear la cuenta, y solo si la versión tiene el formato `AAAA-MM-DD`. Las cuentas anteriores a esta etapa quedan sin constancia (no se les puede imponer retroactivamente).
3. **Eliminar mi cuenta** (`perfil.html`). La persona escribe su contraseña y la frase **ELIMINAR MI CUENTA**; el navegador borra primero sus archivos (fotos de mascotas, perfil, placa QR, logotipos) con la API de Storage y después llama a `delete_my_account`, que borra la cuenta y, en cascada, todo lo suyo (perfil, mascotas y carnet, placas QR, avisos, chat, planes y solicitudes, establecimiento y promociones). **No toca** las denuncias anónimas (no están ligadas a ninguna cuenta) ni la bitácora de administración. Las cuentas de administración **no** se eliminan desde aquí. El servidor se niega si todavía quedan archivos de la persona (así no quedan archivos huérfanos).
4. **`404.html`** (página no encontrada, con enlaces de regreso) y `noindex` en las pantallas de acceso para que los buscadores no las listen.
5. **`database/07_limpiar_demo.sql`:** borra solo los 6 establecimientos ficticios de la demostración (Paso 5).
6. **Auditoría de seguridad** (`pruebas-web/auditar_sitio.py`): recorre todo el sitio buscando claves secretas, `innerHTML` con datos, `eval`, enlaces `javascript:`, `target="_blank"` sin `rel`, scripts externos fuera de la lista permitida, imágenes sin texto alternativo, páginas sin título o sin `h1`, y que la CSP de `_headers` siga cerrada.
7. **Datos de autoridades de la página de denuncias:** quité todo número telefónico que yo no pueda verificar. Ahora la página dice «en una emergencia llama al 911», manda a la fiscalía o autoridad de protección animal **de tu estado o municipio** y enlaza el sitio oficial de PROFEPA para fauna silvestre. Ver el Paso 7.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 11 añade las columnas de constancia de términos, la función `delete_my_account` y su permiso. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal; confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 37 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela.

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Los archivos que se añaden o cambian en esta etapa son:
   - **Nuevos:** `privacidad.html`, `terminos.html`, `404.html`, `js/legal.js`, `js/pages/legal.js`, `database/07_limpiar_demo.sql`, `opcional/mantener-activo.yml`, `pruebas-web/auditar_sitio.py`, `pruebas-web/probar_legal.py`, `pruebas-web/mock_etapa11.py`, `GUIA_ETAPA_11.md`.
   - **Cambian:** `registro.html`, `perfil.html`, `login.html`, `recuperar.html`, `nueva-contrasena.html`, `denuncias.html`, `css/styles.css`, `js/config.js`, `js/layout.js`, `js/plans.js`, `js/tp-client.js`, `js/pages/registro.js`, `js/pages/perfil.js`, `js/pages/login.js`, `.env.example`, la carpeta `database/…`, `GUIA_ETAPA_3.md`, `GUIA_ETAPA_10.md`, `README.md` y, solo para desarrollo, `pruebas-web/probar_acceso.py`, `probar_planes.py` y `probar_admin.py`.
2. **Ojo con `js/config.js`:** al subir el de esta carpeta **reemplazas el tuyo**. Trae tu URL de Supabase y tu clave *publishable*, pero **`TURNSTILE_SITE_KEY` viene vacío**. Si ya habías pegado tu Site Key de Turnstile (Etapa 6), **vuelve a pegarla** (Paso 3). Si no, el formulario de denuncias dirá que falta configurar la verificación.
3. Cloudflare Pages publica solo (1–2 minutos).
4. Abre `https://tecnopatitas.pages.dev/privacidad.html` **sin iniciar sesión** con la consola abierta (**F12 → Console**): debe verse el aviso, con un cuadro de aviso que dice qué datos faltan por llenar (normal hasta el Paso 3) y **sin errores rojos en la consola**.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular cierra y abre la pestaña).

## Paso 3 · Poner tus datos en `js/config.js` (5 minutos)

Abre `js/config.js` en GitHub (lápiz de editar) y llena los tres campos de `LEGAL`. **Son públicos** (aparecen en el aviso de privacidad): escribe solo lo que estés dispuesto a mostrar.

```js
LEGAL: Object.freeze({
  RESPONSABLE: 'Nombre completo o nombre de la microempresa',
  DOMICILIO: 'Calle, número, colonia, municipio, estado y código postal',
  CONTACTO: 'un-correo-para-datos-personales@ejemplo.com'
}),
```

- **RESPONSABLE:** quien decide sobre el tratamiento de los datos (tú o tu microempresa).
- **DOMICILIO:** el aviso de privacidad debe indicar el domicilio del responsable. Si no quieres publicar tu casa, consulta con quien revise los textos (Paso 4) qué domicilio puedes usar.
- **CONTACTO:** un **correo que de verdad revises**. Es la vía para que las personas ejerzan sus derechos ARCO. Si lo escribes como correo, la página lo vuelve un enlace.
- Si usas Turnstile, **vuelve a pegar tu `TURNSTILE_SITE_KEY`** si el archivo la perdió (Paso 2.2). La Site Key es pública; la *Secret Key* **nunca** va aquí.

Guarda con **Commit changes**, espera a que Cloudflare publique y recarga `privacidad.html`: el cuadro de aviso debe desaparecer y verse tus datos. Revisa también `terminos.html` y el pie de cualquier página.

## Paso 4 · Que una persona calificada revise los textos legales (importante)

**No soy abogado ni contador.** Redacté el aviso de privacidad y los términos según lo que **realmente hace** el sitio (qué datos pide, qué publica, con quién los comparte) y teniendo en cuenta la Ley Federal de Protección de Datos Personales en Posesión de los Particulares (la nueva ley, publicada en el DOF el 20 de marzo de 2025, cuya autoridad es la Secretaría Anticorrupción y Buen Gobierno). Pero **no sé si tu caso exige algo más** (por ejemplo, el aviso en su modalidad integral o simplificada, o cláusulas propias de tu microempresa), y las leyes cambian.

- Antes de abrir al público, pide que **un abogado o una persona con experiencia en protección de datos** los lea y te diga qué ajustar. Si eres estudiante, tu escuela o incubadora puede orientarte.
- Si cambia algo, **dime qué texto** y lo ajusto. Cuando los textos cambien de fondo, hay que **subir la fecha y la versión** en `js/legal.js` (por ejemplo `VERSION: '2026-12-01'`, `FECHA: '1 de diciembre de 2026'`): las cuentas nuevas guardarán esa versión; las anteriores conservan la que aceptaron.
- Los textos **no sustituyen** una asesoría. No los presentes como «validados» mientras nadie los haya revisado.

## Paso 5 · Limpiar los datos de demostración (cuando vayas a abrir al público)

Los 6 establecimientos de `06_datos_demo.sql` son **ficticios** (marcados `is_demo`). Antes de que entre gente real:

1. **SQL Editor → New query** → pega todo `database/07_limpiar_demo.sql` → **Run**.
2. Abajo verás tres filas de comprobación: «Establecimientos de demostración que quedan» debe decir **0**, y «Establecimientos reales» no debe cambiar.
3. **No borra cuentas, mascotas, denuncias, chats ni planes** (eso podría ser información real o tuya). Tus cuentas de prueba bórralas una por una: *Authentication → Users → ⋯ → Delete user* (se llevan consigo sus datos); o entra con ellas y usa **Perfil → Eliminar mi cuenta**.
4. Puedes ejecutarlo más de una vez sin problema.

## Paso 6 · Las guías de cuidado y la revisión veterinaria

Las 8 guías de demostración dicen «**pendiente de revisión veterinaria**». **Yo no puedo certificar contenido veterinario** y no lo haré pasar por revisado. Tienes tres caminos:

1. **Que un MVZ las revise** (lo ideal), y luego editar cada guía en **Administración → Guías** cambiando la fuente a algo como «Revisada por MVZ Nombre Apellido, cédula …, fecha» (solo si es verdad).
2. **Dejarlas publicadas** con la leyenda de pendiente (el sitio no hace promesas médicas, pero sigue siendo contenido sin revisar).
3. **Despublicarlas** hasta que se revisen: en `07_limpiar_demo.sql` hay una línea opcional comentada al final (`-- update public.care_guides set is_published = false …`). Quítale los dos guiones y ejecútala. Las guías **no se borran**; pasan a borrador y las vuelves a publicar desde el panel.

## Paso 7 · Datos de las autoridades de tu ciudad

La tarjeta «Autoridades» de `denuncias.html` es **genérica a propósito** (911, fiscalía o autoridad de protección animal de tu estado/municipio, y PROFEPA para fauna silvestre) porque **no pude verificar teléfonos vigentes** y no quise publicar números que podrían estar mal. Cuando quieras hacerla útil de verdad:

1. Busca en el sitio **oficial** de tu gobierno estatal o municipal la unidad de protección animal o la fiscalía que atiende maltrato animal.
2. Mándame el nombre, el teléfono o enlace **oficial** y de dónde lo sacaste, y lo agrego.
3. Recuerda que TECNOPATITAS **registra reportes para su revisión; no presenta denuncias oficiales ante ninguna autoridad**, y así lo dice la página.

## Paso 8 · Tu cuenta de administración

Si todavía no la tienes, sigue «Cómo dar el rol de administración» en `GUIA_ETAPA_10.md`. **Dale el rol solo a cuentas que tú crees y controles**: con la confirmación de correo desactivada, cualquiera puede registrarse con un correo ajeno. Una cuenta de administración **no se puede eliminar desde Perfil** (si algún día hace falta, se quita el rol con SQL y luego se elimina).

## Paso 9 · Recomendado antes de abrir el registro: anti-robots en el acceso

Como la confirmación de correo está desactivada, conviene activar **Cloudflare Turnstile también en el registro y el inicio de sesión** (Paso 7 de `GUIA_ETAPA_6.md`): pegas la Site Key en `js/config.js` y activas **Authentication → Attack Protection → CAPTCHA** en Supabase. Es gratuito. **Orden importante:** primero publica la Site Key, **después** activa el CAPTCHA en Supabase; si lo haces al revés, nadie podrá entrar. Con CAPTCHA activo, también **cambiar contraseña y eliminar la cuenta** piden la verificación (el recuadro aparece en esas pantallas).

## Paso 10 · La pausa del proyecto gratuito de Supabase

Según la documentación de Supabase (consultada el 4–5 de noviembre de 2026), los proyectos del plan gratuito **se pausan si casi no tienen actividad en 7 días**:

- Recibes un **correo de aviso** aproximadamente una semana antes y otro cuando se pausa. Con el sitio pausado, **todo falla**: nadie puede entrar ni ver el directorio.
- **Reactivarlo es gratis:** Supabase → tu organización → el proyecto pausado → **Resume project** → confirmar. Los datos se conservan. La documentación dice que se puede restaurar hasta **1 año** después de la pausa; pasado ese plazo ya no es automático, así que **no lo abandones**.
- **Si el sitio tendrá uso real**, lo normal es que haya visitas todos los días y no se pause. Si habrá semanas sin visitas, tienes dos opciones **gratuitas**: (a) entrar tú al panel cada pocos días, o (b) activar el flujo opcional de GitHub `opcional/mantener-activo.yml`, que hace una consulta pública mínima cada 3 días (las instrucciones están dentro del archivo). Es opcional, **no hace nada mientras esté en esa carpeta**, no usa claves secretas ni cuesta nada si no tienes una tarjeta registrada en GitHub. Supabase dice que las consultas a la API cuentan como actividad, pero no define cuánta es suficiente: no es una garantía.
- **Respaldo:** tu información vive solo en ese proyecto. De vez en cuando, **Database → Backups** (en el plan gratuito no hay copias diarias descargables; revisa qué ofrece hoy tu panel) o exporta tablas importantes. Para una demostración escolar es aceptable; con personas reales, valóralo.
- **No subas de plan** ni agregues complementos: nada de esto lo necesita.

## Paso 11 · Pruebas en el sitio real (checklist)

Hazlas con una ventana de incógnito y, cuando se indique, con una **cuenta de prueba** (no la tuya real).

**Textos legales**

1. `privacidad.html` y `terminos.html` abren sin iniciar sesión, sin errores en la consola, y muestran tu responsable, domicilio y contacto (sin cuadro de aviso).
2. El pie de cada página tiene el bloque «Legal» con ambos enlaces. Las dos páginas se ven bien en el celular.
3. Una dirección inexistente (por ejemplo `.../no-existe.html`) muestra la página 404 con enlaces de regreso (Cloudflare Pages usa `404.html` solo).

**Registro con aceptación**

4. En `registro.html`, **sin marcar la casilla**, el botón no crea la cuenta y dice que debes aceptar el Aviso de privacidad y los Términos.
5. Marcándola, la cuenta se crea y entras. En Supabase → **Table Editor → profiles**, esa fila tiene `terms_version` (la fecha de `js/legal.js`) y `terms_accepted_at`.
6. Desde la consola del navegador de esa cuenta, intentar cambiar `terms_version` con `TP.rest` o similar debe **fallar** (permiso denegado). *(Opcional; si no sabes cómo, sáltala: ya está cubierta por las pruebas automáticas.)*

**Eliminar la cuenta** (con la cuenta de prueba del punto 5)

7. Crea una mascota con foto y manda un mensaje al chat de atención.
8. En **Perfil → Eliminar mi cuenta** (se abre el formulario): sin contraseña o sin la frase, avisa qué falta y no procede; con la frase en minúsculas, también avisa; con la contraseña equivocada, dice «La contraseña no es correcta.» y no borra nada.
9. Con la contraseña correcta y **ELIMINAR MI CUENTA**: te regresa a `login.html` con el aviso de que la cuenta fue eliminada, y **ya no puedes entrar** con esa cuenta.
10. En Supabase: **Authentication → Users** (ya no está), **Table Editor → pets** (ya no está su mascota) y **Storage → pet-photos** (la carpeta con su identificador ya no tiene archivos).
11. **Si el paso 9 falla** (por ejemplo, un error de permisos al borrar el usuario): **no insistas** y mándame el texto exacto del error. Es la única pieza que no pude probar contra el Supabase real (Paso «Lo que NO se pudo probar»). Mientras tanto, la alternativa segura es *Authentication → Users → ⋯ → Delete user* y borrar a mano su carpeta en **Storage**.
12. Con una **cuenta de administración**, Perfil no muestra el botón de eliminar: explica que otra persona administradora debe hacerlo.

**Seguridad general**

13. Sin iniciar sesión, abre `https://tecnopatitas.pages.dev/perfil.html`, `admin.html` y `chat.html`: deben mandarte al inicio de sesión sin mostrar contenido.
14. Con una cuenta normal, abre `admin.html`: «Acceso restringido».
15. En la consola (F12 → Console) de varias páginas no debe haber errores rojos ni avisos de la política de seguridad (CSP).
16. La denuncia de prueba y su seguimiento con el código siguen funcionando (si ya configuraste Turnstile y la función, Etapa 6).

## Riesgos conocidos y aceptados (para que lo decidas con los ojos abiertos)

- **Eliminar la cuenta no vuelve a pedir la contraseña en el servidor.** El navegador sí la pide (vuelve a iniciar sesión con ella) y exige la frase, pero el servidor, al recibir la orden, solo comprueba la sesión y la frase. Quien robara una sesión abierta *y* conociera la frase podría eliminar esa cuenta. La eliminación es definitiva. Se mitiga con sesiones que caducan; si lo quieres más estricto, habría que pasar por una función segura con la contraseña (más complejidad).
- **La función `submit-complaint` acepta peticiones desde cualquier sitio web (CORS `*`).** Es a propósito: el reporte es anónimo y no usa cookies ni sesión, y está protegido por Turnstile y límites. Otro sitio podría intentar usarla, pero necesitaría un token válido de Turnstile para tu dominio y toparía con los límites.
- **Estilos en línea permitidos por la CSP (`'unsafe-inline'` solo en estilos, no en scripts).** Los scripts siguen limitados a los propios y a Cloudflare Turnstile. Quitar los estilos en línea exigiría reescribir todas las páginas.
- **Confirmación de correo desactivada** y **recuperar contraseña por correo que no llega a personas normales** (decisión tuya, Etapa 10).
- **Google Fonts** se carga desde Google (el aviso de privacidad lo dice): al abrir el sitio, Google recibe la dirección IP de la persona. Si prefieres evitarlo, se pueden alojar las fuentes en el propio sitio.
- **Fotos de la placa QR públicas** y **QR con la dirección actual del sitio** (si cambia la dirección, hay que reimprimir). Ver README.
- **Archivos huérfanos:** si se corta la conexión justo al borrar fotos, puede quedar algún archivo sin dueño visible. Está acotado por topes por persona.
- **La bitácora de administración crece sin límite** (una fila por acción, sin contenidos).
- **Ningún sistema es infalible.** Esto es una microempresa escolar sobre servicios gratuitos: sin soporte, sin garantías de disponibilidad y sin copias de seguridad automáticas descargables.

## Decisiones que tomé por ti (dímelas si quieres otra cosa)

1. **Mayoría de edad:** el registro exige declarar tener 18 años o más **o** contar con la autorización de madre, padre o tutor (el aviso de privacidad dice lo mismo y que una cuenta de menor sin autorización se eliminará). No se verifica la edad ni se guarda la edad o la fecha de nacimiento de nadie. Si prefieres prohibir el registro de menores, o exigir un procedimiento de autorización, cambian los textos y el flujo (y conviene asesoría legal).
2. **La constancia de términos guarda solo la versión y la fecha** de aceptación, no la dirección IP.
3. **Al eliminar la cuenta se pide la contraseña y una frase escrita**, y no hay periodo de «arrepentimiento»: es inmediato y definitivo.
4. **Las denuncias anónimas no se borran con la cuenta** (no están ligadas a ella).
5. **La demostración se limpia con un script que tú ejecutas**, no automáticamente; no se borran cuentas ni datos de personas en bloque.
6. **Las guías de demostración no se despublican solas**; tú decides (Paso 6).
7. **No agregué analítica, cookies de seguimiento ni servicios de terceros nuevos.** Lo único que usa el navegador son los datos de sesión de Supabase y, si lo activas, Cloudflare Turnstile.

## Lo que NO se pudo probar desde aquí

- **Tu Supabase real.** Todo se probó contra PostgreSQL local con el mismo esquema y simuladores. En particular, **`delete from auth.users` dentro de `delete_my_account` no se ha ejecutado en Supabase real**: en teoría funciona (la función corre con el rol `postgres`, que puede borrar usuarios desde el SQL Editor), pero el punto 9–11 del checklist lo confirma.
- **El borrado real de archivos con la API de Storage** (se probó contra un simulador que sigue la documentación).
- **Turnstile real** en el registro, el inicio de sesión, cambiar contraseña y eliminar cuenta.
- **El efecto de `404.html` en Cloudflare Pages** (se espera que lo use solo; si ves la página genérica de Cloudflare, dímelo).
- **Un teléfono físico** (se revisó a 360–390 px de ancho).
- **La validez legal de los textos**: la revisión es tuya (Paso 4).

## Lista final antes de abrir el sitio al público

- [ ] Paso 1: SQL actualizado y verificador en **37 comprobaciones superadas**.
- [ ] Paso 2: archivos subidos y sin errores en la consola.
- [ ] Paso 3: `RESPONSABLE`, `DOMICILIO` y `CONTACTO` llenos (y `TURNSTILE_SITE_KEY` recuperada si la usas).
- [ ] Paso 4: textos legales **revisados por una persona calificada**.
- [ ] Paso 5: demostración limpiada (`07_limpiar_demo.sql`) y cuentas de prueba eliminadas.
- [ ] Paso 6: guías revisadas por un MVZ **o** despublicadas **o** aceptas mostrarlas como pendientes.
- [ ] Paso 7: datos de las autoridades de tu ciudad (opcional pero recomendable).
- [ ] Paso 8: tu cuenta de administración creada con SQL; ninguna otra cuenta con el rol.
- [ ] Paso 9: Turnstile en el acceso (recomendado).
- [ ] Paso 10: sabes qué hacer si el proyecto se pausa (y, si quieres, activaste el flujo opcional).
- [ ] Paso 11: checklist del sitio real completo, incluida la eliminación de una cuenta de prueba.
- [ ] No hay ningún plan de pago activado en Supabase, Cloudflare ni GitHub, y ninguna tarjeta registrada.

## Qué sigue

Con esto terminan las 11 etapas del plan. **Cobros:** recibir pagos de suscripciones está **pospuesto por decisión tuya** y **no está habilitado**; si lo retomas, será una decisión nueva y explícita (hay que revisar costos, comisiones, obligaciones fiscales y qué proveedor aplica a tu situación, y todo con una persona contadora). Mientras tanto, los planes se activan a mano y sin cobro.
