-- TECNOPATITAS · Etapa 2 · INSTALADOR COMPLETO (generado: no lo edites; edita 01..05 y vuelve a generarlo)

-- >>>>>>>>>> 01_esquema.sql
-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 01 · ESQUEMA
-- Tablas, restricciones, índices. Se puede ejecutar más de una vez.
-- Se ejecuta en Supabase: SQL Editor → New query → pegar → Run.
-- =====================================================================

-- Esquema interno: NO se expone por la API de Supabase (solo schema "public").
create schema if not exists private;
revoke all on schema private from public;

-- ---------------------------------------------------------------------
-- Perfiles (1 fila por usuario de Supabase Auth)
-- ---------------------------------------------------------------------
create table if not exists public.profiles (
  id                  uuid primary key references auth.users (id) on delete cascade,
  display_name        text not null default '' check (char_length(display_name) <= 80),
  account_type        text not null default 'owner' check (account_type in ('owner', 'business')),
  avatar_path         text check (avatar_path is null or char_length(avatar_path) <= 300),
  phone               text check (phone is null or phone ~ '^[0-9+() .-]{7,20}$'),
  notification_prefs  jsonb not null default jsonb_build_object(
                        'vacuna', true, 'desparasitacion', true, 'cita', true, 'promocion', true,
                        'suscripcion', true, 'mensaje', true, 'aviso', true)
                      check (jsonb_typeof(notification_prefs) = 'object' and pg_column_size(notification_prefs) < 1000),
  email_reminders     boolean not null default false,
  is_suspended        boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Administradores. SOLO se escribe desde el SQL Editor o con service_role.
-- Ningún usuario puede insertarse aquí desde el navegador.
-- ---------------------------------------------------------------------
create table if not exists public.admin_roles (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  role        text not null default 'admin' check (role = 'admin'),
  note        text check (note is null or char_length(note) <= 200),
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Planes (los cinco del modelo de negocio) y sus permisos
-- NULL en un límite = ilimitado.
-- ---------------------------------------------------------------------
create table if not exists public.subscription_plans (
  id                        text primary key check (id ~ '^[a-z]+$'),
  name                      text not null,
  tagline                   text not null,
  audience                  text not null check (audience in ('owner', 'business')),
  price_monthly_mxn         integer not null check (price_monthly_mxn >= 0),
  price_yearly_mxn          integer not null check (price_yearly_mxn >= 0),
  yearly_savings_mxn        integer generated always as (price_monthly_mxn * 12 - price_yearly_mxn) stored,
  benefits                  text[] not null,
  sort_order                smallint not null default 0,
  health_card_pet_limit     integer check (health_card_pet_limit is null or health_card_pet_limit >= 0),
  qr_enabled                boolean not null default false,
  reminders_enabled         boolean not null default false,
  partner_discounts         boolean not null default false,
  stackable_coupons         boolean not null default false,
  priority_workshops        boolean not null default false,
  max_promotions_per_month  integer check (max_promotions_per_month is null or max_promotions_per_month >= 0),
  whatsapp_button           boolean not null default false,
  priority_listing          boolean not null default false,
  verified_badge_eligible   boolean not null default false,
  social_promotion          boolean not null default false,
  is_active                 boolean not null default true
);

-- ---------------------------------------------------------------------
-- Suscripciones (sin pagos: las asigna un administrador)
-- ---------------------------------------------------------------------
create table if not exists public.subscriptions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (id) on delete cascade,
  plan_id         text not null references public.subscription_plans (id),
  billing_period  text not null default 'monthly' check (billing_period in ('monthly', 'yearly')),
  status          text not null default 'active' check (status in ('active', 'cancelled', 'expired', 'replaced')),
  starts_at       timestamptz not null default now(),
  ends_at         timestamptz,
  cancelled_at    timestamptz,
  assigned_by     uuid references auth.users (id) on delete set null,
  note            text check (note is null or char_length(note) <= 500),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  check (ends_at is null or ends_at > starts_at)
);
create unique index if not exists subscriptions_one_active_per_user
  on public.subscriptions (user_id) where status = 'active';
create index if not exists subscriptions_user_idx on public.subscriptions (user_id, created_at desc);

create table if not exists public.subscription_events (
  id               bigint generated always as identity primary key,
  subscription_id  uuid references public.subscriptions (id) on delete set null,
  user_id          uuid not null references public.profiles (id) on delete cascade,
  event            text not null check (event in ('assigned', 'changed', 'renewed', 'cancelled', 'expired', 'dates_changed')),
  from_plan        text,
  to_plan          text,
  actor_id         uuid references auth.users (id) on delete set null,
  details          jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now()
);
create index if not exists subscription_events_user_idx on public.subscription_events (user_id, created_at desc);

-- ---------------------------------------------------------------------
-- Mascotas y carnet de salud
-- ---------------------------------------------------------------------
create table if not exists public.pets (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name         text not null check (char_length(btrim(name)) between 1 and 60),
  photo_path   text check (photo_path is null or char_length(photo_path) <= 300),
  species      text not null check (species in ('perro', 'gato', 'ave', 'conejo', 'pequeno_mamifero', 'otro')),
  breed        text check (breed is null or char_length(breed) <= 80),
  sex          text check (sex is null or sex in ('macho', 'hembra')),
  birth_date   date check (birth_date is null or (birth_date >= date '1990-01-01' and birth_date <= current_date + 1)),
  weight_kg    numeric(5, 2) check (weight_kg is null or (weight_kg > 0 and weight_kg <= 200)),
  description  text check (description is null or char_length(description) <= 1000),
  vet_info     text check (vet_info is null or char_length(vet_info) <= 2000),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists pets_owner_idx on public.pets (owner_id);

create table if not exists public.pet_vaccinations (
  id            uuid primary key default gen_random_uuid(),
  pet_id        uuid not null references public.pets (id) on delete cascade,
  vaccine_name  text not null check (char_length(btrim(vaccine_name)) between 1 and 100),
  applied_on    date not null check (applied_on >= date '1990-01-01' and applied_on <= current_date + 1),
  next_due_on   date check (next_due_on is null or next_due_on >= applied_on),
  veterinarian  text check (veterinarian is null or char_length(veterinarian) <= 100),
  notes         text check (notes is null or char_length(notes) <= 1000),
  created_at    timestamptz not null default now()
);
create index if not exists pet_vaccinations_pet_idx on public.pet_vaccinations (pet_id, applied_on desc);
create index if not exists pet_vaccinations_due_idx on public.pet_vaccinations (next_due_on) where next_due_on is not null;

create table if not exists public.pet_deworming (
  id            uuid primary key default gen_random_uuid(),
  pet_id        uuid not null references public.pets (id) on delete cascade,
  product_name  text not null check (char_length(btrim(product_name)) between 1 and 100),
  kind          text not null default 'interna' check (kind in ('interna', 'externa', 'ambas')),
  applied_on    date not null check (applied_on >= date '1990-01-01' and applied_on <= current_date + 1),
  next_due_on   date check (next_due_on is null or next_due_on >= applied_on),
  notes         text check (notes is null or char_length(notes) <= 1000),
  created_at    timestamptz not null default now()
);
create index if not exists pet_deworming_pet_idx on public.pet_deworming (pet_id, applied_on desc);
create index if not exists pet_deworming_due_idx on public.pet_deworming (next_due_on) where next_due_on is not null;

-- Las consultas realizadas se consultan como citas con status = 'realizada'.
create table if not exists public.pet_appointments (
  id            uuid primary key default gen_random_uuid(),
  pet_id        uuid not null references public.pets (id) on delete cascade,
  kind          text not null default 'consulta' check (kind in ('consulta', 'vacunacion', 'desparasitacion', 'estetica', 'otra')),
  scheduled_at  timestamptz not null,
  status        text not null default 'programada' check (status in ('programada', 'realizada', 'cancelada')),
  clinic        text check (clinic is null or char_length(clinic) <= 120),
  reason        text check (reason is null or char_length(reason) <= 300),
  notes         text check (notes is null or char_length(notes) <= 1000),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists pet_appointments_pet_idx on public.pet_appointments (pet_id, scheduled_at desc);
create index if not exists pet_appointments_upcoming_idx on public.pet_appointments (scheduled_at) where status = 'programada';

-- Placa QR: el token es largo y aleatorio. Lo público lo decide el dueño.
create table if not exists public.pet_qr_profiles (
  id             uuid primary key default gen_random_uuid(),
  pet_id         uuid not null unique references public.pets (id) on delete cascade,
  public_token   text not null unique default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  is_active      boolean not null default true,
  show_name      boolean not null default true,
  show_photo     boolean not null default false,
  show_breed     boolean not null default true,
  public_message text check (public_message is null or char_length(public_message) <= 300),
  contact_name   text check (contact_name is null or char_length(contact_name) <= 80),
  contact_phone  text check (contact_phone is null or contact_phone ~ '^[0-9+() .-]{7,20}$'),
  show_phone     boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check (not show_phone or contact_phone is not null)
);
-- Etapa 4: foto pública de la placa. La foto de la mascota vive en un bucket PRIVADO; para mostrarla a quien
-- escanee la placa, la persona sube a propósito una copia a un bucket público (qr-photos) y la elige aquí.
alter table public.pet_qr_profiles add column if not exists qr_photo_path text
  check (qr_photo_path is null or char_length(qr_photo_path) <= 300);

-- ---------------------------------------------------------------------
-- Establecimientos aliados y promociones
-- ---------------------------------------------------------------------
create table if not exists public.businesses (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid default auth.uid() references public.profiles (id) on delete cascade,
  is_demo       boolean not null default false,
  name          text not null check (char_length(btrim(name)) between 2 and 100),
  category      text not null check (category in ('veterinaria', 'estetica_canina', 'estetica_felina', 'tienda', 'adiestramiento', 'otro')),
  description   text check (description is null or char_length(description) <= 1000),
  address       text check (address is null or char_length(address) <= 200),
  state         text check (state is null or char_length(state) <= 80),
  municipality  text check (municipality is null or char_length(municipality) <= 80),
  phone         text check (phone is null or phone ~ '^[0-9+() .-]{7,20}$'),
  whatsapp_url  text check (whatsapp_url is null or whatsapp_url ~ '^https://wa\.me/[0-9]{8,15}(\?text=[A-Za-z0-9%._~+-]{1,255})?$'),
  maps_query    text check (maps_query is null or char_length(maps_query) <= 200),
  logo_path     text check (logo_path is null or char_length(logo_path) <= 300),
  photo_paths   text[] not null default '{}' check (cardinality(photo_paths) <= 6 and pg_column_size(photo_paths) < 2500),
  hours         jsonb not null default '{}'::jsonb check (jsonb_typeof(hours) = 'object' and pg_column_size(hours) < 2000),
  status        text not null default 'pending' check (status in ('pending', 'approved', 'suspended', 'rejected')),
  verified      boolean not null default false,
  verified_at   timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  check (is_demo or owner_id is not null),
  check (not verified or status = 'approved')
);
create index if not exists businesses_owner_idx on public.businesses (owner_id);
create index if not exists businesses_listing_idx on public.businesses (status, category);

create table if not exists public.business_promotions (
  id           uuid primary key default gen_random_uuid(),
  business_id  uuid not null references public.businesses (id) on delete cascade,
  title        text not null check (char_length(btrim(title)) between 3 and 100),
  description  text check (description is null or char_length(description) <= 500),
  starts_on    date not null default ((now() at time zone 'America/Mexico_City')::date),
  ends_on      date not null,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  check (ends_on >= starts_on and ends_on <= starts_on + 366)
);
create index if not exists business_promotions_business_idx on public.business_promotions (business_id, created_at desc);

-- Estadísticas básicas del directorio (Etapa 5): SOLO contadores por día y por establecimiento.
-- No se guarda IP, identidad ni nada que permita saber quién visitó la ficha.
create table if not exists public.business_daily_stats (
  business_id  uuid not null references public.businesses (id) on delete cascade,
  day          date not null,
  views        integer not null default 0 check (views >= 0),
  map_clicks   integer not null default 0 check (map_clicks >= 0),
  primary key (business_id, day)
);

-- ---------------------------------------------------------------------
-- Denuncias anónimas.
-- IMPORTANTE: esta tabla NO tiene ninguna columna que identifique a quien
-- reporta (ni usuario, ni correo, ni IP).
-- ---------------------------------------------------------------------
create table if not exists public.complaints (
  id                 uuid primary key default gen_random_uuid(),
  tracking_code      text not null unique check (tracking_code ~ '^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$'),
  type               text not null check (type in ('maltrato_fisico', 'abandono', 'sin_agua_alimento_refugio',
                                                   'hacinamiento_insalubre', 'comercio_ilegal', 'otra')),
  description        text not null check (char_length(description) between 30 and 4000),
  approx_date        date not null check (approx_date >= date '2000-01-01' and approx_date <= current_date + 1),
  state              text not null check (char_length(btrim(state)) between 2 and 80),
  municipality       text not null check (char_length(btrim(municipality)) between 2 and 80),
  location_reference text check (location_reference is null or char_length(location_reference) <= 300),
  extra_info         text check (extra_info is null or char_length(extra_info) <= 2000),
  photo_paths        text[] not null default '{}' check (cardinality(photo_paths) <= 3 and pg_column_size(photo_paths) < 1000),
  status             text not null default 'recibida' check (status in ('recibida', 'en_revision', 'en_proceso', 'canalizada', 'cerrada')),
  priority           text check (priority is null or priority in ('baja', 'media', 'alta', 'urgente')),
  internal_notes     text check (internal_notes is null or char_length(internal_notes) <= 4000),
  public_update      text check (public_update is null or char_length(public_update) <= 500),
  attended           boolean not null default false,
  attended_at        timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index if not exists complaints_status_idx on public.complaints (status, created_at desc);

-- ---------------------------------------------------------------------
-- Atención al cliente (chat)
-- ---------------------------------------------------------------------
create table if not exists public.conversations (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  subject          text not null check (char_length(btrim(subject)) between 3 and 120),
  status           text not null default 'abierta' check (status in ('abierta', 'cerrada')),
  last_sender      text not null default 'user' check (last_sender in ('user', 'staff')),
  last_message_at  timestamptz not null default now(),
  created_at       timestamptz not null default now()
);
create index if not exists conversations_user_idx on public.conversations (user_id, last_message_at desc);
create index if not exists conversations_inbox_idx on public.conversations (status, last_sender, last_message_at desc);

create table if not exists public.messages (
  id               uuid primary key default gen_random_uuid(),
  conversation_id  uuid not null references public.conversations (id) on delete cascade,
  sender_id        uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  sender_role      text not null default 'user' check (sender_role in ('user', 'staff')),
  body             text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at       timestamptz not null default now()
);
create index if not exists messages_conversation_idx on public.messages (conversation_id, created_at);
create index if not exists messages_sender_idx on public.messages (sender_id, created_at desc);

-- ---------------------------------------------------------------------
-- Notificaciones
-- ---------------------------------------------------------------------
create table if not exists public.notifications (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (id) on delete cascade,
  type          text not null check (type in ('vacuna', 'desparasitacion', 'cita', 'promocion', 'suscripcion', 'mensaje', 'aviso')),
  title         text not null check (char_length(btrim(title)) between 1 and 120),
  body          text check (body is null or char_length(body) <= 500),
  link          text check (link is null or link ~ '^[a-z0-9._/#?=&-]{1,200}$'),
  is_read       boolean not null default false,
  read_at       timestamptz,
  dedupe_key    text check (dedupe_key is null or char_length(dedupe_key) <= 120),
  email_status  text not null default 'no_solicitado' check (email_status in ('no_solicitado', 'pendiente', 'enviado', 'fallido')),
  created_at    timestamptz not null default now()
);
create index if not exists notifications_user_idx on public.notifications (user_id, is_read, created_at desc);
create unique index if not exists notifications_dedupe_idx on public.notifications (user_id, dedupe_key) where dedupe_key is not null;

-- ---------------------------------------------------------------------
-- Guías de cuidado (contenido administrable)
-- ---------------------------------------------------------------------
create table if not exists public.care_guides (
  id             uuid primary key default gen_random_uuid(),
  slug           text not null unique check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and char_length(slug) <= 120),
  title          text not null check (char_length(btrim(title)) between 3 and 160),
  summary        text not null check (char_length(summary) <= 300),
  content        text not null check (char_length(content) between 1 and 20000),
  category       text not null check (category in ('perros', 'gatos', 'aves', 'conejos', 'pequenos-mamiferos',
                                                   'alimentacion', 'higiene', 'vacunacion', 'salud-preventiva', 'comportamiento')),
  image_path     text check (image_path is null or char_length(image_path) <= 300),
  author_source  text not null default '' check (char_length(author_source) <= 200),
  is_published   boolean not null default false,
  published_at   timestamptz,
  created_by     uuid default auth.uid() references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check (not is_published or published_at is not null)
);
create index if not exists care_guides_listing_idx on public.care_guides (is_published, category, published_at desc);

-- ---------------------------------------------------------------------
-- Bitácora de operaciones administrativas (solo lectura para admins)
-- ---------------------------------------------------------------------
create table if not exists public.admin_audit_log (
  id            bigint generated always as identity primary key,
  admin_id      uuid references auth.users (id) on delete set null,
  action        text not null,
  target_table  text,
  target_id     text,
  details       jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);
create index if not exists admin_audit_log_idx on public.admin_audit_log (created_at desc);

-- ---------------------------------------------------------------------
-- Tablas internas (esquema private: no accesibles desde la API)
-- ---------------------------------------------------------------------
create table if not exists private.settings (
  key    text primary key,
  value  text not null
);
insert into private.settings (key, value)
values ('ip_salt', replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''))
on conflict (key) do nothing;

create table if not exists private.rate_limits (
  bucket        text not null,
  key           text not null,
  window_start  timestamptz not null,
  hits          integer not null default 0,
  primary key (bucket, key, window_start)
);

-- Recordatorios ya generados (Etapa 8): así un recordatorio que la persona borra no vuelve a aparecer.
create table if not exists private.reminder_log (
  user_id     uuid not null references public.profiles (id) on delete cascade,
  dedupe_key  text not null check (char_length(dedupe_key) <= 120),
  created_at  timestamptz not null default now(),
  primary key (user_id, dedupe_key)
);

-- >>>>>>>>>> 02_funciones.sql
-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 02 · FUNCIONES Y DISPARADORES
-- Reglas que el SERVIDOR aplica, sin importar lo que haga el navegador.
-- Todas las funciones SECURITY DEFINER fijan search_path = '' (evita
-- que alguien "secuestre" nombres de funciones o tablas).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Ayudantes de identidad y permisos
-- ---------------------------------------------------------------------

-- ¿El usuario actual es administrador? Solo lee admin_roles (que nadie
-- puede modificar desde el navegador). Nunca usa user_metadata.
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.admin_roles r
    where r.user_id = (select auth.uid()) and r.role = 'admin'
  );
$$;

-- ¿La cuenta actual existe y no está suspendida?
create or replace function public.is_active_user()
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and not p.is_suspended
  );
