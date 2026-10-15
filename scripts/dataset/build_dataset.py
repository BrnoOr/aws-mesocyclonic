#!/usr/bin/env python3
"""Arma el dataset de entrenamiento/validación/prueba desde ERA5, GOES y el catálogo.

Para cada día procesado cruza, celda por celda y hora por hora, las variables físicas de ERA5
(``era5_indices``), un resumen de GOES sobre cada celda (``goes_latlon``) y la etiqueta derivada del
catálogo. Produce un parquet por conjunto de anticipación (0, 1, 3 y 6 h): el de 0 h es el de
**diagnóstico** y los demás toman las variables con esa antelación conservando la etiqueta de la
hora del evento. Las particiones ``train``/``val``/``test``/``dev``/``inference`` se asignan por año
y el grupo de no fuga es la fecha del brote (ver ``features.py`` y ``docs/`` sección 6.3).

La unidad de análisis es una celda ERA5 (0,25°) en una hora UTC. Cada fila lleva:

- identificación: ``date``, ``hour_utc``, ``lat``, ``lon``, ``lead_h``, ``partition``, ``group``;
- variables físicas de ERA5 (cizalladura, SRH, LCL, VGP, STP, Sherburn, …);
- resumen de GOES sobre la celda: temperatura de brillo mínima/media de la banda 13 y su tendencia;
- etiqueta: ``label`` (1 = tornado/tromba reportado), ``event_uid``, ``confirmed``, ``hour_is_range``.

El catálogo solo tiene positivos, así que las celdas sin evento son *sin etiqueta* (0), no negativos
confirmados: el planteamiento es PU (sección 6.1). ``meso_proxy_*`` nunca es la etiqueta.

Entrada::

    data/catalog_clean.csv
    data/crops/<region>/era5_indices/era5_idx_AAAAMMDD.nc
    data/crops/<region>/goes_latlon/AAAAMMDD/goes_AAAAMMDDHH.nc

Salida::

    data/dataset/<region>/dataset_lead0h.parquet   (diagnóstico)
    data/dataset/<region>/dataset_lead1h.parquet
    data/dataset/<region>/dataset_lead3h.parquet
    data/dataset/<region>/dataset_lead6h.parquet
    data/dataset/<region>/summary.csv              (filas y positivos por partición y anticipación)

Uso::

    uv run python scripts/dataset/build_dataset.py --start 2019-05-30
    uv run python scripts/dataset/build_dataset.py --start 2018-01-01 --end 2025-12-31 --force
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features  # noqa: E402

import common  # noqa: E402

# Banda térmica de referencia (10,3 µm, igual que las figuras GOES): el tope frío de la convección.
GOES_BAND = "C13"
# Variables de ERA5 que entran como atributos de cada celda (todo lo que calcula process_era5.py).
ERA5_VARS = (
    "shear_01", "shear_03", "shear_06", "srh_01", "srh_03", "lcl", "gamma_03", "gamma_75",
    "vgp_01", "stp_lm", "sherbs3", "u_06", "v_06", "u_lm", "v_lm", "u_rm", "v_rm", "sfc_height",
)  # fmt: skip


def goes_hour_file(base: Path, date: str, hour: int) -> Path:
    """Ruta del archivo GOES lat/lon de ``date`` (ISO) a la hora ``hour`` (0–23)."""
    day = date.replace("-", "")
    return base / "goes_latlon" / day / f"goes_{day}{hour:02d}.nc"


def summarize_goes(
    ds: xr.Dataset, lat: np.ndarray, lon: np.ndarray, half: float
) -> dict[str, np.ndarray]:
    """Resume la banda térmica de GOES sobre cada celda ERA5, para la última imagen de la hora.

    Para cada celda (centro en ``lat`` × ``lon``, media anchura ``half`` grados) calcula, con los
    píxeles GOES que caen dentro: el mínimo (el tope más frío, señal de convección profunda), la
    media y la tendencia en el último paso de 10 min (``bt_last − bt_prev``, negativa = se enfría).
    Devuelve rejillas 2D ``(len(lat), len(lon))``; ``NaN`` donde no hay píxeles GOES en la celda.

    Se agrega de GOES (0,02°) a ERA5 (0,25°) en vez de interpolar: cada celda es un bloque de ~12×12
    píxeles y el mínimo de la ventana capta el tope frío mejor que un valor interpolado.
    """
    bt = ds[GOES_BAND]
    glat = ds["latitude"].values
    glon = ds["longitude"].values
    last = bt.isel(time=-1).values
    prev = bt.isel(time=-2).values if ds.sizes["time"] >= 2 else last
    tmin = np.full((len(lat), len(lon)), np.nan, dtype="f4")
    mean = np.full((len(lat), len(lon)), np.nan, dtype="f4")
    trend = np.full((len(lat), len(lon)), np.nan, dtype="f4")
    for i, la in enumerate(lat):
        ri = np.abs(glat - la) <= half
        if not ri.any():
            continue
        for j, lo in enumerate(lon):
            rj = np.abs(glon - lo) <= half
            if not rj.any():
                continue
            win = last[np.ix_(ri, rj)]
            if np.isfinite(win).any():
                tmin[i, j] = np.nanmin(win)
                mean[i, j] = np.nanmean(win)
                trend[i, j] = np.nanmean(last[np.ix_(ri, rj)] - prev[np.ix_(ri, rj)])
    return {"goes_bt_min": tmin, "goes_bt_mean": mean, "goes_bt_trend": trend}


def hour_frame(
    era5: xr.Dataset,
    goes: dict[str, np.ndarray],
    feat_hour: int,
    label_hour: int,
    events: list[features.Event],
    date: str,
    lead: int,
    region: str,
) -> pd.DataFrame:
    """Tabla de celdas para una hora: variables de ``feat_hour`` y etiqueta de ``label_hour``.

    Con ``lead == 0`` ambas horas coinciden (diagnóstico). Con ``lead > 0``, ``feat_hour`` es
    ``lead`` horas antes y la etiqueta sigue siendo la del evento (``label_hour``), de modo que la
    fila pregunta «¿se veía venir el evento ``lead`` horas antes?».
    """
    lat = era5["latitude"].values
    lon = era5["longitude"].values
    sel = era5.sel(time=era5["time"].dt.hour == feat_hour)
    if sel.sizes["time"] == 0:
        return pd.DataFrame()
    sel = sel.isel(time=0)
    label, uid, confirmed = features.label_grid(
        lat, lon, events, label_hour, features.MATCH_RADIUS_DEG
    )
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    n = LA.size
    data: dict[str, object] = {
        "date": np.full(n, date),
        "hour_utc": np.full(n, label_hour, dtype="int16"),
        "feat_hour_utc": np.full(n, feat_hour, dtype="int16"),
        "lead_h": np.full(n, lead, dtype="int16"),
        "lat": LA.ravel().astype("f4"),
        "lon": LO.ravel().astype("f4"),
    }
    for v in ERA5_VARS:
        if v in sel:
            data[v] = sel[v].values.ravel().astype("f4")
    for v, arr in goes.items():
        data[v] = arr.ravel().astype("f4")
    data["label"] = label.ravel().astype("int8")
    uid_flat = uid.ravel()
    data["event_uid"] = uid_flat
    data["confirmed"] = confirmed.ravel().astype("int8")
    # Hora imprecisa (el evento venía de un rango): se trata aparte en validación/prueba.
    is_range = {e.uid: e.is_range for e in events}
    data["hour_is_range"] = np.array([is_range.get(u, False) for u in uid_flat], dtype=bool)
    data["region"] = np.full(n, region)
    return pd.DataFrame(data)


def build_day(date: str, base: Path, catalog: pd.DataFrame, region: str) -> dict[int, pd.DataFrame]:
    """Tablas de un día, una por anticipación de ``features.LEAD_HOURS``.

    Carga los índices ERA5 del día y, para cada evento, cruza su hora (y las horas de anticipación)
    con las variables ERA5 y el resumen GOES de esa hora. Devuelve ``{lead: DataFrame}``; vacío si
    faltan los índices ERA5 del día. Los días sin evento positivo no aportan filas aquí: las celdas
    sin etiqueta (negativos PU) salen de los días al azar que procese el equipo, también positivos.
    """
    day = date.replace("-", "")
    f_idx = base / "era5_indices" / f"era5_idx_{day}.nc"
    if not f_idx.exists():
        print(f"{date}: falta {f_idx.name} (corre process_era5.py)", flush=True)
        return {}
    date_obj = pd.Timestamp(date).date()
    events = features.events_from_catalog(catalog, date_obj)
    hours = sorted({e.hour_utc for e in events})
    if not hours:
        print(f"{date}: sin eventos positivos con hora y coordenada", flush=True)
        return {}

    out: dict[int, list[pd.DataFrame]] = {lead: [] for lead in features.LEAD_HOURS}
    with xr.open_dataset(f_idx, engine="h5netcdf") as era5:
        for label_hour in hours:
            for lead in features.LEAD_HOURS:
                feat_hour = label_hour - lead
                if feat_hour < 0:  # la ventana de anticipación se sale del día; se omite
                    continue
                goes = _load_goes(base, date, feat_hour, era5)
                frame = hour_frame(
                    era5.load(), goes, feat_hour, label_hour, events, date, lead, region
                )
                if not frame.empty:
                    out[lead].append(frame)
    return {lead: pd.concat(fs, ignore_index=True) for lead, fs in out.items() if fs}


def _load_goes(base: Path, date: str, hour: int, era5: xr.Dataset) -> dict[str, np.ndarray]:
    """Resumen GOES sobre la grilla ERA5 para una hora; rejillas de ``NaN`` si falta el archivo."""
    lat = era5["latitude"].values
    lon = era5["longitude"].values
    f_goes = goes_hour_file(base, date, hour)
    if not f_goes.exists():
        empty = np.full((len(lat), len(lon)), np.nan, dtype="f4")
        return {
            "goes_bt_min": empty.copy(),
            "goes_bt_mean": empty.copy(),
            "goes_bt_trend": empty.copy(),
        }
    half = float(np.abs(lat[1] - lat[0]) / 2) if len(lat) > 1 else 0.125
    with xr.open_dataset(f_goes, engine="h5netcdf") as ds:
        return summarize_goes(ds, lat, lon, half)


def add_partition(df: pd.DataFrame) -> pd.DataFrame:
    """Añade ``partition`` (por año) y ``group`` (la fecha del brote) para evitar fuga de datos."""
    dates = pd.to_datetime(df["date"]).dt.date
    df = df.copy()
    df["partition"] = [features.partition_of(d) for d in dates]
    df["group"] = df["date"]  # todas las horas y celdas de un día quedan en el mismo grupo
    return df


def summarize(frames: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Resumen de filas y positivos por anticipación y partición, para revisar el reparto."""
    rows = []
    for lead, df in sorted(frames.items()):
        for part, g in df.groupby("partition"):
            rows.append(
                {
                    "lead_h": lead,
                    "partition": part,
                    "rows": len(g),
                    "positives": int((g["label"] == 1).sum()),
                    "confirmed_positives": int(((g["label"] == 1) & (g["confirmed"] == 1)).sum()),
                    "groups": g["group"].nunique(),
                }
            )
    return pd.DataFrame(rows).sort_values(["lead_h", "partition"]).reset_index(drop=True)


