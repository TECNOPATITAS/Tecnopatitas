# Etapa 9 · Planes y suscripciones (sin cobros): lo que tienes que hacer tú

Esta etapa convierte `planes.html` en la pantalla de **Suscripciones** de verdad: cada persona ve **su plan actual y hasta cuándo vale**, puede **solicitar** un plan, ver su **solicitud en revisión** (y cancelarla), consultar el **historial con la respuesta del equipo** y **cancelar su suscripción**. Quien no ha iniciado sesión ve exactamente las mismas tarjetas de siempre.

> Los menús de Supabase y GitHub cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 30–40 minutos. **No hay cuentas nuevas ni claves que pegar en esta etapa.** (La configuración de Gmail para los correos de cuenta va aparte, en `GUIA_CORREOS_GMAIL.md`, y no depende de esta etapa.)

**Reglas que siguen vigentes:**

- **No hay pagos.** Nadie paga, ninguna pantalla pide tarjeta, no hay pruebas gratuitas que se vuelvan de pago ni cargos automáticos. Pedir un plan solo manda una **solicitud**; si el equipo la aprueba, **activa el plan a mano, sin cobrar nada**. Todas las pantallas lo dicen.
- Nadie puede activarse un plan desde el navegador: las suscripciones solo las escribe el servidor cuando el equipo resuelve la solicitud.
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase, la contraseña de la base de datos ni la contraseña de aplicación de Gmail.

---

## Cómo funciona (para que sepas qué estás instalando)

1. **Solicitar.** En `planes.html`, con sesión iniciada, cada plan de pago de tu tipo de cuenta tiene el botón **«Solicitar este plan»**. Al pulsarlo se abre un formulario con el periodo (mensual o anual) y un mensaje opcional de hasta 300 caracteres. **Una persona solo puede tener una solicitud en revisión a la vez**, y un máximo de **5 solicitudes al día**.
2. **Quién puede pedir qué.** Las cuentas de dueño piden Huellita Pro o VIP; las de aliado piden Plata u Oro. Huellita Básica es gratuita y no se solicita. Las cuentas suspendidas no pueden solicitar. **El servidor lo comprueba siempre**: si alguien manipula la página, la base de datos rechaza la solicitud.
3. **Qué pasa al solicitar.** La persona recibe una notificación («Recibimos tu solicitud…»), y **todo el equipo** recibe «Nueva solicitud de plan» con el plan, el periodo, el tipo de cuenta y un **código de 8 caracteres**. El aviso al equipo **no incluye** el correo, el nombre ni el mensaje de la persona.
4. **La respuesta la da el equipo desde el SQL Editor** (ver «Cómo aprobar o rechazar» abajo; en la Etapa 10 habrá botones en el panel de administración). **Aprobar** activa el plan, con vigencia de **1 mes** (mensual) o **1 año** (anual) desde ese momento, y avisa a la persona («Tu suscripción cambió»). **Rechazar** avisa con la nota del equipo. La persona ve la respuesta en su historial.
5. **Renovar.** Cuando faltan **15 días o menos** para que venza su plan, aparece **«Solicitar renovación»**. Aprobarla **extiende la misma suscripción** (no crea otra). Antes de eso, el servidor rechaza la petición con una explicación.
6. **Cambiar de plan** (por ejemplo de Pro a VIP) es otra solicitud; al aprobarla, el plan anterior queda como reemplazado. Solo hay un plan activo por persona.
7. **Cancelar suscripción.** Dos pasos (botón y confirmación). El plan se pierde **de inmediato** y se vuelve a Huellita Básica. No hay reembolsos porque nunca hubo cobro. Una solicitud en revisión no se toca.
8. **Aviso de vencimiento.** Cuando a un plan le faltan **7 días o menos** (o venció hace menos de 30 días), la persona recibe un aviso («Huellita Pro vence pronto» / «venció»), una sola vez por vencimiento. **No hay ninguna tarea programada:** el aviso se genera cuando la persona **abre el sitio** (una vez al día, igual que los recordatorios de la Etapa 8). **Desde esta etapa las cuentas de aliado también hacen esa consulta diaria**, para recibir sus avisos de vencimiento. Se puede apagar en Notificaciones → preferencias → «Tu suscripción».
9. **Historial.** Se conservan las **20 solicitudes resueltas** más recientes de cada persona (cuida el espacio del plan gratuito). Cada persona ve **solo las suyas**, también las cuentas del equipo.
10. **Las tarjetas de planes son un catálogo fijo en la página** (para que un visitante que solo mira los planes no haga ninguna petición a Supabase). Una prueba automática comprueba que ese catálogo coincide con la tabla `subscription_plans` de la base (nombre, lema, precios y beneficios). **Si algún día cambias un precio o un beneficio en la base, hay que cambiarlo también en `js/plans.js`.**

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 9 añade: la tabla `plan_requests` (con sus reglas de seguridad), las funciones para solicitar, cancelar y resolver, los avisos de vencimiento y las funciones de administración que usará el panel. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (reemplaza funciones y políticas); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 37 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela.

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Los archivos que cambian o se añaden en esta etapa son: `planes.html`, `perfil.html`, `notificaciones.html`, `css/styles.css`, `js/plans.js`, `js/tp-ui.js`, `js/tp-client.js`, `js/layout.js`, `js/pages/planes.js` (nuevo), `js/pages/perfil.js`, `js/pages/notificaciones.js`, `js/pages/carnet.js`, `js/pages/placa.js`, la carpeta `supabase/plantillas-correo/` (nueva), `database/…`, las guías y `README.md`.
2. Cloudflare Pages publica solo (1–2 minutos). **No hace falta cambiar `js/config.js` ni `_headers`.**
3. Abre `https://tecnopatitas.pages.dev/planes.html` **sin iniciar sesión** con la consola abierta (**F12 → Console**): debe verse igual que antes y **sin errores rojos**.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular cierra y abre la pestaña).

