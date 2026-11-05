-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 03 · SEGURIDAD (permisos + RLS)
--
-- Estrategia: "todo prohibido, luego permitir lo mínimo".
--  1. Se quitan TODOS los permisos por defecto a anon y authenticated.
--  2. Se activa RLS en todas las tablas (sin política = sin acceso).
--  3. Se conceden solo las operaciones y columnas necesarias.
--  4. Las políticas limitan las FILAS (cada quien lo suyo; admin lo que le toca).
--  5. Los datos públicos salen únicamente por funciones controladas.
-- Nunca se usa la clave service_role en el navegador.
-- =====================================================================

-- 1. Quitar permisos por defecto --------------------------------------
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

-- Lo que se cree después desde el panel de Supabase tampoco queda abierto por defecto.
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from anon, authenticated;

-- 2. Activar RLS en todo ------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'profiles', 'admin_roles', 'subscription_plans', 'subscriptions', 'subscription_events',
    'pets', 'pet_vaccinations', 'pet_deworming', 'pet_appointments', 'pet_qr_profiles',
    'businesses', 'business_promotions', 'business_daily_stats', 'complaints', 'conversations', 'messages',
    'notifications', 'care_guides', 'admin_audit_log'] loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;
alter table private.settings    enable row level security;
alter table private.rate_limits enable row level security;

-- Atajo para recrear políticas sin errores al volver a ejecutar el script.
create or replace function pg_temp.pol(p_table text, p_name text, p_sql text)
returns void language plpgsql as $$
begin
  execute format('drop policy if exists %I on %s', p_name, p_table);
  execute p_sql;
end $$;

-- ---------------------------------------------------------------------
-- profiles: cada quien ve y edita lo suyo; no se puede cambiar el tipo de
-- cuenta ni la suspensión (no están entre las columnas permitidas).
-- ---------------------------------------------------------------------
grant select on public.profiles to authenticated;
grant update (display_name, avatar_path, phone, notification_prefs, email_reminders) on public.profiles to authenticated;

select pg_temp.pol('public.profiles', 'profiles_select', $p$
  create policy profiles_select on public.profiles for select to authenticated
  using (id = (select auth.uid()) or (select public.is_admin())) $p$);
select pg_temp.pol('public.profiles', 'profiles_update_own', $p$
  create policy profiles_update_own on public.profiles for update to authenticated
  using (id = (select auth.uid()) and (select public.is_active_user()))
  with check (id = (select auth.uid())) $p$);

-- ---------------------------------------------------------------------
-- admin_roles: SIN permisos ni políticas para la API. Solo SQL Editor / service_role.
-- ---------------------------------------------------------------------

-- ---------------------------------------------------------------------
-- Planes: lectura pública. Se modifican solo desde el SQL Editor.
-- ---------------------------------------------------------------------
grant select on public.subscription_plans to anon, authenticated;
select pg_temp.pol('public.subscription_plans', 'plans_select', $p$
  create policy plans_select on public.subscription_plans for select to anon, authenticated
  using (is_active) $p$);

-- Suscripciones: solo lectura propia (o admin). Los cambios van por funciones.
grant select on public.subscriptions, public.subscription_events to authenticated;
select pg_temp.pol('public.subscriptions', 'subs_select', $p$
  create policy subs_select on public.subscriptions for select to authenticated
  using (user_id = (select auth.uid()) or (select public.is_admin())) $p$);
select pg_temp.pol('public.subscription_events', 'subevents_select', $p$
  create policy subevents_select on public.subscription_events for select to authenticated
  using (user_id = (select auth.uid()) or (select public.is_admin())) $p$);

-- ---------------------------------------------------------------------
-- Mascotas: solo su dueño (ni siquiera el admin las ve: mínimo privilegio).
-- ---------------------------------------------------------------------
grant select, delete on public.pets to authenticated;
grant insert (id, owner_id, name, photo_path, species, breed, sex, birth_date, weight_kg, description, vet_info) on public.pets to authenticated;
grant update (name, photo_path, species, breed, sex, birth_date, weight_kg, description, vet_info) on public.pets to authenticated;

select pg_temp.pol('public.pets', 'pets_select', $p$
  create policy pets_select on public.pets for select to authenticated
  using (owner_id = (select auth.uid())) $p$);
select pg_temp.pol('public.pets', 'pets_insert', $p$
  create policy pets_insert on public.pets for insert to authenticated
  with check (owner_id = (select auth.uid()) and (select public.is_active_user())) $p$);
