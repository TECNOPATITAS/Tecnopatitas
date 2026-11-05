# Guía de instalación · Etapa 2 (Supabase)

Tiempo aproximado: 15 minutos. **Costo: $0.** No necesitas tarjeta. Si en algún momento un botón te pide pagar, mejorar el plan o «Upgrade», **no lo pulses**: nada de esto lo necesita.

> Los menús de Supabase cambian con frecuencia. Si algún nombre no coincide con lo que ves, dime qué aparece en pantalla y lo ajustamos.

---

## Paso 1 · Crear tu cuenta de Supabase

1. Entra a <https://supabase.com/dashboard> y pulsa **Sign Up** (puedes usar tu cuenta de GitHub o un correo).
2. Activa la verificación en dos pasos en tu cuenta cuando te lo ofrezca (recomendado: esta cuenta controla toda la base de datos).

## Paso 2 · Crear el proyecto

1. Pulsa **New project**.
2. **Organization:** la que se creó contigo (plan **Free**).
3. **Project name:** `tecnopatitas`.
4. **Database password:** pulsa **Generate a password** y guárdala en tu gestor de contraseñas o en un lugar privado. **No me la compartas ni la pongas en GitHub**: no la necesito.
5. **Region:** la más cercana a México que aparezca (normalmente *East US* o *West US*).
6. Si aparece **Security options**, deja activado **Enable Data API** (el sitio la usa). Si ves **Enable automatic RLS**, puedes dejarlo activado: es compatible con este proyecto.
7. Pulsa **Create new project** y espera 1–2 minutos.
8. Comprueba que arriba diga **Free**. No agregues complementos (*add-ons*).

## Paso 3 · Instalar la base de datos

1. En el menú izquierdo abre **SQL Editor** → **New query**.
2. Abre el archivo **`00_instalar_todo.sql`** (carpeta `database/`), copia **todo** su contenido y pégalo en el editor.
3. Pulsa **Run** (o Ctrl/Cmd + Enter). Tarda unos segundos.
4. Si aparece un aviso de *«operaciones destructivas»*: es normal. El script usa `drop policy if exists` y `drop trigger if exists` para poder ejecutarse varias veces sin errores; **no borra datos**. Confirma con **Run this query**.
5. Resultado esperado: una tabla con una sola fila bajo la columna **`resultado`** que dice **«Instalación terminada sin errores…»**. Si ves una tabla casi vacía con una columna llamada `pol`, es el resultado de una instrucción interna anterior (normal e inofensiva): significa que tu archivo es una versión previa del instalador. Si no apareció ningún error rojo, la instalación terminó bien; el paso 5 lo confirma.

> Si el editor se queja por el tamaño o se corta, ejecuta **uno por uno y en este orden** los archivos `01_esquema.sql`, `02_funciones.sql`, `03_seguridad_rls.sql`, `04_storage.sql` y `05_datos_base.sql` (cada uno en una consulta nueva).

## Paso 4 (opcional) · Datos de demostración

Para ver el directorio y las guías con contenido de ejemplo, ejecuta igual **`06_datos_demo.sql`**. Son 6 negocios **ficticios** (marcados como demostración) y 8 guías **generales** marcadas «pendiente de revisión veterinaria». Antes de abrir el sitio al público, bórralos o reemplázalos (`delete from public.businesses where is_demo;`).

## Paso 5 · Verificar que quedó seguro

1. **New query**, pega el contenido de **`verificar_seguridad.sql`** y pulsa **Run**.
2. La primera fila debe decir: **`TODO CORRECTO: 35 comprobaciones superadas`**.
3. Las filas **INFO** son solo datos (número de administradores, demos…). Cualquier fila **REVISAR** significa que algo no coincide: copia la tabla completa y envíamela. Ese resultado **no contiene contraseñas, claves ni datos de usuarios**, así que es seguro compartirlo.

Revisión visual opcional:

