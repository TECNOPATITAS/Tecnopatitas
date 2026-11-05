# Correos de cuenta con Gmail (confirmar cuenta y recuperar contraseña)

Decisión tomada: **Gmail será el servicio de correo con el que las personas crean y recuperan su cuenta.** Sin dominio propio y sin gastar dinero.

**Qué cubre esta guía:** únicamente los correos que envía **Supabase Auth**: *confirmar cuenta* y *recuperar contraseña*.
**Qué NO cubre:** los avisos de la plataforma (vacunas, citas, suscripción…) **siguen viviendo solo dentro del sitio** (campanita y Notificaciones). Todavía no se envía ningún otro correo, y el interruptor de «recordatorios por correo» sigue bloqueado.

Tiempo estimado: 15 minutos. **No hace falta tocar el código ni volver a subir nada a GitHub** (solo ajustes en Google y en el panel de Supabase).

---

## 1. Lo que tienes que saber antes (límites reales)

| Tema | Qué pasa | Fuente |
|---|---|---|
| Correo de cortesía de Supabase (el que usas hoy) | Solo escribe a los correos de **tu equipo** de Supabase y máximo **2 por hora**. Por eso hoy nadie más puede registrarse. | Documentación de Supabase |
| Con SMTP propio (Gmail) | Ese límite desaparece. Supabase pone por defecto **30 correos por hora** (se cambia en *Authentication → Rate Limits*). | Documentación de Supabase |
| Una misma persona | No puede pedir otro correo antes de **60 segundos** (registro, recuperar contraseña). Es normal que, si toca el botón dos veces, vea un aviso de espera. | Documentación de Supabase |
| Gmail personal | Más de **500 correos al día** hace que Google bloquee el envío entre 1 y 24 horas. Con 30 por hora de tope de Supabase, un uso normal no se acerca. | Ayuda oficial de Google |
| Contraseña normal de Gmail | **Ya no sirve** para SMTP: hay que usar una *contraseña de aplicación* (16 letras). | Google |
| Spam | Los correos de una cuenta nueva de Gmail sin historial pueden caer en *Spam* las primeras veces. Es el punto débil de no tener dominio. | Experiencia general; compruébalo tú en las pruebas |

> Si algo de esto cambió en Google o Supabase, manda lo que digan sus páginas oficiales. Yo no puedo probar ni Gmail ni tu Supabase desde mi entorno: esta guía y las plantillas están revisadas, pero **la prueba real es la lista del punto 7**.

## 2. ¿Qué cuenta de Gmail usar?

**Recomendado: una cuenta nueva solo para el proyecto** (por ejemplo `tecnopatitas.app@gmail.com`).

- Los correos saldrán **desde esa cuenta**; las personas verán su dirección y el nombre «TECNOPATITAS».
- Si Google limita o suspende el envío por volumen o quejas, **no afecta tu cuenta de siempre**.
- Si prefieres usar tu cuenta personal, funciona igual, pero todos los correos del sitio saldrán de tu dirección personal y, si Google la limita, también afectaría tu correo normal.

## 3. Crear la «contraseña de aplicación» en Google

1. Entra a la cuenta de Gmail del proyecto → <https://myaccount.google.com/security>.
2. Activa la **Verificación en dos pasos** (si no, Google no deja crear contraseñas de aplicación).
3. Abre <https://myaccount.google.com/apppasswords> (o busca *«Contraseñas de aplicaciones»* en la barra de esa página).
4. Ponle un nombre, por ejemplo `supabase`, y pulsa **Crear**.
5. Google muestra **16 letras** (a veces con espacios). **Cópialas ahora: no se vuelven a mostrar.**

Si la opción no aparece: la cuenta tiene activada la *Protección avanzada*, o la verificación en dos pasos usa solo llaves de seguridad, o es una cuenta de trabajo/escuela cuyo administrador la desactivó. Una cuenta de Gmail normal con verificación en dos pasos por teléfono funciona.

> **Seguridad.** Esas 16 letras son un secreto: dan acceso para enviar correos como tu cuenta. Se escriben **solo en el panel de Supabase**. **No me las pegues aquí, no las subas a GitHub, no las pongas en ningún archivo del proyecto.** Si se filtran: bórralas en la misma página de Google y crea otras.

## 4. Conectar Gmail en Supabase

1. Panel de Supabase → tu proyecto → **Authentication → Emails → SMTP Settings**.
2. Activa **Enable custom SMTP** y llena:

| Campo | Valor |
|---|---|
| Sender email | la Gmail del proyecto (**exactamente la misma** que usarás como usuario; Gmail cambia el remitente por el de la cuenta si es otro) |
| Sender name | `TECNOPATITAS` |
| Host | `smtp.gmail.com` |
| Port number | `465` (si falla, prueba `587`) |
| Username | la Gmail del proyecto (completa, con `@gmail.com`) |
| Password | las 16 letras **sin espacios** |

3. **Save changes**. Si Supabase te avisa de algo, léelo antes de continuar.
4. Entra a **Authentication → Rate Limits** y comprueba el límite de correos por hora (30 por defecto). Déjalo así; sirve para empezar y protege tu cuota diaria de Gmail.

## 5. Revisar las direcciones del sitio (probablemente ya lo hiciste)

**Authentication → URL Configuration** (Paso 2 de `GUIA_ETAPA_3.md`):
- **Site URL:** `https://tecnopatitas.pages.dev`
- **Redirect URLs:** `https://tecnopatitas.pages.dev/**`

