# TECNOPATITAS · Plataforma web

Plataforma para el cuidado, protección y bienestar de las mascotas. Se construye **por etapas**; este archivo dice qué está terminado y qué no.

## Estado actual: Etapa 5 de 11 (directorio público y panel de aliados)

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Estructura, diseño y navegación | Terminada |
| 2 | Supabase: base de datos, permisos (RLS), almacenamiento y datos iniciales | Terminada. **Las Etapas 4 y 5 amplían el SQL**: vuelve a ejecutar `database/00_instalar_todo.sql` (es seguro repetirlo); el verificador ahora tiene 34 comprobaciones |
| 3 | Registro, inicio de sesión, recuperar contraseña, sesión, roles y protección de páginas | Terminada y probada en tu sitio real |
| 4 | Mascotas, carnet de salud digital, subida de fotos (Supabase Storage) y placa QR (Huellita VIP) | Terminada y probada en tu sitio real |
| **5** | **Directorio público y panel de aliados: alta del negocio, datos, logotipo y fotos, horarios, promociones, estadísticas y enlaces a Google Maps** | **Escrita y probada contra simuladores (172 pruebas de navegador + 395 de SQL). Falta que la pruebes en tu sitio real: `GUIA_ETAPA_5.md`** |
| 6–11 | Denuncias, chat, notificaciones, planes, panel admin, publicación | Pendientes |

**Terminado en la Etapa 2** (carpeta `database/`)

- 19 tablas en `public` + 2 internas en `private`, con claves, índices y restricciones (CHECK) que impiden datos incoherentes.
- Seguridad por filas (RLS) en **todas** las tablas; permisos por columna (nadie puede cambiar su rol, su suspensión, su plan o el dueño de una mascota desde el navegador); funciones del servidor para todo lo sensible.
- Los 5 planes (nombres, precios MXN y beneficios exactos) y los permisos de cada plan **aplicados en el servidor**, no solo en pantalla.
- Denuncias anónimas **sin ningún dato que identifique a quien reporta**, con código de seguimiento, trampa anti-robots y límite de envíos.
- Chat, notificaciones, guías, directorio con filtros, placa QR con token aleatorio, bitácora de acciones de administración.
- 6 buckets de archivos (solo JPG/PNG/WebP, con tope de tamaño y de cantidad por persona). El sexto, `qr-photos`, se añadió en la Etapa 4.
- Datos de demostración **opcionales y claramente falsos** (`06_datos_demo.sql`).
- 395 pruebas automáticas de seguridad y funcionamiento (`database/pruebas/`) y un verificador de solo lectura para tu Supabase (`database/verificar_seguridad.sql`).

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

**Límite importante del plan gratuito de Supabase:** su servicio de correo de cortesía solo envía a los correos de tu equipo y a un máximo de 2 por hora. Para que cualquier persona pueda registrarse hará falta un SMTP propio. **Sin dominio** (decisión actual) no sirven Resend ni Brevo; la opción gratuita viable es una cuenta de Gmail exclusiva del proyecto con contraseña de aplicación (Paso 4 de `GUIA_ETAPA_3.md`). Los correos de notificación de la Etapa 9 se replantearán con ese límite.

**No terminado (y no finge estarlo)**

- **Conectado a la base de datos:** cuentas, perfil, mascotas, carnet, fotos, placa QR, directorio y panel de aliados. **Todavía no:** denuncias, chat, notificaciones y el panel de administración (siguen mostrando «se conecta en la Etapa N» y no guardan nada). No publiques datos reales todavía.
- **Aprobar aliados y asignar planes** todavía se hace a mano con SQL (`GUIA_ETAPA_5.md`); el panel de administración llega en la Etapa 10. Hasta entonces ningún aliado aparece en el directorio sin que tú lo apruebes.
- **Cobros y contratación no están habilitados.** No se guarda ninguna tarjeta ni dato financiero. Un administrador asigna los planes de pago manualmente (en la Etapa 9 se añade la «solicitud» de plan por parte del usuario). Los **recordatorios** de vacunas y citas por WhatsApp o correo están *previstos*, no activos: hoy el carnet solo marca «vencida» o «próxima» al abrirlo.
- **Faltan** eliminar la cuenta, el **aviso de privacidad y términos**, y el anti-robots en el registro (Turnstile, Etapa 6). Las protecciones de página del navegador son comodidad: la seguridad real está en las políticas RLS.
- **Limpieza de archivos:** al reemplazar o quitar una foto, o eliminar una mascota, el navegador borra los archivos viejos; si se corta la conexión justo en ese momento puede quedar algún archivo huérfano (ocupa espacio, nadie lo ve). Está acotado por los topes por persona; una limpieza automática periódica se valorará en la Etapa 11.
- **La foto de la placa QR es pública** (bucket `qr-photos`, solo para quien la elige) y cualquiera que tenga su dirección exacta puede verla; las demás fotos son privadas.
- **El QR contiene la dirección del sitio** (hoy `…pages.dev`). Si algún día cambia la dirección, los QR impresos hay que reponerlos.
- Las denuncias se **registran en la plataforma**; la plataforma no las presenta ante ninguna autoridad.
- Las guías y los aliados de la demostración son **contenido de ejemplo**. Las guías están marcadas «pendiente de revisión veterinaria» y deben revisarse antes de presentarlas como definitivas.

