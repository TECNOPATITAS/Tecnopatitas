# Etapa 7 · Chat de atención al cliente: lo que tienes que hacer tú

Esta etapa conecta `chat.html` con Supabase: cada persona con cuenta puede **escribirle al equipo de TECNOPATITAS** y ver las respuestas **en la misma pantalla, sin recargar** (Supabase Realtime, plan gratuito). Hay límites diarios por cuenta para cuidar el plan gratuito. **No existen mensajes entre usuarios**: cada conversación es solo entre una persona y el equipo.

> Los menús de Supabase y GitHub cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 30–40 minutos. En esta etapa **no hay cuentas nuevas que crear ni claves que pegar**.

**Reglas que siguen vigentes:**

- No actives ningún plan de pago ni prueba gratuita, y no pongas tarjeta en ningún sitio. El chat usa solo Supabase (base de datos y Realtime) en su plan **gratuito**. Si algún panel te pide una tarjeta, **detente** y avísame.
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase, la contraseña de la base de datos ni la contraseña de aplicación de Gmail. En esta etapa tampoco hace falta.
- **El chat es de atención al cliente, no un asistente automático:** lo contesta una persona del equipo y puede tardar. La página lo dice, y también que **nunca se pedirán contraseñas ni datos de tarjeta por el chat**. Contratación y cobros siguen sin estar habilitados.

---

## Cómo funciona (para que sepas qué estás instalando)

1. La persona entra a **Chat** (`chat.html`), pulsa **Nueva**, escribe un asunto (3 a 120 caracteres) y su mensaje (hasta 2000). La conversación y su primer mensaje se guardan **juntos** (función `start_conversation`): si algo falla, no queda nada a medias.
2. Cada conversación pertenece a una sola persona. Las políticas de seguridad (RLS) de Supabase hacen que **solo vea sus propias conversaciones**; el equipo (administradores) puede ver todas. Nadie puede escribir en la conversación de otra persona.
3. **El navegador no decide quién envía ni con qué rol:** el servidor pone el remitente (quien tiene la sesión abierta) y el rol («usuario» o «equipo»). Aunque alguien manipule la página, el servidor lo corrige o lo rechaza.
4. Los mensajes nuevos llegan **en vivo** por una conexión WebSocket a Supabase Realtime (`js/tp-realtime.js`, sin librerías de terceros). Realtime respeta las mismas políticas RLS. Si esa conexión no está disponible, la página lo avisa («Sin conexión en vivo…») y **consulta cada 15 segundos**: el chat sigue funcionando, solo que con unos segundos de retraso.
5. Cuando el equipo responde, la conversación pasa a **Respondida** (y se reabre si estaba cerrada) y se crea una notificación en la base de datos (se mostrará en la pantalla de notificaciones en la Etapa 8). Cuando la persona escribe, vuelve a **Esperando respuesta**.
6. La marca **«Nuevo»** (respuesta sin leer) se guarda **solo en tu navegador**; no se envía a ningún servidor.
7. Una persona puede **cerrar** su conversación (pide confirmar). **Solo el equipo puede reabrirla** (respondiendo): así nadie esquiva el tope de conversaciones abiertas cerrando y reabriendo.
8. Una cuenta **suspendida** puede leer sus mensajes, pero no escribir ni abrir conversaciones nuevas (lo impide el servidor, no solo la pantalla).

**Límites que aplica el servidor** (para no agotar el plan gratuito):

| Límite | Valor |
|---|---|
| Mensajes por persona | 20 cada 10 minutos y **100 cada 24 horas** |
| Conversaciones abiertas a la vez | 10 |
| Conversaciones nuevas | 20 cada 24 horas |
| Largo del mensaje / del asunto | 2000 / 120 caracteres |
| Mensajes del equipo | Sin límite |

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 7 añade a la base: la función `start_conversation`, los límites diarios, la regla de «solo el equipo reabre» y un índice. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (usa `drop policy if exists` y reemplaza funciones); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 35 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela (no contiene claves ni datos de usuarios). Una de las comprobaciones confirma que las tablas `conversations`, `messages` y `notifications` están en la publicación de Realtime; si esa fila dice REVISAR, el chat funcionará **sin** el modo en vivo (con consulta cada 15 s) hasta que se corrija.

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Se reemplazan los archivos con el mismo nombre y se añaden los nuevos. Los que cambian o se añaden en esta etapa son: `chat.html`, `js/tp-realtime.js` (nuevo), `js/pages/chat.js` (nuevo), `css/styles.css`, `README.md`, `GUIA_ETAPA_7.md`, la carpeta `database/` y `pruebas-web/`.
2. Cloudflare Pages publica solo (1–2 minutos). **No hace falta cambiar `js/config.js` ni `_headers`:** la política de seguridad ya permite la conexión `wss://` a tu proyecto de Supabase.
3. Abre `https://tecnopatitas.pages.dev/chat.html` iniciando sesión, con la consola abierta (**F12 → Console**). **No debe haber errores rojos.** Si ves uno que diga *Content Security Policy* o *Refused to …*, cópialo y envíamelo.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular, cierra y abre la pestaña).

