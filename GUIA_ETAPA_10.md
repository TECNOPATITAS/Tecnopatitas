# Etapa 10 · Panel de administración (y confirmación de correo desactivada): lo que tienes que hacer tú

Esta etapa convierte `admin.html` en el **panel de administración de verdad**: ya no tienes que usar el SQL Editor para aprobar aliados, resolver solicitudes de plan, atender el chat o dar seguimiento a las denuncias. También conecta la página pública de **Guías de cuidado** (`guias.html`) con la base de datos, para que puedas escribirlas y publicarlas desde el panel.

Además, como pediste, **ya no usamos Gmail como servicio de correo** y la **confirmación de correo se desactiva** (Paso 3). Eso es un ajuste que solo puedes hacer tú en el panel de Supabase.

> Los menús de Supabase y GitHub cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 30–40 minutos. **No hay cuentas nuevas ni claves que pegar en esta etapa.**

**Reglas que siguen vigentes:**

- **No hay pagos.** El panel asigna planes **a mano y sin cobrar**; ninguna pantalla pide tarjeta ni datos financieros. Contratar y cobrar **no está habilitado**.
- **Nadie se vuelve administrador desde el navegador.** Los roles de administración solo se dan desde el SQL Editor (tabla `admin_roles`). El panel **no** tiene pantalla para crear ni quitar administradores, a propósito.
- **El panel es solo comodidad. La seguridad real está en el servidor:** cada acción es una función `admin_*` que vuelve a comprobar que quien llama es administrador (error «No autorizado.» si no) y deja una línea en la bitácora. Si alguien abre `admin.html` sin ser administrador, solo ve «Acceso restringido»; y aunque manipulara el navegador, el servidor rechazaría cada llamada.
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase ni la contraseña de la base de datos.

---

## Cómo funciona (para que sepas qué estás instalando)

El panel tiene **8 secciones** (menú de la izquierda; en el teléfono, arriba):

1. **Resumen.** Once cifras (usuarios, cuentas suspendidas, aliados en revisión y en total, denuncias pendientes y en total, conversaciones sin responder y abiertas, solicitudes de plan, suscripciones activas, mascotas). **Lo que espera atención aparece resaltado** y cada tarjeta lleva a su sección.
2. **Usuarios.** Buscar por nombre o correo (25 por página). La ficha muestra **solo datos de la cuenta y conteos** (tipo de cuenta, registro, último acceso, plan, número de mascotas / establecimientos / conversaciones). **No muestra el contenido** de sus mascotas ni de sus conversaciones. Puedes **suspender / reactivar** (con motivo opcional que la persona ve en su aviso) y **asignar un plan a mano** (dueño: Pro o VIP; aliado: Plata u Oro). **A una cuenta de administración no se le puede suspender desde el panel.**
3. **Aliados.** Filtro por estado (por omisión «En revisión»). Ves los datos del establecimiento tal como los capturó su dueño, **aprobar / rechazar / suspender / regresar a revisión** (avisa al dueño), dar o quitar **«Aliado verificado»** (solo a aprobados) y **retirar una promoción** que no cumple las reglas (se **borra**; el dueño recibe el motivo). **El panel no edita los datos del establecimiento**: eso lo hace su dueño.
4. **Denuncias.** Bandeja de denuncias anónimas (por omisión, las pendientes). Puedes cambiar **estado, prioridad, «atendida», la actualización pública** (la ve quien tenga el código de seguimiento) y las **notas internas** (solo el equipo). El texto original **no se puede modificar**. Las **fotos de evidencia** viven en un bucket privado y se muestran con enlaces firmados que duran 10 minutos y que solo un administrador puede pedir. **Las denuncias no tienen ningún dato de quien reporta**, y así lo dice la pantalla. **«Canalizada» significa que orientaste el caso a la instancia que puede atenderlo; NO significa que TECNOPATITAS haya presentado una denuncia oficial**, y la pantalla lo aclara.
5. **Guías.** Editor de las guías de cuidado: título, dirección (se genera sola desde el título), categoría, resumen, contenido, fuente y casilla **«Publicar»**. **Una guía nueva queda como borrador**; publicar es una decisión explícita. El contenido es **texto**: párrafos separados por una línea en blanco y una línea que empieza con `## ` es un subtítulo (no se acepta HTML). Hay vista previa y borrado con confirmación. **Las guías son información general y no sustituyen a un veterinario; revísalas con un profesional antes de publicarlas.**
6. **Suscripciones.** Dos pestañas: **Solicitudes de plan** (aprobar activando el plan, o rechazar, con nota para la persona y fecha de vencimiento opcional) y **Suscripciones** (renovar un periodo, cancelar, cambiar la fecha de vencimiento). **Todo manual y sin cobro**; cada acción avisa a la persona.
7. **Atención.** La bandeja del chat: «Sin responder» (las más antiguas primero), abiertas, cerradas, todas. Abres una conversación, **respondes como «Equipo TECNOPATITAS»** (la persona recibe un aviso), cierras o reabres. **Responder en una conversación cerrada la reabre.** La bandeja se actualiza sola cada 30 segundos y la conversación abierta cada 15 mientras la pestaña está visible, **sin perder lo que estás escribiendo**.
8. **Bitácora.** Historial **de solo lectura** de las acciones del panel: quién, qué y sobre qué. **No guarda contenidos** (ni mensajes, ni notas, ni el texto de las guías). No se puede borrar ni editar desde el sitio.

