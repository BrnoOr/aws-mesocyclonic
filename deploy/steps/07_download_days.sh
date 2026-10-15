#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

# Días: 2019-05-31 (continuación del brote, 2 eventos) y 2019-02-15 (control de verano, sin eventos).
# Solo las variables que necesitan los índices, para bajar menos: pl u v t z ; sfc 10u 10v 2t 2d sp cape.
for DAY in 2019-05-31 2019-02-15; do
  echo "=== $DAY: download_era5 (pl+sfc reducidas) ==="
  uv run python scripts/pipeline/download_era5.py --start "$DAY" \
    --pl u v t z --sfc 10u 10v 2t 2d sp cape --processes 8 2>&1 | tail -8
  echo "=== $DAY: process_era5 ==="
  uv run python scripts/pipeline/process_era5.py --start "$DAY" 2>&1 | tail -5
  echo "--- limpiar pl/sfc crudos de $DAY para ahorrar disco (los indices ya estan) ---"
  D=$(echo "$DAY" | tr -d '-')
  rm -f "data/crops/south-central-austral/era5_pl/era5_pl_${D}.nc"
  df -h / | tail -1
done
echo "=== indices disponibles ==="
ls -la data/crops/south-central-austral/era5_indices/
echo "DOWNLOAD_DONE"
