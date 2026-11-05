# Etapa 5 · Directorio público y panel de aliados: lo que tienes que hacer tú

Esta etapa conecta dos páginas con Supabase: el **Directorio** (`directorio.html`, lo ve cualquiera, sin iniciar sesión) y el **Panel de aliados** (`panel-aliado.html`, solo cuentas de aliado comercial).

> Los menús de Supabase cambian de nombre con frecuencia. Si algo no coincide con lo que ves, busca el texto entre comillas con el buscador del panel, o mándame una captura.

Tiempo estimado: 40–50 minutos. Hazlo en este orden.

**Reglas que siguen vigentes:** no actives ningún plan de pago ni prueba gratuita. No pegues en ningún archivo, ni me envíes, la clave `secret`/`service_role`, la contraseña de la base de datos ni la contraseña de aplicación de Gmail. En esta etapa **no hace falta ninguna clave nueva**. **La contratación y los cobros no están habilitados**: los planes de aliado (Plata y Oro) los asigna un administrador con SQL, solo para probar.

---

## Paso 1 · Actualizar la base de datos (obligatorio, 2 minutos)

La Etapa 5 añadió al SQL: la tabla de contadores de visitas, la función que los suma, más validaciones (rutas de imágenes y horarios) y el cambio para que la etiqueta «Aliado verificado» dependa del plan. **Es seguro repetir el instalador:** no borra datos.

1. Supabase → tu proyecto → **SQL Editor → New query**.
2. Abre `database/00_instalar_todo.sql` (de esta carpeta), copia **todo**, pégalo y pulsa **Run**. Si avisa de «operaciones destructivas» es normal (usa `drop policy if exists`); confirma con **Run this query**.
3. Debe terminar con una fila que dice **«Instalación terminada sin errores…»**.
4. **New query** → pega todo `database/verificar_seguridad.sql` → **Run**. La primera fila debe decir:

   **`TODO CORRECTO: 34 comprobaciones superadas`**

   Si dice otra cosa o aparece alguna fila **REVISAR**, copia la tabla completa y envíamela (no contiene claves ni datos de usuarios).
5. En **Table Editor** deben verse **19 tablas**; la nueva es `business_daily_stats`.

## Paso 2 · Subir los archivos a GitHub

1. En tu repositorio de GitHub: **Add file → Upload files**, arrastra **el contenido** de esta carpeta (no la carpeta en sí) y **Commit changes**. Se reemplazan los archivos con el mismo nombre y se añaden los nuevos: `js/tp-biz.js`, `js/pages/directorio.js` y `js/pages/panel-aliado.js`, `panel-datos.js`, `panel-fotos.js`, `panel-horarios.js`, `panel-promos.js`, `panel-stats.js`, `GUIA_ETAPA_5.md` y `pruebas-web/mock_etapa5.py`, `probar_aliados.py`. Se reemplazan, entre otros, `directorio.html`, `panel-aliado.html`, `css/styles.css`, `js/tp-client.js`, `js/tp-ui.js` y `README.md`.
2. Cloudflare Pages publica solo (1–2 minutos).
3. Abre `https://tecnopatitas.pages.dev/directorio.html` con la consola abierta (**F12 → Console**). **No debe haber errores rojos.** Si ves uno que diga *Content Security Policy* o *Refused to …*, cópialo y envíamelo.

> Si ves la versión vieja de una página, recarga forzando (**Ctrl+Shift+R**, o en el celular, cierra y abre la pestaña).

## Paso 3 · Preparar las cuentas de prueba

Necesitas una **cuenta de aliado** y, para comprobar la privacidad, **una segunda cuenta** (de aliado o de dueño de mascota).

**Cuenta de aliado.** Elige una de estas dos formas:

- **A. Registrarla en el sitio:** `registro.html` → tipo de cuenta **Aliado comercial**. Recuerda que el correo gratuito de Supabase solo envía a 2 correos por hora y solo a tu equipo.
- **B. Convertir una cuenta de prueba que ya tengas** (la más rápida; no uses una cuenta con mascotas reales, porque una cuenta de aliado no entra a «Mis mascotas»). En **SQL Editor** (cambia el correo):

```sql
update public.profiles set account_type = 'business'
 where id = (select id from auth.users where email = 'TU_CORREO_ALIADO@ejemplo.com');
```

Si creas una cuenta nueva desde **Authentication → Users → Add user → Create new user**, marca **Auto Confirm User** y conviértela con el SQL anterior (de fábrica nace como dueño de mascota).