select pg_temp.pol('public.pets', 'pets_update', $p$
  create policy pets_update on public.pets for update to authenticated
  using (owner_id = (select auth.uid()) and (select public.is_active_user()))
  with check (owner_id = (select auth.uid())) $p$);
select pg_temp.pol('public.pets', 'pets_delete', $p$
  create policy pets_delete on public.pets for delete to authenticated
  using (owner_id = (select auth.uid()) and (select public.is_active_user())) $p$);

-- Carnet de salud y QR: solo a través de mascotas propias.
grant select, delete on public.pet_vaccinations, public.pet_deworming, public.pet_appointments, public.pet_qr_profiles to authenticated;
grant insert (pet_id, vaccine_name, applied_on, next_due_on, veterinarian, notes) on public.pet_vaccinations to authenticated;
grant update (vaccine_name, applied_on, next_due_on, veterinarian, notes) on public.pet_vaccinations to authenticated;
grant insert (pet_id, product_name, kind, applied_on, next_due_on, notes) on public.pet_deworming to authenticated;
grant update (product_name, kind, applied_on, next_due_on, notes) on public.pet_deworming to authenticated;
grant insert (pet_id, kind, scheduled_at, status, clinic, reason, notes) on public.pet_appointments to authenticated;
grant update (kind, scheduled_at, status, clinic, reason, notes) on public.pet_appointments to authenticated;
-- public_token NO está en la lista: nadie elige su propio token (se genera en el servidor).
grant insert (pet_id, is_active, show_name, show_photo, show_breed, public_message, contact_name, contact_phone, show_phone, qr_photo_path) on public.pet_qr_profiles to authenticated;
grant update (is_active, show_name, show_photo, show_breed, public_message, contact_name, contact_phone, show_phone, qr_photo_path) on public.pet_qr_profiles to authenticated;

do $$
declare t text;
begin
  foreach t in array array['pet_vaccinations', 'pet_deworming', 'pet_appointments', 'pet_qr_profiles'] loop
    perform pg_temp.pol('public.' || t, t || '_select', format($p$
      create policy %1$I on public.%2$I for select to authenticated
      using (pet_id in (select p.id from public.pets p where p.owner_id = (select auth.uid()))) $p$, t || '_select', t));
    perform pg_temp.pol('public.' || t, t || '_insert', format($p$
      create policy %1$I on public.%2$I for insert to authenticated
      with check (pet_id in (select p.id from public.pets p where p.owner_id = (select auth.uid())) and (select public.is_active_user())) $p$, t || '_insert', t));
    perform pg_temp.pol('public.' || t, t || '_update', format($p$
      create policy %1$I on public.%2$I for update to authenticated
      using (pet_id in (select p.id from public.pets p where p.owner_id = (select auth.uid())) and (select public.is_active_user()))
      with check (pet_id in (select p.id from public.pets p where p.owner_id = (select auth.uid()))) $p$, t || '_update', t));
    perform pg_temp.pol('public.' || t, t || '_delete', format($p$
      create policy %1$I on public.%2$I for delete to authenticated
      using (pet_id in (select p.id from public.pets p where p.owner_id = (select auth.uid())) and (select public.is_active_user())) $p$, t || '_delete', t));
  end loop;
end $$;

-- ---------------------------------------------------------------------
-- Establecimientos: el aliado edita SOLO el suyo. Estado, verificación y
-- demo no están entre las columnas permitidas (los cambia un admin por función).
-- El directorio público sale únicamente por directory_search / directory_get.
-- ---------------------------------------------------------------------
grant select, delete on public.businesses to authenticated;
grant insert (id, owner_id, name, category, description, address, state, municipality, phone, whatsapp_url, maps_query, logo_path, photo_paths, hours)
  on public.businesses to authenticated;
grant update (name, category, description, address, state, municipality, phone, whatsapp_url, maps_query, logo_path, photo_paths, hours)
  on public.businesses to authenticated;

select pg_temp.pol('public.businesses', 'biz_select', $p$
  create policy biz_select on public.businesses for select to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_admin())) $p$);
select pg_temp.pol('public.businesses', 'biz_insert', $p$
  create policy biz_insert on public.businesses for insert to authenticated
  with check (owner_id = (select auth.uid()) and (select public.is_active_user())) $p$);
select pg_temp.pol('public.businesses', 'biz_update_own', $p$
  create policy biz_update_own on public.businesses for update to authenticated
  using (owner_id = (select auth.uid()) and (select public.is_active_user()))
  with check (owner_id = (select auth.uid())) $p$);
