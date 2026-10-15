#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== metrics.json ==="
cat data/model/metrics.json
echo ""
echo "=== score medio por día (coherencia: mayo alto, feb control bajo) ==="
uv run python - <<'PY'
import xarray as xr, glob, os
for f in sorted(glob.glob("data/crops/south-central-austral/model_score/score_*.nc")):
    ds = xr.open_dataset(f)
    s = ds["score"]
    print(f"{os.path.basename(f)}: medio={float(s.mean()):.4f}  máx={float(s.max()):.4f}  "
          f"celdas>0.5={int((s>0.5).sum())}")
    ds.close()
PY
echo "=== top 10 candidatos ==="
head -11 data/model/candidates.csv
echo "=== importancia de variables (permutación rápida) ==="
uv run python - <<'PY'
import pickle, pandas as pd, numpy as np
p = pickle.loads(open("data/model/model.pkl","rb").read())
model, feats = p["model"], p["features"]
df = pd.read_parquet("data/model/dataset.parquet").dropna(subset=feats)
# importancia por permutación sobre una muestra
from sklearn.inspection import permutation_importance
samp = df.sample(min(20000, len(df)), random_state=0)
r = permutation_importance(model, samp[feats].to_numpy("f4"), samp["label"].to_numpy(int),
                           n_repeats=3, random_state=0, scoring="average_precision")
order = np.argsort(r.importances_mean)[::-1]
for i in order:
    print(f"  {feats[i]:>10}: {r.importances_mean[i]:+.4f}")
PY
echo "VERIFY_DONE"
