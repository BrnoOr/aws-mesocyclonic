#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

# Lista combinada de días únicos (eventos + control + ciego 2025).
cat data/tables/dias_eventos.txt data/tables/dias_control.txt data/tables/dias_ciego2025.txt \
  | grep . | sort -u > data/tables/dias_todos.txt
echo "días únicos a procesar: $(wc -l < data/tables/dias_todos.txt)"

# Lanza run_days en background; registra progreso en un log. Idempotente: salta los que ya tienen índices.
nohup bash scripts/model/run_days.sh data/tables/dias_todos.txt > data/tables/run_days.log 2>&1 &
echo "PID: $!"
echo "lanzado en background; log en data/tables/run_days.log"
sleep 5
echo "=== primeras líneas del log ==="
head -5 data/tables/run_days.log 2>/dev/null || true
echo "LAUNCH_DONE"