**Segunda cuenta:** la que ya tenías de la Etapa 4 sirve (cuenta de dueño de mascota).

### SQL que usarás durante las pruebas

> **Actualización (Etapa 10):** aprobar, rechazar, suspender, verificar aliados y asignar planes ya se puede hacer con botones en `admin.html`. Este SQL sigue siendo válido (y útil si el panel no estuviera disponible).

Cada bloque se pega en **SQL Editor → New query → Run**. Cambia los correos y los nombres por los tuyos. Todos se pueden repetir sin error.

**Ver los establecimientos pendientes de aprobación:**

```sql
select b.id, b.name, b.status, u.email
  from public.businesses b left join auth.users u on u.id = b.owner_id
 where b.status = 'pending' order by b.created_at;
```

**Aprobar / suspender / rechazar un establecimiento** (cambia el nombre):

```sql
update public.businesses set status = 'approved'  where name = 'NOMBRE DEL NEGOCIO' and not is_demo;
-- update public.businesses set status = 'suspended' where name = 'NOMBRE DEL NEGOCIO' and not is_demo;
-- update public.businesses set status = 'rejected'  where name = 'NOMBRE DEL NEGOCIO' and not is_demo;
```

**Dar Huellita de Plata u Oro a la cuenta de aliado** (para Plata cambia `'oro'` por `'plata'`; para quitar el plan, ejecuta solo el primer `update`):

```sql
update public.subscriptions set status = 'replaced'
 where status = 'active' and user_id = (select id from auth.users where email = 'TU_CORREO_ALIADO@ejemplo.com');
insert into public.subscriptions (user_id, plan_id, billing_period, note)
select id, 'oro', 'monthly', 'Prueba de la Etapa 5' from auth.users where email = 'TU_CORREO_ALIADO@ejemplo.com';
```

**Marcar como «verificado»** (solo si ya está aprobado; la etiqueta **se muestra únicamente con Oro**):

```sql
update public.businesses set verified = true, verified_at = now()
 where name = 'NOMBRE DEL NEGOCIO' and status = 'approved' and not is_demo;
```

Esto es solo para pruebas; no es un cobro ni una compra.

## Paso 4 · Prueba en el sitio real (checklist)

Marca cada punto. Si algo falla, anota **el número**, lo que viste en pantalla y, si puedes, el mensaje rojo de la consola (**F12 → Console**) y de **F12 → Network** (la petición que salga en rojo; pulsa sobre ella y copia *Status* y *Response*).

Usa una foto real del celular (suelen pesar 3–8 MB) para ver que se reduce.

**A. Directorio sin iniciar sesión** (ventana privada, `directorio.html`)

1. Carga sin errores. Si no hay aliados aprobados dice **«Aún no hay aliados publicados»**. (Si instalaste `06_datos_demo.sql` verás 6 fichas marcadas **«Ejemplo de demostración»** y sin enlaces de mapa; son ficticias y se borran con `delete from public.businesses where is_demo;`).
2. Escribe una palabra sin resultados: aparece «No encontramos establecimientos». Prueba con `50%_'` o `<b>`: no da errores.
3. Pulsa **Destacados primero / Por nombre / Más recientes**: cambia el orden. El filtro de categoría funciona.

**B. Alta del establecimiento** (cuenta de aliado, `panel-aliado.html`)

4. Si no tienes establecimientos, el panel dice **«Registra tu establecimiento»**. Intenta registrar sin nombre, sin categoría, o con un teléfono con letras: te avisa y no guarda.
5. Regístralo con nombre, categoría, descripción, dirección, municipio, estado y teléfono. Debe aparecer **«En revisión»** con el aviso de que **todavía no aparece en el directorio**, y el aviso de que aún no tienes plan de aliado ni hay cobros.
6. Abre `directorio.html` en una ventana privada: el negocio **no** aparece.
7. Con **otra** cuenta (dueño de mascota) entra a `panel-aliado.html`: debe decir **«Solo para aliados comerciales»**.

**C. Aprobado, sin plan** (aprueba el negocio con el SQL del Paso 3)

8. Recarga el panel: estado **«Aprobada»** y aparece el botón **«Ver mi ficha en el directorio»**.
9. En el directorio (ventana privada) ya aparece, mostrando **solo** nombre, categoría, descripción y dirección. **Sin** teléfono, sin botón «Ver ficha», sin etiqueta de verificado.
10. Escribe en la descripción `<b>hola</b>` y guarda: en el directorio se ve **tal cual, como texto**, no en negritas.
11. Edita el nombre y guarda: el cambio se ve de inmediato en el directorio (el panel avisa que, estando aprobado, los cambios se publican de inmediato).

