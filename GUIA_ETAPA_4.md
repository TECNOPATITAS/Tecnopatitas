# Etapa 4 · Mascotas, carnet, fotos y placa QR: lo que tienes que hacer tú

Esta etapa conecta tres páginas con Supabase: **Mis mascotas** (`mascota.html`), **Carnet de salud + placa QR** (`carnet.html`) y la **foto de perfil** (`perfil.html`), además de la página pública que se abre al escanear una placa (`qr.html`).

> Los menús de Supabase cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura.

Tiempo estimado: 30–40 minutos. Hazlo en este orden.

**Reglas que siguen vigentes:** no actives ningún plan de pago ni prueba gratuita. No pegues en ningún archivo, ni me envíes, la clave `secret`/`service_role`, la contraseña de la base de datos ni la contraseña de aplicación de Gmail. En esta etapa **no hace falta ninguna clave nueva**.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 4 añadió al SQL: la columna de la foto de la placa, el sexto bucket (`qr-photos`), sus reglas y la regla de que solo Huellita VIP puede crear placas. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (usa `drop policy if exists`); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 32 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela (no contiene claves ni datos de usuarios).

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio de GitHub: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Se reemplazan los archivos con el mismo nombre y se añaden los nuevos (`qr.html`, `js/media.js`, `js/qr.js`, `js/tp-pets.js`, `js/pages/mascota.js`, `carnet.js`, `placa.js`, `qr-publico.js`…).
2. Cloudflare Pages publica solo (1–2 minutos).
3. Abre `https://tecnopatitas.pages.dev/` con la consola abierta (**F12 → Console**). **No debe haber errores rojos.** Si ves uno que diga *Content Security Policy* o *Refused to …*, cópialo y envíamelo.

> Si usas el navegador en modo normal y ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular, cierra y abre la pestaña).

## Paso 3 · Preparar cuentas de prueba

Necesitas **dos cuentas** para comprobar que una persona no ve lo de la otra.

- **Cuenta 1:** la que ya usas (o crea una).
- **Cuenta 2:** como el servicio de correo gratuito de Supabase solo envía a 2 correos por hora y solo a tu equipo, créala desde el panel: **Authentication → Users → Add user → Create new user**, escribe un correo (puede ser uno tuyo distinto) y una contraseña larga, y marca **Auto Confirm User**. Ya puedes iniciar sesión con ella en el sitio.

### Dar Huellita Pro / VIP a una cuenta de prueba

Los planes de pago **no se contratan todavía** (la contratación y los cobros no están habilitados): un administrador los asigna a mano. Para probar el carnet y la placa asigna el plan desde **SQL Editor** (cambia el correo por el de tu cuenta de pruebas):

```sql
-- Huellita VIP (carnet para todas las mascotas + placa QR). Se puede repetir sin error.
update public.subscriptions set status = 'replaced'
 where status = 'active' and user_id = (select id from auth.users where email = 'TU_CORREO@ejemplo.com');
insert into public.subscriptions (user_id, plan_id, billing_period, note)
select id, 'vip', 'monthly', 'Prueba de la Etapa 4' from auth.users where email = 'TU_CORREO@ejemplo.com';
```

Para probar **Huellita Pro** cambia `'vip'` por `'pro'`; para volver a **Básica**, cambia por `'basica'`. Esto es solo para pruebas; no es un cobro ni una compra.

## Paso 4 · Prueba en el sitio real (checklist)

Marca cada punto. Si algo falla, anota **el número**, lo que viste en pantalla y, si puedes, el mensaje rojo de la consola (**F12 → Console**) y de **F12 → Network** (la petición que salga en rojo; pulsa sobre ella y copia *Status* y *Response*).

Usa una foto real del celular (suelen pesar 3–8 MB) para ver que se reduce.

**A. Mis mascotas** (`mascota.html`, con la cuenta 1)