**Guías públicas (`guias.html`).** Ahora lista **solo las guías publicadas**, con búsqueda y filtro por categoría, y cada guía se abre en `guias.html?g=su-direccion`. Un borrador **no se puede leer**, ni adivinando su dirección: lo impone la base de datos, no la página.

**Avisos al equipo.** Las notificaciones que llegan a la campana de las cuentas de administración (denuncia nueva, chat esperando respuesta, solicitud de plan) **abren directamente la sección correspondiente** del panel.

**Lo que el panel NO hace (a propósito):** crear o quitar administradores, borrar usuarios, editar los datos de un establecimiento, ver el contenido de las mascotas o los chats de una persona fuera de Atención, ni cobrar nada.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 10 añade las 28 funciones `admin_*`, la bitácora de las guías y los permisos de lectura de la evidencia. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (reemplaza funciones y políticas); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 37 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela.

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Los archivos que cambian o se añaden en esta etapa son:
   - **Nuevos:** `js/pages/admin-usuarios.js`, `js/pages/admin-aliados.js`, `js/pages/admin-denuncias.js`, `js/pages/admin-guias.js`, `js/pages/admin-subs.js`, `js/pages/admin-atencion.js`, `js/pages/admin-bitacora.js`, `js/tp-guides.js`, `js/pages/guias.js`, `GUIA_ETAPA_10.md`.
   - **Cambian:** `admin.html`, `guias.html`, `recuperar.html`, `js/pages/admin.js`, `js/tp-client.js`, `css/styles.css`, la carpeta `database/…`, `GUIA_CORREOS_GMAIL.md`, `GUIA_ETAPA_3.md`, `GUIA_ETAPA_9.md` y `README.md`.
2. Cloudflare Pages publica solo (1–2 minutos). **No hace falta cambiar `js/config.js` ni `_headers`.**
3. Abre `https://tecnopatitas.pages.dev/guias.html` **sin iniciar sesión** con la consola abierta (**F12 → Console**): debe verse la página (todavía sin guías, con el aviso «Aún no hay guías publicadas») y **sin errores rojos**.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular cierra y abre la pestaña).

## Paso 3 · Desactivar la confirmación de correo (lo haces tú, 2 minutos)

**Qué hace esto:** quien se registre **entra de inmediato**, sin tener que abrir un correo. El sitio ya está preparado para ese caso (al registrarse con éxito, inicia sesión y te lleva a tu página).

1. Supabase → tu proyecto → **Authentication**.
2. Entra a **Sign In / Providers** (en versiones anteriores se llama **Providers**) y abre **Email**.
3. Apaga el interruptor **«Confirm email»** y pulsa **Save**.
4. Si algunas cuentas se registraron **antes** y se quedaron «sin confirmar», no podrán entrar. En **SQL Editor → New query** corre esto una vez para confirmarlas todas (o agrega `and email = 'CORREO'` para una sola):

   ```sql
   update auth.users set email_confirmed_at = now() where email_confirmed_at is null;
   ```

5. **Prueba:** en una ventana de incógnito crea una cuenta nueva en `registro.html`. Debe **entrar directamente** a su página, sin pedir confirmar nada.

