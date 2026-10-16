#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== procesos del pipeline vivos? ==="
pgrep -f "scripts/model" >/dev/null && echo "SI, aún corriendo" || echo "no corre"
echo "=== outputs actuales (timestamp) ==="
ls -la --time-style=+%H:%M data/outputs/*.csv data/outputs/*.md 2>/dev/null | awk '{print $6, $7}'
echo "=== features generadas? ==="
ls -la --time-style=+%H:%M data/tables/features_*.parquet 2>/dev/null | awk '{print $6, $7}'

echo "=== relanzar pipeline en background (idempotente, regenera todo) ==="
pkill -f "scripts/model" 2>/dev/null || true
sleep 2
cat > /tmp/rerun_bg.sh <<'EOF'
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer
for CORTE in dia 12utc; do
  echo "[$(date +%H:%M)] FEATURES $CORTE"
  uv run python scripts/model/features.py --corte "$CORTE" --start 2018-04-01 --end 2026-07-31 >> data/tables/rerun.log 2>&1
  echo "[$(date +%H:%M)] CV $CORTE"
  uv run python scripts/model/cv.py --corte "$CORTE" >> data/tables/rerun.log 2>&1
  echo "[$(date +%H:%M)] DECIDE $CORTE"
  uv run python scripts/model/decide.py --corte "$CORTE" >> data/tables/rerun.log 2>&1
  echo "[$(date +%H:%M)] TRAIN2024+BLIND $CORTE"
  uv run python scripts/model/train.py --until 2024 --modelo elegido --corte "$CORTE" >> data/tables/rerun.log 2>&1
  uv run python scripts/model/score.py --start 2025-04-01 --end 2025-09-30 --evaluate --corte "$CORTE" >> data/tables/rerun.log 2>&1
  echo "[$(date +%H:%M)] TRAIN2025+CAND2026 $CORTE"
  uv run python scripts/model/train.py --until 2025 --modelo elegido --corte "$CORTE" >> data/tables/rerun.log 2>&1
  uv run python scripts/model/score.py --start 2026-04-01 --end 2026-07-31 --corte "$CORTE" >> data/tables/rerun.log 2>&1
done
uv run python scripts/model/resumen_pitch.py >> data/tables/rerun.log 2>&1
echo "[$(date +%H:%M)] RERUN_BG_DONE" >> data/tables/rerun.log
EOF
: > data/tables/rerun.log
nohup bash /tmp/rerun_bg.sh > /dev/null 2>&1 &
echo "PID: $!"
echo "lanzado en background; log en data/tables/rerun.log"
echo "LAUNCH_RERUN_DONE"
