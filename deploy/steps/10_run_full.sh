#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== build_dataset (3 días: feb control + brote mayo) ==="
uv run python scripts/model/build_dataset.py --start 2019-05-30 --end 2019-05-31 --force 2>&1 | tail -8
echo "--- añadir el control de verano al dataset (día suelto) ---"
# build_dataset de un rango no incluye 2019-02-15; se arma por separado y se concatena.
uv run python - <<'PY'
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, "scripts/model")
import pandas as pd, build_dataset as bd, common, xarray as xr
cat = bd.load_catalog(common.DATA.child("tornados_chile.xlsx"))
base = common.CROPS.child("south-central-austral")
frames = [pd.read_parquet("data/model/dataset.parquet")]
day = "20190215"
with base.child("era5_indices", f"era5_idx_{day}.nc").open_dataset() as idx:
    sfc = base.child("era5_sfc", f"era5_sfc_{day}.nc").open_dataset()
    t = bd.day_table(idx, sfc); sfc.close()
t = bd.label_positives(t, cat, 0.5, 1.0)
frames.append(t)
out = pd.concat(frames, ignore_index=True)
out.to_parquet("data/model/dataset.parquet", index=False)
print(f"dataset final: {len(out)} filas, {int(out['label'].sum())} positivas, {out['event_id'].nunique()-1} eventos")
PY

echo "=== train ==="
uv run python scripts/model/train.py --splits 3 2>&1 | tail -45

echo "=== score (proyecciones de los 3 días; los días sin índices se saltan) ==="
uv run python scripts/model/score.py --start 2019-02-15 --end 2019-05-31 --top 30 2>&1 | tail -12

echo "=== artefactos ==="
ls -la data/model/
find data/crops -name 'score_*.nc'
echo "ALL_DONE"