**D. Plan Plata** (asígnalo con el SQL; vuelve a cargar el panel)

12. El panel dice **«Tu plan: Huellita de Plata»**. En **Datos comerciales** el campo de WhatsApp aparece **bloqueado** y explica que es de Oro.
13. **Fotos y logotipo:** sube el logotipo y 2–3 fotos del celular. En **Supabase → Storage → business-media** hay una carpeta (tu identificador) con archivos `.jpg` **mucho más ligeros que el original** (el logotipo normalmente pesa menos de 150 KB). Reemplaza el logotipo: el viejo desaparece de Storage. Quita una foto: también se borra. Con 6 fotos el campo para agregar otra se desactiva. El panel avisa que **las imágenes son públicas**.
14. **Horarios:** marca lunes a viernes abierto 09:00–18:00 (puedes usar «Copiar el lunes a lunes–viernes»), sábado 10:00–14:00 y domingo cerrado. Guarda. Intenta apertura = cierre: no te deja.
15. **Promociones:** crea una (título, detalle, fechas). Aparece como **«Vigente»**. Con Plata **ya no puedes crear otra este mes** (el botón se desactiva y te lo explica). Pausa la promoción: sale del directorio; actívala: vuelve.
16. **Directorio** (ventana privada, recarga): la tarjeta muestra el logotipo, el teléfono, la etiqueta **«Promoción vigente»**. Pulsa **«Ver ficha»**: se ven descripción, fotos, horario en orden de lunes a domingo, teléfono (con enlace para llamar) y la promoción. **No** hay botón de WhatsApp ni etiqueta de verificado, aunque marques `verified` (con Plata no se muestra).

**E. Plan Oro** (cambia el plan con el SQL; vuelve a cargar el panel)

17. El campo de **WhatsApp** se habilita. Escribe `55 1234 5678` y guarda: en el directorio aparece el botón **WhatsApp** que abre `wa.me/525512345678`. Prueba con letras o con pocos dígitos: te avisa.
18. Marca el negocio como verificado con el SQL: en el directorio aparece **«✔ Aliado verificado»** y **«Destacado»**, y se coloca **antes** que los negocios sin Oro. El panel lo confirma.
19. Crea varias promociones el mismo mes: con Oro son **ilimitadas**.

**F. Mapas**

20. En la tarjeta, **«Ver ubicación»** y **«Cómo llegar»** abren **Google Maps en una pestaña nueva**, buscando el negocio por su nombre y dirección (o por el «Texto para Google Maps» si lo escribiste). Comprueba que encuentra el lugar correcto; si no, ajusta ese texto en **Datos comerciales**.

**G. Estadísticas**

21. Desde **otro navegador o ventana privada, sin sesión**, abre la ficha y pulsa «Cómo llegar». En el panel → **Estadísticas** (recarga la sección) debe subir **1 visita** y **1 clic**. Abrir la ficha varias veces el mismo día desde el mismo dispositivo **no** suma más visitas (se cuenta una por persona y por día).
22. Abre tu propia ficha **con la sesión de aliado iniciada**: **no** suma (tus visitas no se cuentan).

**H. Privacidad y permisos**

23. Con una **segunda cuenta de aliado** (opcional): no ve nada de la primera; sus establecimientos y estadísticas son suyos.
24. El directorio **nunca** muestra el correo ni el nombre de la persona dueña.
25. Suspende el negocio con el SQL: desaparece del directorio y el panel explica que está **«Suspendida»**. Vuelve a aprobarlo.
26. (Opcional) Suspende la **cuenta** de aliado con este SQL y recarga el panel: debe mostrar el aviso de cuenta suspendida, con todos los botones de edición desactivados. Después revierte con `false`.

    ```sql
    update public.profiles set is_suspended = true
     where id = (select id from auth.users where email = 'TU_CORREO_ALIADO@ejemplo.com');
    ```

**I. Eliminar**

27. Crea un segundo establecimiento («Registrar otro establecimiento») y elimínalo: pide confirmación, avisa que se borran promociones, estadísticas e imágenes, y al confirmar desaparece del panel y sus archivos de **Storage → business-media**.

**J. Consola**

28. Durante todas las pruebas, **F12 → Console** no debe mostrar errores rojos de *Content Security Policy*.

