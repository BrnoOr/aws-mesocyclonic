#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
pgrep -f run_days_par.sh >/dev/null && echo "descarga 2026: EN CURSO" || echo "descarga 2026: TERMINADA"
echo "índices 2026: $(ls data/crops/south-central-austral/era5_indices/era5_idx_2026*.nc 2>/dev/null | wc -l) de 122"
tail -4 data/tables/run_2026.log 2>/dev/null || true
df -h / | tail -1
echo "MON2026_DONE"
