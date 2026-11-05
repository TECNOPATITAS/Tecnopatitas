# Etapa 3 · Cuentas y sesión: lo que tienes que hacer tú

Esta etapa conecta el sitio con **Supabase Auth**: registro, inicio de sesión, recuperar contraseña, sesión y protección de páginas por rol.
El código ya está listo y trae tu **Project URL** y tu clave **publishable** en `js/config.js` (son públicas por diseño; la seguridad real la dan las políticas RLS de la Etapa 2). **Nunca pongas ahí la clave `secret` / `service_role`**: el sitio se niega a arrancar si la detecta.

> Los menús de Supabase cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura.

Tiempo estimado: 20 minutos. Hazlo en este orden.

---

## Paso 1 · Subir los archivos nuevos y esperar el despliegue

1. En tu repositorio de GitHub, sube **el contenido** de esta carpeta sobre lo que ya tienes (**Add file → Upload files**, arrastra todo, **Commit changes**). Se reemplazan los archivos con el mismo nombre y se añaden los nuevos (`js/tp-client.js`, `js/guard.js`, `js/pages/…`, `nueva-contrasena.html`, `GUIA_ETAPA_3.md`…).
2. Cloudflare Pages vuelve a publicar solo (1–2 minutos). Es 1 compilación de las 500 mensuales gratuitas.
3. Abre `https://tecnopatitas.pages.dev/` con la consola del navegador abierta (**F12 → Console**). **No debe aparecer ningún error rojo.** Si ves uno que dice *Content Security Policy* o *Refused to …*, cópialo y mándamelo: la política de seguridad del archivo `_headers` está bloqueando algo que no debería.

## Paso 2 · Decirle a Supabase cuáles son tus direcciones

Sin esto, los enlaces de los correos (confirmar cuenta, recuperar contraseña) llevarían a la dirección equivocada o serían rechazados.

1. En el panel de Supabase abre tu proyecto → **Authentication → URL Configuration**.
2. **Site URL:** `https://tecnopatitas.pages.dev`
3. **Redirect URLs** → **Add URL**, una por una:
   - `https://tecnopatitas.pages.dev/**`
   - `http://localhost:8000/**` (solo si vas a probar en tu computadora)
4. **Save changes.**

Si más adelante compras o conectas un dominio propio, hay que añadirlo aquí también.

## Paso 3 · Longitud mínima de contraseña

El sitio ya exige **10 caracteres como mínimo** al registrarse, pero eso es solo una ayuda en pantalla. Lo que cuenta es la regla del servidor:

1. **Authentication → Sign In / Providers** (o **Providers → Email**; también puede estar en **Authentication → Policies**).
2. Busca **Minimum password length** y pon **10**. Guarda.
3. **No actives** «Prevent use of leaked passwords»: es una función de pago (plan Pro). El sitio ya bloquea por su cuenta las contraseñas más obvias (repetidas, muy comunes o parecidas al correo).

## Paso 4 · Correos: la limitación real del plan gratuito (**léelo**)

> **Actualización (Etapa 9):** ya elegiste Gmail. La versión completa y actualizada de este paso (límites, contraseña de aplicación, plantillas en español, pruebas y fallos comunes) está en **`GUIA_CORREOS_GMAIL.md`**. Sigue esa guía; lo de abajo queda como contexto.

Supabase trae un servicio de correo de cortesía **solo para probar**, con dos límites:

- **Solo envía a los correos de tu equipo de Supabase** (es decir, el tuyo y los de quienes invites a tu organización). A cualquier otra persona le llega el error `email_address_not_authorized`.
- **Máximo 2 correos por hora** en todo el proyecto (error `over_email_send_rate_limit`).

Eso significa que **ahora mismo solo tú (y tu equipo) pueden crear cuentas con confirmación por correo**. El sitio muestra mensajes claros en español cuando pasa esto, y **nunca** dice «te enviamos un correo» si el envío falló.

**Decisión tomada: no hay dominio propio.** Eso descarta a **Resend** (exige un dominio verificado) y a **Brevo** (también pide verificar un dominio y escribir a su soporte para activar el SMTP). Estas son las opciones reales sin dominio, todas gratuitas:

| Opción | Qué implica | Para qué sirve |
|---|---|---|
| **A. Dejarlo así** | Confirmación de correo activada con el servicio de cortesía. Solo funcionan tu correo y los de tu equipo. | Pruebas y **demostración escolar**. No requiere configurar nada. |
| **B. Gmail como servicio de correo** *(recomendada si quieres que otras personas se registren)* | Una cuenta de Gmail **solo para el proyecto** envía los correos mediante una «contraseña de aplicación». Hasta unos 500 destinatarios al día (cifra de fuentes secundarias; no pude abrir la página oficial de Google, confírmala en su ayuda). Sin costo y sin tarjeta. | Uso real a pequeña escala. Los correos pueden caer en *spam* y Gmail puede limitar o suspender el envío si hay mucho volumen o quejas. |
| **C. Apagar «Confirm email»** | Cualquiera se registra al instante, **incluso con un correo que no es suyo**, y «recuperar contraseña» no llega a nadie fuera del equipo. | **No lo recomiendo** con personas reales. |

