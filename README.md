# TECNOPATITAS · Plataforma web

Plataforma para el cuidado, protección y bienestar de las mascotas. Se construye **por etapas**; este archivo dice qué está terminado y qué no.

## Estado actual: Etapa 3 de 11 (cuentas, sesión y roles)

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Estructura, diseño y navegación | Terminada |
| 2 | Supabase: base de datos, permisos (RLS), almacenamiento y datos iniciales | Terminada e instalada en tu proyecto (verificador: 31/31) |
| **3** | **Registro, inicio de sesión, recuperar contraseña, sesión, roles y protección de páginas** | **Escrita y probada contra un simulador de Supabase (105 pruebas de navegador). Falta que la pruebes en tu sitio real: `GUIA_ETAPA_3.md`** |
| 4–11 | Mascotas, directorio, denuncias, chat, notificaciones, planes, panel admin, publicación | Pendientes |

**Terminado en la Etapa 2** (carpeta `database/`)

- 18 tablas en `public` + 2 internas en `private`, con claves, índices y restricciones (CHECK) que impiden datos incoherentes.
- Seguridad por filas (RLS) en **todas** las tablas; permisos por columna (nadie puede cambiar su rol, su suspensión, su plan o el dueño de una mascota desde el navegador); funciones del servidor para todo lo sensible.
- Los 5 planes (nombres, precios MXN y beneficios exactos) y los permisos de cada plan **aplicados en el servidor**, no solo en pantalla.
- Denuncias anónimas **sin ningún dato que identifique a quien reporta**, con código de seguimiento, trampa anti-robots y límite de envíos.
- Chat, notificaciones, guías, directorio con filtros, placa QR con token aleatorio, bitácora de acciones de administración.
- 5 buckets de archivos (solo JPG/PNG/WebP, con tope de tamaño y de cantidad por persona).
- Datos de demostración **opcionales y claramente falsos** (`06_datos_demo.sql`).
- 319 pruebas automáticas de seguridad y funcionamiento (`database/pruebas/`) y un verificador de solo lectura para tu Supabase (`database/verificar_seguridad.sql`).

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
- 105 pruebas automáticas de navegador (`pruebas-web/`).

**Cómo se probó la Etapa 3, con honestidad**

Desde mi entorno no hay acceso a tu Supabase (y no debe haberlo), así que las pruebas corrieron en Chromium contra un **simulador** de Supabase que escribí según la documentación oficial de GoTrue y PostgREST. Si el servicio real responde distinto en algún detalle, solo lo sabremos al probar en tu sitio: por eso `GUIA_ETAPA_3.md` trae una lista de 15 comprobaciones. Se comprobó también que las pruebas detectan sabotajes (por ejemplo, quitar la regla que oculta las páginas privadas o el aviso entre pestañas).

**Límite importante del plan gratuito de Supabase:** su servicio de correo de cortesía solo envía a los correos de tu equipo y a un máximo de 2 por hora. Para que cualquier persona pueda registrarse hará falta un SMTP propio (normalmente con dominio). Detalle y opciones en el Paso 4 de `GUIA_ETAPA_3.md`.

**No terminado (y no finge estarlo)**

- **Solo cuentas y perfil están conectados a la base de datos.** El resto de formularios (mascotas, carnet, directorio, denuncias, chat…) siguen mostrando «se conecta en la Etapa N» y no guardan nada. No publiques datos reales todavía.
- **Cobros y contratación no están habilitados.** No se guarda ninguna tarjeta ni dato financiero. Un administrador asigna los planes de pago manualmente (en la Etapa 9 se añade la «solicitud» de plan por parte del usuario). Los recordatorios por WhatsApp o correo están *previstos*, no activos.
- **Faltan** subir foto de perfil (Etapa 4), eliminar la cuenta, el **aviso de privacidad y términos**, y el anti-robots en el registro (Turnstile, Etapa 6). Las protecciones de página del navegador son comodidad: la seguridad real está en las políticas RLS.
- Las denuncias se **registran en la plataforma**; la plataforma no las presenta ante ninguna autoridad.
- Las guías y los aliados de la demostración son **contenido de ejemplo**. Las guías están marcadas «pendiente de revisión veterinaria» y deben revisarse antes de presentarlas como definitivas.

## Estructura

```
index.html  registro.html  login.html  recuperar.html  nueva-contrasena.html
guias.html  directorio.html  denuncias.html  planes.html  sobre-nosotros.html
perfil.html  mascota.html  carnet.html  notificaciones.html  chat.html
panel-aliado.html  admin.html
css/styles.css        estilos compartidos
js/config.js          URL y clave publishable de Supabase (públicas; NUNCA la secret)
js/tp-client.js       cliente de Supabase Auth/REST sin dependencias (Etapa 3)
js/tp-ui.js           ayudas de formularios (mensajes, botones ocupados)
js/guard.js           protección de páginas privadas por rol
js/layout.js          cabecera (según sesión), pie y avisos compartidos
js/pages/             lógica de registro, login, recuperar, nueva-contraseña y perfil
js/plans.js           planes y selector mensual/anual
_headers              cabeceras HTTP y CSP (Cloudflare Pages)
.env.example          solo para claves secretas futuras (Edge Functions)
GUIA_ETAPA_3.md       pasos manuales de la Etapa 3 y lista de pruebas en tu sitio
database/             Etapa 2: SQL de la base de datos (ver abajo)
pruebas-web/          Etapa 3: pruebas de navegador con simulador de Supabase (solo desarrollo)
```

### Carpeta `database/`

| Archivo | Para qué sirve |
|---|---|
| `GUIA_INSTALACION.md` | **Empieza aquí.** Pasos exactos para instalarlo en tu Supabase |
| `00_instalar_todo.sql` | Todo junto (01 a 05) para pegarlo de una vez. Se puede ejecutar varias veces |
| `01_esquema.sql` … `05_datos_base.sql` | Las partes: tablas · funciones · permisos (RLS) · archivos · planes |
| `06_datos_demo.sql` | Opcional: 6 aliados ficticios y 8 guías generales de ejemplo |
| `verificar_seguridad.sql` | Solo lectura: confirma que tu Supabase quedó seguro (31 comprobaciones) |
| `construir_instalador.sh` | Regenera `00_instalar_todo.sql` si editas 01–05 |
| `pruebas/` | Batería de pruebas y simulador de Supabase (solo para desarrollo local) |

Todas las rutas son relativas.

## Probar en tu computadora

Desde la Etapa 3 hay que servir la carpeta (con doble clic en el archivo no funcionan las sesiones): `python3 -m http.server 8000` y entra a `http://localhost:8000`. Para que los correos de confirmación regresen ahí, añade `http://localhost:8000/**` en *Authentication → URL Configuration → Redirect URLs* (Paso 2 de `GUIA_ETAPA_3.md`).

**Pruebas automáticas (opcional, para quien edite el código):** `pip install playwright && playwright install chromium`, luego `python3 pruebas-web/probar_acceso.py` (Etapa 3) y `bash database/pruebas/ejecutar_pruebas.sh` (Etapa 2, requiere PostgreSQL).

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

## Siguiente: Etapa 4 (mascotas, carnet, QR y fotos)

Conectar `mascota.html`, `carnet.html` y la foto de perfil: fichas de mascotas (máx. 30 por cuenta), carnet de salud según plan, subida de fotos a Supabase Storage (JPG/PNG/WebP con los topes de la Etapa 2) y placa QR con token aleatorio para Huellita VIP. Antes, completa y prueba la Etapa 3 con `GUIA_ETAPA_3.md`.
