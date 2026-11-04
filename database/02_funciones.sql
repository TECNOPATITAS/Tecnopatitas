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
declare v_prefs jsonb;
begin
  select notification_prefs into v_prefs from public.profiles where id = p_user;
  if not found then return; end if;
  if coalesce(v_prefs ->> p_type, 'true') = 'false' then return; end if;
  insert into public.notifications (user_id, type, title, body, link, dedupe_key)
  values (p_user, p_type, left(p_title, 120), left(p_body, 500), p_link, p_dedupe)
  on conflict (user_id, dedupe_key) where dedupe_key is not null do nothing;
end;
$$;

-- Huella anónima del visitante: hash(IP + sal secreta + día). No se guarda
-- la IP y la huella cambia cada día, así que no sirve para rastrear personas.
create or replace function private.client_key()
returns text language plpgsql stable security definer set search_path = ''
as $$
declare v_headers jsonb; v_ip text; v_salt text;
begin
  begin
    v_headers := nullif(current_setting('request.headers', true), '')::jsonb;
  exception when others then
    v_headers := null;
  end;
  v_ip := nullif(btrim(coalesce(v_headers ->> 'cf-connecting-ip',
                                split_part(coalesce(v_headers ->> 'x-forwarded-for', ''), ',', 1), '')), '');
  select value into v_salt from private.settings where key = 'ip_salt';
  return encode(sha256(convert_to(coalesce(v_ip, 'sin-ip') || ':' || coalesce(v_salt, '') || ':' || current_date::text, 'UTF8')), 'hex');
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
  select * into v_plan from private.plan_for(v_owner);
  if not found or not v_plan.qr_enabled then
    raise exception 'Tu plan no incluye la placa QR. Está disponible en Huellita VIP.' using errcode = 'P0001';
  end if;
  return new;
end;
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
  end if;
  return new;
end;
$$;

create or replace function private.after_message()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare v_owner uuid;
begin
  update public.conversations c
     set last_message_at = new.created_at,
         last_sender = new.sender_role,
         status = case when new.sender_role = 'staff' then 'abierta' else c.status end
   where c.id = new.conversation_id
  returning c.user_id into v_owner;
  if new.sender_role = 'staff' then
    perform private.notify(v_owner, 'mensaje', 'Nueva respuesta de atención al cliente', left(new.body, 140), 'chat.html');
  end if;
  return new;
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
create trigger tp_guard before insert on public.pet_qr_profiles for each row execute function private.guard_qr();

drop trigger if exists tp_guard on public.subscriptions;
create trigger tp_guard before insert or update of plan_id, user_id on public.subscriptions for each row execute function private.guard_subscription();

drop trigger if exists tp_guard on public.conversations;
create trigger tp_guard before insert on public.conversations for each row execute function private.before_conversation();

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
drop trigger if exists tp_audit on public.complaints;
create trigger tp_audit after update on public.complaints for each row execute function private.complaint_audit();

-- =====================================================================
-- FUNCIONES PÚBLICAS (RPC): lo que el navegador puede llamar
-- =====================================================================

-- ---- Denuncias anónimas ---------------------------------------------
-- p_website es un campo trampa ("honeypot"): los humanos no lo ven; si
-- viene lleno es un robot y se descarta sin avisarle.
create or replace function public.submit_complaint(
  p_type text, p_description text, p_approx_date date, p_state text, p_municipality text,
  p_location_reference text default null, p_extra_info text default null,
  p_photo_paths text[] default '{}', p_website text default null)
returns text language plpgsql volatile security definer set search_path = ''
as $$
declare v_key text; v_code text; v_try integer := 0; v_path text;
begin
  if coalesce(btrim(p_website), '') <> '' then
    return private.new_tracking_code();                    -- robot: respuesta falsa, nada se guarda
  end if;
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
  if coalesce(char_length(btrim(p_state)), 0) < 2 or coalesce(char_length(btrim(p_municipality)), 0) < 2 then
    raise exception 'Indica el estado y el municipio.' using errcode = '22023';
  end if;
  if coalesce(cardinality(p_photo_paths), 0) > 3 then
    raise exception 'Máximo 3 fotografías.' using errcode = '22023';
  end if;
  foreach v_path in array coalesce(p_photo_paths, '{}') loop
    if v_path is null or v_path !~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,198}$' or v_path like '%..%' then
      raise exception 'Ruta de fotografía no válida.' using errcode = '22023';
    end if;
  end loop;

  v_key := private.client_key();
  perform private.rate_limit('complaint_h', v_key, 'hour', 5);
  perform private.rate_limit('complaint_d', v_key, 'day', 15);
  perform private.rate_limit('complaint_g', 'all', 'day', 300);   -- tope global: protege la cuota de la base gratuita

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
    'photo_path',    case when q.show_photo then p.photo_path end,
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
           b.verified, b.is_demo,
           coalesce(pl.priority_listing, false),
           coalesce(pl.audience = 'business', false),
           coalesce(pl.audience = 'business', false) and exists (
             select 1 from public.business_promotions bp
             where bp.business_id = b.id and bp.is_active
               and private.today_mx() between bp.starts_on and bp.ends_on),
           count(*) over ()
    from public.businesses b
    left join lateral (select x.audience, x.whatsapp_button, x.priority_listing from public.subscription_plans x
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
    'verified', b.verified, 'is_demo', b.is_demo,
    'promotions', case when not coalesce(pl.audience = 'business', false) then '[]'::jsonb else coalesce((
      select jsonb_agg(jsonb_build_object('id', bp.id, 'title', bp.title, 'description', bp.description,
                                          'starts_on', bp.starts_on, 'ends_on', bp.ends_on) order by bp.ends_on)
      from public.business_promotions bp
      where bp.business_id = b.id and bp.is_active and private.today_mx() between bp.starts_on and bp.ends_on
    ), '[]'::jsonb) end)
  from public.businesses b
  left join lateral (select x.audience, x.whatsapp_button from public.subscription_plans x
                     where x.id = private.effective_plan_id(b.owner_id)) pl on true
  where b.id = p_id and b.status = 'approved';
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
