#!/usr/bin/env python3
"""Variables celda-día por corte temporal (docs/claude/design.md §4, requirements R1).

Para cada día pedido:
1. carga los índices horarios de la spec (``indices.py``) desde ``era5_indices`` + ``era5_sfc``;
2. recorta las horas a las ≤ τ del corte (``dia`` = 00–23 UTC del día d, ``12utc`` = 00–12 UTC);
3. agrega a la grilla de 1° (promedio de las celdas ERA5 de 0,25° dentro de cada celda de 1°);
4. calcula por índice ``_max``, ``_tend6`` (máx aumento en 6 h hacia atrás), ``_pers`` (horas sobre
   umbral) y ``_max3x3`` (máximo de ``_max`` en la vecindad 3×3);
5. añade contexto (``mes``, ``banda_lat``), ``completo`` y las etiquetas (``labels.py``).

Escribe ``data/tables/features_<corte>.parquet``.

Uso::
    uv run python scripts/model/features.py --corte dia  --start 2019-05-30 --end 2019-05-31
    uv run python scripts/model/features.py --corte 12utc --start 2018-04-01 --end 2024-09-30
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import indices as indices_mod  # noqa: E402
import labels as labels_mod  # noqa: E402

CONFIG = Path(__file__).resolve().parent / "config" / "model_selection.yaml"

# Última hora UTC (índice de hora) que puede usar cada corte sobre el día d.
CORTE_TAU = {"dia": 23, "12utc": 12, "00utc": 0}


def load_config() -> dict:
    """Lee ``config/model_selection.yaml``."""
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_cell_grid(ds: xr.Dataset, cfg: dict) -> xr.Dataset:
    """Promedia los índices ERA5 (0,25°) dentro de cada celda de 1° del dominio.

    Devuelve un Dataset ``(time, lat, lon)`` en los centros de celda del dominio, en orden creciente.
    Se agrega con pandas para evitar problemas de alineación de grilla de xarray.
    """
    d = cfg["dominio"]
    res = d["resolucion_grados"]
    lat = ds["latitude"]
    lon = ds["longitude"]
    ds = ds.isel(
        latitude=np.flatnonzero(((lat >= d["lat_min"]) & (lat <= d["lat_max"])).values),
        longitude=np.flatnonzero(((lon >= d["lon_min"]) & (lon <= d["lon_max"])).values),
    )
    df = ds.to_dataframe().reset_index()
    df["lat"] = labels_mod.cell_center(df["latitude"], res)
    df["lon"] = labels_mod.cell_center(df["longitude"], res)
    dv = list(ds.data_vars)
    g = df.groupby(["time", "lat", "lon"])[dv].mean().reset_index()
    return g.set_index(["time", "lat", "lon"]).to_xarray().sortby(["lat", "lon"])


def cut_hours(ds: xr.Dataset, corte: str) -> xr.Dataset:
    """Conserva solo las horas ≤ τ del corte, sobre el día d (dims con hora UTC en ``time``)."""
    tau = CORTE_TAU[corte]
    hours = pd.to_datetime(ds["time"].values).hour
    return ds.isel(time=np.flatnonzero(hours <= tau))


def aggregate_cell_day(ds: xr.Dataset, cfg: dict) -> pd.DataFrame:
    """Agrega un día (ya recortado al corte y a la grilla de 1°) a una fila por celda.

    Calcula ``_max``, ``_tend6``, ``_pers`` y ``_max3x3`` por índice usando reducciones de xarray
    sobre el tiempo, lo que evita suposiciones sobre el orden de la grilla. ``ds`` tiene dims
    ``(time, lat, lon)``.
    """
    pers_umbral = cfg["persistencia"]
    n_horas = ds.sizes["time"]
    agg = {}

    for name in indices_mod.INDICES:
        col = indices_mod.SHERBE_COL if name == "sherbe_aprox" else name
        if col not in ds.data_vars:
            continue
        da = ds[col]  # (time, lat, lon)
        imax = da.max("time", skipna=True)
        # Tendencia: máximo aumento en 6 h (hacia atrás).
        if n_horas > 6:
            itend = (da.isel(time=slice(6, None)).values - da.isel(time=slice(None, -6)).values)
            itend = xr.DataArray(np.nanmax(itend, axis=0), coords=imax.coords, dims=imax.dims)
        elif n_horas > 1:
            itend = (da - da.isel(time=0)).max("time", skipna=True)
        else:
            itend = xr.zeros_like(imax)
        umbral = pers_umbral.get(col, pers_umbral.get(name, np.inf))
        ipers = (da > umbral).sum("time").astype(float)
        # _max3x3: máximo en la vecindad 3×3 sobre lat/lon.
        imax3 = (
            imax.rolling(lat=3, center=True, min_periods=1)
            .max()
            .rolling(lon=3, center=True, min_periods=1)
            .max()
        )
        agg[f"{col}_max"] = imax
        agg[f"{col}_tend6"] = itend
        agg[f"{col}_pers"] = ipers
        agg[f"{col}_max3x3"] = imax3

    out_ds = xr.Dataset(agg)
    feat = out_ds.to_dataframe().reset_index()
    feat["n_horas"] = n_horas
    return feat


def build(corte: str, days: list, cfg: dict, base: common.Store) -> pd.DataFrame:
    """Arma la tabla celda-día del corte para la lista de días (``datetime.date``)."""
    frames = []
    tau = CORTE_TAU[corte]
    for day in days:
        ds = indices_mod.load_day(base, f"{day:%Y%m%d}")
        if ds is None:
            continue
        ds = to_cell_grid(ds, cfg)
        ds_cut = cut_hours(ds, corte)
        if ds_cut.sizes["time"] == 0:
            continue
        feat = aggregate_cell_day(ds_cut, cfg)
        feat["fecha"] = day
        n_esperadas = tau + 1
        feat["completo"] = feat["n_horas"] >= 0.75 * n_esperadas
        frames.append(feat)
        print(f"  {day}: {len(feat)} celdas, {ds_cut.sizes['time']} horas (corte {corte})", flush=True)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["fecha"] = pd.to_datetime(out["fecha"]).dt.date
    f = pd.to_datetime(out["fecha"])
    out["anio"] = f.dt.year
    out["mes"] = f.dt.month
    out["banda_lat"] = (np.floor(out["lat"] / 2.0) * 2).astype(int)
    return out


def write_parquet(df: pd.DataFrame, out_file: common.Store) -> None:
    """Escribe ``df`` en parquet (local o S3)."""
    if out_file.is_s3:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            df.to_parquet(tmp_path, index=False)
            out_file.fs.put_file(str(tmp_path), out_file.root)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        Path(out_file.root).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_file.root, index=False)


def main() -> None:
    """Punto de entrada: construye y escribe ``features_<corte>.parquet``."""
    p = common.parser(__doc__, "los días")
    p.add_argument("--corte", choices=list(CORTE_TAU), default="dia", help="corte temporal")
    a = p.parse_args()
    common.set_data_root(a)
    reg = common.region_of(a)
    base = common.CROPS.child(reg.name)
    cfg = load_config()

    tbl = build(a.corte, common.days(a), cfg, base)
    if tbl.empty:
        raise SystemExit("no se armó ninguna fila; genera primero los índices (process_era5.py)")

    events = labels_mod.load_events(common.DATA.child("tornados_chile.xlsx"), cfg["dominio"]["resolucion_grados"])
    tbl = labels_mod.label_table(tbl, events)

    out_file = common.DATA.child("tables", f"features_{a.corte}.parquet")
    write_parquet(tbl, out_file)
    print(
        f"features_{a.corte}: {len(tbl)} celdas-día, {int(tbl['y'].sum())} positivas -> {out_file.root}",
        flush=True,
    )


if __name__ == "__main__":
    main()
