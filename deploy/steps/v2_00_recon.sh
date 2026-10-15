#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
APP=/opt/mesocyclonic-viewer
cd "$APP"

echo "=== disco ==="
df -h / | tail -1
echo "=== git estado ==="
git rev-parse --short HEAD 2>/dev/null || echo "sin git"
git branch --show-current 2>/dev/null || echo "sin rama"
git remote -v 2>/dev/null | head -2 || echo "sin remoto"
git status --short 2>/dev/null | head -10 || true
echo "=== ramas ==="
git branch -a 2>/dev/null | head -10 || true
echo "=== era5_indices disponibles ==="
echo "total: $(ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | wc -l)"
echo "primeros/últimos:"
ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | sort | head -3
ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | sort | tail -3
echo "=== variables en un era5_sfc ==="
SFC=$(ls data/crops/south-central-austral/era5_sfc/*.nc 2>/dev/null | head -1)
echo "archivo: $SFC"
uv run python - "$SFC" <<'PY'
import sys, xarray as xr
f = sys.argv[1]
if f:
    ds = xr.open_dataset(f)
    print("sfc vars:", list(ds.data_vars))
    ds.close()
PY
echo "=== variables en un era5_indices ==="
IDX=$(ls data/crops/south-central-austral/era5_indices/*.nc 2>/dev/null | head -1)
uv run python - "$IDX" <<'PY'
import sys, xarray as xr
f = sys.argv[1]
if f:
    ds = xr.open_dataset(f)
    print("idx vars:", list(ds.data_vars))
    ds.close()
PY
echo "=== salidas v1 presentes ==="
ls data/outputs/ 2>/dev/null
echo "RECON_DONE"