**Qué cambia al desactivarla (para que lo decidas con los ojos abiertos):**

- **Nadie comprueba que el correo sea de quien se registra.** Puede haber cuentas con correos falsos o ajenos. La seguridad de los datos **no depende de eso** (las reglas RLS se basan en la cuenta, no en el correo), pero **ya no puedes fiarte de que un correo registrado sea de una persona real**.
- **Cuidado al dar el rol de administración:** haz las cuentas de administración **tú mismo** (Authentication → Users → *Add user* con **Auto Confirm User**, o registrándote tú) y revisa que el correo al que le das el rol sea el de la persona correcta antes de correr el `insert into public.admin_roles…`.
- **Recuperar contraseña por correo no funcionará para personas normales.** El servicio de correo de cortesía de Supabase solo escribe a los correos de **tu equipo** de Supabase y un máximo de 2 por hora; sin un SMTP propio (Gmail quedó descartado por ahora), quien olvide su contraseña **no recibirá el enlace**. La pantalla de recuperar ya no promete un envío y ahora avisa de esto. Mientras tanto, lo puedes resolver **tú** desde el SQL Editor (la persona debe cambiarla en cuanto entre; **no pude probar esta consulta en tu Supabase real**):

  ```sql
  update auth.users
     set encrypted_password = extensions.crypt('PON-AQUÍ-UNA-CLAVE-TEMPORAL-LARGA', extensions.gen_salt('bf'))
   where email = 'CORREO-DE-LA-PERSONA';
  ```

  Entrégale la clave temporal por un medio que ya uses con esa persona. **Nunca** pidas ni guardes su contraseña original.
- **Más cuentas basura posibles.** Supabase aplica límites a los registros por IP, pero no sustituyen a la confirmación; si notas abuso, activa **Cloudflare Turnstile** (opcional, `GUIA_ETAPA_6.md`) y suspende las cuentas desde **Panel → Usuarios**.
- **Si algún día pones un SMTP propio**, vuelve a encender «Confirm email». Las cuentas existentes siguen funcionando, y las guías de Gmail (`GUIA_CORREOS_GMAIL.md`) y las plantillas de `supabase/plantillas-correo/` se conservan por si las quieres usar.

> **Importante:** la plataforma **no envía ningún correo propio** (ni avisos de vacunas ni de planes): todo vive dentro del sitio (campanita y Notificaciones).

---

## Cómo dar el rol de administración (SQL Editor)

Solo desde ahí. Cambia el correo y pulsa **Run** (debe decir que insertó 1 fila):

```sql
insert into public.admin_roles (user_id, note)
select id, 'Administración' from auth.users where email = 'CORREO-DE-LA-PERSONA';
```

Para quitarlo: `delete from public.admin_roles where user_id = (select id from auth.users where email = 'CORREO-DE-LA-PERSONA');`

---

## Paso 4 · Pruebas en el sitio real (checklist)

Usa **tu cuenta de administración** y, en una ventana de incógnito, **una cuenta de dueño de mascota** de pruebas. Si no hay datos, crea algunos desde el sitio (una denuncia anónima, un aliado, un mensaje al chat, una solicitud de plan).

