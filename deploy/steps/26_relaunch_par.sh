#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== matar run secuencial ==="
pkill -f run_days.sh 2>/dev/null || true
pkill -f download_era5 2>/dev/null || true
sleep 3

# Escribe run_days_par.sh (se transfiere aparte); aquí solo se lanza.
chmod +x scripts/model/run_days_par.sh
echo "=== lanzar run paralelo (6 días simultáneos) ==="
nohup bash scripts/model/run_days_par.sh data/tables/dias_todos.txt 6 > data/tables/run_par.log 2>&1 &
echo "PID: $!"
sleep 8
echo "=== índices actuales ==="
ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | wc -l
tail -5 data/tables/run_par.log 2>/dev/null || true
echo "RELAUNCH_DONE"