$$;

create or replace function public.is_business_account()
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and p.account_type = 'business' and not p.is_suspended
  );
$$;

-- Conexión directa a la base (SQL Editor) o service_role: no hay rol en el JWT.
create or replace function private.is_backend()
returns boolean language sql stable set search_path = ''
as $$ select coalesce((select auth.role()), 'service_role') = 'service_role'; $$;

create or replace function private.is_privileged()
returns boolean language sql stable security definer set search_path = ''
as $$ select private.is_backend() or public.is_admin(); $$;

create or replace function private.today_mx()
returns date language sql stable set search_path = ''
as $$ select (now() at time zone 'America/Mexico_City')::date; $$;

-- Plan vigente de un usuario: suscripción activa, o Huellita Básica para
-- dueños de mascota. Un aliado sin suscripción no tiene plan (NULL).
create or replace function private.effective_plan_id(p_user uuid)
returns text language sql stable security definer set search_path = ''
as $$
  select coalesce(
    (select s.plan_id from public.subscriptions s
      where s.user_id = p_user and s.status = 'active'
        and s.starts_at <= now() and (s.ends_at is null or s.ends_at > now())
      order by s.starts_at desc limit 1),
    (select 'basica'::text from public.profiles p where p.id = p_user and p.account_type = 'owner')
  );
$$;

create or replace function private.plan_for(p_user uuid)
returns setof public.subscription_plans language sql stable security definer set search_path = ''
as $$
  select pl.* from public.subscription_plans pl
  where pl.id = private.effective_plan_id(p_user) and pl.is_active;
$$;

-- ---------------------------------------------------------------------
-- Bitácora, notificaciones, límites de uso
-- ---------------------------------------------------------------------
create or replace function private.audit(p_action text, p_table text, p_target text, p_details jsonb default '{}'::jsonb)
returns void language sql security definer set search_path = ''
as $$
  insert into public.admin_audit_log (admin_id, action, target_table, target_id, details)
  values ((select auth.uid()), p_action, p_table, p_target, coalesce(p_details, '{}'::jsonb));
$$;

create or replace function private.notify(
  p_user uuid, p_type text, p_title text, p_body text default null,
  p_link text default null, p_dedupe text default null)
