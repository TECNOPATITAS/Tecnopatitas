#!/usr/bin/env bash
# =====================================================================
# TECNOPATITAS · Etapa 2 · Ejecuta la batería de pruebas en un PostgreSQL LOCAL
# (NO se usa en Supabase real; allí usa verificar_seguridad.sql).
#
# Uso:   bash pruebas/ejecutar_pruebas.sh
# Requiere un PostgreSQL 15+ accesible. Conexión por variables estándar:
#   PGHOST PGPORT PGUSER PGPASSWORD    (o define PSQL="comando psql completo")
# Crea (y borra si existe) una base llamada "tp_test".
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PSQL_BASE="${PSQL:-psql -X -q}"
DB="${TP_DB:-tp_test}"
ERR_LOG="$(mktemp)"
trap 'rm -f "$ERR_LOG"' EXIT

run()    { $PSQL_BASE -v ON_ERROR_STOP=1 -d "$DB" "$@"; }
admin()  { $PSQL_BASE -v ON_ERROR_STOP=1 -d postgres "$@"; }

echo ">> Preparando base de datos limpia '$DB'..."
admin -c "drop database if exists $DB" -c "create database $DB"

echo ">> Simulador de Supabase + instalador..."
bash construir_instalador.sh >/dev/null
export PGOPTIONS="-c client_min_messages=warning"
run -o /dev/null < pruebas/shim_supabase.sql
run -o /dev/null < 00_instalar_todo.sql
run -o /dev/null < 06_datos_demo.sql
# Opcional (prueba de las pruebas): TP_EXTRA_SQL=archivo.sql aplica un "sabotaje" antes de probar.
if [ -n "${TP_EXTRA_SQL:-}" ]; then run -o /dev/null < "$TP_EXTRA_SQL"; fi

echo ">> Ejecutando pruebas..."
sed \
  -e 's/{A}/aaaaaaaa-0000-4000-8000-000000000001/g' \
  -e 's/{B}/bbbbbbbb-0000-4000-8000-000000000002/g' \
  -e 's/{C}/cccccccc-0000-4000-8000-000000000003/g' \
  -e 's/{D}/dddddddd-0000-4000-8000-000000000004/g' \
  -e 's/{E}/eeeeeeee-0000-4000-8000-000000000005/g' \
  -e 's/{F}/ffffffff-0000-4000-8000-000000000006/g' \
  -e 's/{G}/77777777-0000-4000-8000-000000000007/g' \
  -e 's/{H}/88888888-0000-4000-8000-000000000008/g' \
  -e 's/{I}/99999999-0000-4000-8000-000000000009/g' \
  -e 's/{P1}/11111111-0000-4000-8000-0000000000a1/g' \
  -e 's/{P2}/11111111-0000-4000-8000-0000000000a2/g' \
  -e 's/{P3}/11111111-0000-4000-8000-0000000000a3/g' \
  -e 's/{P4}/11111111-0000-4000-8000-0000000000a4/g' \
  -e 's/{P5}/11111111-0000-4000-8000-0000000000a5/g' \
  -e 's/{P6}/11111111-0000-4000-8000-0000000000a6/g' \
  -e 's/{BIZ1}/22222222-0000-4000-8000-0000000000b1/g' \
  -e 's/{BIZ2}/22222222-0000-4000-8000-0000000000b2/g' \
  -e 's/{CONV}/33333333-0000-4000-8000-0000000000c1/g' \
  pruebas/pruebas_seguridad.sql | $PSQL_BASE -v ON_ERROR_STOP=1 -d "$DB" -P pager=off 2> "$ERR_LOG" || RC=$?
cat "$ERR_LOG" >&2
# El archivo de pruebas corre con ON_ERROR_STOP apagado (así una prueba fallida no detiene a las demás). Por eso un ERROR de PREPARACIÓN
# (una inserción mal escrita, una columna que no existe...) podría dejar pruebas vacías sin que nadie lo note: cualquier ERROR aquí es una falla.
# («HAY PRUEBAS FALLIDAS» es el aviso normal del final cuando alguna prueba falla; no es un error de preparación.)
if grep '^ERROR:' "$ERR_LOG" | grep -qv 'HAY PRUEBAS FALLIDAS'; then echo "FALLA: hubo errores de SQL en la preparación de las pruebas (arriba). Las pruebas que dependen de esos datos no valen."; exit 1; fi
[ "${RC:-0}" -eq 0 ] || exit "$RC"

# ---- Etapa 11: 07_limpiar_demo.sql borra SOLO la demostración (y la línea opcional despublica las guías pendientes de revisión) ----
echo ">> Probando 07_limpiar_demo.sql..."
run -o /dev/null <<'SQL'
insert into auth.users (id, email) values ('99999999-9999-4999-8999-999999999999', 'aliado-real@prueba.mx') on conflict do nothing;
insert into public.businesses (owner_id, name, category, status, is_demo) values ('99999999-9999-4999-8999-999999999999', 'Veterinaria Real de Prueba', 'veterinaria', 'approved', false);
insert into public.care_guides (slug, title, summary, category, author_source, is_published, content)
  values ('guia-revisada-x', 'Guía revisada', 'r', 'perros', 'Revisada por la MVZ Fulana', true, 'Contenido.');
SQL
before=$(run -t -A -c "select (select count(*) from public.businesses where is_demo) || '/' || (select count(*) from public.businesses where not is_demo) || '/' || (select count(*) from public.care_guides)")
run -o /dev/null < 07_limpiar_demo.sql
run -o /dev/null < 07_limpiar_demo.sql
after=$(run -t -A -c "select (select count(*) from public.businesses where is_demo) || '/' || (select count(*) from public.businesses where not is_demo) || '/' || (select count(*) from public.care_guides)")
echo "   antes (demo/reales/guías) = $before · después = $after"
[ "${before%%/*}" = "6" ] || { echo "FALLA: la demostración no estaba completa antes de limpiar ($before)"; exit 1; }
[ "${after%%/*}" = "0" ] || { echo "FALLA: la limpieza no dejó 0 establecimientos de demostración ($after)"; exit 1; }
[ "${before#*/}" = "${after#*/}" ] || { echo "FALLA: la limpieza tocó establecimientos reales o guías ($before → $after)"; exit 1; }
run -t -A -c "select 1/count(*) from public.businesses where name = 'Veterinaria Real de Prueba'" >/dev/null || { echo "FALLA: se borró el aliado real"; exit 1; }
sed -n 's/^-- update public/update public/p' 07_limpiar_demo.sql | run -o /dev/null
unrev=$(run -t -A -c "select count(*) from public.care_guides where is_published and author_source ilike '%pendiente de revisión veterinaria%'")
rev=$(run -t -A -c "select count(*) from public.care_guides where is_published and slug = 'guia-revisada-x'")
echo "   tras la línea opcional: pendientes publicadas = $unrev · revisada publicada = $rev"
[ "$unrev" = "0" ] && [ "$rev" = "1" ] || { echo "FALLA: la línea opcional no despublicó solo las pendientes de revisión"; exit 1; }
echo ">> 07_limpiar_demo.sql OK"
