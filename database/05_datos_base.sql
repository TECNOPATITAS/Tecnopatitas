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