select pg_temp.pol('public.businesses', 'biz_update_admin', $p$
  create policy biz_update_admin on public.businesses for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin())) $p$);
select pg_temp.pol('public.businesses', 'biz_delete', $p$
  create policy biz_delete on public.businesses for delete to authenticated
  using ((owner_id = (select auth.uid()) and (select public.is_active_user())) or (select public.is_admin())) $p$);

-- Estadísticas del directorio: cada aliado lee solo las suyas; nadie escribe desde el navegador (solo directory_track).
grant select on public.business_daily_stats to authenticated;
select pg_temp.pol('public.business_daily_stats', 'stats_select', $p$
  create policy stats_select on public.business_daily_stats for select to authenticated
  using (business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) or (select public.is_admin())) $p$);

grant select, delete on public.business_promotions to authenticated;
grant insert (business_id, title, description, starts_on, ends_on, is_active) on public.business_promotions to authenticated;
grant update (title, description, starts_on, ends_on, is_active) on public.business_promotions to authenticated;

select pg_temp.pol('public.business_promotions', 'promo_select', $p$
  create policy promo_select on public.business_promotions for select to authenticated
  using (business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) or (select public.is_admin())) $p$);
select pg_temp.pol('public.business_promotions', 'promo_insert', $p$
  create policy promo_insert on public.business_promotions for insert to authenticated
  with check (business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) and (select public.is_active_user())) $p$);
select pg_temp.pol('public.business_promotions', 'promo_update', $p$
  create policy promo_update on public.business_promotions for update to authenticated
  using ((business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) and (select public.is_active_user()))
         or (select public.is_admin()))
  with check (business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) or (select public.is_admin())) $p$);
select pg_temp.pol('public.business_promotions', 'promo_delete', $p$
  create policy promo_delete on public.business_promotions for delete to authenticated
  using ((business_id in (select b.id from public.businesses b where b.owner_id = (select auth.uid())) and (select public.is_active_user()))
         or (select public.is_admin())) $p$);

-- ---------------------------------------------------------------------
-- Denuncias: NADIE las inserta directamente (ni siquiera usuarios con sesión);
-- se reciben con submit_complaint(), que solo ejecuta la función segura del servidor (Etapa 6).
-- Solo administradores las leen y gestionan,
-- y solo pueden cambiar estado, prioridad, notas y seguimiento.
-- ---------------------------------------------------------------------
grant select on public.complaints to authenticated;
grant update (status, priority, internal_notes, public_update, attended) on public.complaints to authenticated;
select pg_temp.pol('public.complaints', 'complaints_select_admin', $p$
  create policy complaints_select_admin on public.complaints for select to authenticated
  using ((select public.is_admin())) $p$);
select pg_temp.pol('public.complaints', 'complaints_update_admin', $p$
  create policy complaints_update_admin on public.complaints for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin())) $p$);

-- ---------------------------------------------------------------------
-- Chat: la persona ve sus conversaciones; el admin, todas.
-- Los mensajes son inmutables (sin permisos de editar o borrar).
-- ---------------------------------------------------------------------
grant select on public.conversations, public.messages to authenticated;
grant insert (id, user_id, subject) on public.conversations to authenticated;
grant update (status) on public.conversations to authenticated;
grant insert (conversation_id, body) on public.messages to authenticated;

select pg_temp.pol('public.conversations', 'conv_select', $p$
  create policy conv_select on public.conversations for select to authenticated
  using (user_id = (select auth.uid()) or (select public.is_admin())) $p$);
select pg_temp.pol('public.conversations', 'conv_insert', $p$
  create policy conv_insert on public.conversations for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_active_user())) $p$);
select pg_temp.pol('public.conversations', 'conv_update', $p$
  create policy conv_update on public.conversations for update to authenticated
  using (user_id = (select auth.uid()) or (select public.is_admin()))
  with check (user_id = (select auth.uid()) or (select public.is_admin())) $p$);

select pg_temp.pol('public.messages', 'msg_select', $p$
  create policy msg_select on public.messages for select to authenticated
  using (conversation_id in (select c.id from public.conversations c)) $p$);
select pg_temp.pol('public.messages', 'msg_insert', $p$
  create policy msg_insert on public.messages for insert to authenticated
  with check (conversation_id in (select c.id from public.conversations c) and (select public.is_active_user())) $p$);

-- ---------------------------------------------------------------------
-- Notificaciones: lectura propia, marcar leída y borrar. Se crean en el servidor.
-- ---------------------------------------------------------------------
grant select, delete on public.notifications to authenticated;
grant update (is_read, read_at) on public.notifications to authenticated;
select pg_temp.pol('public.notifications', 'notif_select', $p$
  create policy notif_select on public.notifications for select to authenticated
  using (user_id = (select auth.uid())) $p$);