### Cómo hacer la opción B (Gmail), paso a paso

1. **Crea una cuenta de Gmail nueva solo para el proyecto** (por ejemplo `tecnopatitas.app@gmail.com`). Es mejor no usar tu correo personal: si Google limita el envío, no afecta tu cuenta de siempre.
2. En esa cuenta entra a <https://myaccount.google.com/security> y activa la **Verificación en dos pasos** (sin ella Google no deja crear contraseñas de aplicación).
3. En el buscador de esa misma página escribe **«Contraseñas de aplicaciones»** (*App passwords*), crea una llamada `supabase` y **copia las 16 letras** que muestra. Solo se ven una vez.
4. En Supabase: **Authentication → Emails → SMTP Settings → Enable custom SMTP** y llena:
   - **Sender email:** el Gmail del proyecto
   - **Sender name:** `TECNOPATITAS`
   - **Host:** `smtp.gmail.com`
   - **Port:** `465` (si no funciona, prueba `587`)
   - **Username:** el mismo Gmail del proyecto
   - **Password:** las 16 letras del paso 3 (sin espacios)
5. **Save changes.** Luego, en **Authentication → Rate Limits**, Supabase pone por defecto **30 correos por hora** al activar SMTP propio; para este proyecto alcanza.
6. Repite las pruebas 3, 5 y 11 del Paso 6 **con un correo que no sea del equipo** (por ejemplo, uno tuyo de Hotmail o de un amigo) y revisa también la carpeta de spam.

> **Seguridad:** la contraseña de aplicación es un secreto. Se escribe **solo** en el panel de Supabase. **No me la pegues aquí ni la subas a GitHub.** Si se filtra, bórrala en la misma página de Google y crea otra.
>
> Los correos de Supabase llegan **en inglés** por defecto. Se pueden cambiar a español en **Authentication → Emails → Templates**; si quieres, te preparo las plantillas.
>
> Tampoco necesitas resolver esto hoy: con la opción A todo lo demás de la plataforma se puede construir y demostrar. Se vuelve necesario antes de abrir el sitio a personas reales.

## Paso 5 · Tu cuenta de administrador

Nadie puede volverse administrador desde el navegador; el rol se da desde la base de datos. Hay dos formas; elige según cuántos correos tengas (recuerda el límite del Paso 4: solo funcionan los correos de tu equipo, y **un correo solo puede tener una cuenta**):

- **Si tienes un solo correo (lo más probable):** haz primero las pruebas 1 a 12 del Paso 6 registrándote en el sitio con ese correo, y **al terminar** conviértela en administradora con el SQL de abajo (salta el punto 1).
- **Si quieres crear la cuenta de administrador aparte:** **Authentication → Users → Add user → Create new user**, con otro correo y una contraseña de **10 o más caracteres**, marcando **Auto Confirm User**.

Después, en **SQL Editor → New query**, pega esto cambiando el correo y pulsa **Run**:

```sql
insert into public.admin_roles (user_id, note)
select id, 'Administrador principal' from auth.users where email = 'TU_CORREO@ejemplo.com';
```

Debe decir que insertó 1 fila. Si dice 0, el correo no coincide exactamente con el de la cuenta. Al volver a entrar al sitio, la cabecera dirá «Administración».

## Paso 6 · Prueba en el sitio real (checklist)

Desde aquí **no puedo probar contra tu Supabase** (mi entorno no tiene acceso a internet abierto, y tampoco debe tener tus claves). Mis 105 pruebas del navegador corrieron contra un **simulador** de Supabase; esta lista es la que confirma que el simulador y el servicio real se comportan igual. Usa una ventana de incógnito. Las pruebas 1–12 y 14 se hacen **antes** de volver administradora la cuenta (Paso 5); la 13 y la 15 después.

