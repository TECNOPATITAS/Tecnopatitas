# TECNOPATITAS · Plataforma web

Plataforma para el cuidado, protección y bienestar de las mascotas. Se construye **por etapas**; este archivo dice qué está terminado y qué no.

## Estado actual: Etapa 11 de 11 (seguridad final, textos legales y publicación)

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Estructura, diseño y navegación | Terminada |
| 2 | Supabase: base de datos, permisos (RLS), almacenamiento y datos iniciales | Terminada. **Las Etapas 4 a 11 amplían el SQL**: vuelve a ejecutar `database/00_instalar_todo.sql` (es seguro repetirlo); el verificador ahora tiene 37 comprobaciones |
| 3 | Registro, inicio de sesión, recuperar contraseña, sesión, roles y protección de páginas | Terminada y probada en tu sitio real |
| 4 | Mascotas, carnet de salud digital, subida de fotos (Supabase Storage) y placa QR (Huellita VIP) | Terminada y probada en tu sitio real |
| 5 | Directorio público y panel de aliados: alta del negocio, datos, logotipo y fotos, horarios, promociones, estadísticas y enlaces a Google Maps | Terminada y probada por ti |
| 6 | Denuncias anónimas con código de seguimiento, fotos de evidencia por una función segura y anti-robots con Cloudflare Turnstile (también en registro, inicio de sesión y recuperar) | Escrita y probada contra simuladores. Faltan tus pasos manuales y pruebas en tu sitio real: `GUIA_ETAPA_6.md` |
| 7 | Chat de atención al cliente: conversaciones entre una persona y el equipo, mensajes en vivo (Supabase Realtime) con respaldo por consulta, límites diarios por cuenta y cuenta suspendida solo lectura | Escrita y probada contra simuladores (171 pruebas de navegador del chat + 457 de SQL). Falta que la pruebes en tu sitio real: `GUIA_ETAPA_7.md` |
| 8 | Notificaciones: pantalla con lista, filtros y preferencias, campanita con el número de no leídas, recordatorios de vacunas, desparasitaciones y citas, y avisos al equipo (denuncias y chat). Solo dentro de la plataforma: todavía no se envían correos ni WhatsApp | Escrita y probada contra simuladores (194 pruebas de navegador + 511 de SQL). Probar en tu sitio real: `GUIA_ETAPA_8.md` |
| **9** | **Planes y suscripciones sin cobros: «Tu plan» con vigencia, solicitud de plan (o de renovación), cancelación, historial con la respuesta del equipo, avisos de vencimiento. El equipo aprueba o rechaza desde SQL y activa el plan a mano. Además, guía (y plantillas) para usar Gmail como correo de las cuentas, que desde la Etapa 10 ya no se usa** | **Escrita y probada contra simuladores (195 pruebas de navegador + 62 de plantillas de correo + 603 de SQL). Falta que la pruebes en tu sitio real: `GUIA_ETAPA_9.md` y `GUIA_CORREOS_GMAIL.md`** |
| **10** | **Panel de administración (`admin.html`) conectado a la base de datos: resumen, usuarios (suspender/reactivar, asignar plan a mano), aliados (aprobar, rechazar, suspender, verificar, retirar promociones), denuncias (estado, prioridad, seguimiento público y notas internas, fotos de evidencia), guías de cuidado (editor con borradores y publicación), suscripciones y solicitudes de plan, atención al cliente (responder el chat) y bitácora. La página pública de guías (`guias.html`) ahora lee las guías publicadas. Sin Gmail y con la confirmación de correo desactivada (la desactivas tú en Supabase)** | **Escrita y probada contra simuladores (271 pruebas de navegador del panel + 735 de SQL). Falta que la pruebes en tu sitio real: `GUIA_ETAPA_10.md`** |
| **11** | **Seguridad final y publicación: Aviso de privacidad y Términos y condiciones (con aceptación al registrarse y constancia de versión y fecha), eliminar la cuenta (con borrado de archivos), página 404, limpieza de los datos de demostración, auditoría automática de seguridad del sitio, datos de autoridades sin teléfonos sin verificar y lista de pendientes antes de abrir al público. Cobros: pospuestos, no habilitados** | **Escrita y probada contra simuladores (92 pruebas de navegador de la etapa + 770 de SQL + auditoría de 42 comprobaciones). Faltan tus pasos manuales y que revises los textos legales con una persona calificada: `GUIA_ETAPA_11.md`** |

**Terminado en la Etapa 2** (carpeta `database/`)

- 19 tablas en `public` + 3 internas en `private`, con claves, índices y restricciones (CHECK) que impiden datos incoherentes.
- Seguridad por filas (RLS) en **todas** las tablas; permisos por columna (nadie puede cambiar su rol, su suspensión, su plan o el dueño de una mascota desde el navegador); funciones del servidor para todo lo sensible.
- Los 5 planes (nombres, precios MXN y beneficios exactos) y los permisos de cada plan **aplicados en el servidor**, no solo en pantalla.
- Tablas y funciones para denuncias anónimas **sin ningún dato que identifique a quien reporta**, con código de seguimiento, trampa anti-robots y límite de envíos (conectadas a la página en la Etapa 6).
- Chat, notificaciones, guías, directorio con filtros, placa QR con token aleatorio, bitácora de acciones de administración.
- 6 buckets de archivos (solo JPG/PNG/WebP, con tope de tamaño y de cantidad por persona). El sexto, `qr-photos`, se añadió en la Etapa 4.
- Datos de demostración **opcionales y claramente falsos** (`06_datos_demo.sql`).
- 770 pruebas automáticas de seguridad y funcionamiento (`database/pruebas/`; 395 hasta la Etapa 5, 420 hasta la Etapa 6, 457 hasta la Etapa 7, 511 hasta la Etapa 8, 603 hasta la Etapa 9 y 735 hasta la Etapa 10) y un verificador de solo lectura para tu Supabase (`database/verificar_seguridad.sql`).

**Cómo se probó la Etapa 2, con honestidad**

Las pruebas corrieron en un PostgreSQL 16 local con un simulador de Supabase (roles `anon`/`authenticated`, `auth.uid()`, Storage). **No se pudieron correr contra tu Supabase real** porque desde aquí no hay acceso a tu cuenta (ni debe haberlo). Por eso existe `verificar_seguridad.sql`: lo corres tú en tu proyecto y confirma que quedó igual. Durante las pruebas aparecieron y se corrigieron 3 errores reales del SQL (permisos de dos disparadores, una cuota de archivos que se llamaba a sí misma y una expresión regular inválida); además se comprobó que las pruebas detectan «sabotajes» (RLS apagado, función de admin abierta, etc.).

**Terminado en la Etapa 3** (guía: `GUIA_ETAPA_3.md`)

- Registro (dueño de mascota o aliado comercial; el rol *admin* no se puede pedir desde el navegador), inicio y cierre de sesión, recuperar y cambiar contraseña (el cambio pide la actual).
- Sesión que se renueva sola, se cierra en todas las pestañas y caduca de forma ordenada. Cliente propio sin dependencias externas (`js/tp-client.js`).
- Protección de páginas privadas por rol (`js/guard.js`): el contenido ni siquiera se muestra hasta que el servidor confirma la sesión; el rol de administrador se verifica con `is_admin()` en el servidor.
- Perfil editable (nombre y teléfono) y consulta del plan vigente.
- Enlaces de correo (confirmar, recuperar) con redirección **solo a páginas internas** (sin redirecciones abiertas) y dirección limpiada tras leer el token.
- Mensajes en español; no se revela si un correo ya tiene cuenta; nunca se dice «correo enviado» si falló el envío.
- Política de seguridad de contenido (CSP) en `_headers`: scripts solo propios; conexiones solo a tu proyecto de Supabase. El sitio **se niega a funcionar** si alguien pone una clave `secret`/`service_role` en `js/config.js`.
- 106 pruebas automáticas de navegador (`pruebas-web/`).

**Cómo se probó la Etapa 3, con honestidad**

Desde mi entorno no hay acceso a tu Supabase (y no debe haberlo), así que las pruebas corrieron en Chromium contra un **simulador** de Supabase que escribí según la documentación oficial de GoTrue y PostgREST. Si el servicio real responde distinto en algún detalle, solo lo sabremos al probar en tu sitio: por eso `GUIA_ETAPA_3.md` trae una lista de 15 comprobaciones. Se comprobó también que las pruebas detectan sabotajes (por ejemplo, quitar la regla que oculta las páginas privadas o el aviso entre pestañas).

**Terminado en la Etapa 4** (guía: `GUIA_ETAPA_4.md`)

- **Mis mascotas** (`mascota.html`): crear, editar y eliminar fichas (máx. 30 por cuenta) con especie, raza, sexo, nacimiento, peso, descripción, información veterinaria y foto. Cada cuenta ve únicamente las suyas.
- **Carnet de salud digital** (`carnet.html`): vacunas, desparasitaciones y citas veterinarias por mascota. Los límites del plan (Básica: sin carnet · Pro: 2 mascotas · VIP: ilimitado) los aplica **el servidor**, no solo la pantalla. Las citas se escriben y se muestran en hora de Ciudad de México.
- **Fotos** (mascotas, perfil, placa): el navegador **reduce y vuelve a codificar cada imagen como JPEG antes de subirla**, lo que elimina los metadatos EXIF (modelo de cámara, fecha y, sobre todo, la **ubicación GPS**). Los buckets de mascotas y perfil son **privados**: las fotos se ven con enlaces firmados que caducan.
- **Placa QR (Huellita VIP)**: el dueño elige qué publica (nombre, raza, mensaje, contacto, teléfono, foto). La página pública `qr.html?t=…` se abre **sin iniciar sesión**, no muestra correo ni dirección de nadie y responde igual ante un enlace inexistente o desactivado. El enlace puede regenerarse (el anterior deja de funcionar). El QR se genera en el navegador con un codificador propio (`js/qr.js`), sin servicios externos, y se puede descargar en PNG o SVG.
- Todo texto que escribe una persona se muestra como **texto**, nunca como HTML.