def check_no_leakage(frames: dict[int, pd.DataFrame]) -> None:
    """Comprueba que ningún grupo (día) aparece en más de una partición (fuga de datos)."""
    for lead, df in frames.items():
        per_group = df.groupby("group")["partition"].nunique()
        bad = per_group[per_group > 1]
        assert bad.empty, f"anticipación {lead} h: grupos en varias particiones: {list(bad.index)}"


def main() -> None:
    """Punto de entrada: arma el dataset de cada día pedido y escribe un parquet por anticipación."""
    p = common.parser(__doc__, "los días")
    a = p.parse_args()
    reg = common.region_of(a)
    base = common.CROPS / reg.name
    out_dir = common.DATA / "dataset" / reg.name
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_file = common.DATA / "catalog_clean.csv"
    if not catalog_file.exists():
        raise SystemExit(f"falta {catalog_file}; corre clean_catalog.py antes")
    catalog = pd.read_csv(catalog_file)

    collected: dict[int, list[pd.DataFrame]] = {lead: [] for lead in features.LEAD_HOURS}
    t0 = time.time()
    for day in common.days(a):
        frames = build_day(day.isoformat(), base, catalog, reg.name)
        for lead, df in frames.items():
            collected[lead].append(df)
        if frames:
            n = sum(len(df) for df in frames.values())
            pos = int(frames[0]["label"].sum()) if 0 in frames else 0
            print(f"{day}: {n} filas, {pos} celdas positivas (diagnóstico)", flush=True)

    merged = {
        lead: add_partition(pd.concat(fs, ignore_index=True))
        for lead, fs in collected.items()
        if fs
    }
    if not merged:
        raise SystemExit("ningún día aportó filas; revisa que existan los índices ERA5 del rango")
    check_no_leakage(merged)

    for lead, df in sorted(merged.items()):
        out_file = out_dir / f"dataset_lead{lead}h.parquet"
        if out_file.exists() and not a.force:
            # Con un rango que amplía el dataset, se concatena con lo ya escrito y se deduplica.
            old = pd.read_parquet(out_file)
            keys = ["date", "hour_utc", "lead_h", "lat", "lon"]
            df = pd.concat([old, df], ignore_index=True).drop_duplicates(keys, keep="last")
        df.to_parquet(out_file, index=False)
        print(
            f"{out_file.name}: {len(df)} filas, {int(df['label'].sum())} positivas",
            flush=True,
        )

    summary = summarize(merged)
    summary.to_csv(out_dir / "summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"listo en {time.time() - t0:.0f} s · {out_dir}", flush=True)


if __name__ == "__main__":
    main()