## Estructura

```
index.html  registro.html  login.html  recuperar.html  nueva-contrasena.html
guias.html  directorio.html  denuncias.html  planes.html  sobre-nosotros.html
perfil.html  mascota.html  carnet.html  qr.html (página pública de la placa)
notificaciones.html  chat.html  panel-aliado.html  admin.html
css/styles.css        estilos compartidos
js/config.js          URL y clave publishable de Supabase (públicas; NUNCA la secret)
js/tp-client.js       cliente de Supabase Auth/REST/Storage sin dependencias (Etapas 3 y 4)
js/tp-ui.js           ayudas de formularios, fechas en español y construcción segura de elementos
js/media.js           reduce y recodifica imágenes a JPEG (quita EXIF/GPS) antes de subirlas
js/qr.js              generador de códigos QR propio (sin servicios externos)
js/tp-pets.js         ayudas compartidas de mascotas, fotos firmadas y planes
js/tp-biz.js          ayudas del directorio: categorías, enlaces de Google Maps/teléfono/WhatsApp, horarios
js/guard.js           protección de páginas privadas por rol
js/layout.js          cabecera (según sesión), pie y avisos compartidos
js/pages/             lógica de cada página: registro, login, recuperar, nueva-contraseña, perfil,
                      mascota, carnet, placa (en carnet.html), qr-publico, directorio y panel-aliado
                      (panel-aliado.js + un módulo por sección: panel-datos, -fotos, -horarios, -promos, -stats)
js/plans.js           planes y selector mensual/anual
_headers              cabeceras HTTP y CSP (Cloudflare Pages)
.env.example          solo para claves secretas futuras (Edge Functions)
GUIA_ETAPA_3.md       pasos manuales de la Etapa 3 y lista de pruebas en tu sitio
GUIA_ETAPA_4.md       pasos manuales de la Etapa 4 y lista de pruebas en tu sitio
GUIA_ETAPA_5.md       pasos manuales de la Etapa 5 (aprobar aliados, asignar planes) y lista de pruebas
database/             Etapa 2: SQL de la base de datos (ver abajo)
pruebas-web/          pruebas de navegador con simuladores de Supabase (solo desarrollo):
                      probar_acceso.py (Etapa 3), probar_mascotas.py y probar_qr.py (Etapa 4),
                      probar_aliados.py (Etapa 5); simuladores mock_supabase.py, mock_etapa4.py y mock_etapa5.py
```

### Carpeta `database/`

| Archivo | Para qué sirve |
|---|---|
| `GUIA_INSTALACION.md` | **Empieza aquí.** Pasos exactos para instalarlo en tu Supabase |
| `00_instalar_todo.sql` | Todo junto (01 a 05) para pegarlo de una vez. Se puede ejecutar varias veces |
| `01_esquema.sql` … `05_datos_base.sql` | Las partes: tablas · funciones · permisos (RLS) · archivos · planes |
| `06_datos_demo.sql` | Opcional: 6 aliados ficticios y 8 guías generales de ejemplo |
| `verificar_seguridad.sql` | Solo lectura: confirma que tu Supabase quedó seguro (34 comprobaciones) |
| `construir_instalador.sh` | Regenera `00_instalar_todo.sql` si editas 01–05 |
| `pruebas/` | Batería de pruebas y simulador de Supabase (solo para desarrollo local) |

Todas las rutas son relativas.

## Probar en tu computadora

Desde la Etapa 3 hay que servir la carpeta (con doble clic en el archivo no funcionan las sesiones): `python3 -m http.server 8000` y entra a `http://localhost:8000`. Para que los correos de confirmación regresen ahí, añade `http://localhost:8000/**` en *Authentication → URL Configuration → Redirect URLs* (Paso 2 de `GUIA_ETAPA_3.md`).

**Pruebas automáticas (opcional, para quien edite el código):** `pip install playwright && playwright install chromium`, luego `pip install pillow numpy opencv-python-headless`, luego `python3 pruebas-web/probar_acceso.py` (Etapa 3), `python3 pruebas-web/probar_mascotas.py` y `python3 pruebas-web/probar_qr.py` (Etapa 4), `python3 pruebas-web/probar_aliados.py` (Etapa 5) y `bash database/pruebas/ejecutar_pruebas.sh` (SQL, requiere PostgreSQL).

