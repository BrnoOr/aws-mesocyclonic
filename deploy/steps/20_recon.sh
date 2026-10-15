#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== scripts/model en la instancia ==="
ls -la scripts/model/ 2>/dev/null
echo "=== hay run_days.sh / plan_days.py / baselines.py / kpis.py? ==="
for f in run_days.sh plan_days.py baselines.py kpis.py indices.py features.py labels.py models.py cv.py decide.py; do
  [ -e "scripts/model/$f" ] && echo "SI: $f" || echo "no: $f"
done
echo "=== /srv/tornados/data existe? ==="
ls -la /srv/tornados/data 2>/dev/null || echo "no existe /srv/tornados/data"
echo "=== indices ERA5 disponibles ==="
ls data/crops/south-central-austral/era5_indices/ 2>/dev/null
echo "=== catalogo: eventos por anio 2015-2026 ==="
uv run python - <<'PY'
import pandas as pd, numpy as np
df = pd.read_excel("data/tornados_chile.xlsx")
d = pd.to_datetime(df["Date (Gregorian Calendar)"], errors="coerce")
lat = pd.to_numeric(df["Latitude"].astype(str).str.replace(",",".",regex=False), errors="coerce")
lon = pd.to_numeric(df["Longitude"].astype(str).str.replace(",",".",regex=False), errors="coerce")
ok = d.notna() & lat.notna() & lon.notna()
yr = d.dt.year
print("eventos por anio (2018-2026):")
for y in range(2018, 2027):
    n = int(((yr == y) & ok).sum())
    print(f"  {y}: {n}")
print("total 2018-2025:", int(((yr>=2018)&(yr<=2025)&ok).sum()))
h = df["Hour (UTC)"].astype(str)
print("filas con algo en Hour (UTC) (no nan):", int((h.str.strip().str.lower()!="nan").sum()))
print("rango lat eventos 2018-2025:", float(lat[(yr>=2018)&(yr<=2025)&ok].min()), float(lat[(yr>=2018)&(yr<=2025)&ok].max()))
print("rango lon eventos 2018-2025:", float(lon[(yr>=2018)&(yr<=2025)&ok].min()), float(lon[(yr>=2018)&(yr<=2025)&ok].max()))
PY
echo "INSPECT_DONE"