**Cómo se probó la Etapa 4, con honestidad**

- 133 pruebas de navegador en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_mascotas.py`), 106 de la Etapa 3 (siguen pasando) y 73 códigos QR generados que se leen con OpenCV (un lector independiente) en todas las versiones usadas.
- Se hicieron **pruebas de sabotaje**: se rompió el código a propósito de 10 maneras (por ejemplo, mostrar el mensaje público como HTML, enviar la sesión en la consulta pública, no borrar la foto anterior, equivocar el huso horario) y las pruebas las detectaron. Dos de esas pruebas de sabotaje dejaron al descubierto huecos en mis propias pruebas, que se completaron.
- **Lo que no se pudo probar:** el Storage real de Supabase. El simulador sigue la documentación oficial (subida con `FormData`, URLs firmadas con `POST /object/sign/<bucket>`, URL pública), pero si el servicio real responde distinto en algún detalle solo lo sabremos en tu sitio: por eso `GUIA_ETAPA_4.md` trae una lista de comprobaciones. Tampoco se probó el escaneo con un teléfono real.

**Terminado en la Etapa 5** (guía: `GUIA_ETAPA_5.md`)

- **Directorio público** (`directorio.html`, sin iniciar sesión): búsqueda por nombre, servicio o municipio, filtro por categoría, orden (destacados / A–Z / recientes) y paginación de 12 en 12. Solo aparecen establecimientos **aprobados**. Lo que se muestra depende del plan del aliado y lo decide **el servidor**: sin plan, nombre, categoría, descripción y dirección; con Plata u Oro, además teléfono, horario, logotipo, fotos y promociones vigentes; con Oro, botón de WhatsApp, lugar prioritario y la etiqueta «Aliado verificado» (que solo asigna un administrador). Nunca se muestra quién es el dueño.
- **Google Maps sin API ni claves**: «Ver ubicación» y «Cómo llegar» son enlaces directos (`google.com/maps/search` y `/maps/dir`) con el texto del lugar codificado. Las fichas de demostración no llevan mapa.
- **Panel de aliados** (`panel-aliado.html`, solo cuentas de aliado): alta de hasta 5 establecimientos (quedan **«en revisión»** hasta que un administrador los apruebe), datos comerciales, logotipo y hasta 6 fotos (bucket público `business-media`, reducidas y sin datos ocultos), horario por día, promociones y estadísticas. Cada aliado ve y edita **únicamente lo suyo** (RLS).
- **Promociones según el plan**: Plata, 1 nueva al mes; Oro, ilimitadas; sin plan, ninguna. El límite lo impone el servidor. Se pueden pausar, editar y eliminar; se muestran solo mientras estén activas y dentro de sus fechas.
- **Estadísticas básicas y anónimas**: visitas a la ficha y clics en «Ver ubicación» / «Cómo llegar», por día (últimos 7 y 30 días y tabla de 14 días). Son solo contadores: no se guarda quién visitó.
- Todo lo que viene del servidor se muestra como **texto**; los enlaces (mapa, teléfono, WhatsApp, imágenes) se arman solo con partes validadas, nunca con un enlace guardado tal cual.

**Cómo se probó la Etapa 5, con honestidad**

- **395 pruebas de SQL** (113 del grupo «Aliados, directorio y promociones») y **34 comprobaciones** del verificador; el instalador se ejecutó dos veces seguidas sin error. 7 «sabotajes» del SQL (por ejemplo, dejar que el dueño cambie el horario con valores raros o que cualquiera lea las estadísticas) fueron detectados.
- **172 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_aliados.py`, contra el simulador `mock_etapa5.py`): directorio, alta, datos, fotos, horarios, promociones, estadísticas, varias fichas, cuenta suspendida y contenido hostil. Siguen pasando las de las Etapas 3 y 4 (106 + 133 + QR).
- **26 sabotajes de la interfaz** (por ejemplo, mostrar la descripción como HTML, no validar el enlace de WhatsApp, no borrar la foto anterior, permitir una promoción sin cupo, tratar a una cuenta suspendida como activa) y los 26 fueron detectados; dos de esas pruebas de sabotaje dejaron al descubierto huecos en mis pruebas, que se completaron. Revisando capturas de pantalla apareció además un defecto real (el texto «null» en algunas secciones del panel), que se corrigió y ahora tiene su prueba.
- **Lo que no se pudo probar:** el Storage y PostgREST reales de tu Supabase (el simulador sigue la documentación oficial; los detalles solo se confirman en tu sitio: por eso `GUIA_ETAPA_5.md` trae una lista de comprobaciones), la apertura real de Google Maps y la vista en un teléfono físico (se revisó con pantalla de 390 px de ancho).

**Terminado en la Etapa 6** (guía: `GUIA_ETAPA_6.md`)

- **Denuncias anónimas** (`denuncias.html`): tipo de situación, descripción (30–4000 caracteres), fecha aproximada, estado, municipio, referencia opcional y hasta 3 fotos. **No se pide ni se envía nombre, correo, teléfono ni sesión** (aunque la persona tenga una cuenta abierta) y la tabla `complaints` no tiene ninguna columna que identifique a quien reporta. Al enviar se muestra un **código de seguimiento** `TP-XXXX-XXXX` que no se puede recuperar.
- **Función segura `submit-complaint`** (Supabase Edge Function, `supabase/functions/submit-complaint/index.ts`): es la **única puerta** de entrada. Valida los datos, comprueba **Cloudflare Turnstile en el servidor** con una clave secreta que nunca está en el navegador ni en el repositorio, aplica los límites **antes** de subir archivos, limpia cada foto (solo JPEG; se eliminan EXIF/GPS, comentarios y miniaturas) y la guarda en el bucket **privado** `complaint-evidence`. Si algo falla, no queda nada guardado. Si falta la clave de Turnstile o Cloudflare no responde, **rechaza** el reporte (falla cerrado). Las funciones SQL `submit_complaint` y `complaint_precheck` ya **no** las puede llamar el navegador: solo esa función con la clave del servidor.
- **Límites:** 5 reportes por hora y 15 por día por visitante (código derivado de la IP que cambia cada día; no se guarda la IP), 300 al día en total y 100 con fotos al día, 300 MB de evidencias en total, y consulta de seguimiento limitada a 30 por hora. Campo trampa (honeypot) contra robots simples.
- **Seguimiento público:** con el código se ve el estado (recibida, en revisión, en proceso, canalizada, cerrada), las fechas y el «mensaje del equipo»; nunca las notas internas. «Canalizada» aclara que TECNOPATITAS **no sustituye una denuncia oficial**.
- **Turnstile también en registro, inicio de sesión y recuperar contraseña** (`js/tp-captcha.js`): si hay una Site Key en `js/config.js` se muestra el recuadro y se envía el token; Supabase lo comprueba cuando activas **Authentication → Attack Protection → CAPTCHA** (Paso 7 de la guía, opcional). Sin Site Key todo funciona como en la Etapa 3.
- Si falta algo (Site Key, función, secreto), la página **lo dice y bloquea el formulario**; nunca finge que el reporte se envió. Si por error se pega la clave **secreta** en `config.js`, la página se niega a funcionar y lo avisa.
- La CSP de `_headers` permite scripts y marcos solo de `challenges.cloudflare.com` (además de los propios).
- Todo lo que viene del servidor se muestra como **texto**.

**Cómo se probó la Etapa 6, con honestidad**