1. Sin mascotas aparece el aviso vacío y el contador dice «0 de 30».
2. Intenta guardar sin nombre, o con peso 0 o fecha de nacimiento futura: el formulario lo explica y no guarda.
3. Crea una mascota **sin foto**: aparece con un icono de su especie, con su edad calculada.
4. Crea otra **con foto**: aparece la foto. En Supabase → **Storage → pet-photos** debe haber una carpeta (tu identificador) con un archivo `.jpg` **mucho más ligero que tu original** (normalmente entre 100 y 600 KB aunque tu foto pesara varios MB). Si ves que mide varios MB, avísame.
5. Edita una mascota y **reemplaza la foto**: la nueva se ve y el archivo viejo desaparece de Storage (queda uno solo).
6. Edita y marca **quitar foto**: vuelve el icono y el archivo se borra.
7. Escribe en la descripción `<b>hola</b>`: se muestra tal cual, como texto (no en negritas).
8. Elimina una mascota: pide confirmación, avisa que se borra también su carnet y su placa, y al confirmar desaparece.

**B. Foto de perfil** (`perfil.html`)

9. Sube una foto: aparece y en **Storage → avatars** hay un `.jpg`. Cámbiala (el anterior se borra) y quítala.
10. Intenta subir un PDF o un archivo de texto: se rechaza con un mensaje claro.

**C. Carnet con plan Básica** (`carnet.html`)

11. Aparece el aviso de que tu plan no incluye el carnet y **no** hay botones para agregar registros. La sección de placa QR dice que es de Huellita VIP.

**D. Carnet con Pro o VIP** (asigna el plan con el SQL del Paso 3 y vuelve a entrar)

12. Agrega una **vacuna** con fecha de aplicación y próxima fecha. Se ve con fechas en español. Si pones una próxima fecha ya pasada, aparece **«Vencida»**.
13. Agrega una **desparasitación** y una **cita** (por ejemplo, mañana a las 10:30). La cita debe mostrarse **a las 10:30** y, al editarla, el campo debe volver a decir 10:30.
14. Edita y elimina un registro (el borrado pide confirmación).
15. Con **Pro**: crea 3 mascotas, agrega un registro de carnet a las dos primeras y prueba con la tercera: debe decir que tu plan permite carnet para 2 mascotas. Con **VIP** no hay límite.

**E. Placa QR** (con **VIP**)

16. Pulsa **Crear placa QR**: aparece el código y debajo el enlace (`https://tecnopatitas.pages.dev/qr.html?t=…`, con 64 letras y números). Escribe un mensaje, un nombre de contacto, un teléfono y activa «mostrar el teléfono públicamente». **Guardar placa.**
17. **Descarga el PNG** y también el SVG. Se abren como imágenes.
18. **Escanea el QR con tu celular** (apunta la cámara a la pantalla o al PNG impreso). Debe abrir la página pública de tu mascota. Hazlo mejor **con los datos móviles, sin iniciar sesión**.
19. La página pública muestra **solo** lo que activaste: nombre, especie, raza, mensaje, el teléfono (con botón «Llamar») y nada más: ni tu correo, ni tu dirección, ni tu nombre de cuenta.
20. Vuelve a la placa y **apaga «mostrar el nombre»**: la página pública pasa a decir solo «Mascota». Después **desmarca «Placa activa»** y guarda: el enlace debe mostrar «Enlace no disponible». Vuélvela a activar.
21. Sube una **foto para la placa** y marca «mostrar la foto pública»: la página pública la muestra. La pantalla te advierte que esa foto **es pública**. En **Storage → qr-photos** hay un archivo pequeño (normalmente menos de 300 KB).
22. **Generar enlace nuevo**: pide confirmación y avisa que los QR impresos dejarán de funcionar. Tras confirmar, el enlace anterior muestra «Enlace no disponible» y el nuevo sí funciona.
23. Abre `https://tecnopatitas.pages.dev/qr.html?t=cualquiercosa`: «Enlace no disponible».