## Publicar esta etapa (opcional, gratis)

1. **GitHub:** crea una cuenta en <https://github.com/signup>, pulsa **New** para crear un repositorio (por ejemplo `tecnopatitas`), pulsa **uploading an existing file**, sube **el contenido** de esta carpeta (no la carpeta en sí) y confirma con **Commit changes**.
2. **Cloudflare:** entra a <https://dash.cloudflare.com>, crea una cuenta gratuita y abre **Workers & Pages → Create → Pages → Connect to Git**. Elige tu repositorio.
3. En la configuración de compilación deja **Build command** vacío y escribe `/` en **Build output directory**. Pulsa **Save and Deploy**.
4. Cuando termine, Cloudflare te dará una URL `https://tu-proyecto.pages.dev`.

Los nombres de los menús de Cloudflare cambian con frecuencia; si algo no coincide, dime qué ves y lo ajustamos. No actives ningún plan de pago: no hace falta ninguno.

## Límites gratuitos verificados (4 de noviembre de 2026)

| Servicio | Límites del plan gratuito relevantes |
|---|---|
| **Supabase** | 2 proyectos activos; 500 MB de base de datos; 1 GB de archivos; 5 GB de transferencia al mes; 50,000 usuarios activos al mes; unos 200 usuarios conectados a Realtime a la vez; 500,000 invocaciones de funciones al mes. **El proyecto se pausa tras 7 días sin actividad** y hay que reactivarlo a mano desde el panel (los datos se conservan). |
| **Resend** | 3,000 correos al mes y **100 al día**; 1 dominio. Los correos recibidos también cuentan. Si se supera, el envío se pausa; no hay cobro automático. |
| **Cloudflare Pages** | 500 compilaciones al mes, 1 a la vez; 20,000 archivos por sitio; 25 MiB por archivo. |

Consecuencias para el diseño:

- **Pausa de Supabase:** para una demostración escolar es aceptable. Si el sitio se usa con personas reales, habrá que mantenerlo activo o aceptar que a veces se pause. Lo documentaremos en la Etapa 11.
- **Correos:** con 100 al día, los recordatorios por correo se enviarán en lotes y con tope diario. Si se alcanza, se registrará como «no enviado» y nunca se mostrará como enviado.
- **Fotos de denuncias:** 1 GB se agota rápido; se limitarán a 3 archivos de 5 MB por reporte.
- Los límites cambian con el tiempo. Se vuelven a comprobar antes de cada integración.

## Decisiones de la Etapa 2 que conviene confirmar

1. **Mascotas y carnet:** registrar la ficha de una mascota es gratis (máx. 30 por cuenta); el **carnet de salud** depende del plan (Básica: no · Pro: 2 mascotas · VIP: ilimitado).
2. **Placa QR:** solo se puede *crear* con Huellita VIP. Si el plan vence, la placa ya creada se conserva (para no dejar a una mascota extraviada sin su QR) pero no se pueden crear nuevas.
3. **Planes de pago:** un usuario **no puede activarse un plan** desde el navegador; lo asigna un administrador. Así no hay forma de «regalarse» beneficios. Cancelar es inmediato.
4. **Directorio público:** cualquiera ve los aliados *aprobados*. Sin plan de aliado solo se muestra nombre, categoría, descripción y dirección; la **ficha completa** (teléfono, horario, logotipo, fotos y promociones) llega con Plata u Oro, y el **WhatsApp** y el lugar prioritario solo con Oro. Nunca se muestra quién es el dueño. Si un plan vence, los datos se conservan pero dejan de mostrarse.
5. **Privacidad del administrador:** un admin gestiona usuarios, aliados, denuncias, guías y chat, pero **no puede leer las mascotas ni el carnet** de otras personas.
6. **Límite anti-abuso por IP:** las denuncias se limitan por visitante usando un código derivado de la IP (no se guarda la IP). Detrás de redes compartidas puede ser impreciso; en la Etapa 6 se añadirá Cloudflare Turnstile (gratuito).
7. **Fotos de denuncias:** se suben mediante una función segura en la Etapa 6 (no hay subida directa desde el navegador).
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

## Siguiente: Etapa 6 (denuncias anónimas)

Conectar `denuncias.html`: reporte **sin ningún dato que identifique a quien denuncia**, código de seguimiento, evidencias (fotos) mediante una función segura, anti-robots con Cloudflare Turnstile (gratuito) y límite de envíos. La plataforma **registra** las denuncias; no las presenta ante ninguna autoridad. Antes, completa y prueba la Etapa 5 con `GUIA_ETAPA_5.md`.