| # | Qué hacer | Qué debe pasar |
|---|---|---|
| 1 | Entra a `…/perfil.html` sin haber iniciado sesión | Te manda a `login.html` (y la página privada nunca se alcanza a ver) |
| 2 | En `…/admin.html`, igual | Te manda a `login.html` |
| 3 | **Crear cuenta** como *dueño de mascota* con **tu correo de Supabase** y contraseña de 10+ caracteres | Mensaje de «revisa tu correo». Llega un correo de confirmación |
| 4 | Intenta entrar **antes** de confirmar | Mensaje: falta confirmar el correo |
| 5 | Abre el enlace del correo | Vuelve al sitio con la sesión iniciada (y la dirección queda limpia, sin `#access_token…`) |
| 6 | Entra a **Mi cuenta** (`perfil.html`) | Ves tu nombre y tu plan **Básico** |
| 7 | Cambia tu nombre y teléfono, **Guardar**, recarga la página | Los cambios se conservan |
| 8 | Cambia la contraseña (pide la actual) | Mensaje de éxito; cierra sesión y entra con la nueva |
| 9 | Con esa cuenta de dueño abre `…/panel-aliado.html` y `…/admin.html` | Aviso de acceso restringido (no el panel) |
| 10 | **Salir** | Vuelves al inicio; `perfil.html` ya te pide login |
| 11 | **¿Olvidaste tu contraseña?** con tu correo | Mensaje genérico; llega un correo; el enlace abre `nueva-contrasena.html`; tras cambiarla entras con la nueva |
| 12 | Pon un correo que **no** esté registrado en «recuperar» | **Mismo mensaje** que en el paso 11 (para no revelar quién tiene cuenta) |
| 13 | Ya con el SQL del Paso 5 aplicado, **cierra sesión y vuelve a entrar** con la cuenta de administrador | La cabecera dice «Administración» y `admin.html` abre |
| 14 | Con dos pestañas abiertas, cierra sesión en una | La otra, si estaba en una página privada, pide iniciar sesión |
| 15 | Registra una cuenta *aliado comercial* con otro correo del equipo (si solo tienes uno, primero borra la cuenta de prueba en **Authentication → Users → Delete user**) | Entra a `panel-aliado.html`; en `mascota.html` ve el aviso de «solo para dueños» |

**Si algo falla**, mándame: el número del paso, lo que ves en pantalla y, si es posible, el mensaje rojo de la consola (**F12 → Console**) o de la pestaña **Network** (la petición que salió en rojo). Con eso lo corrijo.

Para borrar cuentas de prueba: **Authentication → Users →** (menú `…` de la fila) **Delete user**.

---

## Qué hace y qué no hace esta etapa

**Sí**

- Registro de dueños y aliados (el rol *admin* no se puede elegir ni enviar desde el navegador).
- Inicio y cierre de sesión; sesión que se renueva sola y se cierra en todas las pestañas.
- Recuperación y cambio de contraseña (el cambio pide la contraseña actual).
- Protección de páginas privadas por rol, con el rol de administrador **verificado en el servidor** (`is_admin()`).
- Edición del perfil (nombre y teléfono) y consulta del plan vigente.
- Mensajes de error en español; sin revelar si un correo ya tiene cuenta.
- Política de seguridad (CSP) que solo permite hablar con tu proyecto de Supabase.

**No (todavía)**

- **Las protecciones de páginas en el navegador son solo comodidad.** Quien salte ese código no obtiene datos: lo que protege la información son las políticas RLS de la Etapa 2.
- **Subir foto de perfil**: se activa en la Etapa 4 junto con las demás subidas de archivos.
- **Eliminar la cuenta** y **aviso de privacidad / términos**: faltan. Antes de abrir el sitio a personas reales hay que añadirlos (Etapa 11 como muy tarde).
- **Anti-robots (Cloudflare Turnstile, gratis)** en el registro: se añade junto con denuncias (Etapa 6); mientras tanto Supabase aplica sus límites de peticiones.
- **Correos para cualquier persona**: depende del Paso 4.
- **Contratación de planes y cobros: no están habilitados.** No se pide ni se guarda ningún dato de tarjeta.

## Decisiones que conviene que confirmes

1. **Enlaces de correo con el flujo «implícito»:** el enlace regresa al sitio con la sesión en la dirección (`#access_token=…`) y el sitio la guarda y limpia la dirección de inmediato. Es el flujo que funciona sin servidor propio. (El flujo PKCE necesita un servidor intermedio; si más adelante usamos Functions, se puede cambiar.)
2. **Sesión guardada en el navegador (`localStorage`):** es lo habitual en sitios estáticos. Por eso toda la página usa `textContent` (nunca inserta HTML venido del servidor) y la CSP bloquea scripts ajenos.
3. **`js/config.js` se sube a GitHub** con la URL y la clave publishable. Es público a propósito (cualquiera lo vería en el navegador de todos modos).

## Etapa 4 (siguiente): mascotas, carnet, QR y fotos

Conectará `mascota.html`, `carnet.html` y la foto de perfil, con subida de archivos a Supabase Storage (JPG/PNG/WebP, con los topes de la Etapa 2) y la placa QR para Huellita VIP. No necesito nada nuevo de tu parte salvo las respuestas de este documento.
