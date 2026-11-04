#!/usr/bin/env bash
# Une los scripts 01..05 en un solo archivo (00_instalar_todo.sql) para pegarlo de una vez en Supabase.
# El archivo 06 (datos de demostración) es opcional y va aparte.
set -euo pipefail
cd "$(dirname "$0")"
{
  echo "-- TECNOPATITAS · Etapa 2 · INSTALADOR COMPLETO (generado: no lo edites; edita 01..05 y vuelve a generarlo)"
  for f in 01_esquema.sql 02_funciones.sql 03_seguridad_rls.sql 04_storage.sql 05_datos_base.sql; do
    echo; echo "-- >>>>>>>>>> $f"; cat "$f"
  done
  echo; echo "-- Mensaje final: el editor de Supabase muestra el resultado de la ÚLTIMA instrucción."
  echo "select 'Instalación terminada sin errores. Siguiente paso: ejecutar verificar_seguridad.sql' as resultado;"
} > 00_instalar_todo.sql
echo "Generado 00_instalar_todo.sql ($(wc -l < 00_instalar_todo.sql) líneas)"
