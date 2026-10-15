#!/usr/bin/env bash
# Descarga y procesa ERA5 (índices horarios) para una lista de días, limpiando los crudos de niveles
# de presión tras calcular los índices (el disco de la EC2 es de 40 GiB). Reutiliza el pipeline
# existente (download_era5.py + process_era5.py). Solo baja u v t z en presión y las seis variables
# de superficie necesarias para los índices.
#
# Uso: run_days.sh <archivo_de_dias.txt>
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

LISTA="${1:?uso: run_days.sh <archivo_de_dias.txt>}"
REGION="south-central-austral"
BASE="data/crops/${REGION}"
PL="data/.parts"

n=0
total=$(grep -c . "$LISTA" || echo 0)
while read -r DAY; do
  [ -z "$DAY" ] && continue
  n=$((n+1))
  D=$(echo "$DAY" | tr -d '-')
  if [ -f "${BASE}/era5_indices/era5_idx_${D}.nc" ]; then
    echo "[$n/$total] $DAY: índices ya existen, salto"
    continue
  fi
  echo "[$n/$total] $DAY: descargando..."
  uv run python scripts/pipeline/download_era5.py --start "$DAY" \
    --pl u v t z --sfc 10u 10v 2t 2d sp cape --processes 8 >/dev/null 2>&1 || { echo "  fallo descarga $DAY"; continue; }
  uv run python scripts/pipeline/process_era5.py --start "$DAY" >/dev/null 2>&1 || { echo "  fallo proceso $DAY"; continue; }
  # Limpieza: borra los crudos de presión (pesados); conserva era5_sfc (cape) y era5_indices.
  rm -f "${BASE}/era5_pl/era5_pl_${D}.nc" "${PL}/"*"${D}"* 2>/dev/null || true
done < "$LISTA"

echo "=== resumen ==="
echo "índices disponibles: $(ls ${BASE}/era5_indices/ 2>/dev/null | wc -l)"
df -h / | tail -1
echo "RUN_DAYS_DONE"
