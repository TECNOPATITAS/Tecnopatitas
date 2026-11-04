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
  -e 's/{P1}/11111111-0000-4000-8000-0000000000a1/g' \
  -e 's/{P2}/11111111-0000-4000-8000-0000000000a2/g' \
  -e 's/{P3}/11111111-0000-4000-8000-0000000000a3/g' \
  -e 's/{BIZ1}/22222222-0000-4000-8000-0000000000b1/g' \
  -e 's/{BIZ2}/22222222-0000-4000-8000-0000000000b2/g' \
  -e 's/{CONV}/33333333-0000-4000-8000-0000000000c1/g' \
  pruebas/pruebas_seguridad.sql | $PSQL_BASE -v ON_ERROR_STOP=1 -d "$DB" -P pager=off
