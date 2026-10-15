#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "=== proceso vivo? ==="
pgrep -f run_days_par.sh >/dev/null && echo "SI, corriendo (paralelo)" || echo "NO (terminó o murió)"
echo "=== procesos download_era5 activos ==="
pgrep -fc download_era5 || echo 0
echo "=== índices generados / total ==="
echo "$(ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | wc -l) de 259"
echo "=== últimas líneas del log paralelo ==="
tail -6 data/tables/run_par.log 2>/dev/null || true
echo "=== disco ==="
df -h / | tail -1
echo "MON_DONE"