- **420 pruebas de SQL** (las de denuncias se reescribieron: nadie —anónimo, con sesión ni administrador— puede llamar a las funciones de envío; límites por IP, por día y globales; cuota de evidencias) y **35 comprobaciones** del verificador; el instalador se ejecutó sobre una base ya instalada (actualización) y sobre una limpia. 7 «sabotajes» del SQL fueron detectados.
- **76 pruebas de la función segura** (`pruebas-web/probar_funcion.py`): se ejecuta el **código real** de `index.ts` contra una base PostgreSQL local con el esquema real y un Turnstile y un Storage simulados: validaciones, anti-robots (token falso, repetido, Cloudflare caído), límites, fotos con EXIF/GPS/comentarios/datos al final del archivo, anonimato, y que no quede basura si algo falla. **24 sabotajes** de la función (por ejemplo, no verificar Turnstile, confiar en una cabecera de IP falsificable, dejar los metadatos de las fotos, no borrar fotos si falla el registro) y los 24 fueron detectados; esas pruebas de sabotaje dejaron al descubierto huecos en mis pruebas, que se completaron.
- **140 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_denuncias.py`): formulario, fotos, código, anonimato (sin sesión ni cookies en la petición), errores del servidor, doble clic, campo trampa, seguimiento (incluido un mensaje hostil con HTML), Turnstile en registro/inicio/recuperar, script bloqueado y reintento, y diseño de 390 px y de escritorio. **30 sabotajes de la interfaz** (por ejemplo, enviar la sesión a la función segura, mostrar el mensaje del equipo como HTML, no reiniciar la verificación tras cada intento, no mandar el token de Turnstile en el registro, dibujar dos recuadros de verificación o quitar a Cloudflare de la CSP) y los 30 fueron detectados; uno de ellos dejó al descubierto un hueco en mis pruebas, que se completó (otro, que quitaba una comprobación duplicada, no cambiaba el comportamiento y se descartó).
- Siguen pasando las regresiones de las Etapas 3, 4 y 5 (106 + 133 + 172 pruebas de navegador y los códigos QR).
- Revisando capturas de pantalla aparecieron dos defectos reales de la interfaz (la casilla de aceptación partía su texto en columnas y las miniaturas tenían una sangría de más) y botones demasiado pequeños para el móvil; se corrigieron y ahora tienen su prueba.
- **Lo que NO se pudo probar desde aquí:** (1) **Deno**, el entorno real de las Edge Functions: no se pudo instalar (red bloqueada), así que el mismo archivo se ejecutó con **Node 22**, que tiene las mismas funciones web (`fetch`, `FormData`, `crypto`); si Supabase se comporta distinto en algún detalle, solo se sabrá al desplegar; (2) el **Turnstile real** (se probó con una versión simulada del script de Cloudflare; el recuadro de verdad, su dominio permitido y el *siteverify* real se confirman en tu sitio), (3) el **Storage y la IP** reales de Supabase (la IP llega en las cabeceras `cf-connecting-ip` / `x-real-ip`; si en tu proyecto llegaran vacías, todos compartirían un solo límite —es seguro, pero habría que ajustarlo—: la prueba 16 de la guía lo comprueba) y (4) la apertura en un teléfono físico. Por eso `GUIA_ETAPA_6.md` trae una lista de 18 comprobaciones.

**Terminado en la Etapa 7** (guía: `GUIA_ETAPA_7.md`)

- **Chat de atención al cliente** (`chat.html`): lista de conversaciones, hilo de mensajes, **Nueva** conversación (asunto de 3 a 120 caracteres y mensaje de hasta 2000), enviar con botón o **Ctrl+Enter**, cerrar con confirmación y «Cargar mensajes anteriores» (de 50 en 50). Es solo entre **una persona y el equipo**; no existen mensajes entre usuarios.
- **Privacidad y reglas en el servidor** (RLS y disparadores, no solo en pantalla): cada persona ve solo sus conversaciones; el remitente y el rol («usuario» o «equipo») los fija el servidor, aunque el navegador mande otra cosa; una cuenta **suspendida** puede leer pero no escribir ni abrir conversaciones; la persona puede cerrar su conversación, pero **solo el equipo puede reabrirla** (respondiendo). La conversación y su primer mensaje se guardan juntos con la función `start_conversation` (si falla, no queda nada a medias).
- **Límites por cuenta** para cuidar el plan gratuito: 20 mensajes cada 10 minutos y **100 cada 24 horas**, 10 conversaciones abiertas y 20 nuevas por día. El equipo no tiene límite. Los avisos salen en español.
- **Mensajes en vivo** con Supabase Realtime mediante un cliente propio y mínimo (`js/tp-realtime.js`, sin librerías de terceros): reconexión con esperas crecientes, latidos para detectar conexiones muertas, renovación del token, pausa si la pestaña lleva más de 5 minutos oculta (para no gastar el límite de conexiones gratuito) y **respaldo por consulta cada 15 segundos** si el modo en vivo no está disponible; la página siempre dice cuál de los dos modos está usando.
- La marca **«Nuevo»** (respuesta sin leer) vive solo en tu navegador. Todo lo que viene del servidor se muestra como **texto**. Teléfono: una columna a la vez, botones de al menos 44 px.
- Cuando el equipo responde se **guarda** una notificación (desde la Etapa 8 se ve en Notificaciones y en la campanita). Hasta la Etapa 10 el equipo responde con SQL (consultas en `GUIA_ETAPA_7.md`).

**Cómo se probó la Etapa 7, con honestidad**

- **457 pruebas de SQL** (37 nuevas del chat: privacidad entre personas, remitente y rol fijados por el servidor, cuenta suspendida, cierre y reapertura, los tres límites, `start_conversation`, notificaciones) y **35 comprobaciones** del verificador (el instalador se ejecutó sobre una base ya instalada y sobre una limpia).
- **171 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_chat.py`, 14 grupos): estructura, texto hostil con HTML mostrado como texto, envío y límites reales (el simulador `mock_etapa7.py` traduce cada petición a SQL contra el esquema real, con las políticas RLS), mensajes en vivo, cierre, privacidad entre dos personas, paginación de 100 mensajes, cuenta suspendida, teléfono de 390 px, accesibilidad, fallos de red y del servidor, y que el resto del sitio no abre conexiones en vivo. La conexión en vivo se probó con un **servidor Realtime simulado** y reloj virtual (latidos, reconexión con retroceso, token que caduca, pestaña oculta, caídas silenciosas, eventos rotos o de otra persona).
- **66 «sabotajes»** al código del chat (por ejemplo, mostrar mensajes como HTML, no filtrar la lista por persona, enviar el rol desde el navegador, no confirmar el cierre, permitir dos conexiones en vivo): **63 detectados**. Los 3 restantes no cambian el comportamiento porque el código tiene una segunda protección que hace lo mismo: marcar la conversación como leída al abrirla (también se marca al cargar sus mensajes), la regla de CSS del botón «← Conversaciones» en móvil (otra regla la repite) y la primera de dos protecciones contra abrir dos conexiones en vivo (quitando las dos, el sabotaje sí se detecta). Esa ronda dejó al descubierto 4 huecos de mis propias pruebas, ya completados, y un defecto real: si el servidor aceptaba la conexión en vivo pero nunca confirmaba la unión, la página quedaba en «conectando» sin consultar; ahora lo detecta a los 10 s y usa el respaldo.
- Siguen pasando las regresiones de las Etapas 3 a 6: 106 + 133 + 172 + 140 pruebas de navegador, 76 de la función segura y los códigos QR.
- **Lo que NO se pudo probar desde aquí:** el **Realtime real** de tu Supabase (el cliente sigue el protocolo documentado y se probó contra el simulador; si algún detalle difiere, solo se sabrá en tu sitio, y para eso está el respaldo por consulta y la lista de pruebas de `GUIA_ETAPA_7.md`), el comportamiento exacto de PostgREST ante estas consultas (simulado fielmente) y un teléfono físico. Un detalle técnico: los eventos de Realtime incluyen el identificador (UUID) de quien escribió, también el del administrador; es solo un número sin nombre ni correo, y la página no lo usa.

**Terminado en la Etapa 8** (guía: `GUIA_ETAPA_8.md`)

- **Notificaciones** (`notificaciones.html`): lista de 50 en 50 con «Mostrar más», filtro «Sin leer», marcar como leída o no leída, «Marcar todas», borrar una o «Borrar las leídas» (con confirmación), y un botón «Ver» que abre la página relacionada y la marca como leída. Tipos: vacuna, desparasitación, cita, mensaje, promoción, suscripción y aviso. Cada persona puede apagar los tipos que no quiera, **menos «aviso»** (cuenta y seguridad).
- **Las crea el servidor, nunca el navegador.** La persona solo puede leer las suyas, marcarlas y borrarlas (RLS y permisos por columna): no puede crear notificaciones, cambiar su texto, pasárselas a otra persona ni tocar las ajenas. Los enlaces «Ver» solo se aceptan si apuntan a una página conocida de este sitio; todo lo que viene del servidor se muestra como texto.
- **Campanita** en la cabecera (solo con sesión): número de no leídas hasta «99+». **No usa conexión en vivo**: consulta al abrir cada página, cada 60 segundos con la pestaña visible, al volver a ella y cada vez que marcas o borras algo, para que cada pestaña abierta no gaste una de las ~200 conexiones simultáneas del plan gratuito. La pantalla de Notificaciones sí usa Realtime (solo las filas de tu cuenta) con **respaldo por consulta cada 20 s** y lo dice en pantalla.
- **Recordatorios de salud sin tareas programadas:** cuando una persona abre el sitio (una vez al día por navegador) o abre Notificaciones, el servidor revisa **solo sus mascotas**: vacunas y desparasitaciones con próxima fecha en los siguientes 7 días o vencidas hace menos de 60 días (se usa el último registro de cada una, así un registro viejo ya renovado no da avisos falsos) y citas programadas en las próximas 48 horas. Cada hecho avisa **una sola vez**; si lo borras no vuelve. Tope de 30 por llamada y 30 llamadas por hora.
- **Avisos al equipo:** cada denuncia nueva avisa a todas las cuentas de administración con el **código, el tipo y el estado** (nunca la descripción, fotos ni datos de quien denuncia), y un mensaje del chat que espera respuesta avisa **una vez por turno**. Cuando el equipo responde, la persona recibe un aviso con un adelanto de hasta 140 caracteres de la respuesta.
- **Tope por persona:** 200 notificaciones; al crear una nueva se limpian las más antiguas que sobren, las leídas de más de 90 días y cualquiera de más de 365.

**Cómo se probó la Etapa 8, con honestidad**

