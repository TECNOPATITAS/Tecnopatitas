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
