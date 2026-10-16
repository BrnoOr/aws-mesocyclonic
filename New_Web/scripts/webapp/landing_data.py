#!/usr/bin/env python3
"""Genera los datos de la página de presentación de Vórtice (``landing/``).

Escribe en ``landing/assets/`` (no en ``data/``, que git ignora):

- ``caso2019.json``: el 30 de mayo de 2019 hora a hora (12–23 UTC) sobre la grilla ERA5 de
  ``south-central``: puntaje del modelo (0–100), dónde se dispara cada regla física (STP y HSLC B),
  la altura del terreno y los tornados del catálogo con su hora.
- ``eventos_aiwp.json``: los 25 eventos de la evaluación sobre el pronóstico Pangu-Weather, con sus
  coordenadas del catálogo y si los capturó el modelo o las reglas.

Copia además a ``landing/assets/`` la foto del tornado de Los Ángeles y las figuras del documento
que usa la página.

Uso::

    uv run python scripts/webapp/landing_data.py
"""

import json
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "model"))

from baselines import score_baseline  # noqa: E402

DATA = ROOT / "data"
OUT = ROOT / "landing"
DAY = "20190530"
HOURS = range(12, 24)
REPO = ROOT.parent
FIGS = {
    "goes_20190530.png": REPO / "figs" / "fig3_goes_20190530.png",
    "catalogo.png": REPO / "figs" / "fig1_catalog_map.png",
    "tornado_los_angeles.webp": REPO / "scripts" / "viewer" / "assets" / "tornado_los_angeles.webp",
}


def case_2019() -> dict:
    """Puntaje del modelo y disparos de las reglas, hora a hora, para el brote del 30 de mayo de 2019."""
    bundle = joblib.load(ROOT / "modelo.joblib")
    feats = list(bundle["features"])
    f = DATA / "crops" / "south-central" / "era5_indices" / f"era5_idx_{DAY}.nc"
    with xr.open_dataset(f, engine="h5netcdf") as ds:
        lats = ds["latitude"].to_numpy()
        lons = ds["longitude"].to_numpy()
        terrain = ds["sfc_height"].isel(time=0).to_numpy()
        hours = []
        for h in HOURS:
            df = ds.isel(time=h).to_dataframe().reset_index()
            ok = df[feats].notna().all(axis=1).to_numpy()
            score = np.full(len(df), -1)
            score[ok] = np.rint(
                bundle["model"].predict_proba(df.loc[ok, feats])[:, 1] * 100
            ).astype(int)
            hours.append(
                {
                    "hour": h,
                    "score": score.tolist(),
                    "stp": score_baseline("stp", df).astype(int).tolist(),
                    "hslc_b": score_baseline("hslc_b", df).astype(int).tolist(),
                }
            )
    cat = pd.read_csv(DATA / "catalog_clean.csv")
    ev = cat[cat["date"] == f"{DAY[:4]}-{DAY[4:6]}-{DAY[6:]}"]
    events = [
        {"name": r.location, "hour": r.hour_utc, "lat": r.lat, "lon": r.lon, "ef": r.ef}
        for r in ev.itertuples()
    ]
    return {
        "day": DAY,
        "lats": lats.round(2).tolist(),
        "lons": lons.round(2).tolist(),
        "terrain": np.rint(np.nan_to_num(terrain)).astype(int).ravel().tolist(),
        "threshold": round(float(bundle["metadata"]["threshold"]) * 100),
        "hours": hours,
        "events": events,
    }


def aiwp_events() -> list[dict]:
    """Eventos de ``aiwp_bundle_eval.csv`` con coordenadas del catálogo (mismo día y nombre)."""
    ev = pd.read_csv(ROOT / "reports" / "aiwp_bundle_eval.csv")
    cat = pd.read_csv(DATA / "catalog_clean.csv")
    rows = []
    for r in ev.itertuples():
        day = r.time[:10]
        key = r.name.split("(")[0].split()[0].lower()
        same = cat[cat["date"] == day]
        hit = same[same["location"].str.lower().str.contains(key, regex=False)]
        loc = (hit if len(hit) else same).iloc[0]
        rows.append(
            {
                "name": r.name,
                "time": r.time[:16],
                "year": int(r.year),
                "kind": r.kind,
                "ef": r.ef,
                "unseen": not bool(r.oof),
                "lat": round(float(loc["lat"]), 3),
                "lon": round(float(loc["lon"]), 3),
                "model_a": bool(r.caught_model_areaA),
                "model_b": bool(r.caught_model_areaB),
                "rule_a": bool(r.caught_A),
                "rule_b": bool(r.caught_B),
            }
        )
    return rows


def main() -> None:
    """Escribe los JSON y copia las figuras."""
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "caso2019.json").write_text(
        json.dumps(case_2019(), separators=(",", ":")), encoding="utf-8"
    )
    (assets / "eventos_aiwp.json").write_text(
        json.dumps(aiwp_events(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for dst, src in FIGS.items():
        if src.exists():
            shutil.copy2(src, assets / dst)
    print(f"Datos de la página en {assets}")


if __name__ == "__main__":
    main()