---

## Cómo aprobar o rechazar solicitudes (desde SQL Editor)

Ahí actúas con permisos de servidor; estas consultas **nunca** van en el sitio.

**Ver las solicitudes en revisión** (con el correo de cada persona):

```sql
select upper(left(replace(r.id::text, '-', ''), 8)) as codigo, r.id, u.email, p.display_name,
       p.account_type, r.plan_id, r.billing_period, r.user_note, r.created_at
from public.plan_requests r
join public.profiles p on p.id = r.user_id
join auth.users u on u.id = r.user_id
where r.status = 'pending'
order by r.created_at;
```

**Aprobar** (copia el `id` de la fila; la nota es opcional y la ve la persona):

```sql
select private.resolve_plan_request('PEGA-AQUÍ-EL-ID'::uuid, true, 'Bienvenido a Huellita Pro', null, null);
```

**Rechazar** (explica el motivo en la nota; la persona la verá):

```sql
select private.resolve_plan_request('PEGA-AQUÍ-EL-ID'::uuid, false, 'Por ahora no podemos activarlo; escríbenos por Atención al cliente.', null, null);
```

Opcional: para aprobar con **otra fecha de vencimiento**, cambia el último `null` por una fecha, por ejemplo `'2026-12-31 23:59:59-06'`.

**Asignar un plan a alguien sin que lo haya pedido** (por ejemplo, a un aliado que acordó con el equipo):

```sql
select private.assign_subscription((select id from auth.users where email = 'CORREO-DE-LA-PERSONA'), 'plata', 'monthly');
```

**Ver quién tiene plan y cuándo vence:**

```sql
select u.email, s.plan_id, s.billing_period, s.starts_at, s.ends_at
from public.subscriptions s join auth.users u on u.id = s.user_id
where s.status = 'active' order by s.ends_at nulls last;
```

Cada resolución queda en la bitácora y en el historial de eventos de la suscripción.

---

## Paso 3 · Pruebas en el sitio real (checklist)

Necesitas **dos cuentas de pruebas** (una de dueño y, si quieres probar aliados, otra de aliado) y tu cuenta de administración para la parte del SQL Editor. Usa una ventana de incógnito para cada cuenta.