- **511 pruebas de SQL** (54 nuevas: privacidad entre cuentas, columnas que el navegador no puede tocar, tipos y preferencias, tope y limpieza, recordatorios sin duplicados ni avisos falsos, límites por hora, avisos al equipo sin datos de quien denuncia, adelanto del chat) y **35 comprobaciones** del verificador. **22 sabotajes** al SQL (por ejemplo, dejar que el navegador cree notificaciones, avisar dos veces el mismo hecho, incluir la descripción de la denuncia en el aviso): **los 22 se detectan**.
- **194 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_notificaciones.py`, 17 grupos, contra el simulador `mock_etapa8.py`, que traduce cada petición a SQL real con las políticas RLS): lista y privacidad entre dos cuentas, marcar y borrar con doble clic y errores del servidor, filtros y paginación, texto hostil y enlaces peligrosos, la campanita, tiempo real con un **servidor Realtime simulado** y reloj virtual (repetidos, eventos de otra persona o mal formados, reconexión, pestaña oculta), teléfono de 390 px, cuentas de aliado y de administración, y una **comprobación automática de contraste** de la paleta.
- **79 «sabotajes»** al código de la página, la campanita y el CSS: **73 se detectaron a la primera**. Los 6 restantes eran huecos de mis pruebas (una fecha mal formateada que pasaba por coincidir con otra fecha, un evento en vivo repetido, un tipo de notificación desconocido, el globo del número despegado de la campana, la campana visible un instante para un invitado y consultas simultáneas de la campana); ya los cubrí y ahora **se detectan los 79**.
- Siguen pasando las regresiones de las Etapas 3 a 7 (106 + 133 + 172 + 140 + 171 pruebas de navegador, 76 de la función segura y los códigos QR). Una prueba del chat que usaba Notificaciones como página «sin conexión en vivo» se cambió a Perfil, porque ahora esa pantalla sí abre conexión en vivo.
- **Lo que NO se pudo probar desde aquí:** el **Realtime real** y el **PostgREST real** de tu Supabase (el cliente sigue el protocolo documentado y se probó contra simuladores; por eso existe el respaldo por consulta y la lista de pruebas de `GUIA_ETAPA_8.md`) y un teléfono físico (se revisó a 390 px). Un detalle técnico: los eventos de Realtime incluyen el identificador (UUID) de la dueña de la notificación; es solo un número sin nombre ni correo.

**Terminado en la Etapa 9** (guías: `GUIA_ETAPA_9.md` y `GUIA_CORREOS_GMAIL.md`)

- **Suscripciones sin cobros** (`planes.html`): con sesión, muestra **«Tu plan»** con su vigencia, permite **solicitar** un plan de pago de tu tipo de cuenta (dueño: Pro o VIP; aliado: Plata u Oro) con periodo mensual o anual y un mensaje opcional de hasta 300 caracteres, ver la **solicitud en revisión** (y cancelarla), el **historial** con la respuesta del equipo y **cancelar la suscripción** (dos pasos). Sin sesión se ve el catálogo de siempre. **Nadie paga nada**: no hay tarjetas, pruebas gratuitas que se vuelvan de pago ni cargos; todas las pantallas lo dicen.
- **Lo escribe el servidor, nunca el navegador.** Las solicitudes se crean y cancelan con funciones del servidor (tabla `plan_requests` con RLS: cada persona solo lee las suyas y no puede escribir directo). El servidor comprueba la audiencia del plan (dueño/aliado), la cuenta suspendida, **una solicitud en revisión por persona**, **5 por día** y el historial (se conservan las 20 más recientes).
- **El equipo responde desde SQL** (el panel con botones llega en la Etapa 10): **aprobar** asigna el plan a mano (1 mes o 1 año, o la fecha que indiques) y **rechazar** deja una nota. Ambas avisan a la persona dentro de la plataforma; el aviso al equipo lleva el código, el plan y el tipo de cuenta, nunca el correo ni el mensaje. Cada resolución queda en la bitácora.
- **Renovación:** con 15 días o menos de vigencia aparece «Solicitar renovación»; aprobarla **extiende la misma suscripción** (no crea otra).
- **Aviso de vencimiento** (7 días antes y hasta 30 después) sin tareas programadas: se genera cuando la persona abre el sitio, junto con los recordatorios de salud. Desde esta etapa las cuentas de aliado también hacen esa consulta diaria.
- **Correos de cuenta con Gmail** (`GUIA_CORREOS_GMAIL.md`, decisión tuya): Gmail como SMTP de Supabase para **confirmar cuenta y recuperar contraseña**, con contraseña de aplicación escrita solo en el panel de Supabase, límites reales, pruebas y solución de problemas, y dos plantillas en español con la paleta del proyecto (`supabase/plantillas-correo/`). **Los avisos de la plataforma (vacunas, citas, suscripción) siguen sin enviarse por correo.**

**Cómo se probó la Etapa 9, con honestidad**

- **603 pruebas de SQL** (92 nuevas: solicitudes, audiencias, límites, renovaciones, aprobación y rechazo, permisos y avisos) y **37 comprobaciones** del verificador. **46 sabotajes** al SQL (por ejemplo, dejar que una cuenta suspendida solicite, que el rechazo asigne un plan, que cancelar toque solicitudes ajenas o que los avisos incluyan el correo): **los 46 se detectan** (dos huecos de mis pruebas se cubrieron).
- **195 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_planes.py`, 14 grupos, contra el simulador `mock_etapa9.py`, que traduce cada petición a SQL real con RLS): visitante sin peticiones a Supabase, catálogo idéntico a la tabla `subscription_plans`, solicitar/cancelar/doble clic/carreras con el equipo, aprobada y rechazada, renovación, cancelar suscripción, cuenta de aliado, errores y texto hostil, accesibilidad y teclado, teléfono de 390 px y contraste de la paleta. **75 sabotajes** al código de la página, el CSS y el catálogo: **los 75 se detectan** (se reforzaron las pruebas de doble envío, de la marca del selector y de cancelar con historial).
- **62 comprobaciones de las plantillas de correo** (`pruebas-web/probar_correos.py`): HTML bien formado, solo la variable `{{ .ConfirmationURL }}`, sin imágenes, scripts ni recursos externos, solo colores de la paleta, sin desbordes a 360/390/900 px y contraste AA.
- Siguen pasando las regresiones de las Etapas 3 a 8 (navegador, función segura y códigos QR).
- **Errores reales que las pruebas encontraron y ya corregí:** una cuenta de administración habría visto las solicitudes de todas las personas en su pantalla (RLS lo permite al equipo; ahora se filtra por la propia cuenta); botones Mensual/Anual de 41 px en teléfono; un mensaje confuso («cuenta suspendida») al caducar la sesión a mitad de una solicitud; la marca «Tu plan actual» se perdía mientras había otra solicitud en revisión; y un aviso de límite de correos que decía «en una hora» sin ser exacto.
- **Lo que NO se pudo probar desde aquí:** tu Supabase real y su PostgREST real (todo se probó contra PostgreSQL local con el mismo esquema y un simulador de PostgREST), **el envío real de correos con Gmail** (ni cómo los muestra tu aplicación de correo), y un teléfono físico (se revisó a 360–390 px).

**Terminado en la Etapa 10** (guía: `GUIA_ETAPA_10.md`)

- **Panel de administración** (`admin.html`, 8 secciones) que usa **solo** las 28 funciones `admin_*` del servidor: cada una vuelve a comprobar el rol de administración (error «No autorizado.» si no lo eres) y deja una línea en la bitácora. Ocultar un botón nunca es la protección. Una cuenta que no es de administración solo ve «Acceso restringido».
- **Usuarios:** búsqueda, ficha con solo datos de la cuenta y conteos (nunca el contenido de mascotas ni chats), suspender/reactivar con motivo (no a otro administrador) y asignar un plan a mano **sin cobro**. **Aliados:** aprobar, rechazar, suspender, regresar a revisión, «Aliado verificado» (solo aprobados) y retirar promociones con motivo; el panel no edita los datos del establecimiento. **Denuncias:** estado, prioridad, atendida, actualización pública (500) y notas internas (4000); el contenido original no se modifica; fotos de evidencia con enlaces firmados de 10 minutos que solo un administrador puede pedir; «canalizada» no significa denuncia oficial presentada. **Guías:** editor con borrador/publicación explícita, vista previa y borrado con confirmación; el contenido es texto (párrafos y `## ` para subtítulos), nunca HTML. **Suscripciones:** aprobar/rechazar solicitudes, renovar, cancelar y cambiar vencimiento, todo manual y sin cobro. **Atención:** bandeja del chat, responder como «Equipo TECNOPATITAS» (responder reabre una conversación cerrada), cerrar y reabrir; se actualiza sola cada 30/15 s sin perder lo que escribes. **Bitácora:** solo lectura, sin contenidos.
- **Guías públicas** (`guias.html`): lista solo las publicadas, con búsqueda y categoría; un borrador no se puede leer ni adivinando la dirección (lo impone la base de datos).
- Los avisos al equipo (campana) abren directamente la sección correspondiente del panel.
- **Sin Gmail y sin confirmación de correo:** ver el párrafo «Correo y confirmación de cuenta» más abajo.

**Cómo se probó la Etapa 10, con honestidad**

