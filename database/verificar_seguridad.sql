-- =====================================================================
-- TECNOPATITAS · Etapa 2 · VERIFICADOR DE SEGURIDAD (solo lectura)
--
-- Pégalo en  Supabase → SQL Editor → New query  y pulsa Run.
-- NO modifica nada: solo consulta el catálogo de la base de datos.
-- Devuelve una tabla: todas las filas deben decir OK (las INFO son datos
-- informativos). Cualquier fila "REVISAR" indica algo que corregir.
-- El resultado NO contiene contraseñas, claves ni datos de usuarios; es
-- seguro copiarlo y compartirlo para que lo revisemos juntos.
-- =====================================================================
with
-- Funciones propias (se excluyen las que instalan extensiones)
fn as (
  select p.oid, p.proname, p.prosecdef, p.proconfig, p.proacl, p.proowner
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
),
tbl as (
  select c.oid, n.nspname, c.relname, c.relrowsecurity
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname in ('public', 'private') and c.relkind in ('r', 'p')
),
exp_public_fn as (select unnest(array['directory_get','directory_search','directory_track','get_public_pet_profile','track_complaint']) as f),
exp_auth_fn as (select unnest(array[
  'admin_assign_subscription','admin_cancel_subscription','admin_dashboard_stats','admin_list_users','admin_renew_subscription',
  'admin_set_business_status','admin_set_business_verified','admin_set_subscription_dates','admin_set_user_suspended',
  'cancel_my_subscription','directory_get','directory_search','directory_track','get_public_pet_profile','is_active_user','is_admin',
  'has_qr_plan','is_business_account','my_entitlements','regenerate_pet_qr_token','start_conversation','storage_has_room','track_complaint']) as f),