select pg_temp.pol('public.notifications', 'notif_update', $p$
  create policy notif_update on public.notifications for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid())) $p$);
select pg_temp.pol('public.notifications', 'notif_delete', $p$
  create policy notif_delete on public.notifications for delete to authenticated
  using (user_id = (select auth.uid())) $p$);

-- ---------------------------------------------------------------------
-- Guías: lectura pública de las publicadas; los administradores gestionan todo.
-- ---------------------------------------------------------------------
grant select on public.care_guides to anon, authenticated;
grant insert, update, delete on public.care_guides to authenticated;
select pg_temp.pol('public.care_guides', 'guides_select_public', $p$
  create policy guides_select_public on public.care_guides for select to anon, authenticated
  using (is_published) $p$);
select pg_temp.pol('public.care_guides', 'guides_admin_all', $p$
  create policy guides_admin_all on public.care_guides for all to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin())) $p$);

-- ---------------------------------------------------------------------
-- Bitácora: solo lectura para administradores. Escribe únicamente el servidor.
-- ---------------------------------------------------------------------
grant select on public.admin_audit_log to authenticated;
select pg_temp.pol('public.admin_audit_log', 'audit_select_admin', $p$
  create policy audit_select_admin on public.admin_audit_log for select to authenticated
  using ((select public.is_admin())) $p$);

-- ---------------------------------------------------------------------
-- Funciones que el navegador puede llamar (todo lo demás está cerrado)
-- ---------------------------------------------------------------------
-- Público (sin sesión): consultar seguimiento, placa QR, directorio.
-- (Reportar NO está aquí: las denuncias solo entran por la función segura «submit-complaint», que usa la clave secreta
--  del servidor después de comprobar Cloudflare Turnstile. Ver más abajo, «Solo el servidor».)
grant execute on function public.track_complaint(text) to anon, authenticated;
grant execute on function public.get_public_pet_profile(text) to anon, authenticated;
grant execute on function public.directory_search(text, text, text, integer, integer) to anon, authenticated;
grant execute on function public.directory_get(uuid) to anon, authenticated;
grant execute on function public.directory_track(uuid, text) to anon, authenticated;

-- Solo el servidor (clave secreta de la función segura de denuncias; nunca el navegador).
revoke execute on function public.complaint_precheck(text, integer) from public, anon, authenticated;
revoke execute on function public.submit_complaint(text, text, date, text, text, text, text, text[]) from public, anon, authenticated;
grant execute on function public.complaint_precheck(text, integer) to service_role;
grant execute on function public.submit_complaint(text, text, date, text, text, text, text, text[]) to service_role;

-- Con sesión.
grant execute on function public.is_admin(), public.is_active_user(), public.is_business_account() to authenticated;
grant execute on function public.my_entitlements() to authenticated;
grant execute on function public.cancel_my_subscription() to authenticated;
grant execute on function public.regenerate_pet_qr_token(uuid) to authenticated;
grant execute on function public.storage_has_room(text, integer) to authenticated;
grant execute on function public.has_qr_plan() to authenticated;
grant execute on function public.start_conversation(text, text) to authenticated;

-- Administración (cada función vuelve a comprobar is_admin() en el servidor).
grant execute on function public.admin_dashboard_stats() to authenticated;
grant execute on function public.admin_list_users(text, integer, integer) to authenticated;
grant execute on function public.admin_set_user_suspended(uuid, boolean, text) to authenticated;
grant execute on function public.admin_set_business_status(uuid, text) to authenticated;
grant execute on function public.admin_set_business_verified(uuid, boolean) to authenticated;
grant execute on function public.admin_assign_subscription(uuid, text, text, timestamptz, timestamptz, text) to authenticated;
grant execute on function public.admin_cancel_subscription(uuid, text) to authenticated;
grant execute on function public.admin_renew_subscription(uuid, text) to authenticated;
grant execute on function public.admin_set_subscription_dates(uuid, timestamptz, timestamptz) to authenticated;

-- ---------------------------------------------------------------------
-- Tiempo real (chat y notificaciones). Realtime respeta las políticas RLS.
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach t in array array['messages', 'conversations', 'notifications'] loop
      if not exists (select 1 from pg_publication_tables
                     where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
        execute format('alter publication supabase_realtime add table public.%I', t);
      end if;
    end loop;
  end if;
end $$;
