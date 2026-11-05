# Etapa 8 · Notificaciones: lo que tienes que hacer tú

Esta etapa conecta `notificaciones.html` y la **campana** de la cabecera con Supabase: cada persona ve **sus** notificaciones (recordatorios de vacunas, desparasitaciones y citas, respuestas de atención al cliente y avisos), las marca como leídas, las borra y elige qué quiere recibir. Las nuevas aparecen **en vivo** (Supabase Realtime, plan gratuito). El equipo recibe aviso dentro de la plataforma cuando llega **una denuncia** o **un mensaje que espera respuesta**.

> Los menús de Supabase y GitHub cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura (sin claves visibles).

Tiempo estimado: 40–50 minutos. En esta etapa **no hay cuentas nuevas que crear ni claves que pegar**.

**Reglas que siguen vigentes:**

- No actives ningún plan de pago ni prueba gratuita, y no pongas tarjeta en ningún sitio. Las notificaciones usan solo Supabase (base de datos y Realtime) en su plan **gratuito**. Si algún panel te pide una tarjeta, **detente** y avísame.
- No pegues ni me envíes la clave `secret`/`service_role` de Supabase, la contraseña de la base de datos ni la contraseña de aplicación de Gmail. En esta etapa tampoco hace falta.
- **Esta etapa NO envía correos.** Todo llega **dentro de la plataforma**. El interruptor de «recordatorios por correo» aparece **apagado y bloqueado**, con la explicación. Nunca se afirma que se envió un correo. (El correo depende de una decisión tuya pendiente: ver «Decisiones».)
- Contratación y cobros siguen sin estar habilitados.

---

## Cómo funciona (para que sepas qué estás instalando)

1. **Las notificaciones las crea el servidor, nunca el navegador.** La persona solo puede **leer** las suyas, **marcarlas** como leídas o no leídas y **borrarlas**. Aunque alguien manipule la página, Supabase rechaza crear notificaciones, cambiar su texto, pasárselas a otra persona o tocar las de alguien más (políticas RLS, probadas).
2. **Tipos:** vacuna, desparasitación, cita, promoción, suscripción, mensaje y aviso. La persona puede **apagar cualquier tipo menos «aviso»**: los avisos importantes (cuenta, seguridad) no se pueden silenciar.
3. **Recordatorios de salud (sin tareas programadas).** No hay ningún proceso que corra de noche. Cuando una persona **abre cualquier página del sitio** con sesión iniciada (una vez al día por navegador, hora de México) o **abre Notificaciones**, la página le pide al servidor que revise **solo sus mascotas** y genere lo que corresponda:
   - **Vacunas y desparasitaciones:** se usa el **último registro** de cada vacuna (o el último de desparasitación) de cada mascota. Se avisa cuando su «próxima fecha» está **dentro de los próximos 7 días** (*«Vacuna próxima: Rabia (Nube)»*) o **venció hace menos de 60 días** (*«Vacuna vencida: …»*). Un registro viejo que ya se renovó **no** genera avisos falsos.
   - **Citas:** las **programadas** (no canceladas ni pasadas) dentro de las **próximas 48 horas**.
   - **Cada hecho avisa una sola vez** (se guarda un registro interno). Si borras un recordatorio, **no vuelve** a aparecer. «Próxima» y «vencida» son dos avisos distintos como máximo.
   - Tope: 30 por llamada y 30 llamadas por hora por cuenta. Las cuentas de aliado (sin mascotas) no los piden.
   - **Limitación honesta:** si una persona no entra al sitio, no se genera nada hasta que entre. A cambio no hay nada que activar ni que pueda generar cargos.
