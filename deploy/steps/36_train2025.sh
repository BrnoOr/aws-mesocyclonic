#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer

echo "=== descarga 2026 en curso? ==="
pgrep -f run_days_par.sh >/dev/null && echo "SI" || echo "NO"
echo "índices 2026: $(ls data/crops/south-central-austral/era5_indices/era5_idx_2026*.nc 2>/dev/null | wc -l) de 122"

for CORTE in dia 12utc; do
  echo "=== TRAIN 2025 ($CORTE) ==="
  uv run python scripts/model/train.py --until 2025 --modelo elegido --corte "$CORTE" 2>&1 | grep -v Warning | tail -2
done
echo "TRAIN2025_DONE"
