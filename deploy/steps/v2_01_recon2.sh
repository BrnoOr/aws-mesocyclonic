#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

uv run python - <<'PY'
import glob, xarray as xr, pandas as pd, numpy as np
base = "data/crops/south-central-austral"
sfc = sorted(glob.glob(f"{base}/era5_sfc/*.nc"))
idx = sorted(glob.glob(f"{base}/era5_indices/*.nc"))
print("era5_sfc archivos:", len(sfc))
if sfc:
    ds = xr.open_dataset(sfc[0]); print("sfc vars:", list(ds.data_vars)); ds.close()
if idx:
    ds = xr.open_dataset(idx[0])
    print("idx vars:", list(ds.data_vars))
    print("idx lat range:", float(ds['latitude'].min()), float(ds['latitude'].max()))
    print("idx lon range:", float(ds['longitude'].min()), float(ds['longitude'].max()))
    ds.close()

# Días por año-mes disponibles en era5_indices
import re, collections
fechas = [re.search(r'(\d{8})', f).group(1) for f in idx]
anios = collections.Counter(f[:4] for f in fechas)
print("índices por año:", dict(sorted(anios.items())))

# Catálogo
df = pd.read_excel("data/tornados_chile.xlsx")
print("\ncolumnas catálogo:", list(df.columns))
d = pd.to_datetime(df["Date (Gregorian Calendar)"], errors="coerce")
lat = pd.to_numeric(df["Latitude"].astype(str).str.replace(",",".",regex=False), errors="coerce")
lon = pd.to_numeric(df["Longitude"].astype(str).str.replace(",",".",regex=False), errors="coerce")
ok = d.notna() & lat.notna() & lon.notna()
season = d.dt.month.between(4,9)
print("\neventos por año (abril-sep), 2015-2025:")
for y in range(2015,2026):
    n = int(((d.dt.year==y) & ok & season).sum())
    print(f"  {y}: {n}")
print("total 2015-2024 abr-sep:", int(((d.dt.year>=2015)&(d.dt.year<=2024)&ok&season).sum()))
h = df["Hour (UTC)"].astype(str)
print("Hour(UTC) no-nan:", int((h.str.strip().str.lower()!="nan").sum()), "de", len(df))
print("ejemplos Hour(UTC):", df["Hour (UTC)"].dropna().astype(str).head(6).tolist())
print("Register valores:", df["Register"].value_counts(dropna=False).to_dict())
print("lat eventos ok:", float(lat[ok].min()), float(lat[ok].max()))
PY
echo "RECON2_DONE"