- **735 pruebas de SQL** (132 nuevas: cada función `admin_*` rechaza a quien no es administrador, validaciones, bitácora sin contenidos, avisos, privacidad de la evidencia y de los borradores, permisos) y **37 comprobaciones** del verificador. **93 sabotajes** al SQL (quitar la comprobación de rol a cada función, abrir permisos o políticas a cualquier cuenta o a visitantes, guardar contenidos en la bitácora, saltarse validaciones…): **93 se detectan**.
- **271 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_admin.py`, 15 grupos, contra el simulador `mock_etapa10.py`, que traduce cada llamada `admin_*` a SQL real con el rol «authenticated» y las políticas RLS): estructura y seguridad de los archivos, control de acceso (visitante, dueño, aliado, suspendido; las 28 funciones rechazan a quien no es administrador aunque se llamen desde la consola), cada sección con sus acciones, doble clic y envíos simultáneos, errores del servidor y sesión vencida, texto hostil escrito como texto, actualización automática con reloj simulado, paginación, navegación y avisos del equipo, accesibilidad (teclado, nombres, contraste AA, objetivos táctiles de 44 px, textos largos sin desbordes a 390 px) y las guías públicas.
- **135 «sabotajes» al código del panel, de las guías, del CSS y de `admin.html`: 130 se detectaron.** Los 5 restantes son equivalentes (cambian el código pero no lo que ve ni lo que guarda nadie: por ejemplo, el navegador y el servidor recortan el mismo texto, o un estilo que la tarjeta ya hereda). Los huecos que aparecieron durante la prueba se cerraron con comprobaciones más estrictas y se repitió el sabotaje hasta detectarlos.
- **Dos errores reales que las pruebas encontraron y ya corregí:** (1) un nombre de establecimiento o un asunto del chat muy largo y sin espacios desbordaba la pantalla del panel; (2) en la página pública de guías, un título, resumen o fuente larguísimos y sin espacios se salían de la pantalla del teléfono.
- Siguen pasando las regresiones de las Etapas 3 a 9.
- **Lo que NO se pudo probar desde aquí:** tu Supabase real y su PostgREST/Storage reales (todo se probó contra PostgreSQL local con el mismo esquema y un simulador), el interruptor «Confirm email» de tu Supabase, la consulta para restablecer una contraseña desde el SQL Editor y un teléfono físico (se revisó a 360–390 px).

**Terminado en la Etapa 11** (guía: `GUIA_ETAPA_11.md`)

- **Aviso de privacidad (`privacidad.html`) y Términos y condiciones (`terminos.html`)**, públicos y enlazados en el pie de todas las páginas. Se redactaron según lo que el sitio **realmente hace**: qué datos pide, qué es público y qué no, con quién se comparten (Supabase, Cloudflare, Google Fonts), derechos ARCO, conservación y eliminación, menores, cookies y almacenamiento del navegador, y reglas de uso (aliados, reportes, planes **sin cobros**). **Los datos de quien responde (responsable, domicilio, contacto) los pone la persona dueña del sitio en `js/config.js` (`LEGAL`)**: vacíos por diseño; si faltan, las páginas muestran un aviso con lo que falta en lugar de inventarlos. **No sustituyen asesoría legal: hay que hacerlos revisar** (`GUIA_ETAPA_11.md`, Paso 4).
- **Aceptación al registrarse:** casilla obligatoria (con la declaración de tener 18 años o más o contar con la autorización de madre, padre o tutor). La base guarda la **versión** (`AAAA-MM-DD`, de `js/legal.js`) y la **fecha y hora** de aceptación en `profiles.terms_version` / `terms_accepted_at`. Solo las escribe el servidor al crear la cuenta (y solo si la versión tiene formato válido); el navegador no puede cambiarlas.
- **Eliminar mi cuenta (`perfil.html`):** contraseña + frase «ELIMINAR MI CUENTA»; el navegador borra primero los archivos de la persona con la API de Storage y después llama a `delete_my_account`, que elimina la cuenta y, en cascada, todo lo suyo. El servidor **se niega** si quedan archivos suyos, si la cuenta es de administración o si la frase no coincide. No se tocan las denuncias anónimas ni la bitácora. Con CAPTCHA activo, la verificación también se pide al cambiar la contraseña y al eliminar.
- **`404.html`**, `noindex` en las pantallas de acceso, **`database/07_limpiar_demo.sql`** (borra solo la demostración y lista las guías pendientes de revisión) y **`opcional/mantener-activo.yml`** (flujo opcional y gratuito de GitHub contra la pausa del proyecto de Supabase; no hace nada mientras esté en esa carpeta).
- **Auditoría automática del sitio** (`pruebas-web/auditar_sitio.py`, 42 comprobaciones): sin archivos `.env` ni claves, sin `innerHTML`/`eval` con datos, CSP cerrada, enlaces internos existentes, `rel="noopener"`, `alt`, etiquetas de formularios, políticas de indexación, funciones `SECURITY DEFINER` con `search_path` fijo y demostración separada.
- **Datos de autoridades de denuncias:** sin teléfonos que no se pudieron verificar. La tarjeta dice «en una emergencia llama al 911», manda a la fiscalía o la autoridad de protección animal de **tu** estado o municipio y enlaza el sitio oficial de PROFEPA para fauna silvestre.
- **`.env.example` y este README** documentan qué es público y qué es secreto, y cómo configurar y publicar.
- **Cobros: pospuestos, no habilitados.** Sigue sin existir ninguna pantalla de pago.

**Cómo se probó la Etapa 11, con honestidad**

- **770 pruebas de SQL** (35 nuevas, grupo 13: constancia de términos —versión inventada, cuenta creada sin aceptar, cambio desde el navegador, restricción CHECK incluso para el dueño de la base—, permisos de `delete_my_account`, frase exacta en mayúsculas, administradores, archivos pendientes, cascada completa y lo ajeno intacto) y **37 comprobaciones** del verificador; el instalador se ejecutó sobre una base ya instalada y sobre una limpia. **21 sabotajes** al SQL (quitar el chequeo de administrador, de archivos o de sesión; borrar a todos o a nadie; aceptar cualquier frase o ignorar mayúsculas; abrir permisos a visitantes; no validar la versión de términos; dejar que el navegador la edite…): **los 21 se detectan**. Esa ronda dejó al descubierto **dos huecos de mis propias pruebas**: (1) el archivo de pruebas corre con los errores no fatales (para que una falla no detenga a las demás) y una inserción de preparación estaba mal escrita, así que la prueba de «se borra en cascada la solicitud de plan» comparaba contra datos que nunca existieron; ya está corregida, ahora hay una comprobación previa de que todo lo que debe desaparecer sí existía, y **el corredor de pruebas falla si hay cualquier error de SQL en la preparación** (se probó rompiendo una inserción a propósito); (2) un sabotaje (dar al navegador permiso de columna sobre la constancia) era frenado por un segundo seguro (el disparador de perfiles), así que se añadió una prueba que también verifica el primer seguro.
- **92 pruebas de navegador** en Chromium con **las mismas cabeceras CSP del sitio** (`pruebas-web/probar_legal.py`, contra el simulador `mock_etapa11.py`, que traduce cada petición a SQL real con RLS): páginas legales (estructura, datos de `config.js` escritos como texto, aviso de datos faltantes, enlaces), aceptación al registrarse (sin casilla no se envía, versión enviada, texto hostil), eliminar la cuenta de punta a punta (contraseña incorrecta, frase, archivos borrados antes que la cuenta, cuenta de otra persona intacta, administrador, cuenta suspendida, doble clic, errores del servidor, sesión local cerrada), Turnstile en cambiar contraseña y eliminar, 404, indexación, pie de página y diseño de 390 px. **66 sabotajes** de la interfaz (no pedir la contraseña, no borrar archivos antes, olvidar un depósito, ignorar un fallo de Storage, no cerrar la sesión local, no reiniciar el token del anti-robots, mostrar datos legales como HTML…): **los 66 se detectan**, después de reforzar varias pruebas que al principio dejaban pasar sabotajes (por ejemplo, no se verificaba que se cerrara la sesión después de eliminar, ni cada dato de las páginas legales, ni el desbordamiento del menú lateral en el teléfono).
- **Auditoría estática** (42 comprobaciones) con su propia **autoprueba** (17 casos que deben detectarse): `TODO` como identificador de código y la palabra «todo» en español daban falsos positivos y se acotó la búsqueda a marcas de trabajo pendiente.
- Siguen pasando las regresiones de las Etapas 3 a 10 (navegador, función segura, códigos QR, plantillas de correo y SQL). Se actualizaron las expectativas del registro (la constancia de términos viaja en los metadatos).
- **Errores reales que encontraron las pruebas y ya corregí:** (1) en Perfil los botones no respondían hasta que llegaba la consulta del plan (ahora esa consulta no bloquea); (2) con CAPTCHA activo, la nueva comprobación de contraseña al cambiarla o eliminar la cuenta habría fallado por no mandar el token (hay recuadro y token en ambas); (3) un mensaje largo y sin espacios ensanchaba la página en el teléfono; (4) botones de 31 px en Perfil en móvil (ahora 44 px); (5) un manejador de formularios sin uso en el pie, ya quitado; (6) el mini-catálogo de planes se armaba con `innerHTML` (ahora con construcción segura de elementos); (7) quedaban textos de la Etapa 1 en el sitio («Plataforma en construcción por etapas…» en la portada, «se habilitará en una versión futura», «en desarrollo por etapas» en el pie y un aviso de correo que prometía «estamos configurando el envío»): ya se reescribieron para describir lo que el sitio hace hoy, y la auditoría ahora los detecta (la encontró el usuario a simple vista: mi búsqueda de textos viejos era demasiado estrecha).
- **Lo que NO se pudo probar desde aquí:** tu Supabase real (`delete from auth.users` dentro de la función y el borrado real de archivos con la API de Storage se probaron contra PostgreSQL local y un simulador), Turnstile real, el efecto de `404.html` en Cloudflare Pages, un teléfono físico, **y la validez legal de los textos** (necesitan revisión de una persona calificada). `GUIA_ETAPA_11.md` trae una lista de comprobaciones para tu sitio real.

**Correo y confirmación de cuenta (decisión del 4 de noviembre de 2026):** Gmail **ya no se usa** (su guía y las plantillas se conservan, marcadas «no se usa por ahora») y la **confirmación de correo se desactiva** (la apagas tú en Supabase: `GUIA_ETAPA_10.md`, Paso 3). Consecuencias: nadie comprueba que el correo sea de quien se registra, y **recuperar contraseña por correo no llega a personas normales** (el correo de cortesía de Supabase solo escribe a tu equipo, máximo 2 por hora); mientras no haya un SMTP propio, el equipo restablece accesos desde el SQL Editor.

**No terminado (y no finge estarlo)**

- **Conectado a la base de datos:** cuentas, perfil, mascotas, carnet, fotos, placa QR, directorio, panel de aliados, denuncias anónimas, chat de atención y notificaciones. El panel de administración ya está conectado (Etapa 10). Antes de publicar con personas reales, completa `GUIA_ETAPA_11.md` (datos legales, revisión de los textos, limpiar la demostración).
- **Aprobar aliados, resolver solicitudes de plan y asignar planes** se hace desde el panel (`admin.html`); el SQL de `GUIA_ETAPA_5.md` y `GUIA_ETAPA_9.md` sigue funcionando. Ningún aliado aparece en el directorio sin que un administrador lo apruebe.
- **Cobros y contratación no están habilitados.** No se guarda ninguna tarjeta ni dato financiero. La persona **solicita** su plan (Etapa 9) y el equipo lo activa a mano, sin cargo; si algún día se habilitan pagos, será una decisión nueva y explícita. Los **recordatorios por WhatsApp o correo** están *previstos*, no activos: hoy los avisos de vacunas, desparasitaciones y citas llegan solo dentro de la plataforma (Notificaciones y campanita), cuando la persona entra al sitio.
- **Los textos legales necesitan revisión de una persona calificada** y tus datos de responsable, domicilio y contacto (`js/config.js`). Las protecciones de página del navegador son comodidad: la seguridad real está en las políticas RLS.
- **Responder el chat** se hace desde el panel (Atención); el chat no admite archivos adjuntos.
- **Revisar y responder las denuncias** se hace desde el panel (Denuncias). Cuando llega una denuncia, el equipo recibe un aviso dentro de la plataforma (solo con el código, el tipo y el estado: nunca datos de quien denuncia); el botón «Ver» de ese aviso abre directamente la sección Denuncias del panel (`admin.html#denuncias`). Las evidencias se borran a mano.
- **Datos de autoridades:** la página de denuncias es genérica a propósito (911, la fiscalía o la autoridad de protección animal de tu estado o municipio, y el sitio oficial de PROFEPA); no se publican teléfonos sin verificar. Si quieres datos locales concretos, pásame la fuente oficial (`GUIA_ETAPA_11.md`, Paso 7).
- **Limpieza de archivos:** al reemplazar o quitar una foto, o eliminar una mascota, el navegador borra los archivos viejos; si se corta la conexión justo en ese momento puede quedar algún archivo huérfano (ocupa espacio, nadie lo ve). Está acotado por los topes por persona; no hay limpieza automática periódica (se puede revisar a mano en Storage).
- **La foto de la placa QR es pública** (bucket `qr-photos`, solo para quien la elige) y cualquiera que tenga su dirección exacta puede verla; las demás fotos son privadas.
- **El QR contiene la dirección del sitio** (hoy `…pages.dev`). Si algún día cambia la dirección, los QR impresos hay que reponerlos.
- Las denuncias se **registran en la plataforma**; la plataforma no las presenta ante ninguna autoridad. Tampoco hay anonimato técnico absoluto frente a los proveedores de infraestructura (Supabase, Cloudflare): lo que se garantiza es que TECNOPATITAS no guarda nada que identifique a quien reporta.
- Las guías y los aliados de la demostración son **contenido de ejemplo**. Las guías están marcadas «pendiente de revisión veterinaria» y deben revisarse antes de presentarlas como definitivas (o despublicarse: `database/07_limpiar_demo.sql`, línea opcional).