| # | Haz esto | Debe pasar |
|---|---|---|
| 1 | Sin sesión, abre `planes.html` | Las 5 tarjetas de siempre; los botones llevan a registro; «Mensual/Anual» cambia los precios. Sin errores en consola |
| 2 | Inicia sesión con la cuenta de dueño y abre `planes.html` | Arriba aparece «Tu plan»: **Huellita Básica**, gratuito. Pro y VIP tienen **«Solicitar este plan»**; los planes de aliado dicen que son para cuentas de aliado |
| 3 | Pulsa «Solicitar este plan» en Pro, elige Anual y escribe un mensaje | Se abre el formulario con la aclaración de que **no hay cargo ni datos de pago**. «Cancelar» lo cierra |
| 4 | Envía la solicitud | Aviso verde con un **código**; aparece «Solicitud en revisión»; VIP queda desactivado; la campana sube a 1 |
| 5 | Pulsa **«Cancelar solicitud»** | Desaparece y el historial muestra «Cancelada por ti». Pide otra |
| 6 | En SQL Editor, lista las pendientes y **aprueba** la solicitud (consulta de arriba) | — |
| 7 | Recarga `planes.html` en la cuenta de dueño | «Tu plan»: **Huellita Pro, vigente hasta** una fecha 1 año adelante; el historial dice «Aprobada» con tu nota; la campana tiene «Tu suscripción cambió»; aparece «Cancelar mi suscripción» |
| 8 | Pide **VIP** estando en Pro y **recházala** con una nota | El historial muestra «Rechazada» con tu nota; sigues con Pro |
| 9 | Pulsa «Cancelar mi suscripción» y luego «No, conservarla» | No pasa nada. Repite y pulsa «Sí, cancelar…»: vuelves a Huellita Básica |
| 10 | (Aliado) Entra con la cuenta de aliado | «Sin plan»; Plata y Oro tienen «Solicitar este plan»; los de dueño dicen que no corresponden |
| 11 | En SQL Editor asigna un plan con vencimiento cercano: `update public.subscriptions set ends_at = now() + interval '3 days' where user_id = (select id from auth.users where email = 'CORREO') and status = 'active';` y abre cualquier página con esa cuenta | Aviso «… vence pronto» (una sola vez); en `planes.html` aparece «te quedan 3 días: ya puedes solicitar la renovación» y el botón **«Solicitar renovación»** |
| 12 | Revisa `perfil.html` | Muestra tu plan y ya no dice que «los asigna un administrador» |
| 13 | En el celular (o con F12 → modo móvil a 390 px) repite 2–4 | Sin desplazamiento horizontal, botones cómodos de tocar |

---

## Decisiones que tomé por ti (dímelas si quieres otra cosa)

- **Aprobar = activar a mano sin cobrar.** Es la única forma de "contratar" mientras no existan pagos reales.
- **Vigencia:** 1 mes o 1 año desde la aprobación (editable al aprobar).
- **Renovación solo en los últimos 15 días**, para no acumular tiempo por adelantado.
- **1 solicitud en revisión por persona, 5 al día, historial de 20.**
- **El aviso de vencimiento depende de que la persona abra el sitio** (no hay tareas programadas ni `pg_cron`).
- **Catálogo de planes fijo en el sitio** (con prueba automática contra la base).
- **Las cuentas de aliado ahora también piden la generación diaria de avisos** (cambio respecto a la Etapa 8, necesario para avisarles del vencimiento de su plan).

## Lo que NO se pudo probar desde aquí

- Tu Supabase real y su PostgREST real (todo se probó contra una base PostgreSQL local con el mismo esquema y un simulador de PostgREST; por eso existe la lista de arriba).
- Un teléfono físico (se revisó a 360–390 px en Chromium).
- El envío de correos con Gmail (ver `GUIA_CORREOS_GMAIL.md`).

## Qué sigue

**Etapa 10 · Panel de administración** (aprobar solicitudes con botones, usuarios, aliados, denuncias, chat…). No la empiezo hasta que pruebes esta etapa y me lo pidas.