- **Table Editor:** deben verse 19 tablas (más las internas del esquema `private` si cambias de esquema), cada una con la etiqueta **RLS enabled**.
- **Storage:** 6 buckets: `avatars`, `pet-photos`, `business-media`, `guide-images`, `complaint-evidence` y `qr-photos`. Solo `business-media`, `guide-images` y `qr-photos` son públicos.
- **Database → Publications → supabase_realtime:** debe incluir `messages`, `conversations` y `notifications`.

## Paso 6 (puedes dejarlo para la Etapa 3) · Tu cuenta de administrador

Nadie puede volverse administrador desde el sitio web: el rol se asigna solo desde aquí, con acceso a tu proyecto.

1. **Authentication → Users → Add user → Create new user.** Escribe tu correo y una contraseña larga y única, y marca **Auto Confirm User**.
2. En **SQL Editor** ejecuta (cambia el correo por el tuyo):

```sql
insert into public.admin_roles (user_id, note)
select id, 'Administrador principal' from auth.users where email = 'TU_CORREO@ejemplo.com';
```

3. Debe responder **«Success… 1 row affected»**. Si dice 0, el correo no coincide con el de la cuenta.

## Paso 7 · Lo que se necesita para la Etapa 3 (ya entregado)

> Esos dos datos ya están en `js/config.js`. Lo que sigue ahora está en `GUIA_ETAPA_3.md`.

Solo dos datos, ambos **públicos por diseño** (la seguridad la dan las políticas que acabas de instalar):

| Dato | Dónde se encuentra |
|---|---|
| **Project URL** (`https://xxxx.supabase.co`) | Botón **Connect** (arriba) o **Project Settings → Data API** |
| **Publishable key** (`sb_publishable_…`; en proyectos antiguos se llama *anon*) | **Project Settings → API Keys** |

**Nunca me pegues, ni subas a GitHub:** la *secret key* (`sb_secret_…`) o *service_role*, la contraseña de la base de datos, ni tokens de acceso.

## Cosas que conviene saber (plan gratuito)

- **El proyecto se pausa tras 7 días sin actividad.** Los datos se conservan; se reactiva con un botón en el panel (*Restore project*). Si lo vas a usar con personas reales, entra al menos una vez por semana o acepta que a veces esté dormido.
- Límites: 500 MB de base de datos, 1 GB de archivos, 5 GB de transferencia al mes, 2 proyectos activos. El diseño ya incluye topes (30 mascotas por cuenta, archivos por persona, límite de envíos de denuncias) para cuidar la cuota.
- No se almacenan tarjetas ni datos financieros, y no hay cobros automáticos.

## Si algo sale mal

| Síntoma | Qué hacer |
|---|---|
| Error rojo al ejecutar un archivo | Copia el mensaje completo y dime en qué archivo y línea. Postgres trata una consulta con varias instrucciones como una sola operación, así que normalmente no queda a medias; aun así, dime qué archivo falló antes de repetirlo. |
| `verificar_seguridad.sql` muestra **REVISAR** | Envíame la tabla. Normalmente se corrige volviendo a ejecutar `00_instalar_todo.sql`, que es seguro repetir. |
| «permission denied» al ejecutar | Asegúrate de estar en **SQL Editor** del panel (rol `postgres`) y no en una conexión externa limitada. |
| Quieres empezar de cero | Dímelo antes: hay que borrar tablas, y eso destruye datos. |

---

## Para desarrolladores: ejecutar las pruebas en tu computadora (opcional)

Requiere PostgreSQL 15 o superior y que puedas crear bases de datos. Simula Supabase con `pruebas/shim_supabase.sql`, instala todo en una base llamada `tp_test` y ejecuta 457 pruebas de seguridad y funcionamiento:

```bash
bash database/pruebas/ejecutar_pruebas.sh
```

Usa las variables estándar `PGHOST`, `PGPORT`, `PGUSER` y `PGPASSWORD`. **No lo ejecutes contra tu proyecto de Supabase**: borra y recrea la base `tp_test`, y el simulador solo es válido en una base local.
