"""Lo que la API calcula: puntaje de un día completo, reglas físicas y eventos del catálogo.

Todo sale de los recortes ERA5 de ``data/crops/<región>/era5_indices/`` y del catálogo limpio. La
respuesta de ``day_payload`` es la misma que la web guarda como respaldo en ``site/assets/``, así la
consola funciona igual con la API encendida o en modo demostración.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "model"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baselines import score_baseline  # noqa: E402
from predictors import Predictor  # noqa: E402

REGION = "south-central"
CROPS = ROOT / "data" / "crops" / REGION / "era5_indices"
CATALOG = ROOT / "data" / "catalog_clean.csv"
HOURS = list(range(12, 24))
RULES = ("stp", "hslc_b")
# Índices que la consola muestra al explicar una celda (con su umbral calibrado para Chile, si hay).
KEY_FEATURES = {
    "shear_01": "Cizalle 0–1 km (m/s)",
    "srh_01": "Helicidad 0–1 km (m²/s²)",
    "lcl": "Base de la nube, LCL (m)",
    "gamma_03": "Gradiente térmico 0–3 km (K/km)",
    "stp_lm": "STP left-mover",
}


def available_days() -> list[str]:
    """Fechas (AAAAMMDD) con recorte ERA5 para puntuar."""
    return sorted(p.stem.replace("era5_idx_", "") for p in CROPS.glob("era5_idx_*.nc"))


def events_of(day: str) -> list[dict]:
    """Tornados y trombas del catálogo en ``day``, con hora UTC si la tiene."""
    if not CATALOG.exists():
        return []
    cat = pd.read_csv(CATALOG)
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    rows = cat[(cat["date"].astype(str) == iso) & cat["lat"].notna() & cat["lon"].notna()]
    return [
        {
            "name": str(r.location),
            "hour": None if pd.isna(r.hour_utc) else str(r.hour_utc),
            "lat": round(float(r.lat), 3),
            "lon": round(float(r.lon), 3),
            "kind": None if pd.isna(r.kind) else str(r.kind),
            "ef": None if pd.isna(r.ef) else str(r.ef),
        }
        for r in rows.itertuples()
    ]


def _quantize(values: np.ndarray, digits: int) -> list[float | None]:
    """Redondea y cambia NaN por ``None`` (JSON no tiene NaN)."""
    return [None if not np.isfinite(v) else round(float(v), digits) for v in values]


def day_payload(day: str, predictor: Predictor) -> dict:
    """Puntaje 0–100 de ``predictor``, reglas físicas e índices clave de ``day``, de 12 a 23 UTC."""
    f = CROPS / f"era5_idx_{day}.nc"
    if not f.exists():
        raise FileNotFoundError(day)
    feats = predictor.features
    with xr.open_dataset(f, engine="h5netcdf") as ds:
        lats = ds["latitude"].to_numpy()
        lons = ds["longitude"].to_numpy()
        terrain = np.nan_to_num(ds["sfc_height"].isel(time=0).to_numpy()).ravel()
        hours = []
        for h in HOURS:
            sel = ds.sel(time=ds["time"].dt.hour == h)
            if sel.sizes["time"] == 0:
                continue
            df = sel.isel(time=0).to_dataframe().reset_index()
            ok = df[feats].notna().all(axis=1).to_numpy()
            score = np.full(len(df), -1)
            if ok.any():
                p = predictor.predict(df.loc[ok, feats])
                score[ok] = np.rint(p * 100).astype(int)
            hours.append(
                {
                    "hour": h,
                    "score": score.tolist(),
                    **{r: score_baseline(r, df).astype(int).tolist() for r in RULES},
                    "features": {
                        k: _quantize(df[k].to_numpy(dtype=float), 1) for k in KEY_FEATURES
                    },
                }
            )
    return {
        "day": day,
        "lats": lats.round(2).tolist(),
        "lons": lons.round(2).tolist(),
        "terrain": np.rint(terrain).astype(int).tolist(),
        "threshold": round(float(predictor.metadata.get("threshold", 0.9)) * 100),
        "feature_labels": KEY_FEATURES,
        "hours": hours,
        "events": events_of(day),
    }
