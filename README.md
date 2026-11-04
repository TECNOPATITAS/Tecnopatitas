# TECNOPATITAS · Plataforma web

Plataforma para el cuidado, protección y bienestar de las mascotas. Se construye **por etapas**; este archivo dice qué está terminado y qué no.

## Estado actual: Etapa 1 de 11 (estructura, diseño y navegación)

**Terminado**

- 15 páginas diferenciadas con cabecera, navegación y pie compartidos: Inicio, Registro, Inicio de sesión, Recuperar contraseña, Guías, Directorio, Mis mascotas, Carnet digital, Denuncias, Suscripciones, Perfil, Notificaciones, Chat, Panel de aliados y Panel administrativo. «Sobre nosotros» queda deliberadamente sin contenido institucional.
- Los cinco planes con sus precios y beneficios exactos. Los ahorros anuales se calculan: Pro $58, VIP $118, Plata $298 y Oro $598 MXN.
- Diseño responsive con la identidad original (verde petróleo, menta, crema, coral), foco visible por teclado y respeto de «reducir movimiento».
- Estructura de carpetas, `.gitignore`, `.env.example` y `_headers` (cabeceras de seguridad básicas para Cloudflare Pages).

**No terminado (y no finge estarlo)**

- **No hay base de datos, cuentas, cobros ni almacenamiento.** Ningún formulario guarda o envía datos: al enviarlos aparece un aviso que dice en qué etapa se activa.
- Las páginas de perfil, mascotas, carnet, notificaciones, chat, panel de aliados y panel administrativo **no están protegidas todavía** y no contienen datos reales. La protección real (roles verificados en el servidor y RLS) llega en las Etapas 2, 3 y 10. Hasta entonces no publiques datos reales ni enlaces a esas páginas como si fueran privadas.
- Guías y directorio muestran estados vacíos. No hay guías ni aliados de ejemplo.

## Estructura

```
index.html  registro.html  login.html  recuperar.html
guias.html  directorio.html  denuncias.html  planes.html  sobre-nosotros.html
perfil.html  mascota.html  carnet.html  notificaciones.html  chat.html
panel-aliado.html  admin.html
css/styles.css        estilos compartidos
js/layout.js          cabecera, pie y avisos compartidos
js/plans.js           planes y selector mensual/anual
_headers              cabeceras HTTP (Cloudflare Pages)
.env.example          variables previstas (sin valores)
```

Todas las rutas son relativas.

## Probar en tu computadora

Abre `index.html` con doble clic, o sirve la carpeta con `python3 -m http.server` y entra a `http://localhost:8000`.

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

## Siguiente: Etapa 2 (Supabase, base de datos y seguridad)

Voy a escribir el SQL completo (tablas, claves, índices, restricciones, RLS, roles seguros y datos iniciales). Para probarlo contra una base real vas a necesitar un proyecto de Supabase; te daré los pasos exactos cuando lleguemos, y nunca necesitaré que me pegues claves secretas.
