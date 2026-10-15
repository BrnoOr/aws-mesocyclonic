#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

for CORTE in dia 12utc; do
  echo "=== features --corte $CORTE (2018-2025) ==="
  uv run python scripts/model/features.py --corte "$CORTE" \
    --start 2018-04-01 --end 2025-09-30 2>&1 | tail -4
done
echo "=== tablas generadas ==="
ls -la data/tables/*.parquet 2>/dev/null
echo "=== positivos por tabla ==="
uv run python - <<'PY'
import pandas as pd
for c in ["dia","12utc"]:
    df = pd.read_parquet(f"data/tables/features_{c}.parquet")
    comp = df[df["completo"]]
    print(f"{c}: {len(df)} celdas-día, completas {len(comp)}, positivas {int(df['y'].sum())}, "
          f"años {sorted(df['anio'].unique())}")
PY
echo "FEATURES_DONE"