## Estructura

```
index.html  registro.html  login.html  recuperar.html  nueva-contrasena.html
guias.html  directorio.html  denuncias.html  planes.html  sobre-nosotros.html
perfil.html  mascota.html  carnet.html  qr.html (página pública de la placa)
notificaciones.html  chat.html  panel-aliado.html  admin.html (panel de administración)
privacidad.html  terminos.html  404.html
css/styles.css        estilos compartidos (la paleta de colores está al inicio, en `:root`)
js/config.js          URL y clave publishable de Supabase, tus datos legales (`LEGAL`) y la Site Key de Turnstile (todo público; NUNCA la secret)
js/legal.js           versión y fecha vigentes del aviso de privacidad y los términos (se guarda al registrarse)
js/tp-client.js       cliente de Supabase Auth/REST/Storage sin dependencias (Etapas 3 y 4)
js/tp-ui.js           ayudas de formularios, fechas en español y construcción segura de elementos
js/media.js           reduce y recodifica imágenes a JPEG (quita EXIF/GPS) antes de subirlas
js/qr.js              generador de códigos QR propio (sin servicios externos)
js/tp-pets.js         ayudas compartidas de mascotas, fotos firmadas y planes
js/tp-biz.js          ayudas del directorio: categorías, enlaces de Google Maps/teléfono/WhatsApp, horarios
js/tp-captcha.js      Cloudflare Turnstile (anti-robots): solo usa la clave PÚBLICA de config.js
js/guard.js           protección de páginas privadas por rol
js/layout.js          cabecera (según sesión), campanita con el número de no leídas, recordatorios diarios, pie y avisos compartidos
js/pages/             lógica de cada página: registro, login, recuperar, nueva-contraseña, perfil,
                      mascota, carnet, placa (en carnet.html), qr-publico, directorio y panel-aliado
                      (panel-aliado.js + un módulo por sección: panel-datos, -fotos, -horarios, -promos, -stats)
                      denuncias (formulario anónimo + seguimiento), chat (lista, hilo y mensajes en vivo)
                      y notificaciones (lista, filtros, preferencias; la campanita vive en layout.js),
                      legal (llena los datos del aviso con config.js), guias (lista pública y lectura) y el panel de administración (admin.js + un módulo por sección:
                      admin-usuarios, -aliados, -denuncias, -guias, -subs, -atencion, -bitacora)
js/tp-realtime.js     cliente mínimo de Supabase Realtime (WebSocket), usado por el chat
js/tp-guides.js      ayudas de las guías de cuidado (categorías, dirección, texto → párrafos) para guias.html y el editor del panel
js/plans.js           catálogo de planes (fijo, igual a la base), selector mensual/anual y tarjetas
                      (la pantalla con sesión de Suscripciones es js/pages/planes.js)
_headers              cabeceras HTTP y CSP (Cloudflare Pages)
.env.example          documenta qué es público y qué es secreto (solo TURNSTILE_SECRET_KEY, que va en Supabase y no en el repositorio)
opcional/             mantener-activo.yml: flujo opcional de GitHub contra la pausa de Supabase (no hace nada hasta que tú lo actives)
GUIA_ETAPA_3.md       pasos manuales de la Etapa 3 y lista de pruebas en tu sitio
GUIA_ETAPA_4.md       pasos manuales de la Etapa 4 y lista de pruebas en tu sitio
GUIA_ETAPA_5.md       pasos manuales de la Etapa 5 (aprobar aliados, asignar planes) y lista de pruebas
GUIA_ETAPA_6.md       pasos manuales de la Etapa 6 (Turnstile, función segura, secreto), revisión de denuncias y pruebas
GUIA_ETAPA_7.md       pasos manuales de la Etapa 7 (actualizar SQL, responder el chat con SQL) y lista de pruebas
GUIA_ETAPA_8.md       pasos manuales de la Etapa 8 (actualizar SQL, crear notificaciones de prueba) y lista de pruebas en tu sitio
GUIA_ETAPA_9.md       pasos manuales de la Etapa 9 (actualizar SQL, aprobar o rechazar solicitudes de plan con SQL) y lista de pruebas
GUIA_ETAPA_10.md      pasos manuales de la Etapa 10 (actualizar SQL, desactivar la confirmación de correo, dar el rol de administración) y lista de pruebas
GUIA_ETAPA_11.md      pasos manuales de la Etapa 11 (datos legales, revisión de textos, limpiar la demostración, pausa de Supabase) y lista final antes de publicar
GUIA_CORREOS_GMAIL.md Gmail como correo de las cuentas, paso a paso (NO SE USA POR AHORA; se conserva por si más adelante hay SMTP propio)
supabase/plantillas-correo/  plantillas en español de «Confirm sign up» y «Reset password» para pegar en Supabase
supabase/functions/   función segura submit-complaint (Edge Function; se pega en el editor de Supabase)
database/             Etapa 2: SQL de la base de datos (ver abajo)
pruebas-web/          pruebas de navegador con simuladores de Supabase (solo desarrollo):
                      probar_acceso.py (Etapa 3), probar_mascotas.py y probar_qr.py (Etapa 4),
                      probar_aliados.py (Etapa 5), probar_denuncias.py y probar_funcion.py (Etapa 6),
                      probar_chat.py (Etapa 7), probar_notificaciones.py (Etapa 8),
                      probar_planes.py y probar_correos.py (Etapa 9), probar_admin.py (Etapa 10),
                      probar_legal.py (Etapa 11) y auditar_sitio.py (auditoría estática de todo el sitio);
                      simuladores mock_supabase.py, mock_etapa4.py … mock_etapa11.py;
                      servidor_funcion.mjs ejecuta el código real de la función segura con Node
```

### Carpeta `database/`

| Archivo | Para qué sirve |
|---|---|
| `GUIA_INSTALACION.md` | **Empieza aquí.** Pasos exactos para instalarlo en tu Supabase |
| `00_instalar_todo.sql` | Todo junto (01 a 05; sin demostración) para pegarlo de una vez. Se puede ejecutar varias veces |
| `01_esquema.sql` … `05_datos_base.sql` | Las partes: tablas · funciones · permisos (RLS) · archivos · planes |
| `06_datos_demo.sql` | Opcional: 6 aliados ficticios y 8 guías generales de ejemplo |
| `07_limpiar_demo.sql` | Etapa 11: borra solo los aliados ficticios antes de abrir al público (no toca cuentas ni datos reales) |
| `verificar_seguridad.sql` | Solo lectura: confirma que tu Supabase quedó seguro (37 comprobaciones) |
| `construir_instalador.sh` | Regenera `00_instalar_todo.sql` si editas 01–05 |
| `pruebas/` | Batería de pruebas y simulador de Supabase (solo para desarrollo local) |

Todas las rutas son relativas.

## Paleta de colores

Los colores de la marca son **menta `#80E3B9`**, **lavanda `#C0B8E8`**, **azul cielo `#92C1E9`** y **rosa `#FFCBD9`**. Se definen una sola vez, al inicio de `css/styles.css` (`--mn`, `--lv`, `--sk`, `--pk`), así que cambiarlos allí los cambia en todo el sitio.

- **Menta:** botones principales, página actual en los menús, etiquetas, globos de tus mensajes en el chat e ícono del logotipo.
- **Rosa:** botones de acción destacada (por ejemplo «Crear cuenta», «Enviar»), etiqueta «Más popular», números de los pasos, avisos de «todavía no conectado» y mensajes de error.
- **Azul cielo:** encabezados de página (en degradado con la menta), al pasar el cursor por los menús y avisos informativos.
- **Lavanda:** pie de página, ilustración de las pantallas de acceso y globos del equipo en el chat.
- Para que el texto se lea bien (los pasteles no tienen contraste suficiente), **el texto va en azul marino oscuro** (`#1F2B4D`), y los fondos grandes y las líneas usan **versiones muy claras de los mismos cuatro colores**. Los mensajes de error usan texto vino oscuro sobre el rosa. Todas las combinaciones de texto y fondo superan el contraste mínimo de 4.5:1 (se midió en el navegador en las páginas públicas, en el chat y, con una comprobación automática, en Notificaciones y la campanita).
- Los códigos QR siguen siendo **negro sobre blanco** a propósito: es lo que mejor leen las cámaras.

