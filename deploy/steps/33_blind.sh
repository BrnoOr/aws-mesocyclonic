#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer

for CORTE in dia 12utc; do
  echo "===================== TRAIN 2024 ($CORTE) ====================="
  uv run python scripts/model/train.py --until 2024 --modelo elegido --corte "$CORTE" 2>&1 | grep -v Warning | tail -3
  echo "===================== BLIND 2025 ($CORTE) ====================="
  uv run python scripts/model/score.py --start 2025-04-01 --end 2025-09-30 --evaluate --corte "$CORTE" 2>&1 | grep -v Warning | tail -6
done
echo "=== salidas ==="
ls data/outputs/
echo "BLIND_DONE"
