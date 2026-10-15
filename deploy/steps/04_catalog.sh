#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer
uv run python - <<'PY'
import pandas as pd
df = pd.read_excel("data/tornados_chile.xlsx")
print("filas:", len(df))
print("columnas:", list(df.columns))
print("--- primeras 3 filas (traspuestas) ---")
print(df.head(3).T)
print("--- rango de fechas del grid 2019-05-30 vs eventos ---")
for c in df.columns:
    if df[c].dtype == object:
        continue
print("--- dtypes ---")
print(df.dtypes)
PY
echo "CATALOG_DONE"