### Si algo falla: causas probables

| Síntoma | Qué revisar |
|---|---|
| El directorio dice «No se pudo cargar…» | Que el Paso 1 terminó sin errores y el verificador dice 34. Si el proyecto estuvo pausado, reactívalo en Supabase. |
| El negocio está aprobado pero no aparece | Que `status` sea `approved` (consulta con `select name, status from public.businesses;`) y recarga forzando. |
| No aparece el teléfono, el horario o las fotos | Es lo esperado **sin plan Plata u Oro**. Asigna el plan con el SQL y recarga. |
| No aparece la etiqueta de verificado | Debe estar aprobado, con `verified = true` **y** plan Oro. |
| «Tu plan no incluye el botón directo a WhatsApp» | El WhatsApp es de Oro; revisa el plan de la cuenta y cierra sesión / vuelve a entrar. |
| «No se pudo subir la imagen» | Que la cuenta sea de aliado, no esté suspendida y no pase de 30 archivos. Anota el *Status* y *Response* de la petición que contenga `/storage/v1/` en **F12 → Network**. |
| La imagen sube pero no se ve en el directorio | Con plan Plata/Oro y negocio aprobado. Confirma en **Storage** que el bucket `business-media` es **Public**. |
| «Tu plan permite 1 promoción(es) al mes» | Es el límite de Plata. Con Oro no hay límite. |
| Las visitas no suben | Solo cuentan fichas **aprobadas**, abiertas con «Ver ficha» (requiere Plata u Oro), una vez al día por persona y no las del propio dueño. |

---

## Qué hace y qué no hace esta etapa

**Sí hace**

- Directorio público con búsqueda, filtros, orden y paginación; ficha según el plan; enlaces directos a Google Maps (sin API ni claves); contadores anónimos de visitas y clics.
- Panel de aliados: alta (queda en revisión), datos comerciales, logotipo y fotos, horarios, promociones con el límite del plan, estadísticas y eliminación con confirmación.
- Los permisos (quién ve qué, qué muestra cada plan, límites de promociones, quién puede subir imágenes) los aplica **Supabase**, no la pantalla. Lo que escribe una persona se muestra siempre como **texto**.

**No hace todavía**

- **Aprobar, rechazar, suspender, verificar y asignar planes desde una pantalla:** *(actualización de la Etapa 10: ya existe, en `admin.html` → Aliados y Usuarios; el SQL de esta guía sigue funcionando)*.
- **Contratar o pagar** un plan: no está habilitado y no se guarda ningún dato financiero. La «difusión en redes sociales» del plan Oro es una acción manual futura, no automática.
- **Avisos al aliado** cuando su ficha es aprobada o suspendida (llegan con las notificaciones, Etapa 8).
- **Mapa incrustado:** solo enlaces a Google Maps.
- **Limpieza automática de archivos huérfanos:** al reemplazar o quitar imágenes o eliminar un negocio el navegador borra los archivos viejos; si se pierde la conexión justo entonces puede quedar alguno (nadie lo ve; ocupa espacio dentro del tope de 30 archivos por cuenta).

## Decisiones que conviene que confirmes

1. **La etiqueta «Aliado verificado» solo se muestra con el plan Oro**, aunque un administrador marque el negocio como verificado.
2. **Los cambios en un establecimiento ya aprobado se publican de inmediato**, sin nueva revisión.
3. **El límite mensual de promociones cuenta las promociones creadas este mes:** si una cuenta Plata borra su promoción, libera el cupo. Es una limitación conocida y de bajo riesgo.
4. **Las estadísticas son aproximadas y anónimas** (una visita por persona y por día; hasta 3 clics de mapa); no se guarda la IP ni nada que identifique a quien visita.
5. **Las imágenes del negocio son públicas** (cualquiera con la dirección exacta puede verlas, incluso si la ficha no está aprobada). Hasta 6 fotos + logotipo por establecimiento; hasta 30 archivos por cuenta.
6. **Máximo 5 establecimientos por cuenta**, con el mismo plan para todos.

## Para la Etapa 6 (denuncias anónimas) necesitaré de ti

- Crear una cuenta gratuita en **Cloudflare Turnstile** (anti-robots) y copiarme solo la **clave del sitio** (*site key*, es pública). La clave secreta **no me la pases**: la pondrás tú en la configuración de Supabase cuando te lo indique.
- Decidir cuántas fotos de evidencia por denuncia (propuesta: hasta 3 de 5 MB).