returns void language plpgsql security definer set search_path = ''
as $$
declare v_prefs jsonb; v_n integer;
begin
  select notification_prefs into v_prefs from public.profiles where id = p_user;
  if not found then return; end if;
  -- Los avisos (suspensión, estado del negocio, denuncias para el equipo) no se pueden silenciar; los demás tipos, sí.
  if p_type <> 'aviso' and coalesce(v_prefs ->> p_type, 'true') = 'false' then return; end if;
  insert into public.notifications (user_id, type, title, body, link, dedupe_key)
  values (p_user, p_type, left(p_title, 120), left(p_body, 500), p_link, p_dedupe)
  on conflict (user_id, dedupe_key) where dedupe_key is not null do nothing;
  get diagnostics v_n = row_count;
  if v_n = 0 then return; end if;
  -- Limpieza automática (cuida el espacio del plan gratuito; no hace falta un proceso programado):
  -- las leídas se borran a los 90 días, todas a los 365 días y cada persona conserva como máximo las 200 más recientes.
  delete from public.notifications n
   where n.user_id = p_user and ((n.is_read and n.created_at < now() - interval '90 days') or n.created_at < now() - interval '365 days');
  delete from public.notifications n
   where n.id in (select x.id from public.notifications x where x.user_id = p_user order by x.created_at desc, x.id desc offset 200);
end;
$$;

-- Avisa a todas las cuentas de administración (el equipo). Solo se usa desde funciones del servidor.
create or replace function private.notify_admins(
  p_type text, p_title text, p_body text default null, p_link text default null, p_dedupe text default null)
returns void language plpgsql security definer set search_path = ''
as $$
declare r record;
begin
  for r in select a.user_id from public.admin_roles a loop
    perform private.notify(r.user_id, p_type, p_title, p_body, p_link, p_dedupe);
  end loop;
end;
$$;

-- Huella anónima del visitante: hash(IP + sal secreta + día). No se guarda
-- la IP y la huella cambia cada día, así que no sirve para rastrear personas.
-- ip_key() la calcula a partir de una IP que ya conocemos (la función segura de denuncias la recibe del servidor);
-- client_key() la saca de las cabeceras de la petición (las demás funciones públicas, llamadas desde el navegador).
create or replace function private.ip_key(p_ip text)
returns text language plpgsql stable security definer set search_path = ''
as $$
declare v_salt text;
begin
  select value into v_salt from private.settings where key = 'ip_salt';
  return encode(sha256(convert_to(coalesce(nullif(btrim(p_ip), ''), 'sin-ip') || ':' || coalesce(v_salt, '') || ':' || current_date::text, 'UTF8')), 'hex');
end;
$$;

create or replace function private.client_key()
returns text language plpgsql stable security definer set search_path = ''
as $$
declare v_headers jsonb; v_ip text;
begin
  begin
    v_headers := nullif(current_setting('request.headers', true), '')::jsonb;
  exception when others then
    v_headers := null;
  end;
  v_ip := nullif(btrim(coalesce(v_headers ->> 'cf-connecting-ip',
                                split_part(coalesce(v_headers ->> 'x-forwarded-for', ''), ',', 1), '')), '');
  return private.ip_key(v_ip);
end;
$$;

create or replace function private.rate_limit(p_bucket text, p_key text, p_window text, p_max integer)
returns void language plpgsql security definer set search_path = ''
as $$
declare v_hits integer;
begin
  insert into private.rate_limits as r (bucket, key, window_start, hits)
  values (p_bucket, p_key, date_trunc(p_window, now()), 1)
  on conflict (bucket, key, window_start) do update set hits = r.hits + 1
  returning r.hits into v_hits;
  if v_hits > p_max then
    raise exception 'Demasiadas solicitudes. Intenta de nuevo más tarde.' using errcode = 'P0001';
  end if;
  if random() < 0.02 then
    delete from private.rate_limits where window_start < now() - interval '3 days';
  end if;
end;
$$;

create or replace function private.new_tracking_code()
returns text language plpgsql volatile set search_path = ''
as $$
declare
  v_alpha constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';  -- 32 símbolos, sin I ni O
  v_bytes bytea := decode(replace(gen_random_uuid()::text, '-', ''), 'hex');
  v_idx   constant int[] := array[0, 1, 2, 3, 4, 5, 7, 9];       -- bytes 6 y 8 del UUID no son totalmente aleatorios
  v_out   text := '';
  i       int;
begin
  for i in 1..8 loop
    v_out := v_out || substr(v_alpha, (get_byte(v_bytes, v_idx[i]) % 32) + 1, 1);
  end loop;
  return 'TP-' || substr(v_out, 1, 4) || '-' || substr(v_out, 5, 4);
end;
$$;

-- ---------------------------------------------------------------------
-- Disparadores
-- ---------------------------------------------------------------------
create or replace function private.touch_updated_at()
returns trigger language plpgsql set search_path = ''
as $$ begin new.updated_at := now(); return new; end; $$;

-- Alta de usuario → crea el perfil. El tipo de cuenta que pide el navegador
-- solo puede ser 'owner' o 'business'; "admin" JAMÁS se concede desde aquí.
create or replace function private.handle_new_user()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, account_type)
  values (
    new.id,
    left(btrim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), 80),
    case when new.raw_user_meta_data ->> 'account_type' = 'business' then 'business' else 'owner' end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

-- Defensa en profundidad: aunque algún día se concedan más permisos por
-- error, un usuario normal no puede cambiar su tipo de cuenta ni su suspensión.
create or replace function private.guard_profiles()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if not private.is_privileged() then
    if (to_jsonb(new) - array['display_name', 'avatar_path', 'phone', 'notification_prefs', 'email_reminders', 'updated_at'])
       is distinct from
       (to_jsonb(old) - array['display_name', 'avatar_path', 'phone', 'notification_prefs', 'email_reminders', 'updated_at']) then
      raise exception 'No tienes permiso para cambiar estos campos.' using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