4. **La campana** de la cabecera (solo con sesión iniciada) muestra cuántas notificaciones **sin leer** tienes (hasta «99+»). **No usa conexión en vivo:** consulta una vez al abrir cada página, **cada 60 segundos** mientras la pestaña está visible, al volver a la pestaña y cada vez que marcas o borras algo. Así cada pestaña abierta no gasta una de las ~200 conexiones simultáneas del plan gratuito.
5. **La pantalla de Notificaciones sí usa Realtime**, escuchando solo las filas de **tu** cuenta. Si la conexión en vivo no está disponible, lo dice («Sin conexión en vivo. Revisamos si hay notificaciones nuevas cada 20 segundos») y **consulta cada 20 s**: funciona igual, con unos segundos de retraso. Con la pestaña oculta no consulta.
6. **Avisos al equipo (todas las cuentas de administración):**
   - **Nueva denuncia:** «Nueva denuncia recibida» con el **código, el tipo y el estado de la República** donde ocurrió. **No** incluye la descripción, la ubicación, fotos ni nada que identifique a quien denunció (las denuncias anónimas siguen sin ligarse a una cuenta).
   - **Mensaje de atención al cliente esperando respuesta:** se avisa **una vez por turno** (cuando una persona escribe y el último mensaje era del equipo, o es el primero). Si la persona escribe tres mensajes seguidos, el equipo recibe **un** aviso. Los avisos del equipo no se pueden silenciar.
   - Su botón «Ver» apunta a `admin.html`, que es la pantalla de administración pendiente (llega en la Etapa 10). Hasta entonces el equipo sigue respondiendo y revisando denuncias con SQL (`GUIA_ETAPA_6.md` y `GUIA_ETAPA_7.md`).
7. **Cuando el equipo responde a una persona en el chat**, a esa persona le llega «Nueva respuesta de atención al cliente» con un **adelanto de hasta 140 caracteres** de la respuesta. Solo esa persona lo ve (RLS).
8. **Límites de almacenamiento (plan gratuito):** cada persona conserva como máximo **200** notificaciones. Al crear una nueva se borran automáticamente las más antiguas que sobren, las **leídas de más de 90 días** y cualquiera de más de **365 días**.
9. **Enlaces seguros:** el botón «Ver» solo aparece si el enlace es una **página conocida de este mismo sitio** (por ejemplo `carnet.html` o `chat.html?c=…`). Cualquier otra cosa («//otro-sitio», «../», páginas que no existen) se ignora. Todo texto que viene del servidor se muestra como **texto**, nunca como HTML.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 8 añade a la base: el registro interno de recordatorios, la función `generate_my_reminders`, los avisos al equipo (denuncias y chat), la regla «los avisos no se silencian», el tope de 200 y la limpieza automática. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (usa `drop policy if exists` y reemplaza funciones); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 35 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela (no contiene claves ni datos de usuarios). Una de las comprobaciones confirma que `notifications` está en la publicación de Realtime; si esa fila dice REVISAR, la pantalla funcionará **sin** el modo en vivo (con consulta cada 20 s).

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Se reemplazan los archivos con el mismo nombre y se añaden los nuevos. Los que cambian o se añaden en esta etapa son: `notificaciones.html`, `js/pages/notificaciones.js` (nuevo), `js/layout.js`, `css/styles.css`, `carnet.html` y `js/pages/carnet.js` (solo el texto sobre recordatorios), `chat.html` (se quitó una etiqueta sobrante), `README.md`, `GUIA_ETAPA_8.md`, la carpeta `database/` y `pruebas-web/`.
2. Cloudflare Pages publica solo (1–2 minutos). **No hace falta cambiar `js/config.js` ni `_headers`:** la política de seguridad ya permite la conexión `wss://` a tu proyecto de Supabase.
3. Abre `https://tecnopatitas.pages.dev/notificaciones.html` iniciando sesión, con la consola abierta (**F12 → Console**). **No debe haber errores rojos.** Si ves uno que diga *Content Security Policy* o *Refused to …*, cópialo y envíamelo.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular, cierra y abre la pestaña).

---

## Crear notificaciones de prueba (desde SQL Editor)

Para probar sin esperar a que ocurra algo real, el servidor puede crear avisos de prueba. En **SQL Editor** (ahí actúas con permisos de servidor; estas consultas **nunca** van en el sitio). Cambia el correo por el de tu cuenta de pruebas y **conserva las comillas simples**:

```sql
select private.notify(
  (select id from auth.users where email = 'CORREO-DE-PRUEBA'),
  'aviso', 'Prueba de notificación', 'Este es un texto de prueba.', 'perfil.html');
```

Para otro tipo cambia `'aviso'` por `'vacuna'`, `'cita'`, `'mensaje'`, `'promocion'`, `'suscripcion'` o `'desparasitacion'`. El último valor es la página a la que lleva «Ver» (puede ser `carnet.html`, `chat.html`, `planes.html`… o quitarse con `null`). Los tipos que la persona apagó en sus preferencias **no** se crean (salvo `aviso`).

---

## Pruebas en tu sitio real (marca cada una)

