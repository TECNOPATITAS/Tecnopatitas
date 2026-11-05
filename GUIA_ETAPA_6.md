# Etapa 6 · Denuncias anónimas y anti-robots: lo que tienes que hacer tú

Esta etapa conecta `denuncias.html` con Supabase: cualquier persona puede **registrar** un reporte de maltrato animal sin dar ningún dato suyo, recibe un **código de seguimiento** y puede consultar su estado. Además añade **Cloudflare Turnstile** (anti-robots gratuito) a las denuncias y, si quieres, al registro, al inicio de sesión y a «olvidé mi contraseña».

> Los menús de Supabase y Cloudflare cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 60–75 minutos. Hazlo **en este orden**: el orden importa (sobre todo el Paso 7).

**Reglas que siguen vigentes:**

- No actives ningún plan de pago ni prueba gratuita, y no pongas tarjeta en ningún sitio. Turnstile, las Edge Functions de Supabase y Cloudflare Pages se usan en su plan **gratuito**. Si algún panel te pide una tarjeta, **detente** y avísame.
- **La clave secreta de Turnstile (*Secret Key*) no se pega en ningún archivo, no se sube a GitHub y no me la envíes.** Solo se pega en el panel de Supabase (Pasos 5 y 7). La **clave del sitio** (*Site Key*) sí es pública y va en `js/config.js`.
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase, la contraseña de la base de datos ni la contraseña de aplicación de Gmail. En esta etapa tampoco hace falta.
- **La plataforma solo REGISTRA las denuncias para que el equipo las revise. No las presenta ante ninguna autoridad**, y así lo dice la página. La contratación y los cobros siguen sin estar habilitados.

---

## Cómo funciona (para que sepas qué estás instalando)

1. La persona llena el formulario (tipo de situación, descripción, fecha aproximada, estado, municipio, referencia opcional y hasta 3 fotos). **No se pide nombre, correo ni teléfono, y no se envía la sesión aunque tenga una cuenta abierta.**
2. Su navegador reduce las fotos y las vuelve a guardar como JPEG (eso borra la ubicación GPS y demás datos ocultos).
3. El formulario NO habla directo con la base de datos. Habla con una **función segura** de Supabase (`submit-complaint`) que: valida los datos, comprueba con Cloudflare que quien envía es una persona (usando la clave secreta, que solo vive en el servidor), aplica los límites de envío, vuelve a limpiar cada foto, la guarda en un bucket **privado** (`complaint-evidence`) y registra el reporte.
4. La persona recibe un código `TP-XXXX-XXXX`. Es **la única forma** de consultar el estado: no se puede recuperar ni saber quién lo envió.
5. Si el servidor no está listo (falta la clave de Turnstile, la función no está desplegada…), la página **lo dice y no finge** que el reporte se envió.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 6 cambia cómo se guardan las denuncias: la función SQL que antes podía llamar el navegador ahora **solo la puede ejecutar la función segura** (así nadie se salta el anti-robots). **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (usa `drop policy if exists` y reemplaza la función de denuncias); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 35 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela (no contiene claves ni datos de usuarios).
5. Comprueba que existe el bucket de evidencias: **Storage** → debe haber un bucket **`complaint-evidence`** marcado como **Private** (candado).

## Paso 2 · Crear el widget de Cloudflare Turnstile (10 minutos)

Ya tienes cuenta de Cloudflare (la usas para Pages). Turnstile es gratuito (hasta 20 widgets y desafíos sin límite) y **no pide tarjeta**.

1. Entra a <https://dash.cloudflare.com> y, en el menú de la izquierda, busca **Turnstile** (en algunas cuentas está dentro de *Application security*; también puedes usar el buscador del panel).
2. Pulsa **Add widget** (o **Add site**).
3. **Widget name:** `tecnopatitas`.
4. **Hostname Management → Add hostnames:** escribe `tecnopatitas.pages.dev` (solo el nombre: sin `https://`, sin `/` y sin `*`). Si vas a probar en tu computadora, añade también `localhost`.
5. **Widget Mode:** deja **Managed** (recomendado). **Pre-clearance:** No.
6. Pulsa **Create**.
7. Cloudflare te muestra **dos claves**:
   - **Site Key** → es **pública**. Cópiala: la usarás en el Paso 3.
   - **Secret Key** → es **secreta**. Déjala a la vista en esa pestaña (o cópiala en un bloc de notas local) solo hasta terminar los Pasos 5 y 7. **No la pegues en ningún archivo ni en el chat.**