---

## Cómo responde el equipo hasta la Etapa 10

> **Actualización (Etapa 10):** ya puedes leer y responder desde `admin.html` → Atención (con botones, sin SQL). Lo de abajo sigue funcionando.

Si prefieres o necesitas hacerlo así, el equipo lee y responde desde **SQL Editor** de Supabase (ahí actúas con permisos de servidor; por eso estas consultas **nunca** van en el sitio ni se comparten).

**1. Ver las conversaciones que esperan respuesta** (las más antiguas primero):

```sql
select c.id, c.subject, c.last_message_at, p.display_name, u.email
  from public.conversations c
  join public.profiles p on p.id = c.user_id
  join auth.users u on u.id = c.user_id
 where c.status = 'abierta' and c.last_sender = 'user'
 order by c.last_message_at;
```

**2. Leer una conversación** (pon el `id` de la consulta anterior):

```sql
select m.created_at, m.sender_role, m.body
  from public.messages m
 where m.conversation_id = 'PEGA-AQUI-EL-ID'
 order by m.created_at;
```

**3. Responder** (cambia el `id`, tu correo de administrador y el texto; **conserva las comillas simples**):

```sql
insert into public.messages (conversation_id, sender_id, body)
values (
  'PEGA-AQUI-EL-ID',
  (select id from auth.users where email = 'TU-CORREO-DE-ADMINISTRADOR'),
  'Hola, con gusto te ayudamos. …'
);
```

Al ejecutarlo: el mensaje aparece **al instante** en la pantalla de la persona (si tiene el chat abierto), la conversación pasa a «Respondida» (y se reabre si estaba cerrada) y se crea su notificación. El servidor marca el mensaje como del **equipo** porque quien escribe no es la dueña de la conversación. **Importante:** usa el correo de tu cuenta de **administrador**, que no sea la dueña de esa conversación; si pones el correo de la dueña, el mensaje se guardaría como suyo, no del equipo.

Reglas: máximo 2000 caracteres; no escribas datos personales de otras personas; **nunca pidas contraseñas ni datos de tarjeta**.

**4. Cerrar una conversación terminada:**

```sql
update public.conversations set status = 'cerrada' where id = 'PEGA-AQUI-EL-ID';
```

**5. Ver cuántos mensajes ha enviado una cuenta en las últimas 24 horas** (por si alguien llega al límite):

```sql
select count(*) from public.messages
 where sender_id = (select id from auth.users where email = 'CORREO-DE-LA-PERSONA')
   and sender_role = 'user' and created_at > now() - interval '24 hours';
```

---

## Pruebas en tu sitio real (marca cada una)

Necesitas **dos cuentas** de prueba ya confirmadas (por ejemplo las de las etapas anteriores) y una cuenta de administrador. Haz las pruebas desde el celular y desde la computadora, con **F12 → Console** abierta en la computadora.

**A. Estado de la página**

1. Sin sesión, `chat.html` te manda a iniciar sesión.
2. Con sesión: aparece el texto que explica que contesta una persona del equipo y que nunca se piden contraseñas ni tarjetas, la lista «Conversaciones» y el botón **Nueva**. Sin conversaciones dice «Todavía no tienes conversaciones…».
3. No hay errores rojos en la consola.

**B. Crear una conversación (cuenta 1)**

4. **Nueva** con asunto de 1–2 letras → avisa que es muy corto y no envía.
5. **Nueva** con mensaje vacío → avisa y no envía.
6. Asunto «Prueba de chat» y mensaje «Hola, es una prueba» → se abre la conversación con tu mensaje a la derecha («Tú»), con la hora en formato de México, y en la lista aparece **Esperando respuesta**.
7. Cerca del título debe verse **«● En vivo: los mensajes nuevos aparecen solos.»** (puede tardar un par de segundos). Si en cambio dice «Sin conexión en vivo…», mira «Si algo falla».

**C. Enviar mensajes**

8. Escribe y pulsa **Enviar**; el cuadro se limpia y vuelve el foco para seguir escribiendo.
9. **Ctrl + Enter** también envía; **Enter** solo hace un salto de línea.
10. El contador muestra `n / 2,000`; con 2001 caracteres avisa y no envía.
11. Un doble clic rápido en **Enviar** guarda **un solo** mensaje.

**D. Respuesta del equipo (en vivo)**