| # | Haz esto | Debe pasar |
|---|---|---|
| 1 | Con la cuenta de **dueño**, abre `admin.html` | «Acceso restringido»; sin menú ni datos. Sin errores en consola |
| 2 | Con tu cuenta de **administración**, abre `admin.html` | Menú con 8 secciones y el **Resumen** con once cifras; lo pendiente aparece resaltado |
| 3 | **Usuarios** → busca a la cuenta de pruebas → «Ver ficha» | Datos de la cuenta y conteos; **sin** contenido de mascotas ni chats |
| 4 | Suspende la cuenta de pruebas con un motivo (botón, luego «Sí») | La cuenta aparece «Suspendida»; la persona recibe un aviso con el motivo y ve el sitio en solo lectura. «Reactivar cuenta» la devuelve a la normalidad |
| 5 | **Aliados** → registra un establecimiento desde otra cuenta de aliado y revísalo | En «En revisión»; **Aprobar** → aparece en `directorio.html` y el dueño recibe aviso. **Suspender** → desaparece del directorio |
| 6 | En un aliado aprobado con una promoción: «Retirar promoción» con motivo | La promoción desaparece del directorio; el dueño recibe el motivo |
| 7 | **Denuncias** → envía una denuncia anónima desde `denuncias.html` (con foto) y ábrela en el panel | Aparece como pendiente, con las fotos; cambia estado/prioridad/actualización pública y guarda. Con el código en `denuncias.html` ves **solo** la actualización pública, nunca las notas internas |
| 8 | Cambia el estado a **«Canalizada»** | El texto aclara que **no** significa denuncia oficial presentada |
| 9 | **Guías** → «Nueva guía», título «Prueba de guía», un par de párrafos y un `## Subtítulo`; guarda **sin** marcar «Publicar» | Queda como **borrador**; abre `guias.html` sin sesión: **no aparece** |
| 10 | Edita la guía, marca **«Publicar»** y guarda | Aparece en `guias.html`; al abrirla se ve el subtítulo y los párrafos. Prueba escribir `<b>hola</b>`: se ve como texto, no como negrita |
| 11 | Despublica la guía y bórrala (botón, luego «Sí») | Desaparece del sitio público y del panel |
| 12 | Con la cuenta de pruebas, pide un plan en `planes.html`; en **Suscripciones → Solicitudes** apruébalo | La persona ve el plan activo **sin ningún cobro**; en **Suscripciones** aparece activa. Prueba **Cambiar fecha**, **Renovar** y **Cancelar** |
| 13 | Con la cuenta de pruebas, escribe al chat (`chat.html`); en **Atención** ábrela y responde | La campana de tu cuenta de administración llevó directo a Atención; la persona recibe la respuesta y un aviso. Ciérrala y vuelve a responder: **se reabre** |
| 14 | **Bitácora** | Aparecen tus acciones con tu nombre y correo, sin textos de mensajes ni notas |
| 15 | Pulsa la **campana** en una cuenta de administración con un aviso del equipo y pulsa «Ver» | Abre `admin.html` directamente en la sección (Denuncias / Atención / Suscripciones) |
| 16 | Revisa el panel en el celular (o F12 → modo móvil a 390 px) | Sin desplazamiento horizontal; botones cómodos de tocar |
| 17 | Crea una cuenta nueva en `registro.html` (incógnito) tras el Paso 3 | Entra directo, sin pedir confirmar el correo |

---

## Decisiones que tomé por ti (dímelas si quieres otra cosa)

- **Los administradores solo se crean desde el SQL Editor.** El panel no tiene forma de dar ni quitar ese rol, ni de suspender a otro administrador.
- **El panel no edita establecimientos:** solo cambia su estado y la verificación, y retira promociones. Los datos los corrige su dueño.
- **Retirar una promoción la borra** (no hay «ocultar»); el dueño recibe el motivo.
- **Responder en una conversación cerrada la reabre.**
- **Atención se actualiza por consulta cada 30/15 segundos** (no usa Realtime): es más simple y gasta menos de las conexiones del plan gratuito. Se pausa si la pestaña está oculta.
- **La bitácora crece sin límite** (una fila por acción, sin contenidos). Hoy no se limpia sola; con el uso normal tardará años en pesar algo relevante.
- **Las guías públicas ahora sí están conectadas** (antes eran una vista de diseño). El formato del contenido es texto: párrafos y `## ` para subtítulos.
- **Las fechas de vencimiento que eliges en el panel terminan a las 23:59:59 hora de México** (UTC−6).
- **Si abres un enlace `admin.html#denuncias` sin sesión**, el inicio de sesión te devuelve al panel, pero **no recuerda la sección** (llegas al Resumen).

## Lo que NO se pudo probar desde aquí

- Tu Supabase real y su PostgREST real (todo se probó contra una base PostgreSQL local con el mismo esquema, con las políticas RLS de verdad, y un simulador de PostgREST/Storage; por eso existe la lista de arriba).
- El interruptor «Confirm email» (es de tu panel de Supabase) y la consulta de restablecer contraseña, que depende de cómo tu Supabase tenga instalada la extensión de cifrado.
- Un teléfono físico (se revisó a 360–390 px en Chromium).

## Qué sigue

**Etapa 11 · Seguridad final y publicación** (aviso de privacidad y términos, eliminar cuenta, limpieza de la demostración, guías pendientes de revisión veterinaria y la lista de pendientes antes de abrir al público): sigue `GUIA_ETAPA_11.md`.