checks(n, grupo, comprobacion, ok, detalle) as (values
  -- ---------------- Estructura ----------------
  (10, 'Estructura', 'Existen las 19 tablas de la plataforma en "public"',
    (select count(*) from tbl where nspname = 'public' and relname in ('profiles','admin_roles','subscription_plans','subscriptions','subscription_events',
       'pets','pet_vaccinations','pet_deworming','pet_appointments','pet_qr_profiles','businesses','business_promotions','business_daily_stats','complaints',
       'conversations','messages','notifications','care_guides','admin_audit_log')) = 19,
    (select count(*)::text || ' de 19 encontradas' from tbl where nspname = 'public' and relname in ('profiles','admin_roles','subscription_plans','subscriptions','subscription_events',
       'pets','pet_vaccinations','pet_deworming','pet_appointments','pet_qr_profiles','businesses','business_promotions','business_daily_stats','complaints',
       'conversations','messages','notifications','care_guides','admin_audit_log'))),
  (11, 'Estructura', 'Existen las 2 tablas internas del esquema "private"',
    (select count(*) from tbl where nspname = 'private') = 2, (select string_agg(relname, ', ') from tbl where nspname = 'private')),
  (12, 'Estructura', 'El disparador de registro (tp_new_user) existe en auth.users',
    exists (select 1 from pg_trigger where tgrelid = 'auth.users'::regclass and tgname = 'tp_new_user' and not tgisinternal and tgenabled <> 'D'), null),
  (13, 'Estructura', 'Existen los 24 disparadores de protección (carnet, QR, aliados, chat, denuncias…)',
    (select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public' and not t.tgisinternal and t.tgname like 'tp\_%' and t.tgenabled <> 'D') = 24,
    (select count(*)::text || ' de 24 activos' from pg_trigger t join pg_class c on c.oid = t.tgrelid join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public' and not t.tgisinternal and t.tgname like 'tp\_%' and t.tgenabled <> 'D')),

  -- ---------------- RLS ----------------
  (20, 'Seguridad por filas (RLS)', 'TODAS las tablas de "public" y "private" tienen RLS activado',
    not exists (select 1 from tbl where not relrowsecurity), (select string_agg(nspname || '.' || relname, ', ') from tbl where not relrowsecurity)),
  (21, 'Seguridad por filas (RLS)', 'Tablas sin políticas (bloqueo total) = solo admin_roles y las 2 internas',
    coalesce((select string_agg(relname, ',' order by relname) from tbl t where not exists (select 1 from pg_policy p where p.polrelid = t.oid)), '') = 'admin_roles,rate_limits,settings',
    (select string_agg(relname, ',' order by relname) from tbl t where not exists (select 1 from pg_policy p where p.polrelid = t.oid))),
  (22, 'Seguridad por filas (RLS)', 'Ninguna política deja una tabla abierta con "using (true)" (salvo planes y guías publicados)',
    not exists (select 1 from pg_policies where schemaname in ('public', 'storage')
                and (qual in ('true', '(true)') or with_check in ('true', '(true)'))),
    (select string_agg(tablename || '.' || policyname, ', ') from pg_policies where schemaname in ('public', 'storage')
                and (qual in ('true', '(true)') or with_check in ('true', '(true)')))),

  -- ---------------- Permisos de visitantes (anon) ----------------
  (30, 'Permisos', 'Un visitante sin sesión solo tiene acceso a care_guides y subscription_plans',
    coalesce((select string_agg(relname, ',' order by relname) from tbl
              where nspname = 'public' and has_any_column_privilege('anon', oid, 'select,insert,update,references')), '') = 'care_guides,subscription_plans',
    (select string_agg(relname, ',' order by relname) from tbl where nspname = 'public' and has_any_column_privilege('anon', oid, 'select,insert,update,references'))),
  (31, 'Permisos', 'Un visitante solo puede ejecutar las 5 funciones públicas (seguimiento de denuncias, QR, directorio y su conteo de visitas)',
    coalesce((select string_agg(proname, ',' order by proname) from fn where has_function_privilege('anon', oid, 'execute')), '')
      = (select string_agg(f, ',' order by f) from exp_public_fn),
    (select string_agg(proname, ',' order by proname) from fn where has_function_privilege('anon', oid, 'execute'))),
  (32, 'Permisos', 'Un usuario con sesión solo puede ejecutar las 23 funciones previstas',
    coalesce((select string_agg(proname, ',' order by proname) from fn where has_function_privilege('authenticated', oid, 'execute')), '')
      = (select string_agg(f, ',' order by f) from exp_auth_fn),
    (select string_agg(proname, ',' order by proname) from fn where has_function_privilege('authenticated', oid, 'execute')
        and proname not in (select f from exp_auth_fn))),
  (33, 'Permisos', 'Ninguna función de "public" es ejecutable por el grupo PUBLIC (cualquiera)',
    not exists (select 1 from fn where exists (select 1 from aclexplode(coalesce(proacl, acldefault('f', proowner))) a where a.grantee = 0 and a.privilege_type = 'EXECUTE')),
    (select string_agg(proname, ', ') from fn where exists (select 1 from aclexplode(coalesce(proacl, acldefault('f', proowner))) a where a.grantee = 0 and a.privilege_type = 'EXECUTE'))),
  (34, 'Permisos', 'Todas las funciones SECURITY DEFINER fijan search_path vacío',
    not exists (select 1 from fn where prosecdef and not coalesce(proconfig, '{}') @> array['search_path=""']),
    (select string_agg(proname, ', ') from fn where prosecdef and not coalesce(proconfig, '{}') @> array['search_path=""'])),
  (35, 'Permisos', 'admin_roles es inaccesible desde la API (ni lectura ni escritura)',
    not (has_table_privilege('anon', 'public.admin_roles', 'select,insert,update,delete')
      or has_table_privilege('authenticated', 'public.admin_roles', 'select,insert,update,delete')
      or has_any_column_privilege('anon', 'public.admin_roles', 'select,insert,update')
      or has_any_column_privilege('authenticated', 'public.admin_roles', 'select,insert,update')), null),
  (36, 'Permisos', 'El esquema "private" es inaccesible desde la API',
    not (has_schema_privilege('anon', 'private', 'usage') or has_schema_privilege('authenticated', 'private', 'usage')), null),

  (37, 'Permisos', 'Las 9 funciones de administración comprueban en el servidor que quien llama es admin',
    (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname like 'admin\_%' and p.prosrc like '%private.require_admin()%') = 9
    and (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'private' and p.proname = 'require_admin' and p.prosrc like '%public.is_admin()%') = 1,
    (select count(*)::text || ' de 9 funciones protegidas' from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname like 'admin\_%' and p.prosrc like '%private.require_admin()%')),

  -- ---------------- Columnas protegidas (nadie se otorga poderes desde el navegador) ----------------
  (40, 'Columnas protegidas', 'Un usuario NO puede cambiar su tipo de cuenta ni su suspensión',
    not (has_column_privilege('authenticated', 'public.profiles', 'account_type', 'update')
      or has_column_privilege('authenticated', 'public.profiles', 'account_type', 'insert')
      or has_column_privilege('authenticated', 'public.profiles', 'is_suspended', 'update')
      or has_table_privilege('authenticated', 'public.profiles', 'insert')), null),
  (41, 'Columnas protegidas', 'Suscripciones: nadie puede crear, cambiar ni borrar desde el navegador',
    not (has_any_column_privilege('authenticated', 'public.subscriptions', 'insert,update')
      or has_table_privilege('authenticated', 'public.subscriptions', 'delete')
      or has_any_column_privilege('anon', 'public.subscriptions', 'select,insert,update')), null),
  (42, 'Columnas protegidas', 'Aliados: estado, verificación, demo y dueño no se pueden editar desde el navegador',
    not (has_column_privilege('authenticated', 'public.businesses', 'status', 'update') or has_column_privilege('authenticated', 'public.businesses', 'status', 'insert')
      or has_column_privilege('authenticated', 'public.businesses', 'verified', 'update') or has_column_privilege('authenticated', 'public.businesses', 'verified', 'insert')
      or has_column_privilege('authenticated', 'public.businesses', 'is_demo', 'update') or has_column_privilege('authenticated', 'public.businesses', 'is_demo', 'insert')
      or has_column_privilege('authenticated', 'public.businesses', 'owner_id', 'update')), null),
  (43, 'Columnas protegidas', 'Mascotas: el dueño no se puede cambiar; QR: el token no se puede elegir ni editar',
    not (has_column_privilege('authenticated', 'public.pets', 'owner_id', 'update')
      or has_column_privilege('authenticated', 'public.pet_qr_profiles', 'public_token', 'insert')
      or has_column_privilege('authenticated', 'public.pet_qr_profiles', 'public_token', 'update')), null),
  (44, 'Columnas protegidas', 'Chat: el rol y el remitente de un mensaje no se pueden falsificar; los mensajes no se editan ni borran',
    not (has_column_privilege('authenticated', 'public.messages', 'sender_role', 'insert')
      or has_column_privilege('authenticated', 'public.messages', 'sender_id', 'insert')
      or has_any_column_privilege('authenticated', 'public.messages', 'update')
      or has_table_privilege('authenticated', 'public.messages', 'delete')), null),
  (45, 'Columnas protegidas', 'Denuncias: no se insertan directamente y su texto original no se puede editar',
    not (has_table_privilege('authenticated', 'public.complaints', 'insert')
      or has_any_column_privilege('anon', 'public.complaints', 'insert,select,update')
      or has_column_privilege('authenticated', 'public.complaints', 'description', 'update')
      or has_column_privilege('authenticated', 'public.complaints', 'tracking_code', 'update')), null),
  (48, 'Columnas protegidas', 'Denuncias: solo la función segura del servidor (service_role) puede registrarlas, con límites y anti-robots; ni visitantes ni usuarios',
    (select count(*) from fn where proname = 'submit_complaint') = 1
    and (select count(*) from fn where proname = 'complaint_precheck') = 1
    and not exists (select 1 from fn where proname in ('submit_complaint', 'complaint_precheck')
                      and (has_function_privilege('anon', oid, 'execute') or has_function_privilege('authenticated', oid, 'execute')))
    and not exists (select 1 from fn where proname in ('submit_complaint', 'complaint_precheck') and not has_function_privilege('service_role', oid, 'execute')),
    (select string_agg(proname || '(' || pg_get_function_identity_arguments(oid) || ') anon=' || has_function_privilege('anon', oid, 'execute')
                       || ' auth=' || has_function_privilege('authenticated', oid, 'execute') || ' servidor=' || has_function_privilege('service_role', oid, 'execute'), ' | ')
       from fn where proname in ('submit_complaint', 'complaint_precheck'))),
  (46, 'Columnas protegidas', 'Notificaciones: solo se pueden marcar como leídas (no crear ni editar contenido)',
    not (has_table_privilege('authenticated', 'public.notifications', 'insert')
      or has_column_privilege('authenticated', 'public.notifications', 'title', 'update')
      or has_column_privilege('authenticated', 'public.notifications', 'user_id', 'update')), null),
  (47, 'Columnas protegidas', 'La bitácora de administración no se puede escribir desde el navegador',
    not (has_any_column_privilege('authenticated', 'public.admin_audit_log', 'insert,update') or has_table_privilege('authenticated', 'public.admin_audit_log', 'delete')), null),

  -- ---------------- Datos base ----------------
  (50, 'Datos base', 'Los 5 planes existen con precios mensual/anual exactos',
    coalesce((select string_agg(id || ':' || price_monthly_mxn || '/' || price_yearly_mxn, ',' order by sort_order) from public.subscription_plans),'')
      = 'basica:0/0,pro:29/290,vip:59/590,plata:149/1490,oro:299/2990',
    (select string_agg(id || ':' || price_monthly_mxn || '/' || price_yearly_mxn, ',' order by sort_order) from public.subscription_plans)),
  (51, 'Datos base', 'Número de beneficios por plan: 3, 4, 5, 3, 6',
    coalesce((select string_agg(cardinality(benefits)::text, ',' order by sort_order) from public.subscription_plans), '') = '3,4,5,3,6', null),
  (52, 'Datos base', 'La sal interna para anonimizar visitantes existe (su valor no se muestra)',
    (select count(*) from private.settings where key = 'ip_salt' and length(value) >= 16) = 1, null),
  (53, 'Datos base', 'Chat y notificaciones están en la publicación de tiempo real',
    coalesce((select string_agg(tablename, ',' order by tablename) from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public'), '')
      like '%conversations%messages%notifications%', (select string_agg(tablename, ',' order by tablename) from pg_publication_tables where pubname = 'supabase_realtime')),

  -- ---------------- Almacenamiento ----------------
  (60, 'Almacenamiento', 'Los 6 buckets existen con visibilidad y tamaño máximo correctos',
    coalesce((select string_agg(id || ':' || public || ':' || file_size_limit, ',' order by id) from storage.buckets where id in ('avatars','pet-photos','business-media','guide-images','complaint-evidence','qr-photos')), '')
      = 'avatars:false:2097152,business-media:true:5242880,complaint-evidence:false:5242880,guide-images:true:5242880,pet-photos:false:5242880,qr-photos:true:1048576',
    (select string_agg(id || ':' || public || ':' || coalesce(file_size_limit::text, 'sin tope'), ',' order by id) from storage.buckets)),
  (61, 'Almacenamiento', 'Solo se aceptan imágenes JPG, PNG o WebP',
    (select count(*) from storage.buckets where id in ('avatars','pet-photos','business-media','guide-images','complaint-evidence','qr-photos')
        and allowed_mime_types is not distinct from array['image/jpeg','image/png','image/webp']) = 6, null),
  (62, 'Almacenamiento', 'Existen las 19 políticas de almacenamiento de TECNOPATITAS',
    (select count(*) from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname like 'tp\_%') = 19,
    (select count(*)::text || ' de 19' from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname like 'tp\_%')),
  (63, 'Almacenamiento', 'No hay políticas de almacenamiento ajenas (p. ej. creadas desde el panel por accidente)',
    not exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname not like 'tp\_%'),
    (select string_agg(policyname, ', ') from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname not like 'tp\_%')),

  (64, 'Almacenamiento', 'La placa QR valida la foto pública (columna y disparador al insertar y al actualizar)',
    exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'pet_qr_profiles' and column_name = 'qr_photo_path')
    and exists (select 1 from pg_trigger t where t.tgrelid = 'public.pet_qr_profiles'::regclass and t.tgname = 'tp_guard' and not t.tgisinternal
                  and (t.tgtype & 2) = 2 and (t.tgtype & 4) = 4 and (t.tgtype & 16) = 16), null),

  (65, 'Columnas protegidas', 'Aliados: las rutas de logotipo y fotos y el horario se validan en el servidor',
    exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'private' and p.proname = 'guard_businesses'
               and p.prosrc like '%El logotipo no es válido%' and p.prosrc like '%Una de las fotos no es válida%' and p.prosrc like '%El horario no es válido%'), null),
  (66, 'Columnas protegidas', 'Estadísticas del directorio: el aliado solo puede leerlas; nadie las escribe desde el navegador',
    has_table_privilege('authenticated', 'public.business_daily_stats', 'select')
    and not (has_any_column_privilege('authenticated', 'public.business_daily_stats', 'insert,update')
             or has_table_privilege('authenticated', 'public.business_daily_stats', 'delete')
             or has_any_column_privilege('anon', 'public.business_daily_stats', 'select,insert,update')), null),

  -- ---------------- Informativo ----------------
  (90, 'INFO', 'Administradores registrados en admin_roles (debe haber al menos 1 después de crear el tuyo)',
    true, (select count(*)::text from public.admin_roles)),
  (91, 'INFO', 'Establecimientos de demostración (bórralos antes de abrir al público: delete from public.businesses where is_demo;)',
    true, (select count(*)::text from public.businesses where is_demo)),
  (92, 'INFO', 'Guías publicadas con fuente "pendiente de revisión veterinaria" (revísalas desde el panel en la Etapa 10)',
    true, (select count(*)::text from public.care_guides where author_source ilike '%pendiente de revisi%'))
)
select n as "#", grupo as "Grupo", comprobacion as "Comprobación",
       case when grupo = 'INFO' then 'INFO' when ok then 'OK' else 'REVISAR' end as "Resultado",
       coalesce(detalle, '') as "Detalle"
from (
  select 0 as n, 'RESUMEN' as grupo,
         case when count(*) filter (where grupo <> 'INFO' and not ok) = 0
              then 'TODO CORRECTO: ' || count(*) filter (where grupo <> 'INFO') || ' comprobaciones superadas'
              else count(*) filter (where grupo <> 'INFO' and not ok) || ' comprobación(es) por REVISAR' end as comprobacion,
         count(*) filter (where grupo <> 'INFO' and not ok) = 0 as ok, null::text as detalle
  from checks
  union all
  select n, grupo, comprobacion, coalesce(ok, false), detalle from checks
) r
order by n;