12. Deja el chat abierto en la cuenta 1 y, desde SQL Editor, responde como se explica arriba. La respuesta aparece **sola**, con el nombre «Equipo TECNOPATITAS», en menos de 2–3 segundos, y la conversación pasa a **Respondida**.
13. Crea una segunda conversación con la cuenta 1, ábrela, responde a la **primera** desde SQL: la primera sube al principio de la lista con la marca **Nuevo**, sin cambiar la conversación que tienes abierta. Al abrirla, «Nuevo» desaparece. Recarga la página: no vuelve a salir.
14. (Opcional) En SQL Editor ejecuta `select type, title, body, link, is_read from public.notifications order by created_at desc limit 3;`: debe aparecer «Nueva respuesta de atención al cliente» (salvo que esa cuenta haya desactivado los avisos de mensajes). Todavía **no** se muestra en la página de notificaciones (Etapa 8).

**E. Cerrar y reabrir**

15. **Cerrar conversación** pide confirmar (primer clic: «¿Cerrar esta conversación?…»; segundo clic: «Confirmar cierre»). Tras cerrar aparece «Cerrada», desaparece el cuadro de escribir y se explica que hay que abrir una nueva.
16. Responde desde SQL a una conversación cerrada: se **reabre sola** y la persona puede escribir otra vez.

**F. Privacidad (importante)**

17. Con la cuenta 2, la lista **no** muestra las conversaciones de la cuenta 1.
18. Con la cuenta 2, abre `https://tecnopatitas.pages.dev/chat.html?c=ID-DE-UNA-CONVERSACION-DE-LA-CUENTA-1` (usa un id real): **no** debe mostrar nada de esa conversación.
19. Abre `chat.html?c=esto-no-es-un-id`: no pasa nada raro (ignora el valor).

**G. Cuenta suspendida**

20. En SQL Editor: `update public.profiles set is_suspended = true where id = (select id from auth.users where email = 'CORREO-DE-LA-CUENTA-2');`
21. Con esa cuenta (recarga el chat): puede leer sus conversaciones, pero **Nueva**, el cuadro y **Enviar** están desactivados y se explica por qué.
22. Reactívala: `update public.profiles set is_suspended = false where id = (select id from auth.users where email = 'CORREO-DE-LA-CUENTA-2');`

**H. Sin conexión en vivo**

23. Con el chat abierto, pon el teléfono en modo avión unos 30–40 segundos y quítalo: la línea pasa a «Sin conexión en vivo. Revisamos si hay mensajes nuevos cada 15 segundos.» y, al volver la red, regresa a «En vivo» y aparece lo que llegó mientras tanto (sin recargar).
24. Deja el chat en una pestaña oculta más de 5 minutos: la conexión en vivo se pausa para no gastar el límite de conexiones del plan gratuito; al volver a la pestaña se reconecta sola.

**I. Teléfono (390 px de ancho)**

25. Se ve **una columna a la vez**: primero la lista; al tocar una conversación, solo el hilo con el botón **← Conversaciones**; **Nueva** ocupa la pantalla con su botón de volver. Todo se puede tocar con el pulgar (botones de al menos 44 px) y no hay desplazamiento horizontal.

**J. Límites (opcional; no hace falta saturar tu cuenta)**

26. Los límites los comprueba el servidor y ya están probados con SQL. Si quieres verlo: envía 21 mensajes en 10 minutos → el 21 muestra «Enviaste demasiados mensajes seguidos. Espera unos minutos.» y tu texto se conserva.

### Limpiar las conversaciones de prueba

```sql
delete from public.conversations where subject in ('Prueba de chat');   -- añade aquí los demás asuntos de prueba
```

(Borra también sus mensajes. Las notificaciones de prueba se pueden dejar o borrar con `delete from public.notifications where link = 'chat.html';`.)

### Si algo falla: causas probables

