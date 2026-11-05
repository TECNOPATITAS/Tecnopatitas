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
  insert into public.profiles (id, display_name, account_type, terms_version, terms_accepted_at)
  values (
    new.id,
    left(btrim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), 80),
    case when new.raw_user_meta_data ->> 'account_type' = 'business' then 'business' else 'owner' end,
    case when new.raw_user_meta_data ->> 'terms_version' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then new.raw_user_meta_data ->> 'terms_version' end,
    case when new.raw_user_meta_data ->> 'terms_version' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then now() end
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
                                  left(v_subject, 120), 'admin.html#atencion', 'chat-' || new.id::text);
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
                                'admin.html#denuncias', 'denuncia-' || new.id::text);
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

  -- Vencimiento del plan (Etapa 9): cualquier tipo de cuenta. Avisa una vez cuando faltan 7 días o menos y una vez cuando venció
  -- (hasta 30 días después, y solo si no tiene ya otro plan vigente).
  perform private.expire_user_subscriptions(v_uid);
  if coalesce(v_prefs ->> 'suscripcion', 'true') <> 'false' then
    for r in
      select s.id, s.ends_at, pl.name
        from public.subscriptions s join public.subscription_plans pl on pl.id = s.plan_id
       where s.user_id = v_uid and s.status in ('active', 'expired') and s.ends_at is not null
         and s.ends_at > now() - interval '30 days' and s.ends_at <= now() + interval '7 days'
         and (s.ends_at > now() or not exists (
               select 1 from public.subscriptions x
                where x.user_id = v_uid and x.status = 'active' and x.starts_at <= now() and (x.ends_at is null or x.ends_at > now())))
       order by s.ends_at desc limit 1
    loop
      v_key := 'plan-' || r.id::text || '-' || to_char(r.ends_at at time zone 'America/Mexico_City', 'YYYYMMDD')
               || case when r.ends_at <= now() then '-vencido' else '-por-vencer' end;
      if r.ends_at <= now() then
        v_title := r.name || ' venció';
        v_body := 'Venció el ' || private.fecha_es(r.ends_at) || '. Puedes solicitar la renovación en Suscripciones; no genera ningún cargo.';
      else
        v_title := r.name || ' vence pronto';
        v_body := 'Vigente hasta el ' || private.fecha_es(r.ends_at) || '. Puedes solicitar la renovación en Suscripciones; no genera ningún cargo.';
      end if;
      insert into private.reminder_log (user_id, dedupe_key) values (v_uid, v_key) on conflict do nothing;
      get diagnostics v_rows = row_count;
      if v_rows = 1 then
        perform private.notify(v_uid, 'suscripcion', v_title, v_body, 'planes.html');
        v_n := v_n + 1;
      end if;
    end loop;
  end if;
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
                                  where status = 'active' and starts_at <= now() and (ends_at is null or ends_at > now())),
    'plan_requests_pending',    (select count(*) from public.plan_requests where status = 'pending'),
    'suspended_users',          (select count(*) from public.profiles where is_suspended),
    'conversations_open',       (select count(*) from public.conversations where status = 'abierta'));
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

-- Texto de una fecha para avisos: «4 dic 2026» (hora de México).
create or replace function private.fecha_es(p_ts timestamptz)
returns text language sql stable set search_path = ''
as $$
  select extract(day from p_ts at time zone 'America/Mexico_City')::int::text || ' '
      || (array['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'])[extract(month from p_ts at time zone 'America/Mexico_City')::int]
      || ' ' || extract(year from p_ts at time zone 'America/Mexico_City')::int::text;
$$;

-- Asigna un plan (reemplaza el vigente). La usan la función de administración y la resolución de solicitudes.
-- p_actor es quien lo hace (null si se ejecuta desde el SQL Editor).
create or replace function private.assign_subscription(
  p_user uuid, p_plan text, p_period text default 'monthly',
  p_starts timestamptz default null, p_ends timestamptz default null, p_note text default null, p_actor uuid default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_plan public.subscription_plans; v_old public.subscriptions; v_new_id uuid;
  v_start timestamptz := coalesce(p_starts, now()); v_end timestamptz;
begin
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
  values (p_user, p_plan, p_period, v_start, v_end, p_actor, left(p_note, 500))
  returning id into v_new_id;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, to_plan, actor_id, details)
  values (v_new_id, p_user, case when v_old.id is null then 'assigned' else 'changed' end,
          v_old.plan_id, p_plan, p_actor, jsonb_build_object('period', p_period, 'ends_at', v_end));
  perform private.audit('subscription_assign', 'subscriptions', v_new_id::text,
                        jsonb_build_object('user', p_user, 'plan', p_plan, 'period', p_period));
  perform private.notify(p_user, 'suscripcion', 'Tu suscripción cambió',
    'Ahora tienes ' || v_plan.name || case when v_end is not null then '. Vigente hasta el ' || private.fecha_es(v_end) else '' end || '.', 'planes.html');
  return v_new_id;
end;
$$;