create or replace function private.guard_businesses()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_plan public.subscription_plans; v_count integer;
begin
  if tg_op = 'INSERT' then
    if not private.is_privileged() then
      if not exists (select 1 from public.profiles p
                     where p.id = new.owner_id and p.account_type = 'business' and not p.is_suspended) then
        raise exception 'Solo las cuentas de aliado comercial pueden registrar un establecimiento.' using errcode = '42501';
      end if;
      select count(*) into v_count from public.businesses b where b.owner_id = new.owner_id;
      if v_count >= 5 then
        raise exception 'Alcanzaste el límite de establecimientos por cuenta.' using errcode = 'P0001';
      end if;
      new.status := 'pending'; new.verified := false; new.verified_at := null; new.is_demo := false;
    end if;
  elsif not private.is_privileged() then
    if new.owner_id is distinct from old.owner_id or new.status is distinct from old.status
       or new.verified is distinct from old.verified or new.verified_at is distinct from old.verified_at
       or new.is_demo is distinct from old.is_demo then
      raise exception 'No tienes permiso para cambiar estos campos.' using errcode = '42501';
    end if;
  end if;

  -- Las imágenes del negocio solo pueden estar en la carpeta de su dueño (no se puede apuntar a archivos ajenos).
  if new.owner_id is not null and (tg_op = 'INSERT' or new.logo_path is distinct from old.logo_path) and new.logo_path is not null
     and (new.logo_path !~ ('^' || new.owner_id::text || '/[A-Za-z0-9._-]{1,120}$') or new.logo_path like '%..%') then
    raise exception 'El logotipo no es válido.' using errcode = '23514';
  end if;
  if new.owner_id is not null and (tg_op = 'INSERT' or new.photo_paths is distinct from old.photo_paths)
     and exists (select 1 from unnest(new.photo_paths) x
                 where x !~ ('^' || new.owner_id::text || '/[A-Za-z0-9._-]{1,120}$') or x like '%..%') then
    raise exception 'Una de las fotos no es válida.' using errcode = '23514';
  end if;
  -- Horario: texto corto por día (p. ej. {"lun": "09:00-18:00", "dom": "Cerrado"}); nada anidado.
  if (tg_op = 'INSERT' or new.hours is distinct from old.hours) and jsonb_typeof(new.hours) = 'object'
     and (exists (select 1 from jsonb_each(new.hours) h
                  where jsonb_typeof(h.value) <> 'string' or char_length(h.key) > 20 or char_length(h.value #>> '{}') > 60)
          or (select count(*) from jsonb_object_keys(new.hours)) > 10) then
    raise exception 'El horario no es válido.' using errcode = '23514';
  end if;

  -- El botón de WhatsApp es un beneficio del plan Huellita de Oro.
  if new.whatsapp_url is not null
     and (tg_op = 'INSERT' or new.whatsapp_url is distinct from old.whatsapp_url)
     and not private.is_privileged() then
    select * into v_plan from private.plan_for(new.owner_id);
    if not found or not v_plan.whatsapp_button then
      raise exception 'Tu plan no incluye el botón directo a WhatsApp.' using errcode = 'P0001';
    end if;
  end if;
  return new;
end;
$$;

-- Promociones por mes según el plan (Plata: 1; Oro: ilimitadas; sin plan: 0).
create or replace function private.guard_promotions()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid; v_plan public.subscription_plans; v_count integer; v_month_start timestamptz;
begin
  if private.is_backend() then return new; end if;
  select b.owner_id into v_owner from public.businesses b where b.id = new.business_id;
  if v_owner is null then
    raise exception 'Este establecimiento no admite promociones.' using errcode = '42501';
  end if;
  select * into v_plan from private.plan_for(v_owner);
  if not found then
    raise exception 'Necesitas un plan de aliado para publicar promociones.' using errcode = 'P0001';
  end if;
  if v_plan.max_promotions_per_month is null then return new; end if;
  v_month_start := date_trunc('month', now() at time zone 'America/Mexico_City') at time zone 'America/Mexico_City';
  select count(*) into v_count
  from public.business_promotions bp join public.businesses b on b.id = bp.business_id
  where b.owner_id = v_owner and bp.created_at >= v_month_start;
  if v_count >= v_plan.max_promotions_per_month then
    raise exception 'Tu plan permite % promoción(es) al mes y ya las usaste.', v_plan.max_promotions_per_month
      using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create or replace function private.guard_pet_count()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if (select count(*) from public.pets p where p.owner_id = new.owner_id) >= 30 then
    raise exception 'Alcanzaste el límite de mascotas por cuenta.' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

-- Carnet de salud: Pro = hasta 2 mascotas con carnet, VIP = ilimitado, Básica = 0.
create or replace function private.guard_health_card()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid; v_plan public.subscription_plans; v_count integer;
begin
  if private.is_backend() then return new; end if;
  select p.owner_id into v_owner from public.pets p where p.id = new.pet_id;
  if v_owner is null then
    raise exception 'Mascota no encontrada.' using errcode = '23503';
  end if;
  select * into v_plan from private.plan_for(v_owner);
  if not found or (v_plan.health_card_pet_limit is not null and v_plan.health_card_pet_limit = 0) then
    raise exception 'Tu plan no incluye el carnet de salud digital. Consulta los planes Huellita Pro o VIP.' using errcode = 'P0001';
  end if;
  if v_plan.health_card_pet_limit is null then return new; end if;
  -- Si esta mascota ya tiene carnet, no cuenta como una nueva.
  if exists (select 1 from public.pet_vaccinations where pet_id = new.pet_id)
     or exists (select 1 from public.pet_deworming where pet_id = new.pet_id)
     or exists (select 1 from public.pet_appointments where pet_id = new.pet_id) then
    return new;
  end if;
  select count(*) into v_count from (
    select v.pet_id from public.pet_vaccinations v join public.pets p on p.id = v.pet_id where p.owner_id = v_owner
    union select d.pet_id from public.pet_deworming d join public.pets p on p.id = d.pet_id where p.owner_id = v_owner
    union select a.pet_id from public.pet_appointments a join public.pets p on p.id = a.pet_id where p.owner_id = v_owner
  ) t;
  if v_count >= v_plan.health_card_pet_limit then
    raise exception 'Tu plan permite carnet de salud para % mascota(s).', v_plan.health_card_pet_limit using errcode = 'P0001';
  end if;
  return new;
end;
$$;

-- Placa QR: solo planes con qr_enabled (Huellita VIP).
create or replace function private.guard_qr()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid; v_plan public.subscription_plans;
begin
  if private.is_backend() then return new; end if;
  select p.owner_id into v_owner from public.pets p where p.id = new.pet_id;
  if v_owner is null then
    raise exception 'Mascota no encontrada.' using errcode = '23503';
  end if;
  -- El plan solo se exige para CREAR la placa: una placa ya creada se conserva aunque el plan venza.
  if tg_op = 'INSERT' then
    select * into v_plan from private.plan_for(v_owner);
    if not found or not v_plan.qr_enabled then
      raise exception 'Tu plan no incluye la placa QR. Está disponible en Huellita VIP.' using errcode = 'P0001';
    end if;
  end if;
  -- La foto pública debe ser un archivo de la carpeta del dueño (sin rutas con «..» ni subcarpetas).
  if new.qr_photo_path is not null
     and (new.qr_photo_path !~ ('^' || v_owner::text || '/[A-Za-z0-9._-]{1,120}$') or new.qr_photo_path like '%..%') then
    raise exception 'La foto de la placa no es válida.' using errcode = '23514';
  end if;
  return new;
end;
$$;

-- ¿El plan vigente de quien llama incluye la placa QR? (lo usa la política de subida a qr-photos)
create or replace function public.has_qr_plan()
returns boolean language sql stable security definer set search_path = ''
as $$
  select coalesce((select pl.qr_enabled from private.plan_for((select auth.uid())) pl), false);
$$;

-- El plan debe corresponder al tipo de cuenta (dueños ↔ planes de dueños, etc.).
create or replace function private.guard_subscription()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_aud text; v_type text;
begin
  select pl.audience into v_aud from public.subscription_plans pl where pl.id = new.plan_id;
  select p.account_type into v_type from public.profiles p where p.id = new.user_id;
  if v_aud is distinct from v_type then
    raise exception 'Ese plan no corresponde al tipo de cuenta del usuario.' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create or replace function private.before_conversation()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if not private.is_backend() and
     (select count(*) from public.conversations c where c.user_id = new.user_id and c.status = 'abierta') >= 10 then
    raise exception 'Tienes demasiadas conversaciones abiertas. Cierra alguna antes de crear otra.' using errcode = 'P0001';
  end if;
  -- Tope diario: evita llenar la base (plan gratuito) abriendo y cerrando conversaciones vacías.
  if not private.is_backend() and
     (select count(*) from public.conversations c
      where c.user_id = new.user_id and c.created_at > now() - interval '24 hours') >= 20 then
    raise exception 'Creaste muchas conversaciones hoy. Escribe en una de las que ya tienes o inténtalo mañana.' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

-- Solo el equipo (o el servidor) puede REABRIR una conversación cerrada. La persona puede cerrarla, no reabrirla:
-- así el tope de conversaciones abiertas no se esquiva cerrando y reabriendo.
create or replace function private.guard_conversation_status()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if old.status = 'cerrada' and new.status = 'abierta' and not private.is_backend() and not public.is_admin() then
    raise exception 'La conversación está cerrada. Abre una nueva.' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create or replace function private.before_message()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid; v_status text;
begin
  select c.user_id, c.status into v_owner, v_status from public.conversations c where c.id = new.conversation_id;
  if not found then
    raise exception 'Conversación no encontrada.' using errcode = '23503';
  end if;
  if not private.is_backend() then
    new.sender_id := (select auth.uid());       -- el remitente siempre es quien está conectado
  end if;
  if new.sender_id = v_owner then
    new.sender_role := 'user';
  elsif private.is_backend() or public.is_admin() then
    new.sender_role := 'staff';
  else
    raise exception 'No autorizado.' using errcode = '42501';
  end if;
  if new.sender_role = 'user' and not private.is_backend() then
    if v_status = 'cerrada' then
      raise exception 'La conversación está cerrada. Abre una nueva.' using errcode = 'P0001';
    end if;
    if (select count(*) from public.messages m
        where m.sender_id = new.sender_id and m.created_at > now() - interval '10 minutes') >= 20 then
      raise exception 'Enviaste demasiados mensajes seguidos. Espera unos minutos.' using errcode = 'P0001';
    end if;
    -- Tope diario por cuenta (protege el plan gratuito de almacenamiento y de conexiones).
    if (select count(*) from public.messages m
        where m.sender_id = new.sender_id and m.sender_role = 'user' and m.created_at > now() - interval '24 hours') >= 100 then
      raise exception 'Llegaste al límite de 100 mensajes en 24 horas. Vuelve a escribirnos más tarde.' using errcode = 'P0001';
    end if;
  end if;
  return new;
end;
$$;

create or replace function private.after_message()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid; v_subject text; v_prev text;
begin
  -- Rol del mensaje anterior de la conversación (null si es el primero): sirve para avisar al equipo una sola vez por «turno».
  select m.sender_role into v_prev from public.messages m
   where m.conversation_id = new.conversation_id and m.id <> new.id
   order by m.created_at desc, m.id desc limit 1;
  update public.conversations c
     set last_message_at = new.created_at,
         last_sender = new.sender_role,
         status = case when new.sender_role = 'staff' then 'abierta' else c.status end
   where c.id = new.conversation_id
  returning c.user_id, c.subject into v_owner, v_subject;
  if new.sender_role = 'staff' then
    perform private.notify(v_owner, 'mensaje', 'Nueva respuesta de atención al cliente', left(new.body, 140), 'chat.html');
  elsif v_prev is null or v_prev = 'staff' then
    perform private.notify_admins('mensaje', 'Atención al cliente: conversación esperando respuesta',
                                  left(v_subject, 120), 'admin.html', 'chat-' || new.id::text);
  end if;
  return new;
end;
$$;

-- Avisa al equipo cuando llega una denuncia. El aviso solo lleva el código, el tipo y el estado: la denuncia no tiene ningún dato de quien reporta.
create or replace function private.complaint_after_insert()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  perform private.notify_admins('aviso', 'Nueva denuncia recibida',
                                'Código ' || new.tracking_code || ' · ' || replace(new.type, '_', ' ') || ' · ' || btrim(new.state),
                                'admin.html', 'denuncia-' || new.id::text);
  return new;
end;
$$;

-- Crea la conversación Y su primer mensaje en una sola operación (si algo falla, no queda nada a medias).
-- SECURITY INVOKER: se ejecuta con los permisos y las políticas de la persona que llama; no salta ninguna regla.
create or replace function public.start_conversation(p_subject text, p_body text)
returns uuid language plpgsql security invoker set search_path = ''
as $$
declare v_id uuid; v_subject text := btrim(coalesce(p_subject, '')); v_body text := btrim(coalesce(p_body, ''));
begin
  if (select auth.uid()) is null then
    raise exception 'Inicia sesión para escribirnos.' using errcode = 'P0001';
  end if;
  if char_length(v_subject) < 3 or char_length(v_subject) > 120 then
    raise exception 'El asunto debe tener entre 3 y 120 caracteres.' using errcode = 'P0001';
  end if;
  if char_length(v_body) < 1 or char_length(v_body) > 2000 then
    raise exception 'El mensaje debe tener entre 1 y 2000 caracteres.' using errcode = 'P0001';
  end if;
  insert into public.conversations (subject) values (v_subject) returning id into v_id;
  insert into public.messages (conversation_id, body) values (v_id, v_body);
  return v_id;
end;
$$;

-- Recordatorios dentro de la plataforma (Etapa 8): vacunas y desparasitaciones por vencer o vencidas, y citas próximas.
-- No hay un proceso programado: la página llama a esta función una vez al día al abrirse (y al entrar a Notificaciones).
-- Solo mira las mascotas de quien la llama. Para cada «próxima fecha» usa el ÚLTIMO registro de esa vacuna (o el último
-- de desparasitación de la mascota), así un registro viejo ya renovado no genera avisos falsos.
-- private.reminder_log recuerda lo ya generado: si la persona borra un recordatorio, no vuelve a aparecer.
create or replace function public.generate_my_reminders()
returns integer language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_uid uuid := (select auth.uid());
  v_prefs jsonb; v_today date := private.today_mx(); v_n integer := 0; v_rows integer;
  r record; v_key text; v_title text; v_body text;
  v_months constant text[] := array['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
begin
  if v_uid is null then
    raise exception 'Inicia sesión para ver tus recordatorios.' using errcode = 'P0001';
  end if;
  select p.notification_prefs into v_prefs from public.profiles p where p.id = v_uid;
  if not found then return 0; end if;
  perform private.rate_limit('reminders_h', v_uid::text, 'hour', 30);
  delete from private.reminder_log l where l.user_id = v_uid and l.created_at < now() - interval '180 days';

  for r in
    select * from (
      select 'vacuna'::text as typ, 'vac-' || x.id::text as ref, x.pet_name, x.vaccine_name as what, x.next_due_on as due, null::timestamptz as at, null::text as kind, null::text as clinic
        from (select v.id, v.next_due_on, v.vaccine_name, p.name as pet_name,
                     row_number() over (partition by v.pet_id, lower(btrim(v.vaccine_name)) order by v.applied_on desc, v.created_at desc, v.id desc) as rn
                from public.pet_vaccinations v join public.pets p on p.id = v.pet_id where p.owner_id = v_uid) x
       where x.rn = 1 and x.next_due_on is not null and x.next_due_on between v_today - 60 and v_today + 7
      union all
      select 'desparasitacion', 'dew-' || x.id::text, x.pet_name, x.product_name, x.next_due_on, null, null, null
        from (select d.id, d.next_due_on, d.product_name, p.name as pet_name,
                     row_number() over (partition by d.pet_id order by d.applied_on desc, d.created_at desc, d.id desc) as rn
                from public.pet_deworming d join public.pets p on p.id = d.pet_id where p.owner_id = v_uid) x
       where x.rn = 1 and x.next_due_on is not null and x.next_due_on between v_today - 60 and v_today + 7
      union all
      select 'cita', 'cita-' || a.id::text, p.name, null, null, a.scheduled_at, a.kind, a.clinic
        from public.pet_appointments a join public.pets p on p.id = a.pet_id
       where p.owner_id = v_uid and a.status = 'programada' and a.scheduled_at >= now() and a.scheduled_at < now() + interval '48 hours'
    ) q
    order by coalesce(q.due::timestamptz, q.at) limit 30
  loop
    if coalesce(v_prefs ->> r.typ, 'true') = 'false' then continue; end if;   -- si la persona apagó ese tipo, no se registra (al reactivarlo sí aparecerán)
    if r.typ = 'cita' then
      v_key := r.ref || '-' || extract(epoch from r.at)::bigint::text;
      v_title := 'Cita próxima de ' || r.pet_name;
      v_body := 'Cita de ' || case r.kind when 'vacunacion' then 'vacunación' when 'desparasitacion' then 'desparasitación' when 'estetica' then 'estética' when 'otra' then 'tu mascota' else 'consulta' end
             || ': ' || extract(day from r.at at time zone 'America/Mexico_City')::int::text || ' ' || v_months[extract(month from r.at at time zone 'America/Mexico_City')::int] || ' '
             || extract(year from r.at at time zone 'America/Mexico_City')::int::text || ', ' || to_char(r.at at time zone 'America/Mexico_City', 'HH24:MI') || ' (hora de México)'
             || case when r.clinic is not null then ' · ' || r.clinic else '' end || '.';
    else
      v_key := r.ref || '-' || r.due::text || case when r.due < v_today then '-vencida' else '-proxima' end;
      v_title := case r.typ when 'vacuna' then 'Vacuna ' else 'Desparasitación ' end
              || case when r.due < v_today then 'vencida: ' else 'próxima: ' end || r.what || ' (' || r.pet_name || ')';
      v_body := case when r.due < v_today then 'Debió aplicarse el ' when r.due = v_today then 'Vence hoy: ' else 'Fecha recomendada: ' end
             || extract(day from r.due)::int::text || ' ' || v_months[extract(month from r.due)::int] || ' ' || extract(year from r.due)::int::text
             || '. Consulta a tu veterinario y actualiza el carnet cuando la apliques.';
    end if;
    insert into private.reminder_log (user_id, dedupe_key) values (v_uid, v_key) on conflict do nothing;
    get diagnostics v_rows = row_count;
    if v_rows = 1 then
      perform private.notify(v_uid, r.typ, v_title, v_body, 'carnet.html');
      v_n := v_n + 1;
    end if;
  end loop;
  return v_n;
end;
$$;

create or replace function private.guard_notifications_update()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if not private.is_backend() then
    if (to_jsonb(new) - array['is_read', 'read_at']) is distinct from (to_jsonb(old) - array['is_read', 'read_at']) then
      raise exception 'Solo puedes marcar una notificación como leída.' using errcode = '42501';
    end if;
    new.read_at := case when new.is_read then coalesce(old.read_at, now()) else null end;
  end if;
  return new;
end;
$$;

create or replace function private.guide_before_write()
returns trigger language plpgsql set search_path = ''
as $$
begin
  if new.is_published and new.published_at is null then new.published_at := now(); end if;
  new.updated_at := now();
  return new;
end;
$$;

-- Las denuncias: el contenido original no se puede editar (integridad de la
-- evidencia). Solo se gestionan estado, prioridad, notas y seguimiento.
create or replace function private.complaint_before_update()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if not private.is_backend() and
     (to_jsonb(new) - array['status', 'priority', 'internal_notes', 'public_update', 'attended', 'attended_at', 'updated_at'])
     is distinct from
     (to_jsonb(old) - array['status', 'priority', 'internal_notes', 'public_update', 'attended', 'attended_at', 'updated_at']) then
    raise exception 'El contenido de una denuncia no se puede modificar.' using errcode = '42501';
  end if;
  if new.attended and not old.attended then new.attended_at := now();
  elsif not new.attended then new.attended_at := null;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

create or replace function private.complaint_audit()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if new.status is distinct from old.status or new.priority is distinct from old.priority
     or new.attended is distinct from old.attended or new.internal_notes is distinct from old.internal_notes
     or new.public_update is distinct from old.public_update then
    perform private.audit('complaint_update', 'complaints', new.id::text, jsonb_build_object(
      'status_from', old.status, 'status_to', new.status, 'priority_to', new.priority,
      'attended', new.attended, 'notes_changed', new.internal_notes is distinct from old.internal_notes));
  end if;
  return new;
end;
$$;

-- ---------------------------------------------------------------------
-- Cuota de archivos por persona (la usan las políticas de Storage).
-- Debe ser una función SECURITY DEFINER: una política de storage.objects que
-- consultara storage.objects directamente provoca "infinite recursion".
-- Solo cuenta los archivos de quien la llama (auth.uid()); devuelve verdadero/falso.
-- ---------------------------------------------------------------------
create or replace function public.storage_has_room(p_bucket text, p_max integer)
returns boolean language sql stable security definer set search_path = ''
as $$
  select (select count(*) from storage.objects o
          where o.bucket_id = p_bucket
            and (storage.foldername(o.name))[1] = (select auth.uid())::text) < p_max;
$$;

-- ---------------------------------------------------------------------
-- Crear los disparadores
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['profiles', 'subscriptions', 'pets', 'pet_appointments', 'pet_qr_profiles', 'businesses', 'business_promotions'] loop
    execute format('drop trigger if exists tp_touch on public.%I', t);
    execute format('create trigger tp_touch before update on public.%I for each row execute function private.touch_updated_at()', t);
  end loop;
end $$;

drop trigger if exists tp_new_user on auth.users;
create trigger tp_new_user after insert on auth.users for each row execute function private.handle_new_user();

drop trigger if exists tp_guard on public.profiles;
create trigger tp_guard before update on public.profiles for each row execute function private.guard_profiles();

drop trigger if exists tp_guard on public.businesses;
create trigger tp_guard before insert or update on public.businesses for each row execute function private.guard_businesses();

drop trigger if exists tp_guard on public.business_promotions;
create trigger tp_guard before insert on public.business_promotions for each row execute function private.guard_promotions();

drop trigger if exists tp_guard on public.pets;
create trigger tp_guard before insert on public.pets for each row execute function private.guard_pet_count();

drop trigger if exists tp_guard on public.pet_vaccinations;
create trigger tp_guard before insert on public.pet_vaccinations for each row execute function private.guard_health_card();
drop trigger if exists tp_guard on public.pet_deworming;
create trigger tp_guard before insert on public.pet_deworming for each row execute function private.guard_health_card();
drop trigger if exists tp_guard on public.pet_appointments;
create trigger tp_guard before insert on public.pet_appointments for each row execute function private.guard_health_card();

drop trigger if exists tp_guard on public.pet_qr_profiles;
create trigger tp_guard before insert or update of qr_photo_path, pet_id on public.pet_qr_profiles for each row execute function private.guard_qr();

drop trigger if exists tp_guard on public.subscriptions;
create trigger tp_guard before insert or update of plan_id, user_id on public.subscriptions for each row execute function private.guard_subscription();

drop trigger if exists tp_guard on public.conversations;
create trigger tp_guard before insert on public.conversations for each row execute function private.before_conversation();

drop trigger if exists tp_status on public.conversations;
create trigger tp_status before update of status on public.conversations for each row execute function private.guard_conversation_status();

drop trigger if exists tp_before on public.messages;
create trigger tp_before before insert on public.messages for each row execute function private.before_message();
drop trigger if exists tp_after on public.messages;
create trigger tp_after after insert on public.messages for each row execute function private.after_message();

drop trigger if exists tp_guard on public.notifications;
create trigger tp_guard before update on public.notifications for each row execute function private.guard_notifications_update();

drop trigger if exists tp_write on public.care_guides;
create trigger tp_write before insert or update on public.care_guides for each row execute function private.guide_before_write();

drop trigger if exists tp_before on public.complaints;
create trigger tp_before before update on public.complaints for each row execute function private.complaint_before_update();
drop trigger if exists tp_notify on public.complaints;
create trigger tp_notify after insert on public.complaints for each row execute function private.complaint_after_insert();
drop trigger if exists tp_audit on public.complaints;
create trigger tp_audit after update on public.complaints for each row execute function private.complaint_audit();

-- =====================================================================
-- FUNCIONES PÚBLICAS (RPC): lo que el navegador puede llamar
-- =====================================================================

-- ---- Denuncias anónimas ---------------------------------------------
-- IMPORTANTE (Etapa 6): estas dos funciones NO las llama el navegador. Solo las ejecuta la función segura
-- «submit-complaint» (Supabase Edge Function) con la clave secreta del servidor, DESPUÉS de comprobar Cloudflare
-- Turnstile y de limpiar las fotos. Así nadie puede saltarse el anti-robots llamando a la base de datos directamente.
-- La IP del visitante llega como parámetro (la función segura la lee de su propia petición); aquí solo se guarda su
-- «huella» del día (hash con sal), nunca la IP.
drop function if exists public.submit_complaint(text, text, date, text, text, text, text, text[], text);

-- Paso 1: aplica los límites ANTES de subir fotos (la cuota de archivos gratuita es pequeña).
create or replace function public.complaint_precheck(p_client_ip text, p_photos integer default 0)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_key text; v_used bigint;
begin
  if coalesce(p_photos, 0) < 0 or coalesce(p_photos, 0) > 3 then
    raise exception 'Máximo 3 fotografías.' using errcode = '22023';
  end if;
  v_key := private.ip_key(p_client_ip);
  perform private.rate_limit('complaint_h', v_key, 'hour', 5);
  perform private.rate_limit('complaint_d', v_key, 'day', 15);
  perform private.rate_limit('complaint_g', 'all', 'day', 300);   -- tope global: protege la cuota de la base gratuita
  if coalesce(p_photos, 0) > 0 then
    perform private.rate_limit('complaint_photo_g', 'all', 'day', 100);   -- tope global de reportes con fotos por día
    select coalesce(sum((o.metadata ->> 'size')::bigint), 0) into v_used
      from storage.objects o where o.bucket_id = 'complaint-evidence';
    if v_used > 300 * 1024 * 1024 then                            -- 300 MB de los 1 GB gratuitos reservados para evidencias
      raise exception 'Por ahora no podemos recibir fotografías. Envía tu reporte sin fotos o inténtalo más tarde.' using errcode = 'P0001';
    end if;
  end if;
end;
$$;

-- Paso 2: registra la denuncia y devuelve el código de seguimiento. Las fotos ya están subidas con rutas «carpeta/n.jpg».
create or replace function public.submit_complaint(
  p_type text, p_description text, p_approx_date date, p_state text, p_municipality text,
  p_location_reference text default null, p_extra_info text default null,
  p_photo_paths text[] default '{}')
returns text language plpgsql volatile security definer set search_path = ''
as $$
declare v_code text; v_try integer := 0; v_path text;
begin
  if p_type is null or p_type not in ('maltrato_fisico', 'abandono', 'sin_agua_alimento_refugio',
                                      'hacinamiento_insalubre', 'comercio_ilegal', 'otra') then
    raise exception 'Selecciona el tipo de situación.' using errcode = '22023';
  end if;
  if p_description is null or char_length(btrim(p_description)) < 30 or char_length(p_description) > 4000 then
    raise exception 'La descripción debe tener entre 30 y 4000 caracteres.' using errcode = '22023';
  end if;
  if p_approx_date is null or p_approx_date > private.today_mx() + 1 or p_approx_date < date '2000-01-01' then
    raise exception 'La fecha aproximada no es válida.' using errcode = '22023';
  end if;
  if coalesce(char_length(btrim(p_state)), 0) < 2 or coalesce(char_length(btrim(p_municipality)), 0) < 2
     or char_length(btrim(p_state)) > 80 or char_length(btrim(p_municipality)) > 80 then
    raise exception 'Indica el estado y el municipio.' using errcode = '22023';
  end if;
  if char_length(coalesce(p_location_reference, '')) > 300 then
    raise exception 'La referencia del lugar admite hasta 300 caracteres.' using errcode = '22023';
  end if;
  if coalesce(cardinality(p_photo_paths), 0) > 3 then
    raise exception 'Máximo 3 fotografías.' using errcode = '22023';
  end if;
  foreach v_path in array coalesce(p_photo_paths, '{}') loop
    if v_path is null or v_path !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[1-3]\.jpg$' then
      raise exception 'Ruta de fotografía no válida.' using errcode = '22023';
    end if;
  end loop;

  loop
    v_try := v_try + 1;
    v_code := private.new_tracking_code();
    begin
      insert into public.complaints (tracking_code, type, description, approx_date, state, municipality,
                                     location_reference, extra_info, photo_paths)
      values (v_code, p_type, btrim(p_description), p_approx_date, btrim(p_state), btrim(p_municipality),
              nullif(btrim(p_location_reference), ''), nullif(btrim(p_extra_info), ''), coalesce(p_photo_paths, '{}'));
      return v_code;
    exception when unique_violation then
      if v_try >= 5 then raise; end if;
    end;
  end loop;
end;
$$;

-- Consulta el estado de una denuncia con su código. No revela notas internas.
create or replace function public.track_complaint(p_code text)
returns jsonb language plpgsql volatile security definer set search_path = ''
as $$
declare v_code text := upper(btrim(coalesce(p_code, ''))); v_res jsonb;
begin
  if v_code !~ '^TP-[A-Z2-9]{4}-[A-Z2-9]{4}$' then return null; end if;
  perform private.rate_limit('track_h', private.client_key(), 'hour', 30);
  select jsonb_build_object('status', c.status, 'received_at', c.created_at, 'updated_at', c.updated_at,
                            'public_update', c.public_update, 'attended', c.attended)
    into v_res
  from public.complaints c where c.tracking_code = v_code;
  return v_res;
end;
$$;

-- ---- Placa QR pública -----------------------------------------------
-- Devuelve SOLO lo que el dueño decidió mostrar. Sin domicilio ni correo.
create or replace function public.get_public_pet_profile(p_token text)
returns jsonb language sql stable security definer set search_path = ''
as $$
  select jsonb_build_object(
    'name',          case when q.show_name  then p.name end,
    'species',       p.species,
    'breed',         case when q.show_breed then p.breed end,
    'photo_path',    case when q.show_photo then q.qr_photo_path end,
    'message',       q.public_message,
    'contact_name',  case when q.show_phone then q.contact_name end,
    'contact_phone', case when q.show_phone then q.contact_phone end)
  from public.pet_qr_profiles q
  join public.pets p on p.id = q.pet_id
  where q.public_token = p_token and q.is_active and p_token ~ '^[0-9a-f]{64}$'
  limit 1;
$$;

-- Si una placa se pierde o se filtra, el dueño genera un enlace nuevo y el anterior deja de funcionar.
create or replace function public.regenerate_pet_qr_token(p_pet_id uuid)
returns void language plpgsql volatile security definer set search_path = ''
as $$
begin
  if (select auth.uid()) is null or not public.is_active_user() then
    raise exception 'No autorizado.' using errcode = '42501';
  end if;
  update public.pet_qr_profiles q
     set public_token = replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
   where q.pet_id = p_pet_id
     and exists (select 1 from public.pets p where p.id = q.pet_id and p.owner_id = (select auth.uid()));
  if not found then
    raise exception 'Placa QR no encontrada.' using errcode = '42501';
  end if;
end;
$$;

-- ---- Directorio de aliados (público) ----------------------------------
-- Solo establecimientos aprobados. El botón de WhatsApp solo se muestra si
-- el plan vigente del aliado lo incluye. No se expone el dueño del negocio.
-- (si cambia la forma del resultado hay que recrearla; 03_seguridad_rls.sql vuelve a dar los permisos)
drop function if exists public.directory_search(text, text, text, integer, integer);
create or replace function public.directory_search(
  p_query text default null, p_category text default null,
  p_order text default 'priority', p_limit integer default 24, p_offset integer default 0)
returns table (
  id uuid, name text, category text, description text, address text, state text, municipality text,
  phone text, whatsapp_url text, maps_query text, logo_path text, hours jsonb,
  verified boolean, is_demo boolean, is_priority boolean, full_listing boolean, has_promotion boolean, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_q text := nullif(btrim(coalesce(p_query, '')), '');
  v_limit integer := least(greatest(coalesce(p_limit, 24), 1), 50);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  if p_category is not null and p_category not in ('veterinaria', 'estetica_canina', 'estetica_felina', 'tienda', 'adiestramiento', 'otro') then
    raise exception 'Categoría no válida.' using errcode = '22023';
  end if;
  if p_order not in ('priority', 'name', 'recent') then
    raise exception 'Orden no válido.' using errcode = '22023';
  end if;
  if v_q is not null then
    v_q := '%' || replace(replace(replace(left(v_q, 80), '\', '\\'), '%', '\%'), '_', '\_') || '%';
  end if;
  return query
    -- Sin plan de aliado solo se muestra nombre, categoría, descripción y dirección.
    -- Con plan (Plata u Oro): ficha completa (teléfono, horario, logotipo, promociones).
    select b.id, b.name, b.category, b.description, b.address, b.state, b.municipality,
           case when coalesce(pl.audience = 'business', false) then b.phone end,
           case when coalesce(pl.whatsapp_button, false) then b.whatsapp_url end,
           b.maps_query,
           case when coalesce(pl.audience = 'business', false) then b.logo_path end,
           case when coalesce(pl.audience = 'business', false) then b.hours else '{}'::jsonb end,
           (b.verified and coalesce(pl.verified_badge_eligible, false)), b.is_demo,
           coalesce(pl.priority_listing, false),
           coalesce(pl.audience = 'business', false),
           coalesce(pl.audience = 'business', false) and exists (
             select 1 from public.business_promotions bp
             where bp.business_id = b.id and bp.is_active
               and private.today_mx() between bp.starts_on and bp.ends_on),
           count(*) over ()
    from public.businesses b
    left join lateral (select x.audience, x.whatsapp_button, x.priority_listing, x.verified_badge_eligible from public.subscription_plans x
                       where x.id = private.effective_plan_id(b.owner_id)) pl on true
    where b.status = 'approved'
      and (p_category is null or b.category = p_category)
      and (v_q is null or b.name ilike v_q escape '\' or coalesce(b.description, '') ilike v_q escape '\'
                       or coalesce(b.municipality, '') ilike v_q escape '\')
    order by (case when p_order = 'priority' then coalesce(pl.priority_listing, false)::int else 0 end) desc,
             (case when p_order = 'recent' then extract(epoch from b.created_at) else 0 end) desc,
             lower(b.name), b.id
    limit v_limit offset v_off;
end;
$$;

create or replace function public.directory_get(p_id uuid)
returns jsonb language sql stable security definer set search_path = ''
as $$
  select jsonb_build_object(
    'id', b.id, 'name', b.name, 'category', b.category, 'description', b.description,
    'address', b.address, 'state', b.state, 'municipality', b.municipality,
    'full_listing', coalesce(pl.audience = 'business', false),
    'phone', case when coalesce(pl.audience = 'business', false) then b.phone end,
    'whatsapp_url', case when coalesce(pl.whatsapp_button, false) then b.whatsapp_url end,
    'maps_query', b.maps_query,
    'logo_path', case when coalesce(pl.audience = 'business', false) then b.logo_path end,
    'photo_paths', case when coalesce(pl.audience = 'business', false) then to_jsonb(b.photo_paths) else '[]'::jsonb end,
    'hours', case when coalesce(pl.audience = 'business', false) then b.hours else '{}'::jsonb end,
    'verified', (b.verified and coalesce(pl.verified_badge_eligible, false)), 'is_demo', b.is_demo,
    'promotions', case when not coalesce(pl.audience = 'business', false) then '[]'::jsonb else coalesce((
      select jsonb_agg(jsonb_build_object('id', bp.id, 'title', bp.title, 'description', bp.description,
                                          'starts_on', bp.starts_on, 'ends_on', bp.ends_on) order by bp.ends_on)
      from public.business_promotions bp
      where bp.business_id = b.id and bp.is_active and private.today_mx() between bp.starts_on and bp.ends_on
    ), '[]'::jsonb) end)
  from public.businesses b
  left join lateral (select x.audience, x.whatsapp_button, x.verified_badge_eligible from public.subscription_plans x
                     where x.id = private.effective_plan_id(b.owner_id)) pl on true
  where b.id = p_id and b.status = 'approved';
$$;

-- Conteo de visitas (Etapa 5): 'view' = alguien abrió la ficha completa; 'map' = tocó «Ver ubicación» o «Cómo llegar».
-- Solo suma contadores por día. Máximo 1 visita y 3 clics por visitante, establecimiento y día (huella anónima que
-- cambia a diario; no se guarda la IP). No cuenta las visitas del propio dueño ni de fichas de demostración.
-- Nunca devuelve error al visitante: si algo no cuadra, simplemente no cuenta.
create or replace function public.directory_track(p_id uuid, p_event text)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_owner uuid;
begin
  if p_id is null or p_event is null or p_event not in ('view', 'map') then return; end if;
  select b.owner_id into v_owner from public.businesses b
   where b.id = p_id and b.status = 'approved' and not b.is_demo;
  if not found then return; end if;
  if v_owner is not null and v_owner = (select auth.uid()) then return; end if;
  begin
    perform private.rate_limit('trk_' || p_event, private.client_key() || ':' || p_id::text, 'day',
                               case p_event when 'view' then 1 else 3 end);
  exception when sqlstate 'P0001' then
    return;
  end;
  insert into public.business_daily_stats as s (business_id, day, views, map_clicks)
  values (p_id, private.today_mx(), (p_event = 'view')::int, (p_event = 'map')::int)
  on conflict (business_id, day) do update
    set views = s.views + excluded.views, map_clicks = s.map_clicks + excluded.map_clicks;
end;
$$;

-- ---- Suscripciones: lo que ve y puede hacer la persona usuaria --------
create or replace function public.my_entitlements()
returns jsonb language sql stable security definer set search_path = ''
as $$
  select jsonb_build_object(
    'plan', (select to_jsonb(pl) from private.plan_for((select auth.uid())) pl),
    'subscription', (select to_jsonb(s) - 'assigned_by' - 'note'
                       from public.subscriptions s
                      where s.user_id = (select auth.uid()) and s.status = 'active'
                        and s.starts_at <= now() and (s.ends_at is null or s.ends_at > now())
                      order by s.starts_at desc limit 1))
  where (select auth.uid()) is not null;
$$;

create or replace function public.cancel_my_subscription()
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare v_uid uuid := (select auth.uid()); v_sub public.subscriptions;
begin
  if v_uid is null then raise exception 'No autorizado.' using errcode = '42501'; end if;
  update public.subscriptions s set status = 'cancelled', cancelled_at = now()
   where s.user_id = v_uid and s.status = 'active'
  returning s.* into v_sub;
  if not found then
    raise exception 'No tienes una suscripción activa.' using errcode = 'P0001';
  end if;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, actor_id)
  values (v_sub.id, v_uid, 'cancelled', v_sub.plan_id, v_uid);
  return v_sub.id;
end;
$$;

-- =====================================================================
-- FUNCIONES DE ADMINISTRACIÓN
-- Cada una verifica is_admin() DENTRO del servidor y deja registro en la
-- bitácora. Ocultar un botón en la página nunca es la protección.
-- =====================================================================
create or replace function private.require_admin()
returns void language plpgsql stable security definer set search_path = ''
as $$
begin
  if not public.is_admin() then
    raise exception 'No autorizado.' using errcode = '42501';
  end if;
end;
$$;

create or replace function public.admin_dashboard_stats()
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  return jsonb_build_object(
    'users',                    (select count(*) from public.profiles),
    'pets',                     (select count(*) from public.pets),
    'businesses',               (select count(*) from public.businesses where not is_demo),
    'businesses_pending',       (select count(*) from public.businesses where status = 'pending'),
    'complaints',               (select count(*) from public.complaints),
    'complaints_pending',       (select count(*) from public.complaints where status in ('recibida', 'en_revision')),
    'conversations_unanswered', (select count(*) from public.conversations where status = 'abierta' and last_sender = 'user'),
    'active_subscriptions',     (select count(*) from public.subscriptions
                                  where status = 'active' and starts_at <= now() and (ends_at is null or ends_at > now())));
end;
$$;

create or replace function public.admin_list_users(p_search text default null, p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, email text, display_name text, account_type text, is_suspended boolean,
               created_at timestamptz, plan_id text, is_admin boolean, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_q text := nullif(btrim(coalesce(p_search, '')), '');
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if v_q is not null then
    v_q := '%' || replace(replace(replace(left(v_q, 80), '\', '\\'), '%', '\%'), '_', '\_') || '%';
  end if;
  return query
    select p.id, u.email::text, p.display_name, p.account_type, p.is_suspended, p.created_at,
           private.effective_plan_id(p.id),
           exists (select 1 from public.admin_roles r where r.user_id = p.id),
           count(*) over ()
    from public.profiles p join auth.users u on u.id = p.id
    where v_q is null or u.email ilike v_q escape '\' or p.display_name ilike v_q escape '\'
    order by p.created_at desc, p.id
    limit v_limit offset v_off;
end;
$$;

-- Suspende o reactiva una cuenta. La suspensión bloquea escrituras (RLS).
-- Los administradores no se pueden suspender por esta vía.
create or replace function public.admin_set_user_suspended(p_user uuid, p_suspended boolean, p_reason text default null)
returns void language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  if exists (select 1 from public.admin_roles r where r.user_id = p_user) then
    raise exception 'No se puede suspender a un administrador.' using errcode = 'P0001';
  end if;
  update public.profiles set is_suspended = coalesce(p_suspended, false) where id = p_user;
  if not found then raise exception 'Usuario no encontrado.' using errcode = 'P0002'; end if;
  perform private.audit(case when p_suspended then 'user_suspend' else 'user_reactivate' end,
                        'profiles', p_user::text, jsonb_build_object('reason', left(p_reason, 300)));
  perform private.notify(p_user, 'aviso',
    case when p_suspended then 'Tu cuenta fue suspendida' else 'Tu cuenta fue reactivada' end,
    left(p_reason, 300), 'perfil.html');
end;
$$;

create or replace function public.admin_set_business_status(p_business uuid, p_status text)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_owner uuid;
begin
  perform private.require_admin();
  if p_status not in ('pending', 'approved', 'suspended', 'rejected') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  update public.businesses b
     set status = p_status,
         verified = case when p_status = 'approved' then b.verified else false end,
         verified_at = case when p_status = 'approved' then b.verified_at else null end
   where b.id = p_business
  returning b.owner_id into v_owner;
  if not found then raise exception 'Establecimiento no encontrado.' using errcode = 'P0002'; end if;
  perform private.audit('business_status', 'businesses', p_business::text, jsonb_build_object('status', p_status));
  if v_owner is not null then
    perform private.notify(v_owner, 'aviso', 'Actualización de tu establecimiento',
      case p_status when 'approved' then 'Tu establecimiento fue aprobado y ya aparece en el directorio.'
                    when 'rejected' then 'Tu establecimiento no fue aprobado. Revisa tu información.'
                    when 'suspended' then 'Tu establecimiento fue suspendido del directorio.'
                    else 'Tu establecimiento está en revisión.' end, 'panel-aliado.html');
  end if;
end;
$$;

-- Solo un administrador puede asignar la etiqueta "Aliado verificado".
create or replace function public.admin_set_business_verified(p_business uuid, p_verified boolean)
returns void language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  update public.businesses b
     set verified = coalesce(p_verified, false),
         verified_at = case when p_verified then now() else null end
   where b.id = p_business and b.status = 'approved';
  if not found then
    raise exception 'Solo se puede verificar un establecimiento aprobado.' using errcode = 'P0001';
  end if;
  perform private.audit('business_verify', 'businesses', p_business::text, jsonb_build_object('verified', p_verified));
end;
$$;

create or replace function public.admin_assign_subscription(
  p_user uuid, p_plan text, p_period text default 'monthly',
  p_starts timestamptz default null, p_ends timestamptz default null, p_note text default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_plan public.subscription_plans; v_old public.subscriptions; v_new_id uuid;
  v_start timestamptz := coalesce(p_starts, now()); v_end timestamptz;
begin
  perform private.require_admin();
  if p_period not in ('monthly', 'yearly') then
    raise exception 'Periodo no válido.' using errcode = '22023';
  end if;
  select * into v_plan from public.subscription_plans where id = p_plan and is_active;
  if not found then raise exception 'Plan no encontrado.' using errcode = 'P0002'; end if;
  if not exists (select 1 from public.profiles where id = p_user) then
    raise exception 'Usuario no encontrado.' using errcode = 'P0002';
  end if;
  v_end := coalesce(p_ends, case when v_plan.price_monthly_mxn = 0 then null
                                 when p_period = 'yearly' then v_start + interval '1 year'
                                 else v_start + interval '1 month' end);
  select * into v_old from public.subscriptions where user_id = p_user and status = 'active' for update;
  if found then
    update public.subscriptions set status = 'replaced' where id = v_old.id;
  end if;
  insert into public.subscriptions (user_id, plan_id, billing_period, starts_at, ends_at, assigned_by, note)
  values (p_user, p_plan, p_period, v_start, v_end, (select auth.uid()), left(p_note, 500))
  returning id into v_new_id;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, to_plan, actor_id, details)
  values (v_new_id, p_user, case when v_old.id is null then 'assigned' else 'changed' end,
          v_old.plan_id, p_plan, (select auth.uid()), jsonb_build_object('period', p_period, 'ends_at', v_end));
  perform private.audit('subscription_assign', 'subscriptions', v_new_id::text,
                        jsonb_build_object('user', p_user, 'plan', p_plan, 'period', p_period));
  perform private.notify(p_user, 'suscripcion', 'Tu suscripción cambió', 'Ahora tienes ' || v_plan.name || '.', 'planes.html');
  return v_new_id;
end;
$$;

create or replace function public.admin_cancel_subscription(p_user uuid, p_note text default null)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_sub public.subscriptions;
begin
  perform private.require_admin();
  update public.subscriptions s set status = 'cancelled', cancelled_at = now(), note = coalesce(left(p_note, 500), s.note)
   where s.user_id = p_user and s.status = 'active'
  returning s.* into v_sub;
  if not found then raise exception 'El usuario no tiene una suscripción activa.' using errcode = 'P0001'; end if;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, actor_id)
  values (v_sub.id, p_user, 'cancelled', v_sub.plan_id, (select auth.uid()));
  perform private.audit('subscription_cancel', 'subscriptions', v_sub.id::text, jsonb_build_object('user', p_user));
  perform private.notify(p_user, 'suscripcion', 'Tu suscripción fue cancelada', null, 'planes.html');
end;
$$;

-- Renovación manual: extiende el vencimiento un periodo más.
create or replace function public.admin_renew_subscription(p_subscription uuid, p_note text default null)
returns timestamptz language plpgsql volatile security definer set search_path = ''
as $$
declare v_sub public.subscriptions; v_new_end timestamptz;
begin
  perform private.require_admin();
  select * into v_sub from public.subscriptions where id = p_subscription for update;
  if not found or v_sub.status not in ('active', 'expired') then
    raise exception 'Solo se pueden renovar suscripciones activas o vencidas.' using errcode = 'P0001';
  end if;
  v_new_end := greatest(now(), coalesce(v_sub.ends_at, now()))
               + case v_sub.billing_period when 'yearly' then interval '1 year' else interval '1 month' end;
  update public.subscriptions set ends_at = v_new_end, status = 'active', note = coalesce(left(p_note, 500), note)
   where id = p_subscription;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, to_plan, actor_id, details)
  values (p_subscription, v_sub.user_id, 'renewed', v_sub.plan_id, v_sub.plan_id, (select auth.uid()),
          jsonb_build_object('ends_at', v_new_end));
  perform private.audit('subscription_renew', 'subscriptions', p_subscription::text, jsonb_build_object('ends_at', v_new_end));
  perform private.notify(v_sub.user_id, 'suscripcion', 'Tu suscripción fue renovada', null, 'planes.html');
  return v_new_end;
end;
$$;

create or replace function public.admin_set_subscription_dates(p_subscription uuid, p_starts timestamptz, p_ends timestamptz)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_sub public.subscriptions;
begin
  perform private.require_admin();
  update public.subscriptions s set starts_at = coalesce(p_starts, s.starts_at), ends_at = p_ends
   where s.id = p_subscription returning s.* into v_sub;
  if not found then raise exception 'Suscripción no encontrada.' using errcode = 'P0002'; end if;
  insert into public.subscription_events (subscription_id, user_id, event, actor_id, details)
  values (p_subscription, v_sub.user_id, 'dates_changed', (select auth.uid()),
          jsonb_build_object('starts_at', v_sub.starts_at, 'ends_at', v_sub.ends_at));
  perform private.audit('subscription_dates', 'subscriptions', p_subscription::text,
                        jsonb_build_object('starts_at', v_sub.starts_at, 'ends_at', v_sub.ends_at));
end;
$$;

-- Marca como vencidas las suscripciones cuya fecha ya pasó (se programará en la Etapa 9).
create or replace function private.expire_subscriptions()
returns integer language plpgsql volatile security definer set search_path = ''
as $$
declare v_n integer;
begin
  with e as (
    update public.subscriptions s set status = 'expired'
     where s.status = 'active' and s.ends_at is not null and s.ends_at <= now()
    returning s.id, s.user_id, s.plan_id)
  insert into public.subscription_events (subscription_id, user_id, event, from_plan)
  select id, user_id, 'expired', plan_id from e;
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;

-- >>>>>>>>>> 03_seguridad_rls.sql
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
alter table private.reminder_log enable row level security;

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
grant execute on function public.generate_my_reminders() to authenticated;

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

-- >>>>>>>>>> 04_storage.sql
-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 04 · ALMACENAMIENTO (Supabase Storage)
--
-- Convención de rutas: <id-del-usuario>/<archivo>   (ej. 8b1c…/luna.webp)
-- Solo imágenes JPG, PNG o WebP, con tope de tamaño por archivo.
-- El plan gratuito da 1 GB en total: además de los topes por archivo hay un
-- máximo de archivos por persona.
-- =====================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
  ('avatars',            'avatars',            false, 2097152, array['image/jpeg', 'image/png', 'image/webp']),
  ('pet-photos',         'pet-photos',         false, 5242880, array['image/jpeg', 'image/png', 'image/webp']),
  ('business-media',     'business-media',     true,  5242880, array['image/jpeg', 'image/png', 'image/webp']),
  ('guide-images',       'guide-images',       true,  5242880, array['image/jpeg', 'image/png', 'image/webp']),
  ('qr-photos',          'qr-photos',          true,  1048576, array['image/jpeg', 'image/png', 'image/webp']),
  ('complaint-evidence', 'complaint-evidence', false, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- Atajo para recrear políticas sin errores al volver a ejecutar el script.
create or replace function pg_temp.pol(p_name text, p_sql text)
returns void language plpgsql as $$
begin
  execute format('drop policy if exists %I on storage.objects', p_name);
  execute p_sql;
end $$;

-- ---- avatars (privado): cada quien en su carpeta, máx. 3 archivos ----------
select pg_temp.pol('tp_avatars_select', $p$
  create policy tp_avatars_select on storage.objects for select to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_avatars_insert', $p$
  create policy tp_avatars_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
    and (select public.is_active_user())
    and (select public.storage_has_room('avatars', 3))) $p$);
select pg_temp.pol('tp_avatars_update', $p$
  create policy tp_avatars_update on storage.objects for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_avatars_delete', $p$
  create policy tp_avatars_delete on storage.objects for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);

-- ---- pet-photos (privado): carpeta propia, máx. 60 archivos ----------------
select pg_temp.pol('tp_pets_select', $p$
  create policy tp_pets_select on storage.objects for select to authenticated
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_pets_insert', $p$
  create policy tp_pets_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = (select auth.uid())::text
    and (select public.is_active_user())
    and (select public.storage_has_room('pet-photos', 60))) $p$);
select pg_temp.pol('tp_pets_update', $p$
  create policy tp_pets_update on storage.objects for update to authenticated
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_pets_delete', $p$
  create policy tp_pets_delete on storage.objects for delete to authenticated
  using (bucket_id = 'pet-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);

-- ---- business-media (lectura pública por URL): solo cuentas de aliado escriben, máx. 30 ----
select pg_temp.pol('tp_biz_select', $p$
  create policy tp_biz_select on storage.objects for select to authenticated
  using (bucket_id = 'business-media' and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))) $p$);
select pg_temp.pol('tp_biz_insert', $p$
  create policy tp_biz_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'business-media' and (storage.foldername(name))[1] = (select auth.uid())::text
    and (select public.is_business_account())
    and (select public.storage_has_room('business-media', 30))) $p$);
select pg_temp.pol('tp_biz_update', $p$
  create policy tp_biz_update on storage.objects for update to authenticated
  using (bucket_id = 'business-media' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'business-media' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_biz_delete', $p$
  create policy tp_biz_delete on storage.objects for delete to authenticated
  using (bucket_id = 'business-media' and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))) $p$);

-- ---- qr-photos (lectura pública por URL): foto que la persona decide mostrar en su placa QR ----
-- Solo planes con placa QR pueden subir; máx. 30 archivos de 1 MB. La URL lleva un nombre aleatorio.
select pg_temp.pol('tp_qr_select', $p$
  create policy tp_qr_select on storage.objects for select to authenticated
  using (bucket_id = 'qr-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_qr_insert', $p$
  create policy tp_qr_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'qr-photos' and (storage.foldername(name))[1] = (select auth.uid())::text
    and (select public.is_active_user())
    and (select public.has_qr_plan())
    and (select public.storage_has_room('qr-photos', 30))) $p$);
select pg_temp.pol('tp_qr_update', $p$
  create policy tp_qr_update on storage.objects for update to authenticated
  using (bucket_id = 'qr-photos' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'qr-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);
select pg_temp.pol('tp_qr_delete', $p$
  create policy tp_qr_delete on storage.objects for delete to authenticated
  using (bucket_id = 'qr-photos' and (storage.foldername(name))[1] = (select auth.uid())::text) $p$);

-- ---- guide-images (lectura pública por URL): solo administradores escriben ----
select pg_temp.pol('tp_guides_admin', $p$
  create policy tp_guides_admin on storage.objects for all to authenticated
  using (bucket_id = 'guide-images' and (select public.is_admin()))
  with check (bucket_id = 'guide-images' and (select public.is_admin())) $p$);

-- ---- complaint-evidence (privado): solo administradores leen o borran. -------
-- No hay política de subida: las fotos de denuncias las sube únicamente la función segura
-- «submit-complaint» (Etapa 6) con la clave secreta del servidor, que no está sujeta a estas políticas.
-- Desde el navegador nadie puede subir ahí, ni siquiera un administrador.
select pg_temp.pol('tp_evidence_admin_read', $p$
  create policy tp_evidence_admin_read on storage.objects for select to authenticated
  using (bucket_id = 'complaint-evidence' and (select public.is_admin())) $p$);
select pg_temp.pol('tp_evidence_admin_delete', $p$
  create policy tp_evidence_admin_delete on storage.objects for delete to authenticated
  using (bucket_id = 'complaint-evidence' and (select public.is_admin())) $p$);

-- >>>>>>>>>> 05_datos_base.sql
-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 05 · DATOS BASE
-- Los cinco planes del modelo de negocio, con nombres, precios (MXN) y
-- beneficios EXACTOS. Se puede ejecutar más de una vez (actualiza los datos).
--
-- Permisos que el servidor comprueba (columnas de subscription_plans):
--   health_card_pet_limit  0 = sin carnet · 2 = hasta 2 mascotas · NULL = ilimitado
--   qr_enabled             placa QR digital
--   max_promotions_per_month  0 = ninguna · 1 = una al mes · NULL = ilimitadas
--   whatsapp_button, priority_listing, verified_badge_eligible, ...
-- Los aliados no tienen plan hasta que un administrador les asigna uno.
-- =====================================================================

insert into public.subscription_plans (
  id, name, tagline, audience, price_monthly_mxn, price_yearly_mxn, sort_order, benefits,
  health_card_pet_limit, qr_enabled, reminders_enabled, partner_discounts, stackable_coupons, priority_workshops,
  max_promotions_per_month, whatsapp_button, priority_listing, verified_badge_eligible, social_promotion)
values
('basica', 'Huellita Básica', 'Plan Comunidad', 'owner', 0, 0, 1, array[
   'Acceso ilimitado a guías informativas de cuidados principales',
   'Acceso al módulo de denuncias de maltrato animal, diseñado para permitir reportes anónimos',
   'Consulta del directorio general de aliados locales con nombre y dirección'],
   0, false, false, false, false, false,   0, false, false, false, false),

('pro', 'Huellita Pro', 'Plan Cuidadores', 'owner', 29, 290, 2, array[
   'Todos los beneficios del plan gratuito',
   'Carnet de Salud Digital interactivo para hasta 2 mascotas, con vacunas, desparasitaciones y citas',
   'Recordatorios automáticos previstos por WhatsApp o correo electrónico',
   'Descuentos exclusivos del 5 % al 10 % en la red de aliados locales'],
   2, false, true, true, false, false,   0, false, false, false, false),

('vip', 'Huellita VIP', 'Plan Familia', 'owner', 59, 590, 3, array[
   'Todos los beneficios del plan Huellita Pro',
   'Carnet de Salud Digital ilimitado para familias con 3 o más mascotas',
   'Generador de placa QR digital con acceso al perfil de contacto de la mascota en caso de extravío',
   'Cupones de descuento acumulables',
   'Acceso prioritario a talleres y materiales PDF de nutrición y adiestramiento'],
   null, true, true, true, true, true,   0, false, false, false, false),

('plata', 'Huellita de Plata', 'Plan Aliado Inicial', 'business', 149, 1490, 4, array[
   'Ficha completa en el directorio con nombre, dirección, teléfono, horario y logotipo',
   'Ubicación mediante mapa interactivo',
   'Publicación de hasta una promoción o servicio destacado al mes'],
   0, false, false, false, false, false,   1, false, false, false, false),

('oro', 'Huellita de Oro', 'Plan Aliado Premium', 'business', 299, 2990, 5, array[
   'Todos los beneficios del directorio comercial',
   'Posicionamiento prioritario',
   'Etiqueta «Aliado Verificado / Recomendado», cuando corresponda',
   'Botón directo a WhatsApp',
   'Publicación ilimitada de promociones',
   'Difusión mensual en las redes sociales oficiales de TECNOPATITAS'],
   0, false, false, false, false, false,   null, true, true, true, true)
on conflict (id) do update set
  name = excluded.name, tagline = excluded.tagline, audience = excluded.audience,
  price_monthly_mxn = excluded.price_monthly_mxn, price_yearly_mxn = excluded.price_yearly_mxn,
  sort_order = excluded.sort_order, benefits = excluded.benefits,
  health_card_pet_limit = excluded.health_card_pet_limit, qr_enabled = excluded.qr_enabled,
  reminders_enabled = excluded.reminders_enabled, partner_discounts = excluded.partner_discounts,
  stackable_coupons = excluded.stackable_coupons, priority_workshops = excluded.priority_workshops,
  max_promotions_per_month = excluded.max_promotions_per_month, whatsapp_button = excluded.whatsapp_button,
  priority_listing = excluded.priority_listing, verified_badge_eligible = excluded.verified_badge_eligible,
  social_promotion = excluded.social_promotion, is_active = true;

-- Mensaje final: el editor de Supabase muestra el resultado de la ÚLTIMA instrucción.
select 'Instalación terminada sin errores. Siguiente paso: ejecutar verificar_seguridad.sql' as resultado;