Necesitas **dos cuentas** de prueba ya confirmadas (por ejemplo las de las etapas anteriores) y una cuenta de **administrador** (ver `GUIA_ETAPA_3.md`, Paso 5, si aún no la tienes). Para probar recordatorios, la cuenta 1 necesita **una mascota con carnet**, es decir, plan **Pro o VIP** asignado a mano (ver «Dar Huellita Pro / VIP a una cuenta de prueba» en `GUIA_ETAPA_4.md`; no es un cobro). Haz las pruebas desde el celular y desde la computadora, con **F12 → Console** abierta en la computadora.

**A. Estado de la página y la campana**

1. Sin sesión, `notificaciones.html` te manda a iniciar sesión, y en las páginas públicas (Inicio, Guías…) **no** se ve la campana.
2. Con sesión: la campana aparece en la cabecera (a la derecha en computadora; junto al botón ☰ en el celular). Sin notificaciones dice «No tienes notificaciones» y no hay globo con número.
3. El texto de arriba aclara que **por ahora no se envían correos**. No hay errores rojos en la consola.

**B. Ver, marcar y borrar (cuenta 1)**

4. Crea con SQL 3 notificaciones de prueba (arriba). En unos segundos aparecen **solas** arriba de la lista, y el globo de la campana sube a 3. Cerca de los botones debe verse **«● En vivo: las notificaciones nuevas aparecen solas.»**
5. Las no leídas llevan la marca **Nueva** y un fondo azul claro; cada una dice su tipo con texto (Aviso, Cita…). El contador dice «3 sin leer · 3 notificaciones».
6. **Marcar como leída** en una: pierde «Nueva», el contador baja a 2 y el globo de la campana baja a 2 **enseguida** (sin esperar). **Marcar como no leída** la regresa.
7. **Marcar todas como leídas:** todas quedan leídas, sale «Listo: N notificaciones marcadas como leídas.» y el globo desaparece.
8. **Borrar** en una: desaparece y el foco del teclado pasa a la siguiente fila.
9. **Borrar las leídas** pide confirmar (primer clic: botón «Confirmar: borrar las leídas»; si no confirmas, a los 6 segundos se cancela solo). Al confirmar borra solo las leídas.
10. El filtro **Sin leer** muestra solo las no leídas; con todas leídas dice «Estás al día».

**C. «Ver»**

11. Crea con SQL una notificación con enlace `chat.html`. En una **no leída**, pulsa **Ver**: se abre el chat y, al volver, esa notificación ya está **leída**. En una ya leída, **Ver** solo abre la página.

**D. Recordatorios de salud (cuenta 1 con plan Pro/VIP)**

12. En **Carnet digital**, a una mascota agrégale una vacuna con «Próxima fecha recomendada» **dentro de 3 días**, otra con fecha de **hace 20 días**, y una **cita** para mañana. Abre **Notificaciones** (o cualquier página del sitio): deben aparecer *«Vacuna próxima: … (mascota)»*, *«Vacuna vencida: …»* y *«Cita próxima de …»*, cada una con su fecha en el texto y su botón **Ver** hacia el carnet.
13. Recarga la página varias veces: **no** se duplican. **Borra** uno y recarga: **no vuelve**.
14. Una vacuna con próxima fecha dentro de 30 días, o una vencida hace más de 60 días, **no** generan aviso. Si agregas un registro nuevo de la misma vacuna (ya renovada), el aviso viejo no se repite.

**E. Preferencias**

15. En **Preferencias** apaga «Vacunas próximas o vencidas» y pulsa **Guardar preferencias** (sale «Preferencias guardadas.»). Agrega otra vacuna con próxima fecha en 2 días: **no** debe aparecer aviso.
16. Vuelve a encender «Vacunas…» y guarda: **aparece** el recordatorio que estaba pendiente.
17. «Avisos importantes de TECNOPATITAS» está encendido y **bloqueado** (no se puede apagar). «Recibir recordatorios por correo» está apagado, bloqueado y dice que todavía no está disponible.
18. Apaga «Respuestas de atención al cliente», crea con SQL una de tipo `'mensaje'` → **no** llega. Una de tipo `'aviso'` **sí** llega. Vuelve a encenderlo.

**F. Privacidad (importante)**

19. Con la cuenta 2, la lista **no** muestra nada de la cuenta 1 (y su campana solo cuenta las suyas).
20. (Opcional, desde la consola F12 de la cuenta 2) `await TP.rest('/notifications?select=title')` devuelve **solo** las de la cuenta 2.

**G. Avisos al equipo (con la cuenta de administrador)**

