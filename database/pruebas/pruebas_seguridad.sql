-- =====================================================================
-- TECNOPATITAS · Etapa 2 · PRUEBAS DE SEGURIDAD Y FUNCIONAMIENTO
-- Intenta romper los permisos como visitante anónimo, usuario, aliado y admin.
-- Se ejecuta con: bash pruebas/ejecutar_pruebas.sh   (ver README de la carpeta)
-- Los marcadores {A}, {B}... se reemplazan por UUIDs de prueba.
-- =====================================================================
\set ON_ERROR_STOP off
\o /dev/null
drop schema if exists t cascade;
create schema t;
create table t.results (n serial primary key, grupo text, label text, pass boolean, detail text);
create table t.vars (k text primary key, v text);
create table t.ctx (grupo text);
insert into t.ctx values ('');

-- Ejecuta una sentencia como un rol/usuario concreto y devuelve 'OK rows=N' o 'ERR <sqlstate>: <mensaje>'.
create function t.x(p_uid uuid, p_role text, p_sql text, p_headers text default null) returns text
language plpgsql as $$
declare n bigint;
begin
  begin
    perform set_config('request.jwt.claims',
      case when p_role = 'postgres' then ''
           when p_uid is null then json_build_object('role', p_role)::text
           else json_build_object('sub', p_uid, 'role', p_role)::text end, true);
    if p_headers is not null then perform set_config('request.headers', p_headers, true); end if;
    execute format('set local role %I', p_role);
    execute p_sql;
    get diagnostics n = row_count;
    execute 'reset role';
    return 'OK rows=' || n;
  exception when others then
    return 'ERR ' || sqlstate || ': ' || sqlerrm;
  end;
end $$;

-- Igual, pero devuelve la primera columna de la primera fila como texto.
create function t.q(p_uid uuid, p_role text, p_sql text, p_headers text default null) returns text
language plpgsql as $$
declare v text;
begin
  begin
    perform set_config('request.jwt.claims',
      case when p_role = 'postgres' then ''
           when p_uid is null then json_build_object('role', p_role)::text
           else json_build_object('sub', p_uid, 'role', p_role)::text end, true);
    if p_headers is not null then perform set_config('request.headers', p_headers, true); end if;
    execute format('set local role %I', p_role);
    execute p_sql into v;
    execute 'reset role';
    return coalesce(v, '<null>');
  exception when others then
    return 'ERR ' || sqlstate || ': ' || sqlerrm;
  end;
end $$;

create function t.grupo(p text) returns void language sql as $$ update t.ctx set grupo = p; $$;

-- La sentencia debe dar un resultado que coincida (LIKE) con p_expect.
create function t.ex(p_label text, p_uid uuid, p_role text, p_sql text, p_expect text, p_headers text default null) returns void
language plpgsql as $$
declare r text;
begin
  r := t.x(p_uid, p_role, p_sql, p_headers);
  insert into t.results (grupo, label, pass, detail) values ((select grupo from t.ctx), p_label, r like p_expect, r);
end $$;

-- El valor devuelto por la consulta debe coincidir (LIKE) con p_expect.
create function t.eq(p_label text, p_uid uuid, p_role text, p_sql text, p_expect text, p_headers text default null) returns void
language plpgsql as $$
declare r text;
begin
  r := t.q(p_uid, p_role, p_sql, p_headers);
  insert into t.results (grupo, label, pass, detail) values ((select grupo from t.ctx), p_label, r like p_expect, r);
end $$;

create function t.ok(p_label text, p_cond boolean, p_detail text default null) returns void
language sql as $$
  insert into t.results (grupo, label, pass, detail) values ((select grupo from t.ctx), p_label, coalesce(p_cond, false), p_detail);
$$;

-- ---------------------------------------------------------------------
-- Preparación: usuarios de prueba (se crean como lo haría Supabase Auth)
-- A = dueña (intentará hacerse admin) · B = dueño · C = aliado · D = ADMIN
-- E = otro aliado · F = dueño para pruebas de límites
-- ---------------------------------------------------------------------
insert into auth.users (id, email, raw_user_meta_data) values
 ('{A}', 'ana@prueba.mx',  '{"display_name":"Ana","account_type":"admin"}'),
 ('{B}', 'beto@prueba.mx', '{"display_name":"Beto"}'),
 ('{C}', 'cris@prueba.mx', '{"display_name":"Cris","account_type":"business"}'),
 ('{D}', 'dani@prueba.mx', '{"display_name":"Dani"}'),
 ('{E}', 'eli@prueba.mx',  '{"display_name":"Eli","account_type":"business"}'),
 ('{F}', 'fer@prueba.mx',  '{"display_name":"Fer"}');
insert into public.admin_roles (user_id, note) values ('{D}', 'admin de pruebas');

-- =====================================================================
select t.grupo('1 Perfiles y roles');
-- =====================================================================
select t.ok('A pidió ser "admin" al registrarse y quedó como dueña',
            (select account_type from public.profiles where id = '{A}') = 'owner');
select t.ok('C pidió cuenta de aliado y la obtuvo', (select account_type from public.profiles where id = '{C}') = 'business');
select t.eq('A solo ve su propio perfil', '{A}', 'authenticated', $q$select count(*) from public.profiles$q$, '1');
select t.ex('A puede editar su nombre', '{A}', 'authenticated', $q$update public.profiles set display_name = 'Ana M' where id = '{A}'$q$, 'OK rows=1');
select t.ex('A NO puede cambiar su tipo de cuenta', '{A}', 'authenticated', $q$update public.profiles set account_type = 'business' where id = '{A}'$q$, 'ERR 42501%');
select t.ex('A NO puede quitarse la suspensión / cambiar is_suspended', '{A}', 'authenticated', $q$update public.profiles set is_suspended = false where id = '{A}'$q$, 'ERR 42501%');
select t.ex('A NO puede cambiar el perfil de B', '{A}', 'authenticated', $q$update public.profiles set display_name = 'hack' where id = '{B}'$q$, 'OK rows=0');
select t.ex('A NO puede insertar en admin_roles', '{A}', 'authenticated', $q$insert into public.admin_roles (user_id) values ('{A}')$q$, 'ERR 42501%');
select t.ex('A NO puede leer admin_roles', '{A}', 'authenticated', $q$select * from public.admin_roles$q$, 'ERR 42501%');
select t.ex('A NO puede crear perfiles a mano', '{A}', 'authenticated', $q$insert into public.profiles (id) values (gen_random_uuid())$q$, 'ERR 42501%');
select t.ex('Visitante anónimo NO puede leer perfiles', null, 'anon', $q$select * from public.profiles$q$, 'ERR 42501%');
select t.eq('is_admin() es falso para A', '{A}', 'authenticated', $q$select public.is_admin()$q$, 'false');
select t.eq('is_admin() es verdadero para D (en admin_roles)', '{D}', 'authenticated', $q$select public.is_admin()$q$, 'true');
update auth.users set raw_user_meta_data = '{"role":"admin","is_admin":true,"account_type":"admin"}', raw_app_meta_data = raw_app_meta_data where id = '{A}';
select t.eq('Cambiar user_metadata a "admin" NO convierte a nadie en admin', '{A}', 'authenticated', $q$select public.is_admin()$q$, 'false');
select t.ex('A NO puede llamar funciones de administración', '{A}', 'authenticated', $q$select public.admin_set_user_suspended('{B}', true, 'x')$q$, 'ERR 42501%');
select t.ex('Un anónimo ni siquiera puede ejecutar funciones de administración', null, 'anon', $q$select public.admin_dashboard_stats()$q$, 'ERR 42501%');
select t.eq('D (admin) ve todos los perfiles', '{D}', 'authenticated', $q$select count(*) from public.profiles$q$, '6');
select t.ex('Un admin NO puede suspender a otro admin ni a sí mismo', '{D}', 'authenticated', $q$select public.admin_set_user_suspended('{D}', true, 'x')$q$, 'ERR P0001%');
select t.eq('El listado de usuarios del admin incluye correos', '{D}', 'authenticated', $q$select count(*) from public.admin_list_users() where email like '%@prueba.mx'$q$, '6');
select t.ex('A (no admin) no puede listar usuarios con correos', '{A}', 'authenticated', $q$select * from public.admin_list_users()$q$, 'ERR 42501%');

-- =====================================================================
select t.grupo('2 Planes y suscripciones');
-- =====================================================================
select t.eq('Los 5 planes tienen precio mensual/anual/ahorro exactos', null, 'anon',
  $q$select string_agg(id || ':' || price_monthly_mxn || '/' || price_yearly_mxn || '/' || yearly_savings_mxn, ',' order by sort_order) from public.subscription_plans$q$,
  'basica:0/0/0,pro:29/290/58,vip:59/590/118,plata:149/1490/298,oro:299/2990/598');
select t.eq('Número de beneficios por plan (3,4,5,3,6)', null, 'anon',
  $q$select string_agg(cardinality(benefits)::text, ',' order by sort_order) from public.subscription_plans$q$, '3,4,5,3,6');
select t.eq('El nombre del plan Pro es "Huellita Pro" / "Plan Cuidadores"', null, 'anon',
  $q$select name || '|' || tagline from public.subscription_plans where id = 'pro'$q$, 'Huellita Pro|Plan Cuidadores');
select t.eq('A sin suscripción tiene Huellita Básica', '{A}', 'authenticated', $q$select public.my_entitlements() -> 'plan' ->> 'id'$q$, 'basica');
select t.eq('C (aliado) sin suscripción NO tiene plan', '{C}', 'authenticated', $q$select (public.my_entitlements() -> 'plan')::text$q$, 'null');
select t.ex('A NO puede insertarse una suscripción', '{A}', 'authenticated', $q$insert into public.subscriptions (user_id, plan_id) values ('{A}', 'vip')$q$, 'ERR 42501%');
select t.ex('A NO puede modificar suscripciones', '{A}', 'authenticated', $q$update public.subscriptions set plan_id = 'vip'$q$, 'ERR 42501%');
select t.ex('A NO puede asignarse un plan llamando a la función de admin', '{A}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'vip')$q$, 'ERR 42501%');
select t.ex('Un anónimo no puede ver my_entitlements', null, 'anon', $q$select public.my_entitlements()$q$, 'ERR 42501%');
select t.ex('D asigna Huellita Pro a A', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'pro', 'monthly', null, null, 'prueba')$q$, 'OK rows=1');
select t.eq('A ahora tiene Pro', '{A}', 'authenticated', $q$select public.my_entitlements() -> 'plan' ->> 'id'$q$, 'pro');
select t.eq('La asignación quedó en la bitácora de admin', '{D}', 'authenticated', $q$select count(*) from public.admin_audit_log where action = 'subscription_assign'$q$, '1');
select t.eq('A recibió una notificación de suscripción', null, 'service_role', $q$select count(*) from public.notifications where user_id = '{A}' and type = 'suscripcion'$q$, '1');
select t.ex('D NO puede asignar un plan de aliado a una dueña', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'plata')$q$, 'ERR P0001%');
select t.ex('D NO puede asignar un plan de dueños a un aliado', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{C}', 'pro')$q$, 'ERR P0001%');
select t.ex('Periodo inválido se rechaza', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'pro', 'semanal')$q$, 'ERR 22023%');
select t.ex('Plan inexistente se rechaza', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'diamante')$q$, 'ERR P0002%');
select t.ex('D cambia A a Huellita VIP', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'vip', 'yearly')$q$, 'OK rows=1');
select t.eq('Queda solo 1 suscripción activa y 1 reemplazada', null, 'service_role',
  $q$select count(*) filter (where status = 'active') || '/' || count(*) filter (where status = 'replaced') from public.subscriptions where user_id = '{A}'$q$, '1/1');
select t.eq('El historial registra asignación y cambio', null, 'service_role',
  $q$select string_agg(event, ',' order by id) from public.subscription_events where user_id = '{A}'$q$, 'assigned,changed');
select t.eq('VIP anual vence en ~1 año', null, 'service_role',
  $q$select (ends_at > now() + interval '360 days' and ends_at < now() + interval '370 days')::text from public.subscriptions where user_id = '{A}' and status = 'active'$q$, 'true');
select t.ex('La base impide 2 suscripciones activas del mismo usuario', null, 'service_role',
  $q$insert into public.subscriptions (user_id, plan_id) values ('{A}', 'pro')$q$, 'ERR 23505%');