Si falta, los botones de los correos llevarán a un sitio equivocado o serán rechazados.

## 6. Correos en español con la identidad del sitio

Supabase los manda en inglés. En `supabase/plantillas-correo/` hay dos plantillas ya hechas (paleta del proyecto, sin imágenes ni rastreadores, se ven bien en teléfono):

| Plantilla de Supabase | Archivo | Asunto (Subject) |
|---|---|---|
| **Confirm sign up** | `confirmar-registro.html` | `Confirma tu cuenta en TECNOPATITAS` |
| **Reset password** | `recuperar-contrasena.html` | `Restablece tu contraseña de TECNOPATITAS` |

Para cada una: **Authentication → Emails → Templates →** elige la plantilla → pega el asunto en **Subject** → abre el archivo `.html` con el Bloc de notas, copia **todo** y pégalo en el cuadro del mensaje (*Message body*, vista de código/fuente) → **Save**.

- **No cambies** `{{ .ConfirmationURL }}` (es el enlace que genera Supabase).
- Las demás plantillas (*Invite user*, *Magic link*, *Change email*, *Reauthentication*) no las usa el sitio todavía; pueden quedarse como están.
- Vista previa: Supabase muestra una; si se ve rara, vuelve a pegar el archivo completo.

## 7. Pruebas en el sitio real (hazlas con un correo que NO sea del equipo)

Usa una ventana de incógnito y un correo de otra persona o de otro servicio (Hotmail, Outlook, Yahoo…). Revisa también **Spam**.

| # | Haz esto | Debe pasar |
|---|---|---|
| 1 | En `registro.html` crea una cuenta con un correo ajeno | El sitio dice que revises tu correo (nunca antes de que Supabase confirme el envío) |
| 2 | Abre el correo | Llega en español, remitente «TECNOPATITAS», con botón **Confirmar mi correo**. Si está en *Spam*: márcalo como «No es spam» y anótalo |
| 3 | Toca el botón | Te lleva a `tecnopatitas.pages.dev` y la cuenta queda confirmada |
| 4 | Cierra sesión y entra con ese correo y contraseña | Entra sin errores |
| 5 | En `recuperar.html` pide el cambio de contraseña con ese correo | Llega «Restablece tu contraseña…»; el botón abre `nueva-contrasena.html` |
| 6 | Cambia la contraseña con ese enlace | Puedes entrar con la nueva; el enlace ya no funciona una segunda vez |
| 7 | Pide recuperar contraseña **dos veces seguidas** | La segunda vez avisa que esperes (límite de 60 s); no es un error |
| 8 | Pide recuperar contraseña con un correo que **no** tiene cuenta | El sitio responde igual que si existiera (no revela qué correos existen) y no llega nada |
| 9 | Regístrate con un correo que ya tiene cuenta | El sitio no confirma ni niega que exista |

Dime qué números fallan y con qué mensaje.

## 8. Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El sitio dice que no pudo enviar el correo / Supabase: *Error sending confirmation email* | Usuario o contraseña SMTP mal | Revisa en **Logs → Auth** el detalle. Crea otra contraseña de aplicación y pégala sin espacios |
| Detalle `535 … Username and Password not accepted` | Contraseña de aplicación incorrecta o sin verificación en dos pasos | Mismo paso anterior |
| Detalle `534 … Application-specific password required` | Pusiste la contraseña normal de Gmail | Usa la de aplicación |
| Se queda cargando / tiempo agotado | Puerto bloqueado | Cambia `465` por `587` |
| Detalle `550 5.4.5 Daily user sending quota exceeded` | Gmail alcanzó su tope diario | Espera hasta 24 h; baja el límite por hora en *Rate Limits* si pasa seguido |
| «Se enviaron demasiados correos en poco tiempo» | Límite de 60 s por persona o tope por hora | Espera uno o dos minutos; si sigue, más tarde |
| El correo cae en Spam | Cuenta nueva sin historial | Márcalo como «No es spam» varias veces; con el uso mejora. La solución definitiva sería un dominio propio con SPF/DKIM, que hoy no tenemos |
| La persona no recibe nada y no hay error | Correo mal escrito, filtro o Spam | Revisa **Authentication → Users** (¿quedó registrada sin confirmar?) y **Logs → Auth** |

## 9. Lo que todavía no existe (para que no te sorprenda)

- **No hay botón «Reenviar correo de confirmación».** Si un correo no llega, hoy hay que revisar *Spam*, esperar 60 s y volver a intentar desde el sitio, o ayudar a la persona desde **Authentication → Users**. Puedo añadir el botón en una etapa posterior si lo necesitas.
- Los **avisos de la plataforma por correo** (vacunas, citas, suscripción) no se envían; el tope de Gmail y el de Supabase se tomarán en cuenta cuando se decida hacerlo.
- Gmail no es lo ideal para un negocio con mucho volumen: sirve para arrancar pequeño y gratis. Si el sitio crece, lo recomendable es un dominio propio con un servicio de correo transaccional con plan gratuito.

## 10. Verificación que sí hice desde aquí

`python3 pruebas-web/probar_correos.py` (62 comprobaciones): las plantillas están bien formadas, usan solo la variable `{{ .ConfirmationURL }}`, no cargan nada externo, no llevan imágenes ni scripts, usan solo los colores de la paleta, se ven sin desbordar en pantallas de 360, 390 y 900 px, y el texto cumple el contraste AA.
**No pude** enviar un correo real, ni abrir tu Supabase ni tu Gmail, ni ver cómo las muestra tu aplicación de correo.