## Probar en tu computadora

Desde la Etapa 3 hay que servir la carpeta (con doble clic en el archivo no funcionan las sesiones): `python3 -m http.server 8000` y entra a `http://localhost:8000`. Para que los correos de confirmación regresen ahí, añade `http://localhost:8000/**` en *Authentication → URL Configuration → Redirect URLs* (Paso 2 de `GUIA_ETAPA_3.md`).

**Pruebas automáticas (opcional, para quien edite el código):** `pip install playwright && playwright install chromium`, luego `pip install pillow numpy opencv-python-headless`, luego `python3 pruebas-web/probar_acceso.py` (Etapa 3), `python3 pruebas-web/probar_mascotas.py` y `python3 pruebas-web/probar_qr.py` (Etapa 4), `python3 pruebas-web/probar_aliados.py` (Etapa 5), `python3 pruebas-web/probar_funcion.py` y `python3 pruebas-web/probar_denuncias.py` (Etapa 6; requieren PostgreSQL local, Node 22 y las variables `PGHOST`/`PGPORT`/`PGUSER`), `python3 pruebas-web/probar_chat.py` (Etapa 7) `python3 pruebas-web/probar_notificaciones.py` (Etapa 8), `python3 pruebas-web/probar_planes.py` (Etapa 9) `python3 pruebas-web/probar_admin.py` (Etapa 10) y `python3 pruebas-web/probar_legal.py` (Etapa 11; estas cinco requieren PostgreSQL local y las mismas variables), `python3 pruebas-web/probar_correos.py` (plantillas de correo), `python3 pruebas-web/auditar_sitio.py` (auditoría estática de todo el sitio; no necesita base de datos) y `bash database/pruebas/ejecutar_pruebas.sh` (SQL, requiere PostgreSQL; falla si hay cualquier error de SQL en la preparación de las pruebas).

## Publicar el sitio (gratis)

1. **GitHub:** crea una cuenta en <https://github.com/signup>, pulsa **New** para crear un repositorio (por ejemplo `tecnopatitas`), pulsa **uploading an existing file**, sube **el contenido** de esta carpeta (no la carpeta en sí) y confirma con **Commit changes**.
2. **Cloudflare:** entra a <https://dash.cloudflare.com>, crea una cuenta gratuita y abre **Workers & Pages → Create → Pages → Connect to Git**. Elige tu repositorio.
3. En la configuración de compilación deja **Build command** vacío y escribe `/` en **Build output directory**. Pulsa **Save and Deploy**.
4. Cuando termine, Cloudflare te dará una URL `https://tu-proyecto.pages.dev`.
5. **Configuración que se hace una sola vez, en archivos públicos del repositorio:** abre `js/config.js` y comprueba la URL y la clave *publishable* de tu Supabase, llena los datos de `LEGAL` (responsable, domicilio y contacto) y, si usas anti-robots, tu `TURNSTILE_SITE_KEY`. **Nunca** pongas ahí la clave `secret`/`service_role`, la contraseña de la base de datos ni la *Secret Key* de Turnstile: el sitio se niega a funcionar si detecta una clave secreta, y esas claves van solo como secretos de la función segura en el panel de Supabase (`GUIA_ETAPA_6.md`). No hay archivos `.env` que subir: `.env.example` solo documenta nombres.
6. **Antes de abrir al público,** sigue la lista final de `GUIA_ETAPA_11.md` (SQL actualizado, textos legales revisados, demostración limpiada, administradora creada, pruebas en el sitio real).

Los nombres de los menús de Cloudflare cambian con frecuencia; si algo no coincide, dime qué ves y lo ajustamos. No actives ningún plan de pago ni registres tarjetas en Supabase, Cloudflare o GitHub: no hace falta ninguno. Cada subida a GitHub vuelve a publicar el sitio solo (500 compilaciones al mes en el plan gratuito).

## Límites gratuitos verificados (4 de noviembre de 2026)

| Servicio | Límites del plan gratuito relevantes |
|---|---|
| **Supabase** | 2 proyectos activos; 500 MB de base de datos; 1 GB de archivos; 5 GB de transferencia al mes; 50,000 usuarios activos al mes; unos 200 usuarios conectados a Realtime a la vez; 500,000 invocaciones de funciones al mes. **El proyecto se pausa tras 7 días sin actividad** y hay que reactivarlo a mano desde el panel (los datos se conservan). |
| **Resend** | 3,000 correos al mes y **100 al día**; 1 dominio. Los correos recibidos también cuentan. Si se supera, el envío se pausa; no hay cobro automático. |
| **Cloudflare Pages** | 500 compilaciones al mes, 1 a la vez; 20,000 archivos por sitio; 25 MiB por archivo. |
| **Cloudflare Turnstile** | Gratuito: hasta 20 widgets, desafíos ilimitados y 10 dominios por widget; sin tarjeta. |

Consecuencias para el diseño:

- **Pausa de Supabase:** para una demostración escolar es aceptable. Con personas reales, un proyecto con visitas diarias normalmente no se pausa; si habrá semanas sin visitas hay que mantenerlo activo o aceptar que se pause. Supabase avisa por correo (aproximadamente una semana antes), reactivarlo es gratis desde el panel (**Resume project**; su documentación dice que se puede restaurar hasta 1 año después de la pausa) y los datos se conservan. Opciones gratuitas y la explicación completa en `GUIA_ETAPA_11.md` (Paso 10), incluido el flujo opcional `opcional/mantener-activo.yml`.
- **Correos:** con 100 al día, los recordatorios por correo se enviarán en lotes y con tope diario. Si se alcanza, se registrará como «no enviado» y nunca se mostrará como enviado.
- **Fotos de denuncias:** 1 GB se agota rápido; cada reporte admite hasta 3 fotos de máximo 2 MB (ya reducidas, suelen pesar ~300 KB) y la función se niega a recibir más evidencias al llegar a 300 MB.
- Los límites cambian con el tiempo. Se vuelven a comprobar antes de cada integración.

## Decisiones de la Etapa 2 que conviene confirmar

1. **Mascotas y carnet:** registrar la ficha de una mascota es gratis (máx. 30 por cuenta); el **carnet de salud** depende del plan (Básica: no · Pro: 2 mascotas · VIP: ilimitado).
2. **Placa QR:** solo se puede *crear* con Huellita VIP. Si el plan vence, la placa ya creada se conserva (para no dejar a una mascota extraviada sin su QR) pero no se pueden crear nuevas.
3. **Planes de pago:** un usuario **no puede activarse un plan** desde el navegador; lo asigna un administrador. Así no hay forma de «regalarse» beneficios. Cancelar es inmediato.
4. **Directorio público:** cualquiera ve los aliados *aprobados*. Sin plan de aliado solo se muestra nombre, categoría, descripción y dirección; la **ficha completa** (teléfono, horario, logotipo, fotos y promociones) llega con Plata u Oro, y el **WhatsApp** y el lugar prioritario solo con Oro. Nunca se muestra quién es el dueño. Si un plan vence, los datos se conservan pero dejan de mostrarse.
5. **Privacidad del administrador:** un admin gestiona usuarios, aliados, denuncias, guías y chat, pero **no puede leer las mascotas ni el carnet** de otras personas.
6. **Límite anti-abuso por IP:** las denuncias se limitan por visitante usando un código derivado de la IP (no se guarda la IP). Detrás de redes compartidas puede ser impreciso; desde la Etapa 6 se suma Cloudflare Turnstile (gratuito).
7. **Fotos de denuncias:** se suben mediante una función segura (Etapa 6; no hay subida directa desde el navegador).
8. **Datos de demostración:** hay que revisarlos y borrarlos antes de abrir el sitio al público (`delete from public.businesses where is_demo;`).

## Decisiones de la Etapa 4 que conviene confirmar

1. **Foto de la placa QR pública y separada.** Para que quien encuentre a la mascota pueda ver su foto sin iniciar sesión, la foto que *tú eliges* para la placa se guarda en un bucket público aparte (`qr-photos`, máx. 30 archivos de 1 MB por cuenta, solo con Huellita VIP). La foto de la ficha de la mascota sigue privada.
2. **La placa solo muestra lo que activas.** Por omisión: nombre y raza visibles, teléfono y foto apagados. El teléfono solo se publica si lo escribes y lo autorizas.
3. **Una placa ya creada sobrevive al vencimiento del plan** (se puede seguir editando su texto), pero sin VIP no se pueden crear placas nuevas ni subir fotos nuevas para la placa.
4. **El carnet usa hora de Ciudad de México** (UTC−6 fijo, sin horario de verano desde 2022).
5. **Sin recordatorios todavía** (ver «No terminado»).

## Decisiones de la Etapa 5 que conviene confirmar