21. Presenta una denuncia de prueba en `denuncias.html` (sin sesión, como lo harías normalmente). En la cuenta de **administrador** aparece **«Nueva denuncia recibida»** con el código, el tipo y el estado de la República, y **sin** la descripción ni la ubicación. «Ver» abre `admin.html` (pantalla pendiente de la Etapa 10: es normal que aún no tenga contenido real).
22. Con la cuenta 1 abre el chat y escribe un mensaje: el administrador recibe **«Atención al cliente: conversación esperando respuesta»** con el asunto. Escribe **otro** mensaje antes de que el equipo responda: **no** llega un segundo aviso. Responde desde SQL (ver `GUIA_ETAPA_7.md`) y vuelve a escribir con la cuenta 1: ahora **sí** llega un aviso nuevo.
23. Con la cuenta 1: la respuesta del equipo llega como **«Nueva respuesta de atención al cliente»** con las primeras palabras de la respuesta; **Ver** abre el chat.
24. La cuenta 2 (que no es del equipo) **no** recibe los avisos de denuncias ni de chats ajenos.

**H. Sin conexión en vivo**

25. Con Notificaciones abierta, pon el teléfono en modo avión 30–40 segundos y quítalo: la línea pasa a «Sin conexión en vivo. Revisamos si hay notificaciones nuevas cada 20 segundos.» y, al volver la red, regresa a «En vivo» y aparece lo que llegó mientras tanto (sin recargar).
26. Deja la pestaña oculta más de 5 minutos: la conexión en vivo se pausa; al volver se reconecta sola.

**I. Teléfono (390 px de ancho)**

27. No hay desplazamiento horizontal; la campana se ve en la barra junto a ☰ (con su globo completo); los botones y casillas miden al menos 44 px y se pueden tocar con el pulgar; los títulos largos se ajustan.

**J. Límite (opcional)**

28. Cada persona conserva como máximo 200 notificaciones; ya está probado con SQL. Si quieres verlo, genera más de 200 con `select private.notify(...)` repetido: la pantalla nunca muestra más de 200.

### Limpiar las notificaciones de prueba

```sql
delete from public.notifications where title in ('Prueba de notificación');   -- añade aquí los demás títulos de prueba
```

(Los recordatorios de prueba se pueden dejar; si borras mascotas o vacunas de prueba desde el carnet, sus avisos anteriores quedan hasta que los borres.)

### Si algo falla: causas probables

| Síntoma | Qué revisar |
|---|---|
| Dice «Sin conexión en vivo…» siempre | (1) Que el verificador (Paso 1) no marque REVISAR en la publicación de Realtime. (2) En Supabase → **Database → Replication / Publications → `supabase_realtime`** debe estar activa `notifications`. (3) En la consola (F12), un error de *Content Security Policy* relacionado con `wss://` (dímelo). La pantalla sigue funcionando con consulta cada 20 s. |
| La campana tarda hasta 1 minuto en cambiar | Es lo normal: consulta cada 60 s. Cambia al instante cuando marcas o borras desde la pantalla de Notificaciones o al volver a la pestaña. |
| No aparecen recordatorios | (1) La cuenta debe ser de dueño de mascota con **carnet** (plan Pro/VIP). (2) Las fechas deben estar dentro de la ventana (próximas 7 días, vencidas hasta 60 días, citas 48 h) y ser el **último** registro de esa vacuna. (3) Que el tipo no esté apagado en Preferencias. (4) Si ya borraste ese recordatorio, no se vuelve a crear. (5) Abre Notificaciones: ahí siempre se piden. |
| Los recordatorios no llegan si no entro al sitio | Es una limitación de diseño (no hay tareas programadas): se generan cuando la persona visita el sitio. |
| «Demasiadas solicitudes…» (en consola) al pedir recordatorios | Tope de 30 llamadas por hora por cuenta; la pantalla sigue funcionando. |
| Una notificación de prueba por SQL no se crea | El tipo está apagado en las preferencias de esa cuenta (salvo `'aviso'`), o el correo no existe (la subconsulta no encontró cuenta). |
| Error `function private.notify … does not exist` | No se volvió a ejecutar `00_instalar_todo.sql` (Paso 1). |
| «Ver» no aparece en una notificación | Su enlace no es una página conocida del sitio (se ignora a propósito). |
| «Todavía no está conectado…» | Debe ser la versión vieja de la página: recarga forzando (Ctrl+Shift+R). |
| Te pide iniciar sesión de nuevo | La sesión caducó: inicia sesión otra vez. |