select t.eq('B no ve las suscripciones de A', '{B}', 'authenticated', $q$select count(*) from public.subscriptions where user_id = '{A}'$q$, '0');
select t.ex('A cancela su suscripción', '{A}', 'authenticated', $q$select public.cancel_my_subscription()$q$, 'OK rows=1');
select t.eq('Tras cancelar, A vuelve a Huellita Básica', '{A}', 'authenticated', $q$select public.my_entitlements() -> 'plan' ->> 'id'$q$, 'basica');
select t.ex('Cancelar sin suscripción activa da error claro', '{A}', 'authenticated', $q$select public.cancel_my_subscription()$q$, 'ERR P0001%');
select t.eq('A ve su propio historial (2 suscripciones)', '{A}', 'authenticated', $q$select count(*) from public.subscriptions$q$, '2');
select t.ex('D asigna Pro a B', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{B}', 'pro')$q$, 'OK rows=1');
select t.ex('D renueva la suscripción de B (renovación manual)', '{D}', 'authenticated',
  $q$select public.admin_renew_subscription((select id from public.subscriptions where user_id = '{B}' and status = 'active'))$q$, 'OK rows=1');
select t.eq('La renovación extendió el vencimiento (~2 meses)', null, 'service_role',
  $q$select (ends_at > now() + interval '55 days')::text from public.subscriptions where user_id = '{B}' and status = 'active'$q$, 'true');
select t.ex('D modifica fechas de la suscripción de B', '{D}', 'authenticated',
  $q$select public.admin_set_subscription_dates((select id from public.subscriptions where user_id = '{B}' and status = 'active'), now(), now() + interval '10 days')$q$, 'OK rows=1');
select t.ex('D cancela la suscripción de B', '{D}', 'authenticated', $q$select public.admin_cancel_subscription('{B}', 'prueba')$q$, 'OK rows=1');
select t.ex('No se renueva una suscripción cancelada', '{D}', 'authenticated',
  $q$select public.admin_renew_subscription((select id from public.subscriptions where user_id = '{B}' limit 1))$q$, 'ERR P0001%');
select t.eq('Eventos de B: asignada, renovada, fechas, cancelada', null, 'service_role',
  $q$select string_agg(event, ',' order by id) from public.subscription_events where user_id = '{B}'$q$, 'assigned,renewed,dates_changed,cancelled');
-- Vencimiento automático
select t.ok('Una suscripción vencida deja de dar beneficios',
  (select count(*) from public.subscriptions) > 0);
insert into public.subscriptions (user_id, plan_id, starts_at, ends_at, status) values ('{F}', 'pro', now() - interval '40 days', now() - interval '10 days', 'active');
select t.eq('Con fecha vencida (aunque siga "active") F vuelve a Básica', '{F}', 'authenticated', $q$select public.my_entitlements() -> 'plan' ->> 'id'$q$, 'basica');
select t.eq('El proceso de vencimiento (cron) marca 1 suscripción como expirada', null, 'postgres', $q$select private.expire_subscriptions()$q$, '1');
select t.ex('Ni siquiera service_role puede llamar al proceso interno desde la API', null, 'service_role', $q$select private.expire_subscriptions()$q$, 'ERR 42501%');
delete from public.subscriptions where user_id = '{F}';

-- =====================================================================
select t.grupo('3 Mascotas, carnet y QR');
-- =====================================================================
select t.ex('A registra a Luna', '{A}', 'authenticated', $q$insert into public.pets (id, name, species, breed) values ('{P1}', 'Luna', 'perro', 'Mestiza')$q$, 'OK rows=1');
select t.eq('El dueño queda asignado automáticamente a A', null, 'service_role', $q$select owner_id::text from public.pets where id = '{P1}'$q$, '{A}');
select t.eq('B no ve las mascotas de A', '{B}', 'authenticated', $q$select count(*) from public.pets$q$, '0');
select t.ex('B NO puede modificar la mascota de A', '{B}', 'authenticated', $q$update public.pets set name = 'hack' where id = '{P1}'$q$, 'OK rows=0');
select t.ex('B NO puede borrar la mascota de A', '{B}', 'authenticated', $q$delete from public.pets where id = '{P1}'$q$, 'OK rows=0');
select t.ex('B NO puede crear una mascota a nombre de A', '{B}', 'authenticated', $q$insert into public.pets (owner_id, name, species) values ('{A}', 'Falsa', 'gato')$q$, 'ERR 42501%');
select t.ex('A NO puede "regalar" su mascota cambiando owner_id', '{A}', 'authenticated', $q$update public.pets set owner_id = '{B}' where id = '{P1}'$q$, 'ERR 42501%');
select t.eq('Un admin tampoco ve las mascotas ajenas (mínimo privilegio)', '{D}', 'authenticated', $q$select count(*) from public.pets$q$, '0');
select t.ex('Un anónimo NO puede leer mascotas', null, 'anon', $q$select * from public.pets$q$, 'ERR 42501%');
select t.ex('Peso negativo rechazado', '{A}', 'authenticated', $q$insert into public.pets (name, species, weight_kg) values ('X', 'perro', -1)$q$, 'ERR 23514%');
select t.ex('Especie inválida rechazada', '{A}', 'authenticated', $q$insert into public.pets (name, species) values ('X', 'dragon')$q$, 'ERR 23514%');
select t.ex('Fecha de nacimiento futura rechazada', '{A}', 'authenticated', $q$insert into public.pets (name, species, birth_date) values ('X', 'perro', current_date + 30)$q$, 'ERR 23514%');
select t.ex('A registra a Michi', '{A}', 'authenticated', $q$insert into public.pets (id, name, species) values ('{P2}', 'Michi', 'gato')$q$, 'OK rows=1');
select t.ex('A registra a Kiwi', '{A}', 'authenticated', $q$insert into public.pets (id, name, species) values ('{P3}', 'Kiwi', 'ave')$q$, 'OK rows=1');
-- Plan Básica: sin carnet
select t.ex('Con Básica, el carnet de salud está bloqueado en el servidor', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P1}', 'Rabia', current_date)$q$, 'ERR P0001%no incluye el carnet%');
select t.ex('D asigna Pro a A', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'pro')$q$, 'OK rows=1');
select t.ex('Con Pro: vacuna en mascota 1', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on, next_due_on) values ('{P1}', 'Rabia', current_date - 30, current_date + 335)$q$, 'OK rows=1');
select t.ex('Con Pro: desparasitación en mascota 2', '{A}', 'authenticated',
  $q$insert into public.pet_deworming (pet_id, product_name, applied_on) values ('{P2}', 'Antiparasitario', current_date)$q$, 'OK rows=1');
select t.ex('Con Pro: una mascota 3 supera el límite de 2 con carnet', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P3}', 'Vacuna', current_date)$q$, 'ERR P0001%2 mascota%');
select t.ex('Con Pro: más registros en una mascota que ya tiene carnet sí se permiten', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P1}', 'Parvovirus', current_date)$q$, 'OK rows=1');
select t.ex('Con Pro: las citas también cuentan para el límite', '{A}', 'authenticated',
  $q$insert into public.pet_appointments (pet_id, scheduled_at) values ('{P3}', now() + interval '3 days')$q$, 'ERR P0001%');
select t.ex('B NO puede añadir vacunas a la mascota de A', '{B}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P1}', 'Falsa', current_date)$q$, 'ERR 42501%');
select t.eq('B no ve el carnet de A', '{B}', 'authenticated', $q$select count(*) from public.pet_vaccinations$q$, '0');
select t.ex('Fecha de vacuna futura rechazada', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P1}', 'X', current_date + 60)$q$, 'ERR 23514%');
select t.ex('Próxima fecha anterior a la aplicación rechazada', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on, next_due_on) values ('{P1}', 'X', current_date, current_date - 5)$q$, 'ERR 23514%');
select t.ex('Con Pro NO hay placa QR', '{A}', 'authenticated', $q$insert into public.pet_qr_profiles (pet_id) values ('{P1}')$q$, 'ERR P0001%no incluye la placa QR%');
select t.ex('D asigna VIP a A', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'vip')$q$, 'OK rows=1');
select t.ex('Con VIP: carnet ilimitado (mascota 3)', '{A}', 'authenticated',
  $q$insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on) values ('{P3}', 'Vacuna aves', current_date)$q$, 'OK rows=1');
select t.ex('Con VIP: cita programada', '{A}', 'authenticated',
  $q$insert into public.pet_appointments (pet_id, kind, scheduled_at, clinic) values ('{P1}', 'consulta', now() + interval '3 days', 'Clínica de ejemplo')$q$, 'OK rows=1');
select t.ex('Con VIP: NO se puede elegir el token del QR', '{A}', 'authenticated',
  $q$insert into public.pet_qr_profiles (pet_id, public_token) values ('{P1}', 'a')$q$, 'ERR 42501%');
select t.ex('Con VIP: se crea la placa QR', '{A}', 'authenticated', $q$insert into public.pet_qr_profiles (pet_id, contact_name) values ('{P1}', 'Ana')$q$, 'OK rows=1');
insert into t.vars select 'tok1', public_token from public.pet_qr_profiles where pet_id = '{P1}';
select t.eq('El token es largo (64 caracteres hexadecimales)', '{A}', 'authenticated', $q$select length(public_token)::text from public.pet_qr_profiles$q$, '64');
select t.eq('Cualquiera con el QR ve el nombre de la mascota', null, 'anon',
  format($q$select public.get_public_pet_profile(%L) ->> 'name'$q$, (select v from t.vars where k = 'tok1')), 'Luna');
select t.eq('Por defecto NO se muestra el teléfono', null, 'anon',
  format($q$select public.get_public_pet_profile(%L) ->> 'contact_phone'$q$, (select v from t.vars where k = 'tok1')), '<null>');
select t.eq('El perfil público NO expone al dueño ni el correo', null, 'anon',
  format($q$select (public.get_public_pet_profile(%L)::text ~ '(owner|email|address|@)')::text$q$, (select v from t.vars where k = 'tok1')), 'false');
select t.ex('show_phone sin teléfono es rechazado', '{A}', 'authenticated', $q$update public.pet_qr_profiles set show_phone = true$q$, 'ERR 23514%');
select t.ex('A decide mostrar su teléfono de contacto', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set show_phone = true, contact_phone = '55 1234 5678', public_message = 'Si me encuentras, llámanos' where pet_id = '{P1}'$q$, 'OK rows=1');
select t.eq('Ahora el QR muestra el teléfono autorizado', null, 'anon',
  format($q$select public.get_public_pet_profile(%L) ->> 'contact_phone'$q$, (select v from t.vars where k = 'tok1')), '55 1234 5678');
select t.ex('A desactiva la placa', '{A}', 'authenticated', $q$update public.pet_qr_profiles set is_active = false$q$, 'OK rows=1');
select t.eq('Placa desactivada: el público no ve nada', null, 'anon',
  format($q$select (public.get_public_pet_profile(%L) is null)::text$q$, (select v from t.vars where k = 'tok1')), 'true');
select t.ex('A reactiva la placa', '{A}', 'authenticated', $q$update public.pet_qr_profiles set is_active = true$q$, 'OK rows=1');
select t.ex('B NO puede regenerar el token de la placa de A', '{B}', 'authenticated', $q$select public.regenerate_pet_qr_token('{P1}')$q$, 'ERR 42501%');
select t.ex('A regenera su token (por si se filtró)', '{A}', 'authenticated', $q$select public.regenerate_pet_qr_token('{P1}')$q$, 'OK rows=1');
select t.eq('El token anterior deja de funcionar', null, 'anon',
  format($q$select (public.get_public_pet_profile(%L) is null)::text$q$, (select v from t.vars where k = 'tok1')), 'true');
select t.eq('Un token mal formado devuelve nada (sin error)', null, 'anon', $q$select (public.get_public_pet_profile('abc') is null)::text$q$, 'true');
select t.eq('Un intento de inyección SQL en el token devuelve nada', null, 'anon',
  $q$select (public.get_public_pet_profile($x$' or '1'='1$x$) is null)::text$q$, 'true');