**F. Privacidad entre cuentas** (cuenta 2, en otra ventana privada)

24. La cuenta 2 **no ve** ninguna mascota de la cuenta 1 en `mascota.html`.
25. Entra a `carnet.html?pet=<identificador de una mascota de la cuenta 1>` (lo ves en la dirección cuando la cuenta 1 abre su carnet). La cuenta 2 debe ver **su propia** lista, nunca la de la cuenta 1.
26. Con la cuenta 2 en plan Básica, no puede crear placas ni subir fotos de placa.

**G. Consola**

27. Durante todas las pruebas, **F12 → Console** no debe mostrar errores rojos de *Content Security Policy*.

### Si algo falla: causas probables

| Síntoma | Qué revisar |
|---|---|
| «No se pudo subir la imagen» en todas las fotos | Que el Paso 1 terminó sin errores y el verificador dice 32. En **Storage** deben existir los 6 buckets. |
| La mascota se guarda pero la foto no se ve | Anota el *Status* y *Response* de la petición en rojo en **F12 → Network** (será la que contenga `/storage/v1/`). |
| «Tu plan no incluye…» aunque asignaste el plan | Cierra sesión y vuelve a entrar; revisa que el correo del SQL sea exactamente el de la cuenta. |
| El QR abre «Enlace no disponible» | Confirma que la placa está activa y que escaneaste el QR **actual** (si regeneraste el enlace, el QR impreso anterior ya no sirve). |
| El QR no abre nada en el celular | Prueba con otra app de cámara/lector; sube el brillo de la pantalla; descarga el PNG y ábrelo grande. |

---

## Qué hace y qué no hace esta etapa

**Sí hace**

- Fichas de mascotas (máx. 30 por cuenta) con foto privada; carnet de vacunas, desparasitaciones y citas; foto de perfil; placa QR con página pública controlada por el dueño.
- Las imágenes se reducen y se recodifican en tu navegador (se elimina la ubicación GPS y los datos de la cámara) antes de salir de tu dispositivo.
- Los permisos (quién ve qué, límites del plan, quién puede subir qué) los aplica **Supabase**, no la pantalla.

**No hace todavía**

- **Recordatorios** de vacunas o citas por correo o WhatsApp: están previstos para una etapa posterior. Hoy el carnet solo marca «vencida» o «próxima» cuando lo abres.
- **Contratar o pagar** un plan: no está habilitado y no se guarda ningún dato financiero.
- **Limpieza automática de archivos huérfanos:** al reemplazar o quitar una foto o eliminar una mascota el navegador borra los archivos viejos, pero si se pierde la conexión justo entonces puede quedar alguno (nadie lo ve; ocupa espacio dentro de los topes por persona).
- **Imprimir la placa física:** el QR se puede descargar para imprimirlo tú; el sitio no vende ni fabrica placas.

## Decisiones que conviene que confirmes

1. **La foto de la placa QR es pública** y vive en un bucket aparte; la foto de la ficha de la mascota sigue privada.
2. **Por omisión la placa solo muestra el nombre y la raza**; teléfono y foto están apagados hasta que tú los actives.
3. **Una placa creada sobrevive si vence tu plan** (para no dejar a una mascota extraviada sin su QR), pero sin VIP no se crean placas nuevas ni se suben fotos nuevas para ella.
4. **El QR contiene la dirección del sitio** (`…pages.dev`). Si algún día usas otra dirección, hay que descargar e imprimir los QR de nuevo.
5. **El carnet usa hora de Ciudad de México.**

## Etapa 5 (siguiente): directorio y panel de aliados

Conectar `directorio.html` y `panel-aliado.html`: alta del negocio (queda pendiente de aprobación), logotipo y fotos, ficha según el plan del aliado (Plata/Oro) y enlaces directos a Google Maps, sin API de pago. Para empezar necesitaré que termines este checklist y me avises qué número falló, si alguno.
