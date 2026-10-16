#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer

echo "=== uv sync ==="
uv sync 2>&1 | tail -2

echo "=== índices disponibles ==="
echo "era5_indices: $(ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | wc -l) días"

for CORTE in dia 12utc; do
  echo "===== FEATURES $CORTE ====="
  uv run python scripts/model/features.py --corte "$CORTE" --start 2018-04-01 --end 2026-07-31 2>&1 | tail -1
  echo "===== CV $CORTE ====="
  uv run python scripts/model/cv.py --corte "$CORTE" 2>&1 | grep -v Warning | tail -1
  echo "===== DECIDE $CORTE ====="
  uv run python scripts/model/decide.py --corte "$CORTE" 2>&1 | tail -2
  echo "===== TRAIN 2024 + BLIND 2025 $CORTE ====="
  uv run python scripts/model/train.py --until 2024 --modelo elegido --corte "$CORTE" 2>&1 | grep -v Warning | tail -1
  uv run python scripts/model/score.py --start 2025-04-01 --end 2025-09-30 --evaluate --corte "$CORTE" 2>&1 | grep -v Warning | tail -1
  echo "===== TRAIN 2025 + CANDIDATOS 2026 $CORTE ====="
  uv run python scripts/model/train.py --until 2025 --modelo elegido --corte "$CORTE" 2>&1 | grep -v Warning | tail -1
  uv run python scripts/model/score.py --start 2026-04-01 --end 2026-07-31 --corte "$CORTE" 2>&1 | grep -v Warning | tail -1
done

echo "===== RESUMEN PITCH ====="
uv run python scripts/model/resumen_pitch.py 2>&1 | tail -1
echo "=== salidas ==="
ls data/outputs/*.csv data/outputs/*.md 2>/dev/null | xargs -n1 basename
echo "RERUN_DONE"