> Cloudflare no documenta expresamente los dominios `*.pages.dev`, pero es el caso normal de un sitio en Pages y debe funcionar. Si al guardar el hostname Cloudflare lo **rechaza**, copia el mensaje exacto y envíamelo. Los enlaces de vista previa de Pages (los que tienen una cadena larga antes de `tecnopatitas.pages.dev`) no están en la lista: ahí el anti-robots mostrará error, y es lo esperado.

## Paso 3 · Poner la clave del sitio en `js/config.js`

1. En tu repositorio de GitHub abre `js/config.js` y pulsa el lápiz (**Edit this file**).
2. Busca la línea:

   ```js
   TURNSTILE_SITE_KEY: ''
   ```

   y pega entre las comillas **la Site Key** (suele empezar con `0x4…`). Debe quedar así (con tu clave):

   ```js
   TURNSTILE_SITE_KEY: '0x4AAAAAAA…tu-clave-de-sitio…'
   ```

3. **Commit changes**. Si todavía no has subido los archivos nuevos del Paso 6, hazlo en el mismo commit o después; el orden entre los Pasos 3 y 6 no importa, pero ambos deben estar hechos antes de probar.

> **Seguro contra equivocaciones:** si por error pegas la **Secret Key** (es más larga, unos 35 caracteres), la página **se niega a funcionar** y muestra un aviso en rojo. Si pasa, quítala de inmediato y **genera una clave nueva** en Cloudflare (Turnstile → tu widget → **Rotate secret key**), porque lo que se sube a GitHub queda visible.

## Paso 4 · Crear la función segura en Supabase (10 minutos)