1. **La etiqueta «Aliado verificado» solo se muestra con el plan Oro**, aunque un administrador marque a un negocio como verificado (es un beneficio del plan Huellita de Oro). Si algún día quieres que se muestre con cualquier plan, es un cambio pequeño en el SQL.
2. **Los cambios de un establecimiento ya aprobado se publican de inmediato**, sin nueva revisión. La revisión se hace al registrarlo; el administrador puede suspenderlo después. Si prefieres revisar cada cambio, habría que añadir un estado «cambios pendientes» (más trabajo en la Etapa 10).
3. **El límite mensual de promociones se cuenta por promociones creadas este mes**: quien borra una promoción de Plata libera el cupo y puede crear otra. Es una limitación conocida y de bajo riesgo (la promoción solo es un anuncio de texto); si la quieres estricta, habría que guardar un contador aparte.
4. **Estadísticas aproximadas y anónimas**: una persona cuenta una visita por ficha y por día y hasta 3 clics de mapa (la «huella» es un código derivado de la IP que cambia cada día; no se guarda la IP). Tus propias visitas y las de fichas de demostración no cuentan; detrás de una red compartida puede haber imprecisiones.
5. **Las imágenes del negocio son públicas** (bucket `business-media`, máx. 30 archivos de 5 MB por cuenta; hasta 6 fotos + logotipo por establecimiento). Se avisa en el panel. Quien tenga la dirección exacta de una imagen puede verla aunque la ficha no esté aprobada.
6. **Aprobar, suspender, verificar y asignar plan se hace con SQL hasta la Etapa 10** (el panel de administración). Mientras tanto ningún aliado aparece en el directorio sin tu aprobación.
7. **Un máximo de 5 establecimientos por cuenta** y un mismo plan para todos los de la cuenta.

## Decisiones de la Etapa 6 que conviene confirmar

1. **Hasta 3 fotos por reporte, de máximo 2 MB cada una** (reducidas por el navegador a 1280 px y re-codificadas como JPEG). Es menos de los 5 MB propuestos al inicio: con 300 MB de evidencias se alcanzan cientos de reportes con fotos dentro del 1 GB gratuito.
2. **Límites:** 5 reportes por hora y 15 por día por visitante; 300 al día en total y 100 con fotos al día; 300 MB de evidencias. Detrás de una red compartida (escuela, oficina) varias personas comparten el límite.
3. **El código de seguimiento no se puede recuperar** (así se protege el anonimato). Si se pierde, hay que hacer otro reporte.
4. **El mensaje público del equipo** (`public_update`) lo ve cualquiera que tenga el código; no debe llevar datos personales.
5. **La función falla cerrado:** sin la clave secreta de Turnstile, o si Cloudflare no responde, no se recibe ningún reporte (mejor eso que dejar la puerta abierta a robots).
6. **Turnstile en el acceso es opcional** (Paso 7 de la guía) y conviene activarlo antes de abrir el registro al público; si se activa antes de publicar la Site Key, nadie podría entrar.
7. **Sin dominio propio**, Turnstile se configura para `tecnopatitas.pages.dev`; las vistas previas de Pages no estarán permitidas.
8. **Revisión con SQL** hasta la Etapa 10; las evidencias se descargan desde Storage.

## Decisiones de la Etapa 7 que conviene confirmar

1. **Tope diario: 100 mensajes en 24 horas por cuenta** (y 20 cada 10 minutos), 10 conversaciones abiertas a la vez y 20 nuevas por día. El equipo no tiene límite. Se cambia con una línea de SQL.
2. **La persona puede cerrar su conversación, pero solo el equipo puede reabrirla**, para que el tope de conversaciones abiertas no se esquive cerrando y reabriendo.
3. **El equipo responde con SQL hasta la Etapa 10** (consultas en `GUIA_ETAPA_7.md`).
4. **La marca «Nuevo» se guarda solo en el navegador**: en otro dispositivo vuelve a aparecer.
5. **Sin adjuntos** en el chat (cuida el almacenamiento gratuito) y sin mensajes entre usuarios.
6. **Enlace directo** `chat.html?c=ID`: solo funciona para la dueña de la conversación.

## Decisiones de la Etapa 8 que conviene confirmar

1. **La campanita consulta cada 60 s (no en vivo)** para no gastar conexiones simultáneas del plan gratuito; solo Notificaciones usa conexión en vivo.
2. **Recordatorios al visitar el sitio, sin tareas programadas.** Es lo más simple y no puede generar cargos; su costo es que dependen de que la persona entre. Las cuentas necesitan carnet (planes Pro y Huellita VIP) para tener vacunas que avisar.
3. **Ventanas de aviso:** 7 días antes y hasta 60 días después de vencer; citas 48 horas antes. Se cambian con un número en el SQL.
4. **Los avisos importantes («aviso») no se pueden silenciar.**
5. **Tope de 200 por persona** con limpieza automática (leídas de más de 90 días y todo lo de más de 365).
6. **Chat → equipo: un aviso por turno**, para no saturar al equipo ni llenar la base.
7. **El aviso de respuesta del equipo lleva un adelanto de 140 caracteres** (solo lo ve su dueña). Si prefieres un texto genérico, se cambia.
8. **Correos y WhatsApp: no existen todavía.** El interruptor de correo sigue bloqueado: se decidió no usar Gmail por ahora (Etapa 10) y no hay SMTP propio, así que los avisos viven solo dentro de la plataforma.
9. **El botón «Ver» de los avisos al equipo abre `admin.html` en la sección correspondiente** (conectado en la Etapa 10).

## Decisiones de la Etapa 9 que conviene confirmar

1. **Aprobar una solicitud = activar el plan a mano, sin cobrar.** Es la única forma de «contratar» mientras no existan pagos reales.
2. **Vigencia:** 1 mes (mensual) o 1 año (anual) desde la aprobación; se puede indicar otra fecha al aprobar.
3. **Renovación solo en los últimos 15 días** de vigencia, y extiende la misma suscripción.
4. **Una solicitud en revisión por persona, 5 al día y 20 resueltas en el historial.**
5. **Aviso de vencimiento al visitar el sitio** (7 días antes y hasta 30 después), sin tareas programadas ni `pg_cron`; si la persona no entra, no se entera hasta que entre.
6. **El catálogo de planes está fijo en `js/plans.js`** (los visitantes no hacen peticiones a Supabase); una prueba automática lo compara con la base. Si cambias precios o beneficios en la base, cámbialos también ahí.
7. **Las cuentas de aliado ahora también piden la generación diaria de avisos** (cambio respecto a la Etapa 8).
8. **Las cuentas de administración se comportan como dueñas** en esta pantalla (ven y piden sus propios planes, no los de otras personas); la gestión se hace en el panel (Etapa 10) con `admin_resolve_plan_request`.
9. **Gmail solo para correos de cuenta.** *(Decisión revocada en la Etapa 10: Gmail ya no se usa por ahora.)*

## Decisiones de la Etapa 10 que conviene confirmar

1. **Los administradores solo se crean desde el SQL Editor.** El panel no puede dar ni quitar el rol, ni suspender a otro administrador.
2. **El panel no edita establecimientos:** cambia su estado y la verificación y retira promociones; los datos los corrige su dueño.
3. **Retirar una promoción la borra** (sin «ocultar»); el dueño recibe el motivo.
4. **Responder en una conversación cerrada la reabre.**
5. **Atención se actualiza por consulta (30 s la bandeja, 15 s la conversación)**, no con Realtime; se pausa con la pestaña oculta.
6. **La bitácora crece sin límite** (una fila por acción, sin contenidos); hoy no se limpia sola.
7. **Las guías públicas ya están conectadas.** Formato del contenido: párrafos y `## ` para subtítulos; las guías de demostración siguen marcadas como pendientes de revisión veterinaria.
8. **Las fechas de vencimiento que eliges en el panel terminan a las 23:59:59 de México (UTC−6).**
9. **Sin Gmail y sin confirmación de correo (decisión tuya):** cualquiera puede registrarse con un correo ajeno y la recuperación de contraseña por correo no llega a personas normales; mientras tanto el equipo restablece accesos desde el SQL Editor (`GUIA_ETAPA_10.md`, Paso 3). `recuperar.html` lo dice con honestidad.
10. **Un enlace `admin.html#seccion` abierto sin sesión** lleva al inicio de sesión y vuelve al panel, pero no recuerda la sección.

## Decisiones de la Etapa 11 que conviene confirmar

1. **Registro: 18 años o más, o autorización de madre, padre o tutor** (declaración con casilla; no se verifica ni se guarda la edad de nadie). Si prefieres prohibir el registro de menores o exigir un procedimiento de autorización, cambian los textos y el flujo (y conviene asesoría legal).
2. **La constancia guarda solo la versión y la fecha de aceptación**, no la IP. Al cambiar los textos de fondo, sube `VERSION` y `FECHA` en `js/legal.js`; las cuentas anteriores conservan la versión que aceptaron (no se les pide aceptar de nuevo: si lo quieres, es una pantalla nueva).
3. **Eliminar la cuenta es inmediato y definitivo** (contraseña + frase), sin periodo de arrepentimiento. Las denuncias anónimas no se borran porque no están ligadas a la cuenta.
4. **El servidor no vuelve a pedir la contraseña al eliminar** (lo hace el navegador). Una sesión robada más la frase podría borrar esa cuenta; las sesiones caducan. Si lo prefieres más estricto, hay que pasar por una función segura con la contraseña.
5. **Las cuentas de administración no se eliminan desde Perfil.**
6. **La demostración y las guías pendientes se limpian con un script que ejecutas tú** (no se borra nada en bloque ni automáticamente).
7. **Riesgos aceptados y documentados:** CORS abierto en la función anónima `submit-complaint` (la protegen Turnstile y los límites), estilos en línea permitidos por la CSP (los scripts no), Google Fonts desde Google, y confirmación de correo desactivada (decisión de la Etapa 10).

## Después de las 11 etapas

Las 11 etapas del plan están escritas y probadas contra simuladores y bases locales; **falta tu parte**: los pasos de `GUIA_ETAPA_11.md` (datos legales, revisión de los textos por una persona calificada, limpiar la demostración, revisión veterinaria de las guías) y probar todo en tu sitio real. **Cobros y contratación de suscripciones: no habilitados** (pospuestos por decisión tuya). Si algún día se retoman, será una decisión nueva y explícita (proveedor, comisiones, obligaciones fiscales, revisión con una persona contadora) y no se activará nada que genere cargos automáticos.