| Síntoma | Qué revisar |
|---|---|
| Dice «Sin conexión en vivo…» siempre | (1) Que el verificador (Paso 1) no marque REVISAR en la publicación de Realtime. (2) En Supabase → **Database → Replication / Publications → `supabase_realtime`** deben estar activas `conversations`, `messages` y `notifications`. (3) En la consola (F12), un error de *Content Security Policy* relacionado con `wss://` (dímelo). El chat sigue funcionando con consulta cada 15 s. |
| Las respuestas del equipo tardan hasta 15 s | Es el modo de respaldo (sin conexión en vivo). Mismo diagnóstico de la fila anterior. |
| «Llegaste al límite de 100 mensajes en 24 horas…» | Límite diario por cuenta (decisión 1). El equipo no tiene límite. |
| «Enviaste demasiados mensajes seguidos. Espera unos minutos.» | Más de 20 mensajes en 10 minutos. |
| «Tienes demasiadas conversaciones abiertas. Cierra alguna antes de crear otra.» | 10 abiertas a la vez. Cierra las de prueba. |
| «Creaste muchas conversaciones hoy…» | 20 conversaciones nuevas en 24 horas. |
| «La conversación está cerrada. Abre una nueva.» | La persona no puede reabrir; solo el equipo, respondiendo. |
| «Tu cuenta está suspendida…» | Cuenta suspendida (sección G). |
| La respuesta por SQL sale como mensaje de la persona («Tú») | El correo que usaste en `sender_id` es el de la dueña de esa conversación. Usa la cuenta del administrador. |
| `insert` por SQL falla con «null value in column "sender_id"» | El correo del administrador está mal escrito (la subconsulta no encontró cuenta). |
| «Todavía no está conectado…» al enviar | Debe ser la versión vieja de la página: recarga forzando (Ctrl+Shift+R). |
| Te pide iniciar sesión de nuevo | La sesión caducó: inicia sesión otra vez. |

---

## Qué hace y qué no hace esta etapa

**Sí hace**

- Conversaciones persona ↔ equipo guardadas en Supabase, con lista, hilo, crear, enviar, cerrar y «cargar anteriores» (de 50 en 50).
- Mensajes en vivo por Realtime con reconexión automática, renovación del token de sesión, pausa si la pestaña lleva mucho oculta y **respaldo por consulta cada 15 s**.
- Privacidad real en el servidor (RLS): nadie lee ni escribe en conversaciones ajenas; el remitente y el rol los fija el servidor.
- Límites por cuenta (mensajes, conversaciones, tamaño) aplicados en el servidor.
- Todo lo que viene del servidor se muestra como **texto** (nunca como HTML).

**No hace (y no finge hacerlo)**

- **No hay panel para que el equipo responda:** hasta la Etapa 10 se responde con SQL (arriba). Nada se simula.
- **No hay avisos por correo ni notificaciones en pantalla todavía:** la notificación se **guarda**, pero la pantalla de notificaciones llega en la Etapa 8. Nunca se afirma que se envió un correo.
- **No hay archivos adjuntos ni fotos en el chat** (para cuidar el almacenamiento gratuito).
- **No hay mensajes entre usuarios.**
- **Detalle técnico:** los eventos de Realtime incluyen el identificador (UUID) de quien escribió, también el del administrador. Es solo un número sin nombre ni correo; la página no lo muestra ni lo usa.
- **Lo que no se pudo probar desde aquí:** el **Realtime real** de tu Supabase. El cliente sigue el protocolo documentado y se probó contra un simulador fiel (reconexión, latidos, token, caídas, eventos rotos); por eso existe el respaldo por consulta y la lista de pruebas de arriba. Tampoco se probó en un teléfono físico (se revisó con pantalla de 390 px).

## Decisiones que conviene que confirmes

1. **Tope diario: 100 mensajes en 24 horas por cuenta** (y 20 cada 10 minutos), 10 conversaciones abiertas y 20 nuevas por día. Es lo propuesto para no agotar el plan gratuito; se cambia con una línea de SQL si quieres otros números.
2. **Una persona puede cerrar su conversación, pero solo el equipo puede reabrirla.** Si prefieres que también la persona pueda reabrir, lo cambiamos (pero el tope de abiertas se podría esquivar).
3. **El equipo responde por SQL hasta la Etapa 10.** Si el volumen es bajo, es suficiente; si no, adelantamos el panel.
4. **La marca «Nuevo» se guarda solo en el navegador:** si abres el chat en otro dispositivo, vuelve a aparecer. Más adelante (Etapa 8) podría usar las notificaciones.
5. **Enlace directo a una conversación** con `chat.html?c=ID`: solo funciona para su dueña (podrá usarse desde las notificaciones).
6. **Sin adjuntos** en el chat.

## Para la Etapa 8 (notificaciones) necesitaré de ti

- Que pruebes esta etapa y me confirmes que todo funcionó (o me envíes el síntoma exacto si algo falla; si es de «En vivo», dime también qué dice el verificador).
- Decidir qué avisos quieres en la Etapa 8: **dentro de la plataforma** (campanita y pantalla de notificaciones, gratis y sin límite práctico) y, **opcionalmente**, avisos por correo. Los correos requieren un SMTP: sin dominio propio, la única opción gratuita viable es una cuenta de Gmail exclusiva del proyecto con contraseña de aplicación (Paso 4 de `GUIA_ETAPA_3.md`), con topes de envío diarios bajos. **Sigue pendiente tu decisión**: ¿usamos esa cuenta de Gmail o nos quedamos con avisos dentro de la plataforma y cuentas de prueba confirmadas a mano?
