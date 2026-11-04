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