-- Etapa 4: foto pública de la placa
select t.ex('A elige una foto pública de SU carpeta', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{A}/foto1.jpg' where pet_id = '{P1}'$q$, 'OK rows=1');
select t.ex('A NO puede apuntar la foto a la carpeta de B', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{B}/foto1.jpg' where pet_id = '{P1}'$q$, 'ERR 23514%');
select t.ex('La ruta de la foto no admite «..» para salirse de la carpeta', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{A}/../{B}/foto1.jpg' where pet_id = '{P1}'$q$, 'ERR 23514%');
select t.ex('La ruta de la foto no admite «..» como nombre de archivo', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{A}/..' where pet_id = '{P1}'$q$, 'ERR 23514%');
select t.ex('La ruta de la foto no admite subcarpetas', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{A}/x/foto1.jpg' where pet_id = '{P1}'$q$, 'ERR 23514%');
select t.ex('B NO puede cambiar la foto pública de la placa de A', '{B}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{B}/foto1.jpg' where pet_id = '{P1}'$q$, 'OK rows=0');
select t.eq('Con show_photo apagado el público NO ve la foto', null, 'anon',
  format($q$select public.get_public_pet_profile(%L) ->> 'photo_path'$q$, (select public_token from public.pet_qr_profiles where pet_id = '{P1}')), '<null>');
select t.ex('A decide mostrar la foto', '{A}', 'authenticated', $q$update public.pet_qr_profiles set show_photo = true where pet_id = '{P1}'$q$, 'OK rows=1');
select t.eq('Con show_photo encendido el público ve SOLO la foto pública elegida', null, 'anon',
  format($q$select public.get_public_pet_profile(%L) ->> 'photo_path'$q$, (select public_token from public.pet_qr_profiles where pet_id = '{P1}')), '{A}/foto1.jpg');
select t.eq('La foto privada de la mascota nunca aparece en el perfil público', null, 'service_role',
  format($q$select (public.get_public_pet_profile(%L)::text like '%%pet-photos%%')::text$q$, (select public_token from public.pet_qr_profiles where pet_id = '{P1}')), 'false');
select t.eq('has_qr_plan: VIP = true', '{A}', 'authenticated', $q$select public.has_qr_plan()::text$q$, 'true');
select t.eq('has_qr_plan: Básica = false', '{B}', 'authenticated', $q$select public.has_qr_plan()::text$q$, 'false');
select t.ex('Un anónimo NO puede ejecutar has_qr_plan', null, 'anon', $q$select public.has_qr_plan()$q$, 'ERR 42501%');
-- Si el plan vence, la placa existente se conserva y se puede seguir editando, pero no se crean placas nuevas
select t.ex('D cancela el plan de A', '{D}', 'authenticated', $q$select public.admin_cancel_subscription('{A}', 'prueba de vencimiento')$q$, 'OK rows=1');
select t.ex('Plan vencido: la placa ya creada se puede seguir editando', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set public_message = 'Sigo aquí' where pet_id = '{P1}'$q$, 'OK rows=1');
select t.ex('Plan vencido: se puede cambiar la foto pública (sin exigir el plan)', '{A}', 'authenticated',
  $q$update public.pet_qr_profiles set qr_photo_path = '{A}/foto2.jpg' where pet_id = '{P1}'$q$, 'OK rows=1');
select t.ex('Plan vencido: NO se crea una placa nueva', '{A}', 'authenticated', $q$insert into public.pet_qr_profiles (pet_id) values ('{P3}')$q$, 'ERR P0001%no incluye la placa QR%');
select t.ex('D vuelve a asignar VIP a A', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{A}', 'vip')$q$, 'OK rows=1');
select t.ex('Un anónimo NO puede leer la tabla de placas', null, 'anon', $q$select * from public.pet_qr_profiles$q$, 'ERR 42501%');
select t.eq('B no ve las placas de A', '{B}', 'authenticated', $q$select count(*) from public.pet_qr_profiles$q$, '0');
select t.ex('A borra la mascota Michi: se borra su carnet en cascada', '{A}', 'authenticated', $q$delete from public.pets where id = '{P2}'$q$, 'OK rows=1');
select t.eq('El carnet de Michi desapareció', null, 'service_role', $q$select count(*) from public.pet_deworming where pet_id = '{P2}'$q$, '0');
-- Límite de mascotas por cuenta y suspensión
insert into public.pets (owner_id, name, species) select '{F}', 'm' || g, 'perro' from generate_series(1, 30) g;
select t.ex('Máximo 30 mascotas por cuenta', '{F}', 'authenticated', $q$insert into public.pets (name, species) values ('de más', 'perro')$q$, 'ERR P0001%');
select t.ex('D suspende a B', '{D}', 'authenticated', $q$select public.admin_set_user_suspended('{B}', true, 'prueba de abuso')$q$, 'OK rows=1');
select t.ex('Una cuenta suspendida NO puede crear mascotas', '{B}', 'authenticated', $q$insert into public.pets (name, species) values ('Bloqueada', 'gato')$q$, 'ERR 42501%');
select t.ex('Una cuenta suspendida NO puede editar su perfil', '{B}', 'authenticated', $q$update public.profiles set display_name = 'x' where id = '{B}'$q$, 'OK rows=0');
select t.ex('D reactiva a B', '{D}', 'authenticated', $q$select public.admin_set_user_suspended('{B}', false, 'resuelto')$q$, 'OK rows=1');
select t.ex('B reactivado puede crear mascotas de nuevo', '{B}', 'authenticated', $q$insert into public.pets (name, species) values ('Rocky', 'perro')$q$, 'OK rows=1');
select t.eq('La suspensión y reactivación quedaron en la bitácora', '{D}', 'authenticated', $q$select count(*) from public.admin_audit_log where action in ('user_suspend', 'user_reactivate')$q$, '2');

-- =====================================================================
select t.grupo('4 Aliados, directorio y promociones');
-- =====================================================================
select t.ex('C (aliado) registra su establecimiento', '{C}', 'authenticated',
  $q$insert into public.businesses (id, name, category, description, address) values ('{BIZ1}', 'Vet Cris', 'veterinaria', 'Atención general', 'Calle 1')$q$, 'OK rows=1');
select t.eq('Queda pendiente y sin verificar', null, 'service_role', $q$select status || '/' || verified::text from public.businesses where id = '{BIZ1}'$q$, 'pending/false');
select t.ex('A (cuenta de dueña) NO puede registrar un establecimiento', '{A}', 'authenticated',
  $q$insert into public.businesses (name, category) values ('Falso', 'tienda')$q$, 'ERR 42501%');
select t.ex('C NO puede aprobarse a sí mismo al crear', '{C}', 'authenticated',
  $q$insert into public.businesses (name, category, status) values ('Otro', 'tienda', 'approved')$q$, 'ERR 42501%');
select t.ex('C NO puede cambiar el estado de su negocio', '{C}', 'authenticated', $q$update public.businesses set status = 'approved' where id = '{BIZ1}'$q$, 'ERR 42501%');
select t.ex('C NO puede ponerse la etiqueta de verificado', '{C}', 'authenticated', $q$update public.businesses set verified = true where id = '{BIZ1}'$q$, 'ERR 42501%');
select t.ex('C NO puede cambiar el dueño del negocio', '{C}', 'authenticated', $q$update public.businesses set owner_id = '{E}' where id = '{BIZ1}'$q$, 'ERR 42501%');
select t.ex('C NO puede marcar su negocio como "demo"', '{C}', 'authenticated', $q$update public.businesses set is_demo = true where id = '{BIZ1}'$q$, 'ERR 42501%');
select t.eq('El directorio público solo muestra los 6 demo aprobados (no el pendiente de C)', null, 'anon', $q$select count(*) from public.directory_search()$q$, '6');
select t.eq('directory_get no devuelve un negocio pendiente', null, 'anon', $q$select (public.directory_get('{BIZ1}') is null)::text$q$, 'true');
select t.ex('Un anónimo NO puede leer la tabla de negocios directamente', null, 'anon', $q$select * from public.businesses$q$, 'ERR 42501%');
select t.eq('Búsqueda por texto', null, 'anon', $q$select count(*) from public.directory_search('Gatitos')$q$, '1');
select t.eq('Filtro por categoría', null, 'anon', $q$select count(*) from public.directory_search(null, 'tienda')$q$, '1');
select t.eq('Un comodín "%" se trata como texto literal, no como patrón', null, 'anon', $q$select count(*) from public.directory_search('%')$q$, '0');
select t.eq('Un texto de inyección SQL no devuelve ni rompe nada', null, 'anon',
  $q$select count(*) from public.directory_search($x$'; drop table public.profiles; --$x$)$q$, '0');
select t.eq('...y la tabla profiles sigue existiendo', null, 'service_role', $q$select count(*) from public.profiles$q$, '6');
select t.ex('Categoría inválida rechazada', null, 'anon', $q$select * from public.directory_search(null, 'x')$q$, 'ERR 22023%');
select t.ex('Orden inválido rechazado', null, 'anon', $q$select * from public.directory_search(null, null, 'x')$q$, 'ERR 22023%');
select t.ex('C NO puede aprobar negocios (función de admin)', '{C}', 'authenticated', $q$select public.admin_set_business_status('{BIZ1}', 'approved')$q$, 'ERR 42501%');
select t.ex('D aprueba el negocio de C', '{D}', 'authenticated', $q$select public.admin_set_business_status('{BIZ1}', 'approved')$q$, 'OK rows=1');
select t.eq('Ahora aparece en el directorio (7)', null, 'anon', $q$select count(*) from public.directory_search()$q$, '7');
select t.eq('directory_get ya lo devuelve', null, 'anon', $q$select public.directory_get('{BIZ1}') ->> 'name'$q$, 'Vet Cris');
select t.eq('directory_get no expone al dueño', null, 'anon', $q$select (public.directory_get('{BIZ1}') ? 'owner_id')::text$q$, 'false');
select t.eq('C recibió aviso de aprobación', null, 'service_role', $q$select count(*) from public.notifications where user_id = '{C}' and type = 'aviso'$q$, '1');
select t.ex('C registra un segundo negocio (queda pendiente)', '{C}', 'authenticated',
  $q$insert into public.businesses (id, name, category) values ('{BIZ2}', 'Tienda Cris', 'tienda')$q$, 'OK rows=1');
select t.ex('NO se puede verificar un negocio que no está aprobado', '{D}', 'authenticated', $q$select public.admin_set_business_verified('{BIZ2}', true)$q$, 'ERR P0001%');
select t.ex('C NO puede llamar a la verificación', '{C}', 'authenticated', $q$select public.admin_set_business_verified('{BIZ1}', true)$q$, 'ERR 42501%');
select t.ex('D verifica el negocio aprobado de C', '{D}', 'authenticated', $q$select public.admin_set_business_verified('{BIZ1}', true)$q$, 'OK rows=1');
select t.eq('Sin plan Oro, la etiqueta «verificado» NO se muestra (aunque un admin la haya puesto)', null, 'anon', $q$select verified::text from public.directory_search('Vet Cris')$q$, 'false');
select t.eq('...pero la verificación sigue guardada', null, 'service_role', $q$select verified::text from public.businesses where id = '{BIZ1}'$q$, 'true');
-- Beneficios por plan de aliado
select t.ex('Sin plan, C NO puede poner botón de WhatsApp', '{C}', 'authenticated',
  $q$update public.businesses set whatsapp_url = 'https://wa.me/5215512345678' where id = '{BIZ1}'$q$, 'ERR P0001%WhatsApp%');
select t.ex('Sin plan, C NO puede publicar promociones', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Descuento', current_date + 10)$q$, 'ERR P0001%');
select t.ex('C guarda teléfono y horario de su negocio', '{C}', 'authenticated',
  $q$update public.businesses set phone = '33 1234 5678', hours = '{"lun-vie": "9:00-18:00"}' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.eq('Sin plan, el público NO ve teléfono ni horario (solo nombre y dirección)', null, 'anon',
  $q$select ((public.directory_get('{BIZ1}') ->> 'phone') is null and (public.directory_get('{BIZ1}') -> 'hours')::text = '{}')::text$q$, 'true');
select t.eq('Sin plan: la ficha no es completa', null, 'anon', $q$select full_listing::text from public.directory_search('Vet Cris')$q$, 'false');
select t.ex('D asigna Huellita de Plata a C', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{C}', 'plata')$q$, 'OK rows=1');
select t.eq('Con Plata, el público ve teléfono y horario', null, 'anon',
  $q$select (public.directory_get('{BIZ1}') ->> 'phone' = '33 1234 5678' and public.directory_get('{BIZ1}') -> 'hours' ->> 'lun-vie' = '9:00-18:00')::text$q$, 'true');
select t.eq('Con Plata: la ficha es completa', null, 'anon', $q$select full_listing::text from public.directory_search('Vet Cris')$q$, 'true');
select t.ex('Plata: la primera promoción del mes se permite', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Descuento de apertura', current_date + 10)$q$, 'OK rows=1');
select t.ex('Plata: la segunda promoción del mes se bloquea', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Otro descuento', current_date + 10)$q$, 'ERR P0001%1 promoci%');
select t.ex('Plata: tampoco tiene botón de WhatsApp', '{C}', 'authenticated',
  $q$update public.businesses set whatsapp_url = 'https://wa.me/5215512345678' where id = '{BIZ1}'$q$, 'ERR P0001%WhatsApp%');
select t.ex('D cambia a C a Huellita de Oro', '{D}', 'authenticated', $q$select public.admin_assign_subscription('{C}', 'oro')$q$, 'OK rows=1');
select t.ex('Oro: promociones ilimitadas', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Segundo descuento', current_date + 20)$q$, 'OK rows=1');
select t.ex('Oro: formato de WhatsApp inválido rechazado', '{C}', 'authenticated',
  $q$update public.businesses set whatsapp_url = 'http://sitio-malicioso.com' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Oro: el botón de WhatsApp se permite', '{C}', 'authenticated',
  $q$update public.businesses set whatsapp_url = 'https://wa.me/5215512345678' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.eq('El directorio muestra el WhatsApp con plan Oro', null, 'anon', $q$select public.directory_get('{BIZ1}') ->> 'whatsapp_url'$q$, 'https://wa.me/5215512345678');
select t.eq('Las promociones activas se ven públicamente (2)', null, 'anon', $q$select jsonb_array_length(public.directory_get('{BIZ1}') -> 'promotions')::text$q$, '2');
select t.eq('Oro: aparece primero (posicionamiento prioritario)', null, 'anon', $q$select name from public.directory_search() limit 1$q$, 'Vet Cris');
select t.eq('Oro: marcado como prioritario', null, 'anon', $q$select is_priority::text from public.directory_search('Vet Cris')$q$, 'true');
select t.eq('Oro: la etiqueta «verificado» sí se muestra (búsqueda)', null, 'anon', $q$select verified::text from public.directory_search('Vet Cris')$q$, 'true');
select t.eq('Oro: la etiqueta «verificado» sí se muestra (ficha)', null, 'anon', $q$select public.directory_get('{BIZ1}') ->> 'verified'$q$, 'true');
select t.ex('D cancela el plan de C', '{D}', 'authenticated', $q$select public.admin_cancel_subscription('{C}')$q$, 'OK rows=1');
select t.eq('Sin plan, el teléfono guardado deja de mostrarse y las promociones se ocultan', null, 'anon',
  $q$select ((public.directory_get('{BIZ1}') ->> 'phone') is null and jsonb_array_length(public.directory_get('{BIZ1}') -> 'promotions') = 0
             and not (select has_promotion from public.directory_search('Vet Cris')))::text$q$, 'true');
select t.eq('Sin plan, el WhatsApp guardado deja de mostrarse', null, 'anon', $q$select (public.directory_get('{BIZ1}') ->> 'whatsapp_url') is null$q$, 'true');
select t.eq('...aunque el dato sigue guardado', null, 'service_role', $q$select (whatsapp_url is not null)::text from public.businesses where id = '{BIZ1}'$q$, 'true');
select t.eq('...y pierde la prioridad', null, 'anon', $q$select is_priority::text from public.directory_search('Vet Cris')$q$, 'false');
select t.eq('...y deja de mostrarse la etiqueta «verificado»', null, 'anon', $q$select public.directory_get('{BIZ1}') ->> 'verified'$q$, 'false');
-- Aislamiento entre aliados
select t.ex('E NO puede editar el negocio de C', '{E}', 'authenticated', $q$update public.businesses set name = 'hack' where id = '{BIZ1}'$q$, 'OK rows=0');
select t.ex('E NO puede borrar el negocio de C', '{E}', 'authenticated', $q$delete from public.businesses where id = '{BIZ1}'$q$, 'OK rows=0');
select t.eq('E no ve los negocios de C', '{E}', 'authenticated', $q$select count(*) from public.businesses$q$, '0');
select t.ex('E NO puede poner promociones en el negocio de C', '{E}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Falsa', current_date + 5)$q$, 'ERR %');
select t.eq('...y no se creó ninguna promoción falsa', null, 'service_role', $q$select count(*) from public.business_promotions where title = 'Falsa'$q$, '0');
select t.ex('Nadie puede publicar promociones en los negocios demo', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) select id, 'x', current_date + 5 from public.businesses where is_demo limit 1$q$, 'OK rows=0');
select t.ex('Las fechas de una promoción deben ser coherentes', '{C}', 'authenticated',
  $q$insert into public.business_promotions (business_id, title, ends_on) values ('{BIZ1}', 'Mala', current_date - 5)$q$, 'ERR %');
select t.ex('Teléfono con formato inválido rechazado', '{C}', 'authenticated', $q$update public.businesses set phone = 'abc' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Más de 6 fotos rechazado', '{C}', 'authenticated',
  $q$update public.businesses set photo_paths = array['a','b','c','d','e','f','g'] where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('D (admin) puede editar el negocio de C', '{D}', 'authenticated', $q$update public.businesses set description = 'Editado por admin' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.ex('Un admin tampoco cambia el estado con un UPDATE directo (solo por función)', '{D}', 'authenticated', $q$update public.businesses set status = 'suspended' where id = '{BIZ1}'$q$, 'ERR 42501%');
select t.ex('D suspende el negocio por función', '{D}', 'authenticated', $q$select public.admin_set_business_status('{BIZ1}', 'suspended')$q$, 'OK rows=1');
select t.eq('Suspender quita la verificación', null, 'service_role', $q$select verified::text from public.businesses where id = '{BIZ1}'$q$, 'false');
select t.eq('Un negocio suspendido sale del directorio (6)', null, 'anon', $q$select count(*) from public.directory_search()$q$, '6');
select t.ex('D reaprueba el negocio', '{D}', 'authenticated', $q$select public.admin_set_business_status('{BIZ1}', 'approved')$q$, 'OK rows=1');
insert into public.businesses (owner_id, name, category, status) select '{C}', 'extra' || g, 'otro', 'pending' from generate_series(1, 3) g;
select t.ex('Máximo 5 establecimientos por cuenta', '{C}', 'authenticated', $q$insert into public.businesses (name, category) values ('de más', 'otro')$q$, 'ERR P0001%');

-- ---- Etapa 5: imágenes, horario y estadísticas del directorio ----
select t.ex('Logotipo en la carpeta propia: permitido', '{C}', 'authenticated', $q$update public.businesses set logo_path = '{C}/logo-1.jpg' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.ex('Logotipo en la carpeta de OTRA cuenta: rechazado', '{C}', 'authenticated', $q$update public.businesses set logo_path = '{E}/logo.jpg' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Logotipo con «..» (recorrido de carpetas): rechazado', '{C}', 'authenticated', $q$update public.businesses set logo_path = '{C}/..' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Logotipo dentro de una subcarpeta: rechazado', '{C}', 'authenticated', $q$update public.businesses set logo_path = '{C}/a/b.jpg' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Logotipo con una dirección web: rechazado', '{C}', 'authenticated', $q$update public.businesses set logo_path = 'https://sitio-malicioso.com/x.jpg' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Fotos en la carpeta propia: permitido', '{C}', 'authenticated', $q$update public.businesses set photo_paths = array['{C}/f1.jpg', '{C}/f2.png'] where id = '{BIZ1}'$q$, 'OK rows=1');
select t.ex('Una foto de OTRA cuenta entre las propias: rechazado', '{C}', 'authenticated', $q$update public.businesses set photo_paths = array['{C}/f1.jpg', '{E}/f2.png'] where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Un admin tampoco puede apuntar a archivos de otra cuenta', '{D}', 'authenticated', $q$update public.businesses set logo_path = '{E}/logo.jpg' where id = '{BIZ1}'$q$, 'ERR 23514%');
alter table public.businesses disable trigger tp_guard;                       -- (se simula un dato antiguo, anterior a esta validación)
update public.businesses set logo_path = 'legado/x.jpg' where id = '{BIZ1}';
alter table public.businesses enable trigger tp_guard;
select t.eq('(preparación) el valor antiguo quedó guardado', null, 'service_role', $q$select logo_path from public.businesses where id = '{BIZ1}'$q$, 'legado/x.jpg');
select t.ex('Un valor antiguo no bloquea editar OTROS campos (solo se valida lo que cambia)', '{C}', 'authenticated', $q$update public.businesses set description = 'Texto nuevo' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.eq('...y el logotipo antiguo sigue ahí tras editar otro campo', null, 'service_role', $q$select logo_path from public.businesses where id = '{BIZ1}'$q$, 'legado/x.jpg');
update public.businesses set logo_path = null, photo_paths = '{}' where id = '{BIZ1}';
select t.ex('Horario por días en texto: permitido', '{C}', 'authenticated', $q$update public.businesses set hours = '{"lun": "09:00-18:00", "dom": "Cerrado"}' where id = '{BIZ1}'$q$, 'OK rows=1');
select t.ex('Horario con valores anidados: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = '{"lun": {"a": "1"}}' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Horario con un número como valor: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = '{"lun": 9}' where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Horario con día demasiado largo: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = jsonb_build_object(repeat('x', 21), '9') where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Horario con texto demasiado largo: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = jsonb_build_object('lun', repeat('x', 61)) where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Horario con más de 10 entradas: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = (select jsonb_object_agg('d' || g, '9') from generate_series(1, 11) g) where id = '{BIZ1}'$q$, 'ERR 23514%');
select t.ex('Horario que no es un objeto: rechazado', '{C}', 'authenticated', $q$update public.businesses set hours = '["lun"]' where id = '{BIZ1}'$q$, 'ERR 23514%');

-- Estadísticas del directorio
select t.ok('La tabla de estadísticas NO guarda IP ni identidad de nadie',
  (select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_schema = 'public' and table_name = 'business_daily_stats') = 'business_id,day,views,map_clicks',
  (select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_schema = 'public' and table_name = 'business_daily_stats'));
select t.ex('Un visitante cuenta como 1 visita a la ficha', null, 'anon', $q$select public.directory_track('{BIZ1}', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.10"}');
select t.eq('...queda 1 visita', null, 'service_role', $q$select views::text from public.business_daily_stats where business_id = '{BIZ1}'$q$, '1');
select t.ex('El mismo visitante, el mismo día, no suma otra visita (y no recibe error)', null, 'anon', $q$select public.directory_track('{BIZ1}', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.10"}');
select t.eq('...sigue en 1', null, 'service_role', $q$select views::text from public.business_daily_stats where business_id = '{BIZ1}'$q$, '1');
select t.ex('OTRO visitante sí suma', null, 'anon', $q$select public.directory_track('{BIZ1}', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.11"}');
select t.eq('...ahora hay 2 visitas', null, 'service_role', $q$select views::text from public.business_daily_stats where business_id = '{BIZ1}'$q$, '2');
select public.directory_track('{BIZ1}', 'map') from (select set_config('request.headers', '{"cf-connecting-ip":"203.0.113.10"}', true)) s;
select public.directory_track('{BIZ1}', 'map') from (select set_config('request.headers', '{"cf-connecting-ip":"203.0.113.10"}', true)) s;
select public.directory_track('{BIZ1}', 'map') from (select set_config('request.headers', '{"cf-connecting-ip":"203.0.113.10"}', true)) s;
select public.directory_track('{BIZ1}', 'map') from (select set_config('request.headers', '{"cf-connecting-ip":"203.0.113.10"}', true)) s;
select t.eq('Los clics en «Cómo llegar» de un visitante se limitan a 3 por día', null, 'service_role', $q$select map_clicks::text from public.business_daily_stats where business_id = '{BIZ1}'$q$, '3');
select t.ex('Un evento desconocido se ignora sin error', null, 'anon', $q$select public.directory_track('{BIZ1}', 'borrar')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.12"}');
select t.ex('Un establecimiento inexistente se ignora sin error', null, 'anon', $q$select public.directory_track('99999999-0000-4000-8000-000000000000', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.12"}');
select t.ex('Un establecimiento pendiente no cuenta visitas', null, 'anon', $q$select public.directory_track('{BIZ2}', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.12"}');
select public.directory_track((select id from public.businesses where is_demo limit 1), 'view');   -- (superusuario: la función ignora las fichas de demostración)
select t.eq('...no se creó ninguna fila de más', null, 'service_role', $q$select count(*)::text from public.business_daily_stats$q$, '1');
select t.ex('Las visitas del propio dueño no cuentan', '{C}', 'authenticated', $q$select public.directory_track('{BIZ1}', 'view')$q$, 'OK rows=1', '{"cf-connecting-ip":"203.0.113.50"}');
select t.eq('...seguimos en 2 visitas', null, 'service_role', $q$select views::text from public.business_daily_stats where business_id = '{BIZ1}'$q$, '2');
select t.eq('C ve las estadísticas de su negocio', '{C}', 'authenticated', $q$select views || '/' || map_clicks from public.business_daily_stats where business_id = '{BIZ1}'$q$, '2/3');
select t.eq('E (otro aliado) NO ve las estadísticas de C', '{E}', 'authenticated', $q$select count(*) from public.business_daily_stats$q$, '0');
select t.eq('B (dueño de mascota) NO ve estadísticas', '{B}', 'authenticated', $q$select count(*) from public.business_daily_stats$q$, '0');
select t.eq('D (admin) ve las estadísticas', '{D}', 'authenticated', $q$select count(*) from public.business_daily_stats$q$, '1');
select t.ex('Un anónimo NO puede leer las estadísticas', null, 'anon', $q$select * from public.business_daily_stats$q$, 'ERR 42501%');
select t.ex('C NO puede inflar sus estadísticas (insertar)', '{C}', 'authenticated', $q$insert into public.business_daily_stats (business_id, day, views) values ('{BIZ1}', current_date - 1, 999)$q$, 'ERR 42501%');
select t.ex('C NO puede editar sus estadísticas', '{C}', 'authenticated', $q$update public.business_daily_stats set views = 999 where business_id = '{BIZ1}'$q$, 'ERR 42501%');
select t.ex('C NO puede borrar sus estadísticas', '{C}', 'authenticated', $q$delete from public.business_daily_stats where business_id = '{BIZ1}'$q$, 'ERR 42501%');

-- =====================================================================
select t.grupo('5 Denuncias anónimas');
-- =====================================================================
select t.ok('La tabla de denuncias NO tiene columnas que identifiquen a quien reporta',
  (select count(*) from information_schema.columns where table_schema = 'public' and table_name = 'complaints'
     and column_name ~ '(user|owner|email|phone|reporter|session|^ip$|ip_|_ip|address)') = 0,
  (select string_agg(column_name, ',') from information_schema.columns where table_schema = 'public' and table_name = 'complaints'));
-- ---- Solo la función segura del servidor puede registrar denuncias (Etapa 6) ----
select t.ex('Un anónimo NO puede registrar denuncias llamando a la base de datos (debe pasar por Turnstile)', null, 'anon', $q$select public.submit_complaint('abandono', repeat('Un perro abandonado en la calle. ', 2), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 42501%');
select t.ex('Un usuario con sesión tampoco', '{A}', 'authenticated', $q$select public.submit_complaint('abandono', repeat('Un perro abandonado en la calle. ', 2), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 42501%');
select t.ex('Ni siquiera un administrador', '{D}', 'authenticated', $q$select public.submit_complaint('abandono', repeat('Un perro abandonado en la calle. ', 2), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede usar el paso previo (consumir cupos de otros)', null, 'anon', $q$select public.complaint_precheck('203.0.113.9', 0)$q$, 'ERR 42501%');
select t.ex('Un usuario con sesión tampoco', '{A}', 'authenticated', $q$select public.complaint_precheck('203.0.113.9', 0)$q$, 'ERR 42501%');
select t.eq('Solo existe la versión nueva de submit_complaint (la anterior, pública, se eliminó)', null, 'service_role',
  $q$select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = 'submit_complaint'$q$, '1');
select t.ex('Un anónimo NO puede insertar denuncias directamente', null, 'anon',
  $q$insert into public.complaints (tracking_code, type, description, approx_date, state, municipality) values ('TP-AAAA-AAAA', 'otra', repeat('x', 40), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 42501%');
select t.ex('Un usuario con sesión tampoco puede insertar directamente', '{A}', 'authenticated',
  $q$insert into public.complaints (tracking_code, type, description, approx_date, state, municipality) values ('TP-AAAA-AAAA', 'otra', repeat('x', 40), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede leer denuncias', null, 'anon', $q$select * from public.complaints$q$, 'ERR 42501%');
select t.eq('Un usuario normal ve 0 denuncias', '{A}', 'authenticated', $q$select count(*) from public.complaints$q$, '0');

-- ---- La función segura (service_role) ----
select t.eq('La función segura registra una denuncia y devuelve un código de seguimiento', null, 'service_role',
  $q$select public.submit_complaint('maltrato_fisico', repeat('Descripción de los hechos. ', 3), current_date, 'Jalisco', 'Guadalajara', 'Parque central')$q$, 'TP-%');
insert into t.vars select 'c1', tracking_code from public.complaints order by created_at limit 1;
select t.ok('El código tiene el formato TP-XXXX-XXXX (sin caracteres confusos)', (select v from t.vars where k = 'c1') ~ '^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$', (select v from t.vars where k = 'c1'));
select t.ex('Descripción muy corta rechazada', null, 'service_role', $q$select public.submit_complaint('abandono', 'corta', current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 22023%');
select t.ex('Tipo inválido rechazado', null, 'service_role', $q$select public.submit_complaint('hackeo', repeat('x', 40), current_date, 'Jalisco', 'Zapopan')$q$, 'ERR 22023%');
select t.ex('Fecha futura rechazada', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date + 30, 'Jalisco', 'Zapopan')$q$, 'ERR 22023%');
select t.ex('Falta el municipio', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', '')$q$, 'ERR 22023%');
select t.ex('Estado de más de 80 caracteres rechazado con mensaje claro', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, repeat('e', 81), 'Zapopan')$q$, 'ERR 22023%');
select t.ex('Referencia del lugar de más de 300 caracteres rechazada', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', repeat('r', 301))$q$, 'ERR 22023%');
select t.ex('Más de 3 fotos rechazado', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', null, null, array['11111111-1111-4111-8111-111111111111/1.jpg','11111111-1111-4111-8111-111111111111/2.jpg','11111111-1111-4111-8111-111111111111/3.jpg','11111111-1111-4111-8111-111111111111/3.jpg'])$q$, 'ERR 22023%');
select t.ex('Ruta de foto con ".." rechazada', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', null, null, array['../../etc/passwd'])$q$, 'ERR 22023%');
select t.ex('Rutas de otra carpeta rechazadas por la función', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', null, null, array['evidencia/1.jpg'])$q$, 'ERR 22023%');
select t.ex('Extensión distinta de .jpg rechazada', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', null, null, array['11111111-1111-4111-8111-111111111111/1.png'])$q$, 'ERR 22023%');
select t.ex('Una denuncia con 2 fotos válidas se registra', null, 'service_role', $q$select public.submit_complaint('abandono', repeat('x', 40), current_date, 'Jalisco', 'Zapopan', null, null, array['11111111-1111-4111-8111-111111111111/1.jpg','11111111-1111-4111-8111-111111111111/2.jpg'])$q$, 'OK rows=1');
select t.eq('...y guarda sus 2 rutas', null, 'postgres', $q$select max(cardinality(photo_paths))::text from public.complaints$q$, '2');

-- ---- Paso previo: límites por visitante (la IP llega como parámetro, no se lee de cabeceras que el navegador pueda falsear) ----
select t.ex('Paso previo 1 de 5 desde una misma IP', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'OK rows=1');
select t.ex('Paso previo 2 de 5', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'OK rows=1');
select t.ex('Paso previo 3 de 5', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 1)$q$, 'OK rows=1');
select t.ex('Paso previo 4 de 5', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'OK rows=1');
select t.ex('Paso previo 5 de 5', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'OK rows=1');
select t.ex('Envío 6: bloqueado por exceso de envíos', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'ERR P0001%Demasiadas%');
select t.ex('Cambiar la cabecera x-forwarded-for NO evita el límite (se usa la IP que reporta el servidor)', null, 'service_role', $q$select public.complaint_precheck('10.0.0.9', 0)$q$, 'ERR P0001%Demasiadas%', '{"x-forwarded-for":"1.2.3.4","cf-connecting-ip":"5.6.7.8"}');
select t.ex('Otra IP distinta sí puede enviar', null, 'service_role', $q$select public.complaint_precheck('10.0.0.10', 0)$q$, 'OK rows=1');
select t.ex('Más de 3 fotos rechazado en el paso previo', null, 'service_role', $q$select public.complaint_precheck('10.0.0.11', 4)$q$, 'ERR 22023%');
select t.ex('Fotos negativas rechazadas', null, 'service_role', $q$select public.complaint_precheck('10.0.0.11', -1)$q$, 'ERR 22023%');
select t.eq('No se guarda la IP en ninguna parte (solo hashes sin la IP)', null, 'postgres',
  $q$select count(*) from private.rate_limits where key like '%10.0.0.%'$q$, '0');
select t.eq('Sin IP conocida se usa una huella común (no se deja pasar sin límite)', null, 'service_role',
  $q$select count(*) from (select public.complaint_precheck('', 0) from generate_series(1, 5)) x$q$, '5');
select t.ex('...y la sexta sin IP también se bloquea', null, 'service_role', $q$select public.complaint_precheck(null, 0)$q$, 'ERR P0001%Demasiadas%');
-- Topes globales (se preparan los contadores como administrador de la base de datos)
insert into private.rate_limits (bucket, key, window_start, hits) values ('complaint_photo_g', 'all', date_trunc('day', now()), 99)
  on conflict (bucket, key, window_start) do update set hits = 99;
select t.ex('Tope global de reportes con fotos: el 100.º pasa', null, 'service_role', $q$select public.complaint_precheck('10.0.1.1', 1)$q$, 'OK rows=1');
select t.ex('...el 101.º con fotos se bloquea', null, 'service_role', $q$select public.complaint_precheck('10.0.1.2', 1)$q$, 'ERR P0001%Demasiadas%');
select t.ex('...pero un reporte sin fotos todavía pasa', null, 'service_role', $q$select public.complaint_precheck('10.0.1.3', 0)$q$, 'OK rows=1');
insert into private.rate_limits (bucket, key, window_start, hits) values ('complaint_g', 'all', date_trunc('day', now()), 299)
  on conflict (bucket, key, window_start) do update set hits = 299;
select t.ex('Tope global diario de reportes: el 300.º pasa', null, 'service_role', $q$select public.complaint_precheck('10.0.2.1', 0)$q$, 'OK rows=1');
select t.ex('...el 301.º se bloquea para todos', null, 'service_role', $q$select public.complaint_precheck('10.0.2.2', 0)$q$, 'ERR P0001%Demasiadas%');
delete from private.rate_limits where bucket in ('complaint_g', 'complaint_photo_g');
-- Cuota de almacenamiento de evidencias
insert into storage.objects (bucket_id, name, metadata) values ('complaint-evidence', 'cuota/1.jpg', '{"size": 400000000}');
select t.ex('Si las evidencias ya ocupan demasiado espacio, ya no se reciben fotos', null, 'service_role', $q$select public.complaint_precheck('10.0.3.1', 1)$q$, 'ERR P0001%no podemos recibir fotograf%');
select t.ex('...pero los reportes sin fotos siguen entrando', null, 'service_role', $q$select public.complaint_precheck('10.0.3.2', 0)$q$, 'OK rows=1');
delete from storage.objects where bucket_id = 'complaint-evidence' and name = 'cuota/1.jpg';
select t.ex('Con espacio libre vuelven a recibirse fotos', null, 'service_role', $q$select public.complaint_precheck('10.0.3.3', 1)$q$, 'OK rows=1');
delete from private.rate_limits where bucket in ('complaint_g', 'complaint_photo_g');

-- Seguimiento
select t.eq('El código permite consultar el estado', null, 'anon',
  format($q$select public.track_complaint(%L) ->> 'status'$q$, (select v from t.vars where k = 'c1')), 'recibida', '{"x-forwarded-for":"10.0.0.20"}');
select t.eq('El código funciona en minúsculas', null, 'anon',
  format($q$select public.track_complaint(lower(%L)) ->> 'status'$q$, (select v from t.vars where k = 'c1')), 'recibida', '{"x-forwarded-for":"10.0.0.20"}');
select t.eq('Un código inexistente devuelve nada', null, 'anon', $q$select (public.track_complaint('TP-ZZZZ-ZZZZ') is null)::text$q$, 'true', '{"x-forwarded-for":"10.0.0.20"}');
select t.eq('Un código mal formado devuelve nada (sin error)', null, 'anon', $q$select (public.track_complaint($x$' or 1=1 --$x$) is null)::text$q$, 'true');
select t.eq('D (admin) ve las denuncias', '{D}', 'authenticated', $q$select count(*) >= 2 from public.complaints$q$, 'true');
select t.ex('A (usuaria normal) NO puede cambiar el estado de denuncias', '{A}', 'authenticated', $q$update public.complaints set status = 'cerrada'$q$, 'OK rows=0');
select t.ex('D gestiona la denuncia: estado, prioridad, notas y atendida', '{D}', 'authenticated',
  format($q$update public.complaints set status = 'en_revision', priority = 'alta', internal_notes = 'nota privada del equipo', public_update = 'Estamos revisando tu reporte', attended = true where tracking_code = %L$q$,
         (select v from t.vars where k = 'c1')), 'OK rows=1');
select t.eq('Se registró la fecha de atención', null, 'service_role',
  format($q$select (attended_at is not null)::text from public.complaints where tracking_code = %L$q$, (select v from t.vars where k = 'c1')), 'true');
select t.eq('El cambio quedó en la bitácora', '{D}', 'authenticated', $q$select count(*) from public.admin_audit_log where action = 'complaint_update'$q$, '1');
select t.eq('Quien reportó ve el mensaje público actualizado', null, 'anon',
  format($q$select public.track_complaint(%L) ->> 'public_update'$q$, (select v from t.vars where k = 'c1')), 'Estamos revisando tu reporte', '{"x-forwarded-for":"10.0.0.21"}');
select t.eq('...pero NUNCA las notas internas', null, 'anon',
  format($q$select (public.track_complaint(%L)::text like '%%nota privada%%')::text$q$, (select v from t.vars where k = 'c1')), 'false', '{"x-forwarded-for":"10.0.0.21"}');
select t.ex('Ni un admin puede editar el texto original de la denuncia (integridad)', '{D}', 'authenticated', $q$update public.complaints set description = 'alterada'$q$, 'ERR 42501%');
select t.ex('Estado inválido rechazado', '{D}', 'authenticated', $q$update public.complaints set status = 'borrada'$q$, 'ERR 23514%');
select t.eq('A no ve la bitácora de administración', '{A}', 'authenticated', $q$select count(*) from public.admin_audit_log$q$, '0');
select t.ex('A NO puede escribir en la bitácora', '{A}', 'authenticated', $q$insert into public.admin_audit_log (action) values ('falso')$q$, 'ERR 42501%');

-- =====================================================================
select t.grupo('6 Chat de atención al cliente');
-- =====================================================================
select t.ex('A abre una conversación', '{A}', 'authenticated', $q$insert into public.conversations (id, subject) values ('{CONV}', 'Duda sobre mi plan')$q$, 'OK rows=1');
select t.ex('A NO puede abrir una conversación a nombre de B', '{A}', 'authenticated', $q$insert into public.conversations (user_id, subject) values ('{B}', 'Falsa')$q$, 'ERR 42501%');
select t.ex('A escribe un mensaje', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'Hola, tengo una duda')$q$, 'OK rows=1');
select t.eq('El rol del remitente lo fija el servidor: usuario', null, 'service_role', $q$select sender_role from public.messages where body = 'Hola, tengo una duda'$q$, 'user');
select t.ex('A NO puede hacerse pasar por personal (sender_role)', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body, sender_role) values ('{CONV}', 'x', 'staff')$q$, 'ERR 42501%');
select t.ex('A NO puede falsificar el remitente (sender_id)', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body, sender_id) values ('{CONV}', 'x', '{B}')$q$, 'ERR 42501%');
select t.eq('B no ve la conversación de A', '{B}', 'authenticated', $q$select count(*) from public.conversations$q$, '0');
select t.eq('B no ve los mensajes de A', '{B}', 'authenticated', $q$select count(*) from public.messages$q$, '0');
select t.ex('B NO puede escribir en la conversación de A', '{B}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'intruso')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede leer conversaciones', null, 'anon', $q$select * from public.conversations$q$, 'ERR 42501%');
select t.eq('D (admin) ve la conversación', '{D}', 'authenticated', $q$select count(*) from public.conversations$q$, '1');
select t.eq('Bandeja de admin: 1 conversación sin responder', '{D}', 'authenticated', $q$select public.admin_dashboard_stats() ->> 'conversations_unanswered'$q$, '1');
select t.ex('D responde', '{D}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'Hola Ana, con gusto te ayudamos')$q$, 'OK rows=1');
select t.eq('La respuesta queda marcada como del equipo', null, 'service_role', $q$select sender_role from public.messages where body like 'Hola Ana%'$q$, 'staff');
select t.eq('La conversación pasa a "respondida"', null, 'service_role', $q$select last_sender from public.conversations where id = '{CONV}'$q$, 'staff');
select t.eq('Bandeja de admin: 0 sin responder', '{D}', 'authenticated', $q$select public.admin_dashboard_stats() ->> 'conversations_unanswered'$q$, '0');
select t.eq('A recibe una notificación de mensaje nuevo', '{A}', 'authenticated', $q$select count(*) from public.notifications where type = 'mensaje'$q$, '1');
select t.eq('A ve ambos mensajes', '{A}', 'authenticated', $q$select count(*) from public.messages$q$, '2');
select t.ex('Los mensajes no se pueden editar', '{A}', 'authenticated', $q$update public.messages set body = 'cambiado'$q$, 'ERR 42501%');
select t.ex('Los mensajes no se pueden borrar', '{A}', 'authenticated', $q$delete from public.messages$q$, 'ERR 42501%');
select t.ex('A NO puede cambiar el asunto de la conversación', '{A}', 'authenticated', $q$update public.conversations set subject = 'otro'$q$, 'ERR 42501%');
select t.ex('Estado de conversación inválido rechazado', '{A}', 'authenticated', $q$update public.conversations set status = 'hackeada'$q$, 'ERR 23514%');
select t.ex('A cierra la conversación', '{A}', 'authenticated', $q$update public.conversations set status = 'cerrada' where id = '{CONV}'$q$, 'OK rows=1');
select t.ex('En una conversación cerrada el usuario no puede escribir', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'sigo aquí')$q$, 'ERR P0001%cerrada%');
select t.ex('El equipo puede responder y la reabre', '{D}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'Reabrimos tu caso')$q$, 'OK rows=1');
select t.eq('La conversación quedó abierta de nuevo', null, 'service_role', $q$select status from public.conversations where id = '{CONV}'$q$, 'abierta');
select t.ex('A escribe de nuevo', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'Gracias')$q$, 'OK rows=1');
select t.eq('Vuelve a aparecer como pendiente para el admin', '{D}', 'authenticated', $q$select public.admin_dashboard_stats() ->> 'conversations_unanswered'$q$, '1');
insert into public.messages (conversation_id, sender_id, body) select '{CONV}', '{A}', 'spam' || g from generate_series(1, 20) g;
select t.ex('Límite de mensajes seguidos (anti-spam)', '{A}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'otro más')$q$, 'ERR P0001%demasiados%');
insert into public.conversations (user_id, subject) select '{F}', 'Consulta número ' || g from generate_series(1, 10) g;
select t.ex('Máximo 10 conversaciones abiertas por persona', '{F}', 'authenticated', $q$insert into public.conversations (subject) values ('una más')$q$, 'ERR P0001%');

-- ---- Etapa 7: conversación atómica, tope diario, reapertura, aislamiento ----
select t.ex('B inicia una conversación con su primer mensaje (una sola operación)', '{B}', 'authenticated',
  $q$select public.start_conversation('  Problema con mi QR  ', '  Mi placa no abre  ')$q$, 'OK rows=1');
select t.eq('start_conversation: crea una sola conversación', '{B}', 'authenticated',
  $q$select (count(*) = 1)::text from public.conversations where subject = 'Problema con mi QR'$q$, 'true');
select t.eq('start_conversation: guarda asunto y mensaje sin espacios sobrantes', '{B}', 'authenticated',
  $q$select m.body from public.messages m join public.conversations c on c.id = m.conversation_id where c.subject = 'Problema con mi QR'$q$, 'Mi placa no abre');
select t.eq('start_conversation: el mensaje queda como de la persona (user)', null, 'service_role',
  $q$select m.sender_role from public.messages m join public.conversations c on c.id = m.conversation_id where c.subject = 'Problema con mi QR'$q$, 'user');
select t.eq('start_conversation: la conversación es de quien la inició', null, 'service_role',
  $q$select user_id::text from public.conversations where subject = 'Problema con mi QR'$q$, '{B}');
select t.eq('start_conversation: devuelve el id (uuid) de la conversación nueva', '{B}', 'authenticated',
  $q$select (public.start_conversation('Segundo asunto', 'hola')::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')::text$q$, 'true');
select t.ex('start_conversation: un anónimo NO puede llamarla', null, 'anon', $q$select public.start_conversation('Hola amigos', 'x')$q$, 'ERR 42501%');
select t.ex('start_conversation: asunto demasiado corto → mensaje en español', '{B}', 'authenticated', $q$select public.start_conversation('ab', 'hola')$q$, 'ERR P0001%asunto%');
select t.ex('start_conversation: asunto vacío (solo espacios)', '{B}', 'authenticated', $q$select public.start_conversation('     ', 'hola')$q$, 'ERR P0001%asunto%');
select t.ex('start_conversation: asunto nulo', '{B}', 'authenticated', $q$select public.start_conversation(null, 'hola')$q$, 'ERR P0001%asunto%');
select t.ex('start_conversation: mensaje vacío', '{B}', 'authenticated', $q$select public.start_conversation('Asunto válido', '   ')$q$, 'ERR P0001%mensaje%');
select t.ex('start_conversation: mensaje nulo', '{B}', 'authenticated', $q$select public.start_conversation('Asunto válido', null)$q$, 'ERR P0001%mensaje%');
select t.ex('start_conversation: mensaje de más de 2000 caracteres', '{B}', 'authenticated', $q$select public.start_conversation('Asunto válido', repeat('a', 2001))$q$, 'ERR P0001%mensaje%');
select t.ex('start_conversation: mensaje de exactamente 2000 caracteres sí', '{B}', 'authenticated', $q$select public.start_conversation('Asunto largo ok', repeat('a', 2000))$q$, 'OK rows=1');
select t.ex('start_conversation: asunto de más de 120 caracteres', '{B}', 'authenticated', $q$select public.start_conversation(repeat('a', 121), 'hola')$q$, 'ERR P0001%asunto%');
select t.eq('start_conversation: si algo falla NO queda una conversación vacía', '{B}', 'authenticated',
  $q$select count(*) from public.conversations where subject in ('ab', '     ', 'Asunto válido')$q$, '0');
insert into public.conversations (id, user_id, subject) values ('c0000000-0000-4000-8000-0000000000e1', '{E}', 'Antes de la suspensión');
update public.profiles set is_suspended = true where id = '{E}';
select t.ex('start_conversation: una persona suspendida NO puede abrir conversación', '{E}', 'authenticated', $q$select public.start_conversation('Quiero hablar', 'hola')$q$, 'ERR 42501%');
select t.eq('start_conversation: tras el rechazo de una suspendida no queda nada nuevo', null, 'service_role',
  $q$select count(*) from public.conversations where user_id = '{E}'$q$, '1');
select t.ex('Una persona suspendida NO puede escribir ni en su propia conversación', '{E}', 'authenticated',
  $q$insert into public.messages (conversation_id, body) values ('c0000000-0000-4000-8000-0000000000e1', 'x')$q$, 'ERR 42501%');
select t.eq('Una persona suspendida SÍ puede leer su conversación', '{E}', 'authenticated', $q$select count(*) from public.conversations$q$, '1');
update public.profiles set is_suspended = false where id = '{E}';
select t.ex('start_conversation: respeta el máximo de 10 conversaciones abiertas (y no deja la nueva a medias)', '{F}', 'authenticated',
  $q$select public.start_conversation('Una más de F', 'hola')$q$, 'ERR P0001%');
select t.eq('start_conversation: F sigue con exactamente 10 conversaciones', null, 'service_role', $q$select count(*) from public.conversations where user_id = '{F}'$q$, '10');
select t.ex('A cierra la conversación (antes de probar la reapertura)', '{A}', 'authenticated', $q$update public.conversations set status = 'cerrada' where id = '{CONV}'$q$, 'OK rows=1');
select t.ex('Reabrir: la persona NO puede (hay que abrir una nueva)', '{A}', 'authenticated', $q$update public.conversations set status = 'abierta' where id = '{CONV}'$q$, 'ERR P0001%cerrada%');
select t.eq('La conversación sigue cerrada', null, 'service_role', $q$select status from public.conversations where id = '{CONV}'$q$, 'cerrada');
select t.ex('Reabrir: el equipo (admin) SÍ puede', '{D}', 'authenticated', $q$update public.conversations set status = 'abierta' where id = '{CONV}'$q$, 'OK rows=1');
select t.ex('Cerrar de nuevo es posible para la persona', '{A}', 'authenticated', $q$update public.conversations set status = 'cerrada' where id = '{CONV}'$q$, 'OK rows=1');
select t.ex('B NO puede cerrar la conversación de A', '{B}', 'authenticated', $q$update public.conversations set status = 'cerrada' where id = '{CONV}'$q$, 'OK rows=0');
select t.ex('Un anónimo NO puede leer mensajes', null, 'anon', $q$select * from public.messages$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede escribir mensajes', null, 'anon', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'x')$q$, 'ERR 42501%');
-- Tope diario de 100 mensajes en 24 h (el de 10 minutos se esquiva con mensajes antiguos)
insert into public.conversations (id, user_id, subject) values ('c0000000-0000-4000-8000-000000000099', '{C}', 'Tope diario');
insert into public.messages (conversation_id, sender_id, body, created_at)
  select 'c0000000-0000-4000-8000-000000000099', '{C}', 'antiguo ' || g, now() - interval '3 hours' - g * interval '1 minute' from generate_series(1, 100) g;
select t.ex('Tope diario: con 100 mensajes en 24 h no puede enviar el 101', '{C}', 'authenticated',
  $q$insert into public.messages (conversation_id, body) values ('c0000000-0000-4000-8000-000000000099', 'uno más')$q$, 'ERR P0001%100 mensajes%');
select t.eq('Tope diario: el mensaje 101 no se guardó', null, 'service_role', $q$select count(*) from public.messages where conversation_id = 'c0000000-0000-4000-8000-000000000099'$q$, '100');
select t.ex('Tope diario: el equipo puede responder aunque la persona esté en su tope', '{D}', 'authenticated',
  $q$insert into public.messages (conversation_id, body) values ('c0000000-0000-4000-8000-000000000099', 'Te respondemos')$q$, 'OK rows=1');
update public.messages set created_at = now() - interval '30 hours' where conversation_id = 'c0000000-0000-4000-8000-000000000099' and sender_role = 'user';
select t.ex('Tope diario: pasadas 24 h puede volver a escribir', '{C}', 'authenticated',
  $q$insert into public.messages (conversation_id, body) values ('c0000000-0000-4000-8000-000000000099', 'ya pasó un día')$q$, 'OK rows=1');
select t.ex('El equipo NO tiene límite de mensajes: puede enviar 130 respuestas seguidas', '{D}', 'authenticated',
  $q$insert into public.messages (conversation_id, body) select 'c0000000-0000-4000-8000-000000000099', 'respuesta ' || g from generate_series(1, 130) g$q$, 'OK rows=130');
-- Tope de conversaciones creadas por día (aunque las cierre)
insert into public.conversations (user_id, subject, status) select '{B}', 'Vacía ' || g, 'cerrada' from generate_series(1, 20) g;
select t.ex('Tope diario: 20 conversaciones creadas en 24 h y no se puede crear otra', '{B}', 'authenticated',
  $q$insert into public.conversations (subject) values ('otra más')$q$, 'ERR P0001%conversaciones hoy%');
select t.ex('Tope diario: tampoco con start_conversation', '{B}', 'authenticated', $q$select public.start_conversation('Otra más', 'hola')$q$, 'ERR P0001%conversaciones hoy%');

-- =====================================================================
select t.grupo('7 Notificaciones');
-- =====================================================================
select t.eq('B no ve notificaciones de A', '{B}', 'authenticated', $q$select count(*) from public.notifications where user_id = '{A}'$q$, '0');
select t.eq('A ve las suyas', '{A}', 'authenticated', $q$select (count(*) > 0)::text from public.notifications$q$, 'true');
select t.ex('A marca una como leída', '{A}', 'authenticated', $q$update public.notifications set is_read = true where id = (select id from public.notifications order by created_at limit 1)$q$, 'OK rows=1');
select t.eq('Se registró cuándo se leyó', null, 'service_role', $q$select (count(*) > 0)::text from public.notifications where user_id = '{A}' and is_read and read_at is not null$q$, 'true');
select t.ex('A NO puede editar el título de una notificación', '{A}', 'authenticated', $q$update public.notifications set title = 'hack'$q$, 'ERR 42501%');
select t.ex('A NO puede crear notificaciones', '{A}', 'authenticated', $q$insert into public.notifications (user_id, type, title) values ('{A}', 'aviso', 'falsa')$q$, 'ERR 42501%');
select t.ex('A NO puede crear notificaciones para otros', '{A}', 'authenticated', $q$insert into public.notifications (user_id, type, title) values ('{B}', 'aviso', 'falsa')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede leer notificaciones', null, 'anon', $q$select * from public.notifications$q$, 'ERR 42501%');
select t.ex('Un enlace "javascript:" en una notificación es rechazado', null, 'service_role',
  $q$insert into public.notifications (user_id, type, title, link) values ('{A}', 'aviso', 'x', 'javascript:alert(1)')$q$, 'ERR 23514%');
select t.eq('Las notificaciones de correo no se marcan como enviadas por defecto', null, 'service_role', $q$select count(*) from public.notifications where email_status <> 'no_solicitado'$q$, '0');
select t.ex('A configura sus preferencias: sin avisos de mensajes', '{A}', 'authenticated',
  $q$update public.profiles set notification_prefs = notification_prefs || '{"mensaje": false}' where id = '{A}'$q$, 'OK rows=1');
select count(*) as antes_n from public.notifications where user_id = '{A}' and type = 'mensaje' \gset
select t.ex('D responde otra vez', '{D}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ('{CONV}', 'Una respuesta más')$q$, 'OK rows=1');
select t.ok('Con el aviso desactivado NO se crea notificación de mensaje',
  (select count(*) from public.notifications where user_id = '{A}' and type = 'mensaje') = :antes_n);
select t.ex('Preferencias con formato inválido rechazadas', '{A}', 'authenticated', $q$update public.profiles set notification_prefs = '[1,2]' where id = '{A}'$q$, 'ERR 23514%');
select t.ex('A borra sus notificaciones', '{A}', 'authenticated', $q$delete from public.notifications$q$, 'OK rows=%');
select t.eq('A no tiene notificaciones tras borrar', '{A}', 'authenticated', $q$select count(*) from public.notifications$q$, '0');
select t.eq('...y las de C siguen intactas', null, 'service_role', $q$select (count(*) > 0)::text from public.notifications where user_id = '{C}'$q$, 'true');

-- =====================================================================
select t.grupo('8 Guías de cuidado');
-- =====================================================================
select t.eq('Un visitante ve las 8 guías publicadas', null, 'anon', $q$select count(*) from public.care_guides$q$, '8');
insert into public.care_guides (slug, title, summary, content, category) values ('borrador-secreto', 'Borrador', 'x', 'contenido', 'perros');
select t.eq('Un borrador NO es visible para el público', null, 'anon', $q$select count(*) from public.care_guides$q$, '8');
select t.eq('Un usuario normal tampoco ve borradores', '{A}', 'authenticated', $q$select count(*) from public.care_guides$q$, '8');
select t.eq('El admin sí ve borradores (9)', '{D}', 'authenticated', $q$select count(*) from public.care_guides$q$, '9');
select t.ex('Un anónimo NO puede crear guías', null, 'anon', $q$insert into public.care_guides (slug, title, summary, content, category) values ('x-guia', 'Guía X', 'x', 'c', 'perros')$q$, 'ERR 42501%');
select t.ex('Un usuario normal NO puede crear guías', '{A}', 'authenticated', $q$insert into public.care_guides (slug, title, summary, content, category) values ('x-guia', 'Guía X', 'x', 'c', 'perros')$q$, 'ERR 42501%');
select t.ex('Un usuario normal NO puede editar guías', '{A}', 'authenticated', $q$update public.care_guides set title = 'hack'$q$, 'OK rows=0');
select t.ex('Un usuario normal NO puede borrar guías', '{A}', 'authenticated', $q$delete from public.care_guides$q$, 'OK rows=0');
select t.ex('D crea y publica una guía', '{D}', 'authenticated',
  $q$insert into public.care_guides (slug, title, summary, content, category, author_source, is_published) values ('guia-nueva', 'Guía nueva', 'Resumen', 'Contenido', 'comportamiento', 'Equipo', true)$q$, 'OK rows=1');
select t.eq('Al publicar se fija la fecha de publicación automáticamente', null, 'service_role', $q$select (published_at is not null)::text from public.care_guides where slug = 'guia-nueva'$q$, 'true');
select t.eq('El público ya ve 9 guías', null, 'anon', $q$select count(*) from public.care_guides$q$, '9');
select t.ex('Slug con formato inválido rechazado', '{D}', 'authenticated', $q$insert into public.care_guides (slug, title, summary, content, category) values ('Slug Malo!', 'Guía', 'x', 'c', 'perros')$q$, 'ERR 23514%');
select t.ex('Categoría inválida rechazada', '{D}', 'authenticated', $q$insert into public.care_guides (slug, title, summary, content, category) values ('otra-guia', 'Guía', 'x', 'c', 'reptiles')$q$, 'ERR 23514%');
select t.ex('D edita una guía', '{D}', 'authenticated', $q$update public.care_guides set summary = 'Resumen editado' where slug = 'guia-nueva'$q$, 'OK rows=1');
select t.ex('D elimina una guía', '{D}', 'authenticated', $q$delete from public.care_guides where slug = 'guia-nueva'$q$, 'OK rows=1');
delete from public.care_guides where slug = 'borrador-secreto';

-- =====================================================================
select t.grupo('9 Almacenamiento de archivos');
-- =====================================================================
select t.eq('Los 6 buckets tienen visibilidad y tope de tamaño correctos', null, 'service_role',
  $q$select string_agg(id || ':' || public || ':' || file_size_limit, ',' order by id) from storage.buckets$q$,
  'avatars:false:2097152,business-media:true:5242880,complaint-evidence:false:5242880,guide-images:true:5242880,pet-photos:false:5242880,qr-photos:true:1048576');
select t.eq('Solo se aceptan imágenes JPG, PNG o WebP', null, 'service_role',
  $q$select count(*) from storage.buckets where allowed_mime_types <> array['image/jpeg','image/png','image/webp']$q$, '0');
select t.ex('A sube su foto de perfil a su carpeta', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{A}/yo.png')$q$, 'OK rows=1');
select t.ex('A NO puede subir archivos a la carpeta de B', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{B}/yo.png')$q$, 'ERR 42501%');
select t.ex('A NO puede subir a la raíz del bucket', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', 'yo.png')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede subir archivos', null, 'anon', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{A}/anon.png')$q$, 'ERR 42501%');
select t.eq('B no ve las fotos de A', '{B}', 'authenticated', $q$select count(*) from storage.objects where bucket_id = 'avatars'$q$, '0');
select t.eq('A ve su foto', '{A}', 'authenticated', $q$select count(*) from storage.objects where bucket_id = 'avatars'$q$, '1');
select t.ex('A NO puede borrar la foto de otra persona', '{B}', 'authenticated', $q$delete from storage.objects where bucket_id = 'avatars'$q$, 'OK rows=0');
select t.ex('A sube una 2.ª foto', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{A}/2.png')$q$, 'OK rows=1');
select t.ex('A sube una 3.ª foto', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{A}/3.png')$q$, 'OK rows=1');
select t.ex('Tope de archivos por persona: la 4.ª se rechaza', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{A}/4.png')$q$, 'ERR 42501%');
-- Etapa 4: bucket público de fotos de placas QR
select t.eq('qr-photos es público (lectura por URL), pero escribirlo exige sesión y plan', null, 'service_role', $q$select public::text from storage.buckets where id = 'qr-photos'$q$, 'true');
select t.eq('has_qr_plan: A con VIP = true', '{A}', 'authenticated', $q$select public.has_qr_plan()::text$q$, 'true');
select t.ex('A (VIP) sube la foto de su placa a su carpeta', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{A}/foto1.jpg')$q$, 'OK rows=1');
select t.ex('A NO puede subir a la carpeta de B en qr-photos', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{B}/foto1.jpg')$q$, 'ERR 42501%');
select t.ex('Un anónimo NO puede subir a qr-photos', null, 'anon', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{A}/anon.jpg')$q$, 'ERR 42501%');
select t.ex('F (plan Básica) NO puede subir a qr-photos', '{F}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{F}/foto1.jpg')$q$, 'ERR 42501%');
select t.eq('B no ve en la API los archivos de qr-photos de A', '{B}', 'authenticated', $q$select count(*) from storage.objects where bucket_id = 'qr-photos'$q$, '0');
insert into storage.objects (bucket_id, name, owner) select 'qr-photos', '{A}/relleno' || g, '{A}'::uuid from generate_series(1, 29) g;
select t.ex('Tope de 30 fotos de placa por persona: la 31.ª se rechaza', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{A}/una-mas.jpg')$q$, 'ERR 42501%');
select t.ex('A puede borrar una foto suya de qr-photos', '{A}', 'authenticated', $q$delete from storage.objects where bucket_id = 'qr-photos' and name = '{A}/relleno1'$q$, 'OK rows=1');
select t.ex('B NO puede borrar fotos de A en qr-photos', '{B}', 'authenticated', $q$delete from storage.objects where bucket_id = 'qr-photos'$q$, 'OK rows=0');
select t.ex('D cancela el plan de A (storage)', '{D}', 'authenticated', $q$select public.admin_cancel_subscription('{A}', 'prueba storage')$q$, 'OK rows=1');
select t.eq('Sin plan: has_qr_plan = false', '{A}', 'authenticated', $q$select public.has_qr_plan()::text$q$, 'false');
select t.ex('Sin plan: NO se pueden subir más fotos de placa', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('qr-photos', '{A}/tras-vencer.jpg')$q$, 'ERR 42501%');
select t.ex('Sin plan: sí puede borrar las que ya tenía (limpiar)', '{A}', 'authenticated', $q$delete from storage.objects where bucket_id = 'qr-photos' and name = '{A}/relleno2'$q$, 'OK rows=1');
select t.ex('A sube foto de mascota a su carpeta', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('pet-photos', '{A}/{P1}/luna.webp')$q$, 'OK rows=1');
select t.ex('A NO puede subir imágenes de guías', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('guide-images', 'x/portada.png')$q$, 'ERR 42501%');
select t.ex('D (admin) sí sube imágenes de guías', '{D}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('guide-images', 'perros/portada.png')$q$, 'OK rows=1');
select t.ex('A (dueña) NO puede subir a la galería de aliados', '{A}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('business-media', '{A}/logo.png')$q$, 'ERR 42501%');
select t.ex('C (aliado) sube su logotipo', '{C}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('business-media', '{C}/logo.png')$q$, 'OK rows=1');
select t.ex('C NO puede subir a la carpeta de E', '{C}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('business-media', '{E}/logo.png')$q$, 'ERR 42501%');
select t.ex('NADIE sube evidencia de denuncias desde el navegador (ni el admin)', '{D}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('complaint-evidence', 'x/foto.jpg')$q$, 'ERR 42501%');
select t.ex('Un anónimo tampoco sube evidencia', null, 'anon', $q$insert into storage.objects (bucket_id, name) values ('complaint-evidence', 'x/foto.jpg')$q$, 'ERR 42501%');
select t.ex('SOLO el servidor (la función segura) sube evidencia', null, 'service_role', $q$insert into storage.objects (bucket_id, name, metadata) values ('complaint-evidence', 'servidor/1.jpg', '{"size": 1000}')$q$, 'OK rows=1');
delete from storage.objects where bucket_id = 'complaint-evidence' and name = 'servidor/1.jpg';
insert into storage.objects (bucket_id, name) values ('complaint-evidence', 'denuncia1/foto.jpg');
select t.eq('El admin ve la evidencia de denuncias', '{D}', 'authenticated', $q$select count(*) from storage.objects where bucket_id = 'complaint-evidence'$q$, '1');
select t.eq('Un usuario normal NO ve la evidencia', '{A}', 'authenticated', $q$select count(*) from storage.objects where bucket_id = 'complaint-evidence'$q$, '0');
select t.eq('Un anónimo NO ve la evidencia', null, 'anon', $q$select count(*) from storage.objects where bucket_id = 'complaint-evidence'$q$, '0');
select t.ex('B (no admin) NO puede suspender cuentas', '{B}', 'authenticated', $q$select public.admin_set_user_suspended('{A}', true)$q$, 'ERR 42501%');
select public.admin_set_user_suspended('{B}', true) from (select set_config('request.jwt.claims', '{"sub":"{D}","role":"authenticated"}', true)) s;
select t.ex('Cuenta suspendida NO puede subir fotos', '{B}', 'authenticated', $q$insert into storage.objects (bucket_id, name) values ('avatars', '{B}/yo.png')$q$, 'ERR 42501%');
update public.profiles set is_suspended = false where id = '{B}';

-- =====================================================================
select t.grupo('10 Notificaciones, recordatorios y avisos al equipo (Etapa 8)');
-- =====================================================================
select (now() at time zone 'America/Mexico_City')::date as hoy \gset
insert into auth.users (id, email, raw_user_meta_data) values
 ('{G}', 'gus@prueba.mx',  '{"display_name":"Gus"}'),
 ('{H}', 'hana@prueba.mx', '{"display_name":"Hana"}'),
 ('{I}', 'ines@prueba.mx', '{"display_name":"Ines"}');
insert into public.admin_roles (user_id, note) values ('{I}', 'segunda admin de pruebas');
insert into public.pets (id, owner_id, name, species) values ('{P4}', '{G}', 'Nube', 'perro'), ('{P5}', '{G}', 'Trueno', 'gato'), ('{P6}', '{H}', 'Rocky', 'perro');
insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on, next_due_on) values
 ('{P4}', 'Rabia',         :'hoy'::date - 360, :'hoy'::date + 3),     -- próxima
 ('{P4}', 'Parvovirus',    :'hoy'::date - 400, :'hoy'::date - 20),    -- vencida
 ('{P4}', 'Moquillo',      :'hoy'::date - 380, :'hoy'::date - 10),    -- registro viejo, ya renovado: NO debe avisar
 ('{P4}', 'Moquillo',      :'hoy'::date - 5,   :'hoy'::date + 360),
 ('{P4}', 'Triple felina', :'hoy'::date - 335, :'hoy'::date + 30),    -- falta mucho
 ('{P4}', 'Leptospirosis', :'hoy'::date - 600, :'hoy'::date - 100),   -- vencida hace más de 60 días: no se avisa
 ('{P6}', 'Rabia',         :'hoy'::date - 360, :'hoy'::date + 2);     -- de otra persona (H)
insert into public.pet_deworming (pet_id, product_name, kind, applied_on, next_due_on) values
 ('{P4}', 'Drontal',  'interna', :'hoy'::date - 170, :'hoy'::date - 85),   -- viejo, ya renovado
 ('{P4}', 'Drontal',  'interna', :'hoy'::date - 80,  :'hoy'::date + 1),    -- próxima
 ('{P5}', 'Bravecto', 'externa', :'hoy'::date - 100, :'hoy'::date - 30);   -- vencida
insert into public.pet_appointments (pet_id, kind, scheduled_at, status, clinic) values
 ('{P4}', 'vacunacion', now() + interval '20 hours', 'programada', 'Clínica Patitas'),
 ('{P4}', 'consulta',   now() + interval '5 days',   'programada', null),
 ('{P4}', 'consulta',   now() + interval '10 hours', 'cancelada',  null),
 ('{P4}', 'consulta',   now() - interval '3 hours',  'programada', null);

-- ---- Recordatorios ----
select t.ex('Un anónimo NO puede generar recordatorios', null, 'anon', $q$select public.generate_my_reminders()$q$, 'ERR 42501%');
select t.eq('G genera sus recordatorios: 2 vacunas, 2 desparasitaciones y 1 cita', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '5');
select t.eq('Quedan guardados por tipo', '{G}', 'authenticated',
  $q$select string_agg(type || ':' || c, ',' order by type) from (select type, count(*) c from public.notifications group by type) x$q$, 'cita:1,desparasitacion:2,vacuna:2');
select t.eq('Vacuna próxima: título con la vacuna y la mascota', '{G}', 'authenticated', $q$select title from public.notifications where title like 'Vacuna próxima%'$q$, 'Vacuna próxima: Rabia (Nube)');
select t.eq('Vacuna vencida: título', '{G}', 'authenticated', $q$select title from public.notifications where title like 'Vacuna vencida%'$q$, 'Vacuna vencida: Parvovirus (Nube)');
select t.eq('Vacuna vencida: el texto dice «Debió aplicarse el …»', '{G}', 'authenticated', $q$select body from public.notifications where title like 'Vacuna vencida%'$q$, 'Debió aplicarse el % 20__. Consulta a tu veterinario%');
select t.eq('Desparasitación próxima usa el ÚLTIMO registro de la mascota (el viejo ya renovado no cuenta)', '{G}', 'authenticated', $q$select string_agg(title, ' | ' order by title) from public.notifications where type = 'desparasitacion'$q$, 'Desparasitación próxima: Drontal (Nube) | Desparasitación vencida: Bravecto (Trueno)');
select t.eq('Un registro viejo ya renovado (Moquillo), una fecha lejana y una vencida hace más de 60 días NO generan avisos', '{G}', 'authenticated',
  $q$select count(*) from public.notifications where title like '%Moquillo%' or title like '%Triple%' or title like '%Leptospirosis%'$q$, '0');
select t.eq('Cita próxima: solo la programada dentro de 48 horas (no la lejana, la cancelada ni la pasada)', '{G}', 'authenticated',
  $q$select count(*) from public.notifications where type = 'cita'$q$, '1');
select t.eq('Cita próxima: texto con tipo, fecha, hora de México y clínica', '{G}', 'authenticated',
  $q$select body from public.notifications where type = 'cita'$q$, 'Cita de vacunación: % (hora de México) · Clínica Patitas.');
select t.eq('Todos los recordatorios llevan al carnet', '{G}', 'authenticated', $q$select count(*) from public.notifications where link is distinct from 'carnet.html'$q$, '0');
select t.eq('Llamarla otra vez no duplica nada', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '0');
select t.ex('G borra el recordatorio de Parvovirus', '{G}', 'authenticated', $q$delete from public.notifications where title like 'Vacuna vencida%'$q$, 'OK rows=1');
select t.eq('Un recordatorio borrado NO vuelve a aparecer', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '0');
select t.eq('...y sigue borrado', '{G}', 'authenticated', $q$select count(*) from public.notifications where title like 'Vacuna vencida%'$q$, '0');
select t.eq('H solo recibe lo de SUS mascotas (Rocky)', '{H}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '1');
select t.eq('El recordatorio de H es el de su mascota', '{H}', 'authenticated', $q$select title from public.notifications$q$, 'Vacuna próxima: Rabia (Rocky)');
select t.eq('G no ve las notificaciones de H', '{G}', 'authenticated', $q$select count(*) from public.notifications where user_id = '{H}'$q$, '0');
select t.ex('G NO puede leer el registro interno de recordatorios', '{G}', 'authenticated', $q$select * from private.reminder_log$q$, 'ERR 42501%');
select t.ex('G NO puede llamar a las funciones internas de avisos al equipo', '{G}', 'authenticated', $q$select private.notify_admins('aviso', 'x')$q$, 'ERR 42501%');
-- preferencias: si se apaga el tipo, no se registra (y al reactivarlo sí aparece)
update public.profiles set notification_prefs = notification_prefs || '{"vacuna": false}' where id = '{G}';
insert into public.pet_vaccinations (pet_id, vaccine_name, applied_on, next_due_on) values ('{P5}', 'Bordetella', :'hoy'::date - 300, :'hoy'::date + 1);
select t.eq('Con «vacunas» apagado no se genera el recordatorio', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '0');
update public.profiles set notification_prefs = notification_prefs || '{"vacuna": true}' where id = '{G}';
select t.eq('Al reactivar «vacunas» aparece el que estaba pendiente', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '1');
select t.eq('...y es el de Bordetella', '{G}', 'authenticated', $q$select count(*) from public.notifications where title = 'Vacuna próxima: Bordetella (Trueno)'$q$, '1');
-- límite por hora
insert into private.rate_limits (bucket, key, window_start, hits) values ('reminders_h', '{G}', date_trunc('hour', now()), 30)
  on conflict (bucket, key, window_start) do update set hits = 30;
select t.ex('Más de 30 llamadas en una hora se frenan', '{G}', 'authenticated', $q$select public.generate_my_reminders()$q$, 'ERR P0001: Demasiadas solicitudes%');
delete from private.rate_limits where bucket = 'reminders_h';
-- el registro anti-repetición se limpia: lo de hace más de 180 días se borra, lo reciente se conserva (y solo el de quien llama)
insert into private.reminder_log (user_id, dedupe_key, created_at) values
  ('{G}', 'viejo-prueba', now() - interval '200 days'),
  ('{G}', 'reciente-prueba', now() - interval '5 days'),
  ('{H}', 'viejo-de-otra-persona', now() - interval '200 days');
select t.eq('G llama a generar recordatorios', '{G}', 'authenticated', $q$select public.generate_my_reminders()::text$q$, '%');
select t.ok('El registro de hace más de 180 días se borra al generar recordatorios',
  not exists (select 1 from private.reminder_log where dedupe_key = 'viejo-prueba'),
  (select count(*)::text from private.reminder_log where dedupe_key = 'viejo-prueba'));
select t.ok('...el reciente se conserva', exists (select 1 from private.reminder_log where dedupe_key = 'reciente-prueba'));
select t.ok('...y no toca el registro de otra persona', exists (select 1 from private.reminder_log where dedupe_key = 'viejo-de-otra-persona'));
delete from private.reminder_log where dedupe_key in ('reciente-prueba', 'viejo-de-otra-persona');

-- ---- notify: avisos que no se silencian, duplicados y limpieza automática ----
update public.profiles set notification_prefs = notification_prefs || '{"aviso": false, "mensaje": false}' where id = '{H}';
select private.notify('{H}', 'aviso', 'Aviso importante');
select private.notify('{H}', 'mensaje', 'Mensaje silenciado');
select t.eq('Los avisos NO se pueden silenciar', '{H}', 'authenticated', $q$select count(*) from public.notifications where title = 'Aviso importante'$q$, '1');
select t.eq('Los demás tipos sí (mensajes apagados no llegan)', '{H}', 'authenticated', $q$select count(*) from public.notifications where title = 'Mensaje silenciado'$q$, '0');
select private.notify('{H}', 'aviso', 'Con clave', null, null, 'k1');
select private.notify('{H}', 'aviso', 'Con clave', null, null, 'k1');
select t.eq('La misma clave de duplicado no repite el aviso', '{H}', 'authenticated', $q$select count(*) from public.notifications where title = 'Con clave'$q$, '1');
delete from public.notifications where user_id = '{H}';
insert into public.notifications (user_id, type, title, created_at)
  select '{H}', 'aviso', 'n' || g, now() - (g || ' minutes')::interval from generate_series(1, 205) g;
select private.notify('{H}', 'aviso', 'Disparador de limpieza');
select t.eq('Cada persona conserva como máximo 200 notificaciones', '{H}', 'authenticated', $q$select count(*) from public.notifications$q$, '200');
select t.eq('Se borran las más antiguas y se conservan las recientes', '{H}', 'authenticated',
  $q$select (count(*) filter (where title in ('n199', 'n1', 'Disparador de limpieza')) = 3 and count(*) filter (where title in ('n200', 'n205')) = 0)::text from public.notifications$q$, 'true');
insert into public.notifications (user_id, type, title, is_read, created_at) values
 ('{G}', 'aviso', 'vieja leída',     true,  now() - interval '100 days'),
 ('{G}', 'aviso', 'vieja sin leer',  false, now() - interval '100 days'),
 ('{G}', 'aviso', 'muy vieja',       false, now() - interval '400 days');
select private.notify('{G}', 'aviso', 'Otro aviso');
select t.eq('Limpieza: las leídas de más de 90 días y todas las de más de un año se borran; las sin leer recientes se conservan', null, 'service_role',
  $q$select string_agg(title, ',' order by title) from public.notifications where user_id = '{G}' and title in ('vieja leída', 'vieja sin leer', 'muy vieja')$q$, 'vieja sin leer');

-- ---- Avisos al equipo: denuncias ----
update public.profiles set notification_prefs = notification_prefs || '{"aviso": false}' where id = '{I}';
delete from private.rate_limits;
select count(*) as d_antes from public.notifications where user_id = '{D}' and title = 'Nueva denuncia recibida' \gset
select t.ex('Llega una denuncia', null, 'service_role', $q$select public.submit_complaint('abandono', 'SECRETO-DESCRIPCION ' || repeat('Un perro abandonado. ', 3), current_date, 'Zacatecas', 'Fresnillo')$q$, 'OK rows=1');
select t.eq('Todas las cuentas de administración reciben el aviso (D)', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{D}' and title = 'Nueva denuncia recibida'$q$, (:d_antes + 1)::text);
select t.eq('...también la que tiene los «avisos» apagados (I): los avisos no se silencian', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{I}' and title = 'Nueva denuncia recibida' and body like '%Zacatecas%'$q$, '1');
select t.eq('Quien no es administrador NO recibe nada', null, 'service_role',
  $q$select count(*) from public.notifications where title = 'Nueva denuncia recibida' and user_id not in (select user_id from public.admin_roles)$q$, '0');
select t.eq('El aviso solo lleva código, tipo y estado, no la descripción', null, 'service_role',
  $q$select count(*) from public.notifications where body like '%SECRETO%'$q$, '0');
select t.eq('El aviso lleva al panel y es de tipo «aviso»', null, 'service_role',
  $q$select (link = 'admin.html' and type = 'aviso' and body like 'Código TP-____-____ · abandono · Zacatecas')::text from public.notifications where user_id = '{I}' and title = 'Nueva denuncia recibida' and body like '%Zacatecas%'$q$, 'true');

-- ---- Avisos al equipo: chat (una vez por «turno») ----
update public.profiles set notification_prefs = notification_prefs || '{"aviso": true}' where id = '{I}';
select t.ex('G abre una conversación', '{G}', 'authenticated', $q$select public.start_conversation('Consulta de Gus', 'Hola, necesito ayuda')$q$, 'OK rows=1');
select t.eq('El equipo recibe UN aviso por la conversación nueva (D)', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{D}' and title = 'Atención al cliente: conversación esperando respuesta' and body = 'Consulta de Gus'$q$, '1');
select t.eq('...y la otra administradora (I)', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{I}' and body = 'Consulta de Gus'$q$, '1');
select t.eq('El aviso es de tipo «mensaje» y lleva al panel', null, 'service_role',
  $q$select (type = 'mensaje' and link = 'admin.html')::text from public.notifications where user_id = '{D}' and body = 'Consulta de Gus'$q$, 'true');
select t.ex('G escribe otro mensaje seguido', '{G}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ((select id from public.conversations where subject = 'Consulta de Gus'), 'Sigo aquí')$q$, 'OK rows=1');
select t.eq('Mensajes seguidos del mismo turno NO repiten el aviso', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{D}' and body = 'Consulta de Gus'$q$, '1');
select t.ex('D responde', '{D}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ((select id from public.conversations where subject = 'Consulta de Gus'), 'Con gusto')$q$, 'OK rows=1');
select t.eq('La respuesta del equipo NO genera avisos al equipo', null, 'service_role',
  $q$select count(*) from public.notifications where body = 'Consulta de Gus'$q$, '2');
select t.eq('...y sí avisa a G', null, 'service_role',
  $q$select count(*) from public.notifications where user_id = '{G}' and title = 'Nueva respuesta de atención al cliente'$q$, '1');
select t.ex('G responde tras la respuesta del equipo (turno nuevo)', '{G}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ((select id from public.conversations where subject = 'Consulta de Gus'), 'Gracias, otra duda')$q$, 'OK rows=1');
select t.eq('Turno nuevo: nuevo aviso al equipo (D y I)', null, 'service_role',
  $q$select count(*) from public.notifications where body = 'Consulta de Gus'$q$, '4');
update public.profiles set notification_prefs = notification_prefs || '{"mensaje": false}' where id = '{I}';
select t.ex('D responde otra vez', '{D}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ((select id from public.conversations where subject = 'Consulta de Gus'), 'Listo')$q$, 'OK rows=1');
select t.ex('G escribe de nuevo', '{G}', 'authenticated', $q$insert into public.messages (conversation_id, body) values ((select id from public.conversations where subject = 'Consulta de Gus'), 'Perfecto')$q$, 'OK rows=1');
select t.eq('Quien apagó los avisos de mensajes (I) ya no recibe estos; D sí', null, 'service_role',
  $q$select string_agg(user_id::text || ':' || c, ',' order by user_id) from (select user_id, count(*) c from public.notifications where body = 'Consulta de Gus' group by user_id) x$q$,
  '{I}:2,{D}:3');

-- =====================================================================
select t.grupo('11 Invariantes globales de seguridad');
-- =====================================================================
select t.ok('TODAS las tablas de public y private tienen RLS activado',
  not exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname in ('public', 'private') and c.relkind = 'r' and not c.relrowsecurity),
  (select string_agg(c.relname, ',') from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname in ('public', 'private') and c.relkind = 'r' and not c.relrowsecurity));
select t.eq('Un visitante anónimo solo tiene acceso a tablas de contenido público', null, 'service_role',
  $q$select string_agg(c.relname, ',' order by c.relname) from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r' and has_any_column_privilege('anon', c.oid, 'select,insert,update,references')$q$,
  'care_guides,subscription_plans');
select t.eq('El anónimo solo puede ejecutar 5 funciones públicas', null, 'service_role',
  $q$select string_agg(p.proname, ',' order by p.proname) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and has_function_privilege('anon', p.oid, 'execute')$q$,
  'directory_get,directory_search,directory_track,get_public_pet_profile,track_complaint');
select t.eq('admin_roles es inaccesible para anon y authenticated', null, 'service_role',
  $q$select (has_table_privilege('anon', 'public.admin_roles', 'select,insert,update,delete')
          or has_table_privilege('authenticated', 'public.admin_roles', 'select,insert,update,delete')
          or has_any_column_privilege('anon', 'public.admin_roles', 'select,insert,update')
          or has_any_column_privilege('authenticated', 'public.admin_roles', 'select,insert,update'))::text$q$, 'false');
select t.eq('El esquema private es inaccesible desde la API', null, 'service_role',
  $q$select (has_schema_privilege('anon', 'private', 'usage') or has_schema_privilege('authenticated', 'private', 'usage'))::text$q$, 'false');
select t.eq('Ninguna función de public queda ejecutable por "PUBLIC"', null, 'service_role',
  $q$select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and exists (select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a where a.grantee = 0 and a.privilege_type = 'EXECUTE')$q$, '0');
select t.ok('Todas las funciones SECURITY DEFINER fijan search_path',
  not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname in ('public', 'private') and p.prosecdef
                and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%')),
  (select string_agg(n.nspname || '.' || p.proname, ',') from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname in ('public', 'private') and p.prosecdef
     and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%')));
select t.eq('Chat y notificaciones están en la publicación de tiempo real', null, 'service_role',
  $q$select string_agg(tablename, ',' order by tablename) from pg_publication_tables where pubname = 'supabase_realtime'$q$, 'conversations,messages,notifications');
select t.eq('El usuario normal solo puede ejecutar funciones de usuario, no las internas', null, 'service_role',
  $q$select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'private' and (has_function_privilege('authenticated', p.oid, 'execute') and has_schema_privilege('authenticated', n.oid, 'usage'))$q$, '0');
select t.ex('Un usuario normal NO puede llamar funciones internas', '{A}', 'authenticated', $q$select private.notify('{A}', 'aviso', 'x')$q$, 'ERR 42501%');
select t.eq('Un admin autenticado sí obtiene las estadísticas', '{D}', 'authenticated', $q$select (public.admin_dashboard_stats() ->> 'users')::int >= 6$q$, 'true');

-- ---------------------------------------------------------------------
-- Resultado
-- ---------------------------------------------------------------------
\o
\echo
\echo '=================== RESULTADOS ==================='
select grupo, count(*) filter (where pass) as ok, count(*) filter (where not pass) as fallos from t.results group by grupo order by min(n);
\echo '--- Pruebas que fallaron (si hay) ---'
select n, grupo, label, detail from t.results where not pass order by n;
select count(*) as total, count(*) filter (where pass) as correctas, count(*) filter (where not pass) as fallidas from t.results;
do $$
begin
  if exists (select 1 from t.results where not pass) then
    raise exception 'HAY PRUEBAS FALLIDAS';
  end if;
end $$;