---

## Qué hace y qué no hace esta etapa

**Sí hace**

- Pantalla de notificaciones con lista (de 50 en 50), filtro «Sin leer», marcar leída/no leída, marcar todas, borrar y borrar las leídas, enlaces «Ver» seguros y preferencias por tipo.
- Campana en la cabecera con el número de no leídas, sin gastar conexiones en vivo.
- Notificaciones nuevas en vivo con reconexión automática y **respaldo por consulta cada 20 s**.
- Recordatorios de vacunas, desparasitaciones y citas generados al visitar el sitio, una sola vez cada uno.
- Avisos al equipo por denuncias nuevas y por mensajes que esperan respuesta.
- Privacidad real en el servidor (RLS): nadie lee, cambia ni borra notificaciones ajenas; el navegador no puede crear notificaciones.
- Tope de 200 por persona con limpieza automática.

**No hace (y no finge hacerlo)**

- **No envía correos ni WhatsApp.** El interruptor de correo está bloqueado hasta que decidas el servicio (ver «Decisiones»). Los planes que mencionan «recordatorios por WhatsApp o correo» siguen siendo una **previsión**.
- **No hay recordatorios si la persona no entra al sitio** (no hay tareas programadas).
- **No hay notificaciones de promociones ni de suscripciones todavía:** la preferencia ya se guarda, pero esos avisos llegarán con las etapas de planes y del panel de aliados.
- **No hay panel de administración todavía:** el botón «Ver» de los avisos al equipo abre una página pendiente (Etapa 10); hasta entonces se revisa y se responde con SQL.
- **Detalle técnico:** los eventos de Realtime incluyen el identificador (UUID) de la persona dueña de la notificación. Es solo un número sin nombre ni correo.
- **Lo que no se pudo probar desde aquí:** el **Realtime real** de tu Supabase y el **PostgREST real**. El cliente sigue el protocolo documentado y se probó contra simuladores fieles, con la **base de datos, las políticas y las funciones reales** (PostgreSQL local); por eso existe el respaldo por consulta y la lista de pruebas de arriba. Tampoco se probó en un teléfono físico (se revisó con pantalla de 390 px).

## Decisiones que conviene que confirmes

1. **Campana por consulta cada 60 s (no en vivo).** Protege el límite de ~200 conexiones simultáneas del plan gratuito (cada pestaña con conexión en vivo gasta una). Solo la pantalla de Notificaciones usa conexión en vivo. Si algún día tienes un plan con más margen, se puede cambiar.
2. **Recordatorios al visitar el sitio, sin tareas programadas.** Es lo más simple y sin riesgo de cargos; su costo es que dependen de que la persona entre. (Supabase ofrece tareas programadas, pero no las activé para no añadir piezas que mantener.)
3. **Ventanas de aviso:** vacunas y desparasitaciones 7 días antes y hasta 60 días después de vencer; citas 48 horas antes. Se cambian con un número en el SQL si prefieres otras.
4. **Los avisos importantes no se pueden silenciar** (cuenta, seguridad, denuncias del equipo).
5. **Tope de 200 notificaciones por persona** y limpieza de leídas de más de 90 días (todas las de más de 365).
6. **Avisos de chat al equipo: uno por turno**, para no saturar al equipo ni llenar la base.
7. **La notificación de respuesta del equipo incluye un adelanto de 140 caracteres** del mensaje (solo lo ve su dueña). Si prefieres que sea genérica («Tienes una respuesta»), se cambia.
8. **Correos: sigue pendiente tu decisión.** Sin dominio propio, la única opción gratuita viable es una cuenta de Gmail exclusiva del proyecto con contraseña de aplicación (Paso 4 de `GUIA_ETAPA_3.md`), con topes de envío diarios bajos; si no, seguimos solo con avisos dentro de la plataforma. No hace falta decidirlo para avanzar a la Etapa 9.

## Para la Etapa 9 (planes y suscripciones) necesitaré de ti

- Que pruebes esta etapa y me confirmes que todo funcionó (o me envíes el síntoma exacto si algo falla; si es de «En vivo», dime también qué dice el verificador).
- Confirmar si los planes, precios y beneficios que hoy aparecen en `planes.html` son los definitivos o indicarme qué cambiar. **Recuerda que no habrá cobros:** la contratación seguirá deshabilitada y los planes se asignarán a mano; no necesito datos de tarjeta ni de pago de nadie.
