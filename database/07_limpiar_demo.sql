-- =====================================================================
-- TECNOPATITAS · Etapa 11 · 07 · LIMPIEZA DE LOS DATOS DE DEMOSTRACIÓN
--
-- Ejecútalo UNA vez, desde el SQL Editor de Supabase, cuando vayas a abrir el sitio al público.
-- Se puede ejecutar más de una vez sin problema.
--
-- Qué hace:
--   1) Borra los seis establecimientos FICTICIOS de 06_datos_demo.sql (los marcados is_demo = true).
--      También se van, en cascada, sus promociones y sus contadores. NO toca a ningún aliado real
--      (los aliados reales tienen dueño y is_demo = false).
--   2) Te muestra qué guías de cuidado siguen pendientes de revisión veterinaria (solo las lista).
--
-- Qué NO hace (a propósito):
--   · No borra cuentas de personas, mascotas, denuncias, mensajes ni planes: eso es información real
--     o de tus pruebas, y borrarla en bloque sería irreversible. Las cuentas de prueba se pueden
--     borrar una por una en Authentication → Users (se llevan consigo sus datos).
--   · No despublica las guías. Mira la línea OPCIONAL del final.
-- =====================================================================

delete from public.businesses where is_demo;

-- Comprobación (los dos números de arriba deben decir 0 en «demostración»)
select 'Establecimientos de demostración que quedan' as comprobacion, count(*) as cantidad
  from public.businesses where is_demo
union all
select 'Establecimientos reales (aprobados o en revisión)', count(*)
  from public.businesses where not is_demo
union all
select 'Guías PUBLICADAS que aún dicen «pendiente de revisión veterinaria»', count(*)
  from public.care_guides where is_published and author_source ilike '%pendiente de revisión veterinaria%';

-- OPCIONAL · Si no quieres mostrar al público guías que nadie con formación veterinaria ha revisado,
-- quita los dos guiones de la línea siguiente y ejecútala. Las guías NO se borran: pasan a borrador
-- y las vuelves a publicar desde Administración → Guías cuando estén revisadas.
-- update public.care_guides set is_published = false where author_source ilike '%pendiente de revisión veterinaria%';
