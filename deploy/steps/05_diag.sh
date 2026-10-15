#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer
uv run python - <<'PY'
import pandas as pd, numpy as np
df = pd.read_excel("data/tornados_chile.xlsx")
lat = pd.to_numeric(df["Latitude"], errors="coerce")
print("Latitude: validos", lat.notna().sum(), "de", len(df))
bad = df["Latitude"][lat.isna()]
print("ejemplos no numericos de Latitude:")
print(bad.head(10).tolist())
d = pd.to_datetime(df["Date (Gregorian Calendar)"], errors="coerce")
print("fechas validas:", d.notna().sum())
print("eventos en 2019:", (d.dt.year == 2019).sum())
m = (d.dt.year == 2019) & (d.dt.month == 5)
print("eventos en mayo 2019:")
cols = ["Date (Gregorian Calendar)","Hour (UTC)","Latitude","Longitude","Register","Tornado","Waterspout"]
print(df.loc[m, cols].to_string())
h = pd.to_numeric(df["Hour (UTC)"], errors="coerce")
print("eventos con Hour UTC:", h.notna().sum())
print("rango del grid era5: lat de la region south-central-austral: -30..-56, lon -76..-66")
PY
echo "DIAG_DONE"
