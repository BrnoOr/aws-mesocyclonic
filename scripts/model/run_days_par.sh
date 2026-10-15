#!/usr/bin/env bash
# Igual que run_days.sh pero procesa varios días en paralelo (JOBS). Cada día usa su propio
# download_era5 (que ya paraleliza internamente); se limita el nº de días simultáneos para no
# agotar RAM/disco. Idempotente: salta los días con índices ya calculados.
#
# Uso: run_days_par.sh <archivo_de_dias.txt> [JOBS]
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

LISTA="${1:?uso: run_days_par.sh <archivo> [jobs]}"
JOBS="${2:-4}"
REGION="south-central-austral"
BASE="data/crops/${REGION}"

procesar_dia() {
  DAY="$1"
  D=$(echo "$DAY" | tr -d '-')
  BASE="data/crops/south-central-austral"
  [ -f "${BASE}/era5_indices/era5_idx_${D}.nc" ] && { echo "$DAY: ya"; return 0; }
  uv run python scripts/pipeline/download_era5.py --start "$DAY" \
    --pl u v t z --sfc 10u 10v 2t 2d sp cape --processes 6 >/dev/null 2>&1 || { echo "$DAY: fallo dl"; return 0; }
  uv run python scripts/pipeline/process_era5.py --start "$DAY" >/dev/null 2>&1 || { echo "$DAY: fallo proc"; return 0; }
  rm -f "${BASE}/era5_pl/era5_pl_${D}.nc" "data/.parts/"*"${D}"* 2>/dev/null || true
  echo "$DAY: ok"
}
export -f procesar_dia

grep . "$LISTA" | xargs -P "$JOBS" -I {} bash -c 'procesar_dia "$@"' _ {}

echo "=== resumen ==="
echo "índices: $(ls ${BASE}/era5_indices/ 2>/dev/null | wc -l)"
df -h / | tail -1
echo "RUN_PAR_DONE"