1. Supabase → tu proyecto → **Edge Functions** (menú izquierdo).
2. **Deploy a new function** → **Via Editor** (crear desde el editor del navegador; no necesitas instalar nada).
3. **Function name:** escribe exactamente `submit-complaint` (minúsculas y guion; si el nombre es otro, el sitio recibirá un 404).
4. Borra el código de ejemplo del editor. Abre `supabase/functions/submit-complaint/index.ts` (de esta carpeta), copia **todo** su contenido y pégalo en el editor. El archivo no importa nada externo a propósito, así que se pega tal cual.
5. Pulsa **Deploy function** (o **Deploy**). Espera a que diga que se desplegó.
6. Revisa que la función aparezca como **Active**/**Deployed**. Más adelante, si algo falla, sus mensajes están en la pestaña **Logs** de esa misma función. El código de la función **no escribe en esos registros** ni el texto del reporte ni la IP (Supabase, como cualquier proveedor, guarda por su cuenta registros técnicos de las peticiones: por eso la página advierte que no hay anonimato técnico absoluto).

> Supabase le da a la función automáticamente `SUPABASE_URL` y la clave del servidor (`SUPABASE_SECRET_KEYS`): **no tienes que crearlas ni copiarlas**.

## Paso 5 · Guardar la clave secreta de Turnstile como secreto de la función

Aquí es donde se usa la **Secret Key** de Cloudflare. La escribes **tú, directamente en el panel**.

1. Supabase → **Edge Functions** → pestaña/botón **Secrets** (puede llamarse *Manage secrets* o estar en *Project Settings → Edge Functions*).
2. **Add new secret** (o *Add or replace secrets*):
   - **Name:** `TURNSTILE_SECRET_KEY` (exactamente así, en mayúsculas).
   - **Value:** pega la **Secret Key** de Cloudflare (la del Paso 2).
3. **Save**.
4. Si más tarde la página dice «El envío de reportes todavía no está configurado», vuelve a desplegar la función (Edge Functions → `submit-complaint` → **Deploy** otra vez) y recarga la página: la función lee el secreto al arrancar.

Mientras no exista este secreto, la función **rechaza todos los reportes** (falla cerrado): es mejor no recibir denuncias que dejar la puerta abierta a robots.

## Paso 6 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Se reemplazan los archivos con el mismo nombre y se añaden los nuevos: `js/tp-captcha.js`, `js/pages/denuncias.js`, `supabase/functions/submit-complaint/index.ts`, `GUIA_ETAPA_6.md` y `pruebas-web/` (`mock_etapa6.py`, `probar_denuncias.py`, `probar_funcion.py`, `servidor_funcion.mjs`). Se reemplazan, entre otros, `denuncias.html`, `registro.html`, `login.html`, `recuperar.html`, `js/pages/registro.js`, `login.js`, `recuperar.js`, `js/tp-client.js`, `js/config.js` (**cuidado:** si ya pegaste tu Site Key en el Paso 3, vuelve a poner tu clave en esa línea después de subir, o sube todo **menos** `js/config.js`), `css/styles.css`, `_headers`, `.env.example`, `README.md` y la carpeta `database/`.
2. Cloudflare Pages publica solo (1–2 minutos).
3. Abre `https://tecnopatitas.pages.dev/denuncias.html` con la consola abierta (**F12 → Console**). **No debe haber errores rojos.** Si ves uno que diga *Content Security Policy* o *Refused to …*, cópialo y envíamelo. (`_headers` ahora permite scripts y marcos de `challenges.cloudflare.com`, y nada más.)

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular, cierra y abre la pestaña).

## Paso 7 · (Opcional, recomendado) Activar el anti-robots también en el registro y el inicio de sesión

Esto hace que Supabase exija la verificación de Turnstile en **registro, inicio de sesión con contraseña y «olvidé mi contraseña»**.

> **Hazlo SOLO después de que el Paso 3 esté publicado** (la Site Key ya en tu sitio). Si lo activas antes, **nadie podrá registrarse ni entrar** (ni tú) hasta que lo desactives.

1. Supabase → **Authentication** → **Attack Protection** (en algunos paneles se llama **Bot and Abuse Protection**).
2. Activa **Enable CAPTCHA protection**.
3. **Provider:** elige **Turnstile (Cloudflare)**.
4. **Captcha secret:** pega la **Secret Key** de Cloudflare (la misma del Paso 2). La escribes tú; no me la pases.
5. **Save**.
6. Prueba de inmediato `registro.html`, `login.html` y `recuperar.html` (verás el recuadro de verificación). **Si algo sale mal, desactiva el interruptor y todo vuelve a funcionar como antes.**

Si decides no activarlo, no pasa nada: las páginas de acceso funcionan igual que en la Etapa 3 y la verificación simplemente no se pide a Supabase (el widget se muestra, pero Supabase no lo comprueba).

---

## Pruebas en tu sitio real (marca cada una)

Haz las pruebas desde el celular y desde la computadora, con **F12 → Console** abierta en la computadora.

**A. Estado de la página**

1. `denuncias.html` no muestra el aviso «todavía no está activado» y aparece el recuadro de **verificación de Cloudflare** (puede resolverse sola). Si el aviso sigue ahí: Pasos 2–3 y recarga forzando.

**B. Validaciones (no deben enviar nada)**

2. Pulsa **Enviar reporte** con el formulario vacío: pide el tipo. Escribe solo 10 caracteres de descripción: pide 30. Pon una fecha de mañana: la rechaza. Deja sin marcar la casilla de aceptación: la pide. Sin resolver la verificación: la pide.

**C. Envío sin fotos**

3. Llena el formulario con un caso **inventado** (no uses datos reales de personas ni de lugares reales identificables), resuelve la verificación y pulsa **Enviar reporte**. Debe aparecer **«Recibimos tu reporte»** y un código `TP-XXXX-XXXX`. **Anótalo.**
4. Lee el texto: debe decir que el reporte quedó **registrado para revisión del equipo** y que **no se presentó ante ninguna autoridad**.
5. Pulsa **Copiar código** y pégalo en cualquier campo para comprobar que se copió.
6. Pulsa **Consultar este código**: debe mostrar el estado **Recibida**.

**D. Anonimato (lo más importante)**

7. En Supabase → **Table Editor → `complaints`**: debe estar tu reporte. Revisa las columnas: **no hay ninguna** de usuario, correo, teléfono ni IP. Solo tipo, descripción, fecha, estado, municipio, estado del trámite, etc.
8. Repite el envío **con una cuenta abierta** (inicia sesión en otra pestaña y vuelve a `denuncias.html`): el reporte queda igual de anónimo; en la base no hay nada que lo relacione con tu cuenta.
9. En el navegador (**F12 → Network**), pulsa el envío y abre la petición `submit-complaint`: en **Request Headers** no debe haber **Authorization**, y en el cuerpo solo campos del reporte.

**E. Fotos**

10. Envía un reporte con **2 fotos** (tomadas con el celular, de preferencia con ubicación activada). Deben verse las miniaturas con su peso en KB y el botón **Quitar**. Al elegir una cuarta foto, avisa «Máximo 3».
11. Supabase → **Storage → `complaint-evidence`**: hay una carpeta con un identificador largo y dentro `1.jpg`, `2.jpg`. Descárgalas y revisa sus propiedades: son JPEG **sin ubicación GPS ni modelo de cámara**. El bucket es **privado**: la dirección directa de una foto **no** se abre desde un navegador sin sesión.
12. Intenta subir un archivo que no sea imagen renombrado a `.jpg`: debe rechazarlo con el nombre del archivo.

**F. Seguimiento**

13. En «Consultar seguimiento» escribe tu código en minúsculas y sin guiones (`tp abcd 2345`): lo acepta y lo normaliza. Un código inventado dice «No encontramos ese código».
14. En **SQL Editor** cambia el estado del reporte de prueba (usa tu código):

    ```sql
    update public.complaints
       set status = 'en_revision', public_update = 'El equipo está revisando tu reporte.'
     where tracking_code = 'TP-XXXX-XXXX';
    ```

    Vuelve a consultar: muestra **En revisión** y «Mensaje del equipo: …». Las **notas internas** (`internal_notes`) nunca se muestran.

**G. Límites**

15. Desde la misma red, sigue enviando reportes de prueba (puedes repetir el mismo caso) hasta llegar a **6 en la misma hora** contando los anteriores: el sexto debe decir **«Demasiadas solicitudes. Intenta de nuevo más tarde.»** (el límite es de 5 por hora y 15 por día por visitante; cada envío con éxito cuenta). La consulta de seguimiento también tiene tope (30 por hora).
16. **Cambia de red** (por ejemplo, datos del celular en lugar del wifi) y envía otro reporte: debe dejarte pasar, porque el límite es **por visitante**. Si desde una red distinta también te frena, avísame: significaría que Supabase no está entregando la IP a la función y todos compartirían un solo límite (es seguro, pero habría que ajustarlo).

**H. Anti-robots en el acceso** (solo si hiciste el Paso 7)

17. `registro.html`: sin resolver la verificación, no deja crear la cuenta; con ella, funciona igual que antes. Lo mismo en `login.html` y `recuperar.html`.

**I. Consola**

18. Durante todas las pruebas, **F12 → Console** no debe mostrar errores rojos de *Content Security Policy*.

### Limpiar los reportes de prueba

Borrar las filas **no** borra las fotos. Hazlo en este orden:

1. **Storage → `complaint-evidence`**: marca las carpetas de prueba y elimínalas.
2. **SQL Editor** (esto borra TODAS las denuncias; úsalo solo mientras no haya reportes reales):

   ```sql
   delete from public.complaints;
   ```

   (Si ya hay reportes reales, borra solo los tuyos: `delete from public.complaints where tracking_code in ('TP-XXXX-XXXX', 'TP-YYYY-YYYY');`.)

---

## Cómo revisa el administrador las denuncias (hasta la Etapa 10)

El panel de administración llega en la Etapa 10. Mientras, desde **SQL Editor**:

**Ver las denuncias pendientes** (las más nuevas primero):

```sql
select tracking_code, status, priority, type, state, municipality, approx_date,
       cardinality(photo_paths) as fotos, created_at
  from public.complaints
 where status in ('recibida', 'en_revision')
 order by created_at desc;
```

**Leer una denuncia completa:**

```sql
select * from public.complaints where tracking_code = 'TP-XXXX-XXXX';
```

**Ver las fotos:** Storage → `complaint-evidence` → carpeta cuyo nombre aparece en `photo_paths` (por ejemplo `3f2c…/1.jpg`) → abrir o descargar.

**Cambiar el estado y dejar un mensaje para quien reportó** (estados: `recibida`, `en_revision`, `en_proceso`, `canalizada`, `cerrada`; prioridad opcional: `baja`, `media`, `alta`, `urgente`):

```sql
update public.complaints
   set status = 'canalizada',
       priority = 'alta',
       attended = true,
       public_update = 'El equipo orientó el caso hacia la instancia que puede atenderlo.',
       internal_notes = 'Notas solo para el equipo; nunca se muestran al público.'
 where tracking_code = 'TP-XXXX-XXXX';
```

- `public_update` (hasta 500 caracteres) **es público**: lo ve cualquiera que tenga el código. No pongas ahí datos personales de nadie.
- Los cambios de estado y prioridad quedan en la bitácora de acciones (`admin_audit_log`).
- «Canalizada» significa que el equipo **orientó** el caso; **no** significa que TECNOPATITAS haya presentado una denuncia oficial. La página lo aclara.

---

### Si algo falla: causas probables

| Síntoma | Qué revisar |
|---|---|
| «El envío de reportes todavía no está activado en este sitio…» y el formulario aparece bloqueado | Falta la Site Key en `js/config.js` (Paso 3) o no se publicó. Recarga forzando. |
| Aviso rojo: «…parece ser la SECRETA…» | Pegaste la Secret Key en `config.js`. Quítala, pon la **Site Key**, y genera una clave secreta nueva en Cloudflare (**Rotate secret key**) y actualiza los Pasos 5 y 7. |
| «No se pudo cargar la verificación anti-robots…» | Bloqueador de anuncios o de contenido, o sin internet. Desactívalo para tu sitio y pulsa **Reintentar**. |
| El recuadro de Cloudflare muestra un error de dominio | El hostname no está en el widget (Paso 2, punto 4). Entra a la dirección exacta `tecnopatitas.pages.dev`, no a un enlace de vista previa. |
| «El envío de reportes todavía no está configurado. Inténtalo más tarde.» | La función no encuentra `TURNSTILE_SECRET_KEY` (Paso 5): revisa el nombre exacto y vuelve a desplegar. |
| «Este servicio todavía no está activado en el servidor» | La función no está desplegada o su nombre no es exactamente `submit-complaint` (Paso 4). |
| «El servidor rechazó la solicitud. Avisa al administrador.» (401/403) | Supabase está exigiendo un JWT a la función. En **Edge Functions → `submit-complaint` → Settings**, desactiva **Verify JWT / Enforce JWT Verification** y guarda. Es seguro: la función no depende de la sesión, comprueba Turnstile por su cuenta y aplica sus propios límites. |
| «No se pudo comprobar que eres una persona. Inténtalo de nuevo.» | La Secret Key del Paso 5 no corresponde a la Site Key del Paso 3 (son de widgets distintos), el hostname no coincide, o pasaron más de 5 minutos desde que se resolvió. Se reinicia sola: resuélvela otra vez. |
| «No pudimos comprobar la verificación anti-robots. Inténtalo de nuevo en unos minutos.» | La función no pudo hablar con Cloudflare. Si dura, revisa los **Logs** de la función y <https://www.cloudflarestatus.com>. |
| «No se pudieron guardar las fotos…» | Que exista el bucket `complaint-evidence` (Paso 1, punto 5). Envía sin fotos para confirmar que lo demás funciona. |
| «Por ahora no podemos recibir fotografías…» | Se alcanzó el tope de 300 MB de evidencias (para no agotar el 1 GB gratuito). Limpia reportes de prueba o archiva evidencias. |
| «Demasiadas solicitudes…» | Es el límite por visitante (5 por hora, 15 por día) o el tope global diario. Espera o prueba desde otra red. |
| Tras el Paso 7 nadie puede entrar | Desactiva **Enable CAPTCHA protection** en Supabase y verifica que `TURNSTILE_SITE_KEY` esté publicada y que la clave secreta del Paso 7 sea la del mismo widget. |
| El código de seguimiento «no existe» | Revisa que no tenga I, O, 0 ni 1 (no se usan); el sistema normaliza mayúsculas, espacios y guiones. |

---

## Qué hace y qué no hace esta etapa

**Sí hace**

- Reporte **sin datos de quien denuncia** (ni nombre, correo, teléfono, sesión ni IP guardada), con código de seguimiento aleatorio.
- Anti-robots con Cloudflare Turnstile **verificado en el servidor**; campo trampa para robots; límites por visitante (5 por hora, 15 por día) y topes globales (300 reportes al día, 100 con fotos al día); tope de 300 MB de evidencias.
- Fotos: hasta 3 por reporte, solo JPEG reducido, **sin metadatos** (se limpian dos veces: en el navegador y en el servidor), en un bucket **privado**; si algo falla, no queda nada guardado.
- Consulta pública de estado por código (estado, fechas y mensaje del equipo; jamás notas internas).
- Turnstile opcional en registro, inicio de sesión y recuperar contraseña (Paso 7).
- Todo lo que viene del servidor se muestra como **texto**.

**No hace (y no finge hacerlo)**

- **No presenta denuncias ante autoridades**: solo las registra para revisión del equipo. Para una denuncia oficial, la persona debe acudir a la fiscalía o a la autoridad de protección animal de su estado o municipio (y llamar al 911 si hay peligro inmediato). El texto con las autoridades en la página dice que se verificará antes de publicar la versión final: **confirma esos datos** antes de abrir el sitio al público.
- **No garantiza anonimato técnico absoluto** frente a todos los proveedores de infraestructura (Supabase, Cloudflare): la página lo advierte. Lo que sí garantiza es que **TECNOPATITAS no guarda nada que identifique** a quien reporta.
- **Panel de administración:** hasta la Etapa 10, el equipo revisa y responde con SQL (sección anterior).
- **Avisos por correo o notificación** al llegar un reporte: llegan con las notificaciones (Etapa 8); nunca se afirma que se envió algo que no se envió.
- **Limpieza automática** de evidencias: se borran a mano (arriba).

## Decisiones que conviene que confirmes

1. **Máximo 3 fotos por reporte**, cada una reducida por el navegador a un lado mayor de 1280 px y con un tope de 2 MB (normalmente pesan unos 300 KB). Es menos de los «5 MB» de la propuesta inicial, porque así 300 MB alcanzan para cientos de reportes en el plan gratuito.
2. **Límites:** 5 reportes por hora y 15 por día por visitante; 300 al día en total y 100 con fotos al día; 300 MB de evidencias. El «visitante» se identifica con un código derivado de la IP que cambia cada día (no se guarda la IP). Detrás de una red compartida (escuela, oficina) varias personas pueden compartir el límite.
3. **El código de seguimiento no se puede recuperar.** Es la decisión que protege el anonimato. Si se pierde, hay que hacer otro reporte.
4. **El mensaje público del equipo** (`public_update`) lo ve cualquiera que tenga el código.
5. **Turnstile en el acceso es opcional** (Paso 7). Se recomienda activarlo antes de abrir el registro al público.
6. **Estados del reporte:** recibida → en revisión → en proceso → canalizada → cerrada. «Canalizada» solo significa que el equipo orientó el caso.

## Para la Etapa 7 (chat de atención) necesitaré de ti

- Que pruebes esta etapa y me confirmes que todo funcionó (o me envíes el síntoma exacto si algo falla).
- Decidir si el chat será solo entre el usuario y el equipo (lo previsto) y cuántos mensajes diarios permitimos por cuenta (propuesta: 100 al día, para no agotar el plan gratuito de Supabase).
- Aclarar la decisión pendiente de los correos: ¿usamos una cuenta de Gmail exclusiva del proyecto como SMTP de Supabase (permite que cualquier persona reciba los correos de confirmación), o seguimos con cuentas de prueba confirmadas a mano para la demostración?