create or replace function public.admin_assign_subscription(
  p_user uuid, p_plan text, p_period text default 'monthly',
  p_starts timestamptz default null, p_ends timestamptz default null, p_note text default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  return private.assign_subscription(p_user, p_plan, p_period, p_starts, p_ends, p_note, (select auth.uid()));
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

-- Renovación manual: extiende el vencimiento un periodo más (p_period null = el mismo periodo de la suscripción).
create or replace function private.renew_subscription(
  p_subscription uuid, p_note text default null, p_actor uuid default null, p_period text default null)
returns timestamptz language plpgsql volatile security definer set search_path = ''
as $$
declare v_sub public.subscriptions; v_new_end timestamptz; v_period text; v_name text;
begin
  select * into v_sub from public.subscriptions where id = p_subscription for update;
  if not found or v_sub.status not in ('active', 'expired') then
    raise exception 'Solo se pueden renovar suscripciones activas o vencidas.' using errcode = 'P0001';
  end if;
  v_period := coalesce(p_period, v_sub.billing_period);
  if v_period not in ('monthly', 'yearly') then
    raise exception 'Periodo no válido.' using errcode = '22023';
  end if;
  v_new_end := greatest(now(), coalesce(v_sub.ends_at, now()))
               + case v_period when 'yearly' then interval '1 year' else interval '1 month' end;
  update public.subscriptions set ends_at = v_new_end, status = 'active', billing_period = v_period, note = coalesce(left(p_note, 500), note)
   where id = p_subscription;
  insert into public.subscription_events (subscription_id, user_id, event, from_plan, to_plan, actor_id, details)
  values (p_subscription, v_sub.user_id, 'renewed', v_sub.plan_id, v_sub.plan_id, p_actor,
          jsonb_build_object('ends_at', v_new_end));
  perform private.audit('subscription_renew', 'subscriptions', p_subscription::text, jsonb_build_object('ends_at', v_new_end));
  select name into v_name from public.subscription_plans where id = v_sub.plan_id;
  perform private.notify(v_sub.user_id, 'suscripcion', 'Tu suscripción fue renovada',
    coalesce(v_name, 'Tu plan') || ': vigente hasta el ' || private.fecha_es(v_new_end) || '.', 'planes.html');
  return v_new_end;
end;
$$;

create or replace function public.admin_renew_subscription(p_subscription uuid, p_note text default null)
returns timestamptz language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  return private.renew_subscription(p_subscription, p_note, (select auth.uid()), null);
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

-- =====================================================================
-- SOLICITUDES DE PLAN (Etapa 9) · sin pagos
-- La persona pide un plan; un administrador la aprueba o la rechaza. Aprobar NO cobra nada:
-- asigna el plan manualmente (con vigencia de un mes o un año según el periodo pedido).
-- =====================================================================
create or replace function private.plan_request_code(p_id uuid)
returns text language sql immutable set search_path = ''
as $$ select upper(left(replace(p_id::text, '-', ''), 8)); $$;

create or replace function public.request_plan(p_plan text, p_period text default 'monthly', p_note text default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_uid uuid := (select auth.uid());
  v_prof public.profiles; v_plan public.subscription_plans; v_cur public.subscriptions;
  v_note text := nullif(btrim(coalesce(p_note, '')), '');
  v_id uuid; v_aud text;
begin
  if v_uid is null then raise exception 'Inicia sesión para solicitar un plan.' using errcode = '42501'; end if;
  select * into v_prof from public.profiles where id = v_uid;
  if not found then raise exception 'Inicia sesión para solicitar un plan.' using errcode = '42501'; end if;
  if v_prof.is_suspended then
    raise exception 'Tu cuenta está suspendida y no puede solicitar planes.' using errcode = 'P0001';
  end if;
  if p_period is null or p_period not in ('monthly', 'yearly') then
    raise exception 'Periodo no válido.' using errcode = '22023';
  end if;
  if v_note is not null and char_length(v_note) > 300 then
    raise exception 'El mensaje puede tener hasta 300 caracteres.' using errcode = '22023';
  end if;
  select * into v_plan from public.subscription_plans where id = p_plan and is_active;
  if not found then raise exception 'Ese plan no existe o no está disponible.' using errcode = 'P0002'; end if;
  v_aud := case when v_prof.account_type = 'business' then 'business' else 'owner' end;
  if v_plan.audience <> v_aud then
    raise exception 'Ese plan no corresponde a tu tipo de cuenta.' using errcode = 'P0001';
  end if;
  if v_plan.price_monthly_mxn = 0 then
    raise exception 'Huellita Básica es gratuita: no necesitas solicitarla. Si tienes una suscripción y quieres dejarla, cancélala desde Suscripciones.' using errcode = 'P0001';
  end if;
  select * into v_cur from public.subscriptions s
   where s.user_id = v_uid and s.status = 'active' and s.starts_at <= now() and (s.ends_at is null or s.ends_at > now())
   order by s.starts_at desc limit 1;
  if found and v_cur.plan_id = p_plan and (v_cur.ends_at is null or v_cur.ends_at > now() + interval '15 days') then
    raise exception 'Ya tienes ese plan vigente. Podrás pedir la renovación cuando falten 15 días o menos para que venza.' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.plan_requests r where r.user_id = v_uid and r.status = 'pending') then
    raise exception 'Ya tienes una solicitud pendiente. Espera la respuesta del equipo o cancélala para hacer otra.' using errcode = 'P0001';
  end if;
  perform private.rate_limit('plan_req_d', v_uid::text, 'day', 5);
  begin
    insert into public.plan_requests (user_id, plan_id, billing_period, user_note)
    values (v_uid, p_plan, p_period, v_note)
    returning id into v_id;
  exception when unique_violation then
    raise exception 'Ya tienes una solicitud pendiente. Espera la respuesta del equipo o cancélala para hacer otra.' using errcode = 'P0001';
  end;
  -- Conserva solo las 20 solicitudes más recientes de cada persona (cuida el espacio del plan gratuito).
  delete from public.plan_requests r
   where r.user_id = v_uid and r.status <> 'pending'
     and r.id in (select x.id from public.plan_requests x where x.user_id = v_uid order by x.created_at desc, x.id desc offset 20);
  perform private.notify(v_uid, 'suscripcion', 'Recibimos tu solicitud: ' || v_plan.name,
    'No genera ningún cargo ni pide datos de pago. El equipo la revisará y te avisaremos aquí.', 'planes.html', 'planreq-' || v_id::text);
  perform private.notify_admins('aviso', 'Nueva solicitud de plan',
    v_plan.name || ' · ' || case p_period when 'yearly' then 'anual' else 'mensual' end
      || ' · cuenta de ' || case when v_prof.account_type = 'business' then 'aliado' else 'dueño de mascota' end
      || ' · código ' || private.plan_request_code(v_id),
    'admin.html#subs', 'planreq-admin-' || v_id::text);
  return v_id;
end;
$$;

create or replace function public.cancel_plan_request(p_request uuid)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_uid uuid := (select auth.uid()); v_n integer;
begin
  if v_uid is null then raise exception 'No autorizado.' using errcode = '42501'; end if;
  update public.plan_requests r set status = 'cancelled', resolved_at = now()
   where r.id = p_request and r.user_id = v_uid and r.status = 'pending';
  get diagnostics v_n = row_count;
  if v_n = 0 then
    raise exception 'No encontramos una solicitud pendiente tuya con ese identificador.' using errcode = 'P0001';
  end if;
end;
$$;

-- Aprueba o rechaza una solicitud. Interna: se llama desde el SQL Editor (el equipo) o desde la función de administración.
-- Aprobar asigna el plan (o renueva, si pide el mismo plan que ya tiene); rechazar avisa a la persona con la nota del equipo.
create or replace function private.resolve_plan_request(
  p_request uuid, p_approve boolean, p_note text default null, p_actor uuid default null, p_ends timestamptz default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_req public.plan_requests; v_plan public.subscription_plans; v_cur public.subscriptions; v_sub uuid;
  v_note text := nullif(btrim(coalesce(p_note, '')), '');
begin
  if p_approve is null then raise exception 'Indica si se aprueba o se rechaza.' using errcode = '22023'; end if;
  select * into v_req from public.plan_requests where id = p_request for update;
  if not found then raise exception 'Solicitud no encontrada.' using errcode = 'P0002'; end if;
  if v_req.status <> 'pending' then raise exception 'Esa solicitud ya fue resuelta.' using errcode = 'P0001'; end if;
  select * into v_plan from public.subscription_plans where id = v_req.plan_id;
  if p_approve then
    select * into v_cur from public.subscriptions s
     where s.user_id = v_req.user_id and s.status = 'active' and s.starts_at <= now() and (s.ends_at is null or s.ends_at > now())
     order by s.starts_at desc limit 1;
    if found and v_cur.plan_id = v_req.plan_id and v_cur.ends_at is not null and p_ends is null then
      perform private.renew_subscription(v_cur.id, 'Solicitud ' || private.plan_request_code(p_request), p_actor, v_req.billing_period);
      v_sub := v_cur.id;
    else
      v_sub := private.assign_subscription(v_req.user_id, v_req.plan_id, v_req.billing_period, null, p_ends,
                 'Solicitud ' || private.plan_request_code(p_request) || coalesce(' · ' || left(v_note, 300), ''), p_actor);
    end if;
  else
    perform private.notify(v_req.user_id, 'suscripcion', 'Tu solicitud de ' || v_plan.name || ' no fue aprobada',
      coalesce(left(v_note, 300), 'Si tienes dudas, escríbenos desde Atención al cliente.'), 'planes.html', 'planreq-res-' || p_request::text);
  end if;
  update public.plan_requests
     set status = case when p_approve then 'approved' else 'rejected' end,
         admin_note = left(v_note, 500), resolved_by = p_actor, resolved_at = now()
   where id = p_request;
  perform private.audit(case when p_approve then 'plan_request_approve' else 'plan_request_reject' end,
                        'plan_requests', p_request::text,
                        jsonb_build_object('user', v_req.user_id, 'plan', v_req.plan_id, 'actor', p_actor));
  return v_sub;
end;
$$;

create or replace function public.admin_resolve_plan_request(
  p_request uuid, p_approve boolean, p_note text default null, p_ends timestamptz default null)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  return private.resolve_plan_request(p_request, p_approve, p_note, (select auth.uid()), p_ends);
end;
$$;

-- Marca como vencidas las suscripciones de UNA persona cuya fecha ya pasó. Se llama al generar sus recordatorios
-- (no hay tareas programadas): el plan ya deja de dar beneficios por la fecha, esto solo ordena el historial.
create or replace function private.expire_user_subscriptions(p_user uuid)
returns integer language plpgsql volatile security definer set search_path = ''
as $$
declare v_n integer;
begin
  with e as (
    update public.subscriptions s set status = 'expired'
     where s.user_id = p_user and s.status = 'active' and s.ends_at is not null and s.ends_at <= now()
    returning s.id, s.user_id, s.plan_id)
  insert into public.subscription_events (subscription_id, user_id, event, from_plan)
  select id, user_id, 'expired', plan_id from e;
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;

-- Marca como vencidas las suscripciones cuya fecha ya pasó, de todas las personas (para el SQL Editor; no se programa).
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

-- =====================================================================
-- PANEL DE ADMINISTRACIÓN (Etapa 10)
-- Todo lo que hace el panel pasa por estas funciones: cada una comprueba is_admin() DENTRO del servidor, valida con mensajes
-- en español y deja registro en la bitácora. El navegador no necesita permisos directos sobre las tablas para administrar.
-- Los roles de administrador NO se gestionan aquí: se asignan solo desde el SQL Editor (admin_roles).
-- =====================================================================
create or replace function private.like_pattern(p_q text)
returns text language sql immutable set search_path = ''
as $$
  select case when nullif(btrim(coalesce(p_q, '')), '') is null then null
              else '%' || replace(replace(replace(left(btrim(p_q), 80), '\', '\\'), '%', '\%'), '_', '\_') || '%' end;
$$;

-- Ficha de una cuenta para atención al cliente: solo datos de la cuenta y conteos (no el contenido de mascotas ni de chats).
create or replace function public.admin_get_user(p_user uuid)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare v jsonb;
begin
  perform private.require_admin();
  select jsonb_build_object(
      'id', p.id, 'email', u.email, 'display_name', p.display_name, 'account_type', p.account_type,
      'is_suspended', p.is_suspended, 'created_at', p.created_at,
      'last_sign_in_at', u.last_sign_in_at, 'email_confirmed', u.email_confirmed_at is not null,
      'is_admin', exists (select 1 from public.admin_roles r where r.user_id = p.id),
      'plan_id', private.effective_plan_id(p.id),
      'subscription', (select jsonb_build_object('id', s.id, 'plan_id', s.plan_id, 'billing_period', s.billing_period,
                                                  'starts_at', s.starts_at, 'ends_at', s.ends_at)
                         from public.subscriptions s where s.user_id = p.id and s.status = 'active'
                        order by s.starts_at desc limit 1),
      'pending_request', (select jsonb_build_object('id', r.id, 'plan_id', r.plan_id, 'billing_period', r.billing_period, 'created_at', r.created_at)
                            from public.plan_requests r where r.user_id = p.id and r.status = 'pending'),
      'pets', (select count(*) from public.pets x where x.owner_id = p.id),
      'businesses', (select count(*) from public.businesses b where b.owner_id = p.id),
      'open_conversations', (select count(*) from public.conversations c where c.user_id = p.id and c.status = 'abierta'))
    into v
    from public.profiles p join auth.users u on u.id = p.id
   where p.id = p_user;
  if v is null then raise exception 'Usuario no encontrado.' using errcode = 'P0002'; end if;
  return v;
end;
$$;

-- ---- Aliados ----
create or replace function public.admin_list_businesses(
  p_status text default null, p_search text default null, p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, name text, category text, state text, municipality text, status text, verified boolean, is_demo boolean,
               owner_id uuid, owner_email text, owner_name text, plan_id text, active_promotions bigint,
               created_at timestamptz, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_q text := private.like_pattern(p_search);
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_status is not null and p_status not in ('pending', 'approved', 'suspended', 'rejected') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  return query
    select b.id, b.name, b.category, b.state, b.municipality, b.status, b.verified, b.is_demo,
           b.owner_id, u.email::text, p.display_name,
           case when b.owner_id is null then null else private.effective_plan_id(b.owner_id) end,
           (select count(*) from public.business_promotions bp
             where bp.business_id = b.id and bp.is_active and bp.ends_on >= private.today_mx()),
           b.created_at, count(*) over ()
      from public.businesses b
      left join public.profiles p on p.id = b.owner_id
      left join auth.users u on u.id = b.owner_id
     where (p_status is null or b.status = p_status)
       and (v_q is null or b.name ilike v_q escape '\' or coalesce(b.municipality, '') ilike v_q escape '\' or coalesce(u.email, '') ilike v_q escape '\')
     order by (b.status = 'pending') desc, b.created_at desc, b.id
     limit v_limit offset v_off;
end;
$$;

create or replace function public.admin_get_business(p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare v jsonb;
begin
  perform private.require_admin();
  select jsonb_build_object(
      'id', b.id, 'name', b.name, 'category', b.category, 'description', b.description, 'address', b.address,
      'state', b.state, 'municipality', b.municipality, 'phone', b.phone, 'whatsapp_url', b.whatsapp_url,
      'maps_query', b.maps_query, 'hours', b.hours, 'has_logo', b.logo_path is not null, 'photos', cardinality(b.photo_paths),
      'status', b.status, 'verified', b.verified, 'verified_at', b.verified_at, 'is_demo', b.is_demo,
      'created_at', b.created_at, 'updated_at', b.updated_at,
      'owner', case when b.owner_id is null then null
                    else jsonb_build_object('id', b.owner_id, 'email', u.email, 'display_name', p.display_name, 'is_suspended', p.is_suspended) end,
      'plan', (select jsonb_build_object('id', pl.id, 'name', pl.name, 'verified_badge_eligible', pl.verified_badge_eligible)
                 from private.plan_for(b.owner_id) pl),
      'promotions', coalesce((select jsonb_agg(jsonb_build_object('id', x.id, 'title', x.title, 'description', x.description,
                                      'starts_on', x.starts_on, 'ends_on', x.ends_on, 'is_active', x.is_active) order by x.created_at desc)
                                from (select bp.* from public.business_promotions bp where bp.business_id = b.id
                                       order by bp.created_at desc limit 20) x), '[]'::jsonb))
    into v
    from public.businesses b
    left join public.profiles p on p.id = b.owner_id
    left join auth.users u on u.id = b.owner_id
   where b.id = p_id;
  if v is null then raise exception 'Establecimiento no encontrado.' using errcode = 'P0002'; end if;
  return v;
end;
$$;

-- Moderación: borra una promoción (el dueño la podría reactivar si solo se ocultara). Avisa al dueño con el motivo.
create or replace function public.admin_delete_promotion(p_promo uuid, p_reason text default null)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_biz uuid; v_title text; v_owner uuid;
begin
  perform private.require_admin();
  delete from public.business_promotions bp where bp.id = p_promo returning bp.business_id, bp.title into v_biz, v_title;
  if not found then raise exception 'Promoción no encontrada.' using errcode = 'P0002'; end if;
  select b.owner_id into v_owner from public.businesses b where b.id = v_biz;
  perform private.audit('promotion_delete', 'business_promotions', p_promo::text,
                        jsonb_build_object('business', v_biz, 'title', left(v_title, 100), 'reason', left(p_reason, 300)));
  if v_owner is not null then
    perform private.notify(v_owner, 'aviso', 'Se retiró una promoción', left(coalesce(nullif(btrim(p_reason), ''), 'No cumplía las reglas del directorio.'), 300), 'panel-aliado.html');
  end if;
end;
$$;

-- ---- Denuncias ----
create or replace function public.admin_list_complaints(p_status text default null, p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, tracking_code text, type text, status text, priority text, attended boolean, state text, municipality text,
               approx_date date, photos integer, excerpt text, created_at timestamptz, updated_at timestamptz, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_status is not null and p_status not in ('pendientes', 'recibida', 'en_revision', 'en_proceso', 'canalizada', 'cerrada') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  return query
    select c.id, c.tracking_code, c.type, c.status, c.priority, c.attended, c.state, c.municipality, c.approx_date,
           cardinality(c.photo_paths), left(c.description, 160), c.created_at, c.updated_at, count(*) over ()
      from public.complaints c
     where p_status is null
        or (p_status = 'pendientes' and c.status in ('recibida', 'en_revision'))
        or c.status = p_status
     order by c.created_at desc, c.id
     limit v_limit offset v_off;
end;
$$;

create or replace function public.admin_get_complaint(p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare v jsonb;
begin
  perform private.require_admin();
  select to_jsonb(c) into v from public.complaints c where c.id = p_id;
  if v is null then raise exception 'Denuncia no encontrada.' using errcode = 'P0002'; end if;
  return v;
end;
$$;

-- Estado, prioridad, seguimiento y notas. El contenido original NO se puede cambiar (lo impide además un disparador).
-- «public_update» lo ve cualquier persona que tenga el código de seguimiento; «internal_notes» solo el equipo.
create or replace function public.admin_update_complaint(
  p_id uuid, p_status text, p_priority text default null, p_attended boolean default false,
  p_public_update text default null, p_internal_notes text default null)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_pub text := nullif(btrim(coalesce(p_public_update, '')), ''); v_int text := nullif(btrim(coalesce(p_internal_notes, '')), '');
begin
  perform private.require_admin();
  if p_status is null or p_status not in ('recibida', 'en_revision', 'en_proceso', 'canalizada', 'cerrada') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  if p_priority is not null and p_priority not in ('baja', 'media', 'alta', 'urgente') then
    raise exception 'Prioridad no válida.' using errcode = '22023';
  end if;
  if char_length(coalesce(v_pub, '')) > 500 then
    raise exception 'La actualización pública admite hasta 500 caracteres.' using errcode = 'P0001';
  end if;
  if char_length(coalesce(v_int, '')) > 4000 then
    raise exception 'Las notas internas admiten hasta 4000 caracteres.' using errcode = 'P0001';
  end if;
  update public.complaints c
     set status = p_status, priority = p_priority, attended = coalesce(p_attended, false),
         public_update = v_pub, internal_notes = v_int
   where c.id = p_id;
  if not found then raise exception 'Denuncia no encontrada.' using errcode = 'P0002'; end if;
end;
$$;

-- ---- Guías de cuidado ----
create or replace function public.admin_list_guides(p_search text default null, p_state text default null, p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, slug text, title text, category text, is_published boolean, published_at timestamptz,
               author_source text, updated_at timestamptz, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_q text := private.like_pattern(p_search);
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_state is not null and p_state not in ('published', 'draft') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  return query
    select g.id, g.slug, g.title, g.category, g.is_published, g.published_at, g.author_source, g.updated_at, count(*) over ()
      from public.care_guides g
     where (p_state is null or (p_state = 'published') = g.is_published)
       and (v_q is null or g.title ilike v_q escape '\' or g.slug ilike v_q escape '\')
     order by g.updated_at desc, g.id
     limit v_limit offset v_off;
end;
$$;

create or replace function public.admin_get_guide(p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare v jsonb;
begin
  perform private.require_admin();
  select jsonb_build_object('id', g.id, 'slug', g.slug, 'title', g.title, 'summary', g.summary, 'content', g.content,
                            'category', g.category, 'author_source', g.author_source, 'is_published', g.is_published,
                            'published_at', g.published_at, 'updated_at', g.updated_at)
    into v from public.care_guides g where g.id = p_id;
  if v is null then raise exception 'Guía no encontrada.' using errcode = 'P0002'; end if;
  return v;
end;
$$;

-- Crea (p_id nulo) o edita una guía. Publicar es una decisión explícita: una guía nueva queda como borrador salvo que se pida publicarla.
create or replace function public.admin_save_guide(
  p_id uuid, p_slug text, p_title text, p_summary text, p_content text, p_category text,
  p_author_source text default '', p_publish boolean default false)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare
  v_slug text := lower(btrim(coalesce(p_slug, ''))); v_title text := btrim(coalesce(p_title, ''));
  v_summary text := btrim(coalesce(p_summary, '')); v_content text := btrim(coalesce(p_content, ''));
  v_source text := btrim(coalesce(p_author_source, '')); v_id uuid; v_was boolean;
begin
  perform private.require_admin();
  if v_slug !~ '^[a-z0-9]+(-[a-z0-9]+)*$' or char_length(v_slug) > 120 then
    raise exception 'La dirección de la guía solo admite minúsculas, números y guiones (hasta 120 caracteres).' using errcode = 'P0001';
  end if;
  if char_length(v_title) not between 3 and 160 then raise exception 'El título debe tener entre 3 y 160 caracteres.' using errcode = 'P0001'; end if;
  if char_length(v_summary) > 300 then raise exception 'El resumen admite hasta 300 caracteres.' using errcode = 'P0001'; end if;
  if char_length(v_content) not between 1 and 20000 then raise exception 'El contenido debe tener entre 1 y 20000 caracteres.' using errcode = 'P0001'; end if;
  if p_category is null or p_category not in ('perros', 'gatos', 'aves', 'conejos', 'pequenos-mamiferos', 'alimentacion', 'higiene',
                                              'vacunacion', 'salud-preventiva', 'comportamiento') then
    raise exception 'Categoría no válida.' using errcode = '22023';
  end if;
  if char_length(v_source) > 200 then raise exception 'La fuente admite hasta 200 caracteres.' using errcode = 'P0001'; end if;
  begin
    if p_id is null then
      insert into public.care_guides (slug, title, summary, content, category, author_source, is_published, published_at)
      values (v_slug, v_title, v_summary, v_content, p_category, v_source, coalesce(p_publish, false),
              case when p_publish then now() end)
      returning id into v_id;
    else
      select g.is_published into v_was from public.care_guides g where g.id = p_id for update;
      if not found then raise exception 'Guía no encontrada.' using errcode = 'P0002'; end if;
      update public.care_guides g
         set slug = v_slug, title = v_title, summary = v_summary, content = v_content, category = p_category, author_source = v_source,
             is_published = coalesce(p_publish, false),
             published_at = case when coalesce(p_publish, false) and not v_was then now() else g.published_at end
       where g.id = p_id;
      v_id := p_id;
    end if;
  exception when unique_violation then
    raise exception 'Ya existe otra guía con esa dirección.' using errcode = 'P0001';
  end;
  return v_id;
end;
$$;

create or replace function public.admin_delete_guide(p_id uuid)
returns void language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  delete from public.care_guides g where g.id = p_id;
  if not found then raise exception 'Guía no encontrada.' using errcode = 'P0002'; end if;
end;
$$;

-- Bitácora de cambios en guías (las haga el panel o el SQL Editor con sesión). No registra el contenido, solo quién, qué y cuál.
create or replace function private.guide_audit()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  if private.is_backend() then return coalesce(new, old); end if;      -- carga inicial / SQL Editor: sin sesión no hay a quién atribuirlo
  if tg_op = 'INSERT' then
    perform private.audit('guide_create', 'care_guides', new.id::text, jsonb_build_object('slug', new.slug, 'published', new.is_published));
  elsif tg_op = 'UPDATE' then
    perform private.audit(case when new.is_published and not old.is_published then 'guide_publish'
                               when old.is_published and not new.is_published then 'guide_unpublish'
                               else 'guide_update' end,
                          'care_guides', new.id::text, jsonb_build_object('slug', new.slug, 'published', new.is_published));
  else
    perform private.audit('guide_delete', 'care_guides', old.id::text, jsonb_build_object('slug', old.slug));
  end if;
  return coalesce(new, old);
end;
$$;
drop trigger if exists tp_audit on public.care_guides;
create trigger tp_audit after insert or update or delete on public.care_guides for each row execute function private.guide_audit();

-- ---- Suscripciones y solicitudes de plan ----
create or replace function public.admin_list_plan_requests(p_status text default 'pending', p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, code text, user_id uuid, email text, display_name text, account_type text, plan_id text, plan_name text,
               billing_period text, status text, user_note text, admin_note text, created_at timestamptz, resolved_at timestamptz,
               current_plan_id text, current_ends_at timestamptz, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_status is not null and p_status not in ('pending', 'approved', 'rejected', 'cancelled') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  return query
    select r.id, private.plan_request_code(r.id), r.user_id, u.email::text, p.display_name, p.account_type, r.plan_id, pl.name,
           r.billing_period, r.status, r.user_note, r.admin_note, r.created_at, r.resolved_at,
           private.effective_plan_id(r.user_id),
           (select s.ends_at from public.subscriptions s where s.user_id = r.user_id and s.status = 'active' order by s.starts_at desc limit 1),
           count(*) over ()
      from public.plan_requests r
      join public.profiles p on p.id = r.user_id
      join auth.users u on u.id = r.user_id
      join public.subscription_plans pl on pl.id = r.plan_id
     where p_status is null or r.status = p_status
     order by case when r.status = 'pending' then r.created_at end asc nulls last, coalesce(r.resolved_at, r.created_at) desc, r.id
     limit v_limit offset v_off;
end;
$$;

create or replace function public.admin_list_subscriptions(
  p_status text default 'active', p_search text default null, p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, user_id uuid, email text, display_name text, account_type text, plan_id text, plan_name text,
               billing_period text, status text, starts_at timestamptz, ends_at timestamptz, days_left integer, note text, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_q text := private.like_pattern(p_search);
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_status is not null and p_status not in ('active', 'expiring', 'expired', 'cancelled', 'replaced') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  return query
    select s.id, s.user_id, u.email::text, p.display_name, p.account_type, s.plan_id, pl.name, s.billing_period, s.status,
           s.starts_at, s.ends_at,
           case when s.ends_at is null then null else ceil(extract(epoch from (s.ends_at - now())) / 86400)::integer end,
           s.note, count(*) over ()
      from public.subscriptions s
      join public.profiles p on p.id = s.user_id
      join auth.users u on u.id = s.user_id
      join public.subscription_plans pl on pl.id = s.plan_id
     where (p_status is null
            or (p_status = 'expiring' and s.status = 'active' and s.ends_at is not null and s.ends_at <= now() + interval '15 days')
            or s.status = p_status)
       and (v_q is null or u.email ilike v_q escape '\' or p.display_name ilike v_q escape '\')
     order by case when p_status in ('active', 'expiring') then s.ends_at end asc nulls last, s.created_at desc, s.id
     limit v_limit offset v_off;
end;
$$;

-- ---- Atención al cliente (chat) ----
create or replace function public.admin_list_conversations(p_filter text default 'pending', p_limit integer default 25, p_offset integer default 0)
returns table (id uuid, subject text, status text, last_sender text, last_message_at timestamptz, created_at timestamptz,
               user_id uuid, display_name text, email text, message_count bigint, last_body text, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_limit integer := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if p_filter is null or p_filter not in ('pending', 'open', 'closed', 'all') then
    raise exception 'Filtro no válido.' using errcode = '22023';
  end if;
  return query
    select c.id, c.subject, c.status, c.last_sender, c.last_message_at, c.created_at, c.user_id, p.display_name, u.email::text,
           (select count(*) from public.messages m where m.conversation_id = c.id),
           (select left(m.body, 140) from public.messages m where m.conversation_id = c.id order by m.created_at desc, m.id desc limit 1),
           count(*) over ()
      from public.conversations c
      join public.profiles p on p.id = c.user_id
      join auth.users u on u.id = c.user_id
     where p_filter = 'all'
        or (p_filter = 'pending' and c.status = 'abierta' and c.last_sender = 'user')
        or (p_filter = 'open' and c.status = 'abierta')
        or (p_filter = 'closed' and c.status = 'cerrada')
     order by case when p_filter = 'pending' then c.last_message_at end asc nulls last, c.last_message_at desc, c.id
     limit v_limit offset v_off;
end;
$$;

create or replace function public.admin_get_conversation(p_id uuid)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare v jsonb; v_total bigint;
begin
  perform private.require_admin();
  select count(*) into v_total from public.messages m where m.conversation_id = p_id;
  select jsonb_build_object(
      'id', c.id, 'subject', c.subject, 'status', c.status, 'last_sender', c.last_sender,
      'last_message_at', c.last_message_at, 'created_at', c.created_at,
      'user', jsonb_build_object('id', p.id, 'display_name', p.display_name, 'email', u.email, 'is_suspended', p.is_suspended),
      'total_messages', v_total,
      'messages', coalesce((select jsonb_agg(jsonb_build_object('id', x.id, 'sender_role', x.sender_role, 'body', x.body, 'created_at', x.created_at)
                                             order by x.created_at, x.id)
                              from (select m.* from public.messages m where m.conversation_id = c.id
                                     order by m.created_at desc, m.id desc limit 200) x), '[]'::jsonb))
    into v
    from public.conversations c
    join public.profiles p on p.id = c.user_id
    join auth.users u on u.id = c.user_id
   where c.id = p_id;
  if v is null then raise exception 'Conversación no encontrada.' using errcode = 'P0002'; end if;
  return v;
end;
$$;

-- Responde como «equipo». Los disparadores fijan el remitente y el rol; responder reabre una conversación cerrada y avisa a la persona.
create or replace function public.admin_reply_conversation(p_conversation uuid, p_body text)
returns uuid language plpgsql volatile security definer set search_path = ''
as $$
declare v_body text := btrim(coalesce(p_body, '')); v_id uuid;
begin
  perform private.require_admin();
  if char_length(v_body) not between 1 and 2000 then
    raise exception 'El mensaje debe tener entre 1 y 2000 caracteres.' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.conversations c where c.id = p_conversation) then
    raise exception 'Conversación no encontrada.' using errcode = 'P0002';
  end if;
  insert into public.messages (conversation_id, body) values (p_conversation, v_body) returning id into v_id;
  return v_id;
end;
$$;

create or replace function public.admin_set_conversation_status(p_conversation uuid, p_status text)
returns void language plpgsql volatile security definer set search_path = ''
as $$
begin
  perform private.require_admin();
  if p_status is null or p_status not in ('abierta', 'cerrada') then
    raise exception 'Estado no válido.' using errcode = '22023';
  end if;
  update public.conversations c set status = p_status where c.id = p_conversation;
  if not found then raise exception 'Conversación no encontrada.' using errcode = 'P0002'; end if;
  perform private.audit('conversation_status', 'conversations', p_conversation::text, jsonb_build_object('status', p_status));
end;
$$;

-- ---- Bitácora ----
create or replace function public.admin_list_audit(p_prefix text default null, p_limit integer default 50, p_offset integer default 0)
returns table (id bigint, created_at timestamptz, action text, target_table text, target_id text, details jsonb,
               admin_id uuid, admin_name text, admin_email text, total_count bigint)
language plpgsql stable security definer set search_path = ''
as $$
#variable_conflict use_column
declare
  v_pre text := nullif(btrim(coalesce(p_prefix, '')), '');
  v_limit integer := least(greatest(coalesce(p_limit, 50), 1), 100);
  v_off integer := greatest(coalesce(p_offset, 0), 0);
begin
  perform private.require_admin();
  if v_pre is not null and v_pre !~ '^[a-z_]{1,30}$' then
    raise exception 'Filtro no válido.' using errcode = '22023';
  end if;
  return query
    select a.id, a.created_at, a.action, a.target_table, a.target_id, a.details, a.admin_id, p.display_name, u.email::text, count(*) over ()
      from public.admin_audit_log a
      left join public.profiles p on p.id = a.admin_id
      left join auth.users u on u.id = a.admin_id
     where v_pre is null or a.action like replace(v_pre, '_', '\_') || '%' escape '\'
     order by a.created_at desc, a.id desc
     limit v_limit offset v_off;
end;
$$;

-- =====================================================================
-- Etapa 11 · Eliminar la cuenta propia
-- =====================================================================
-- La persona borra SU cuenta. Borrar la fila de auth.users elimina en cascada (por las claves foráneas) el perfil, las mascotas y su
-- carnet, la placa QR, los avisos, las conversaciones y mensajes, las suscripciones y solicitudes, y los establecimientos con sus
-- promociones y estadísticas. NO se tocan las denuncias anónimas (no están ligadas a ninguna cuenta).
-- Los ARCHIVOS (fotos, logotipos) los borra antes el navegador con la API de Storage: borrar filas de storage.objects por SQL dejaría
-- los archivos huérfanos. Por eso esta función se niega si todavía quedan archivos en la carpeta de la persona.
-- Las cuentas de administración no se eliminan por aquí (otra persona administradora lo hace desde el SQL Editor).
create or replace function public.delete_my_account(p_confirm text)
returns void language plpgsql volatile security definer set search_path = ''
as $$
declare v_uid uuid := (select auth.uid());
begin
  if v_uid is null then raise exception 'Inicia sesión para continuar.' using errcode = '42501'; end if;
  if exists (select 1 from public.admin_roles r where r.user_id = v_uid) then
    raise exception 'Las cuentas de administración no se eliminan desde aquí. Pide a otra persona administradora que lo haga.' using errcode = 'P0001';
  end if;
  if btrim(coalesce(p_confirm, '')) is distinct from 'ELIMINAR MI CUENTA' then
    raise exception 'Para eliminar la cuenta escribe exactamente: ELIMINAR MI CUENTA' using errcode = 'P0001';
  end if;
  if exists (select 1 from storage.objects o where (storage.foldername(o.name))[1] = v_uid::text) then
    raise exception 'Primero hay que borrar tus archivos (fotos y logotipos). Vuelve a intentarlo desde Perfil.' using errcode = 'P0001';
  end if;
  delete from auth.users where id = v_uid;
end;
$$;
