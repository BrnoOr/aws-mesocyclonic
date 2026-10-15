#!/usr/bin/env python3
"""Etiquetas por celda-día y tabla de eventos (docs/claude/design.md §5, requirements R2).

Lee ``data/tornados_chile.xlsx``, asigna cada evento a la celda de 1° que contiene su punto inicial y
a su fecha UTC, y produce:

- una función para etiquetar una tabla celda-día (``y = 1`` si hay evento en esa celda y día),
- ``data/tables/eventos.parquet`` con ``id_evento, fecha, lat, lon`` (centro de celda),
- el conteo de positivos por año (R2.3).

El catálogo trae ``Hour (UTC)`` como texto irregular; para la unidad celda-día solo se usa la fecha
(se documenta). Las celdas se identifican por el centro: ``floor(coord) + 0,5``.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402


def cell_center(coord: np.ndarray | pd.Series, resolucion: float = 1.0) -> np.ndarray:
    """Centro de la celda de ``resolucion`` grados que contiene ``coord`` (floor + media celda)."""
    return np.floor(np.asarray(coord, dtype=float) / resolucion) * resolucion + resolucion / 2.0


def load_events(path: common.Store, resolucion: float = 1.0) -> pd.DataFrame:
    """Lee el catálogo y devuelve ``id_evento, fecha (date), lat, lon`` (centro de celda) por evento.

    Conserva solo eventos con fecha y coordenadas utilizables, descartando fechas fuera del rango de
    pandas (eventos antiguos de 1554, etc.).
    """
    with path.local_copy() as p:
        raw = pd.read_excel(p)
    lat = pd.to_numeric(raw["Latitude"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    lon = pd.to_numeric(raw["Longitude"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    fecha = pd.to_datetime(raw["Date (Gregorian Calendar)"], errors="coerce").dt.normalize()
    fecha = fecha.where(fecha >= pd.Timestamp("1940-01-01"))
    df = pd.DataFrame(
        {
            "id_evento": [f"EV{i:04d}" for i in range(len(raw))],
            "fecha": fecha,
            "lat": cell_center(lat, resolucion),
            "lon": cell_center(lon, resolucion),
        }
    )
    df = df.dropna(subset=["fecha", "lat", "lon"]).reset_index(drop=True)
    df["fecha"] = df["fecha"].dt.date
    return df


def label_table(table: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Añade ``y`` (1 si hay evento en la celda-día) y ``n_eventos`` a ``table``.

    ``table`` tiene columnas ``fecha, lat, lon`` (centro de celda). El cruce es exacto por los tres.
    """
    key = ["fecha", "lat", "lon"]
    counts = events.groupby(key).size().rename("n_eventos").reset_index()
    out = table.merge(counts, on=key, how="left")
    out["n_eventos"] = out["n_eventos"].fillna(0).astype(int)
    out["y"] = (out["n_eventos"] > 0).astype(int)
    return out


def events_in_range(events: pd.DataFrame, anios: list[int], meses: tuple[int, int]) -> pd.DataFrame:
    """Filtra eventos por años y por el rango de meses de temporada (inclusive)."""
    f = pd.to_datetime(events["fecha"])
    m0, m1 = meses
    mask = f.dt.year.isin(anios) & (f.dt.month >= m0) & (f.dt.month <= m1)
    return events[mask].reset_index(drop=True)


def print_counts_by_year(events: pd.DataFrame) -> None:
    """Imprime el conteo de eventos por año (R2.3)."""
    f = pd.to_datetime(events["fecha"])
    counts = f.dt.year.value_counts().sort_index()
    print("eventos por año:", flush=True)
    for year, n in counts.items():
        print(f"  {int(year)}: {int(n)}", flush=True)


def main() -> None:
    """Punto de entrada: escribe eventos.parquet e imprime el conteo por año."""
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", default=None)
    p.add_argument("--resolucion", type=float, default=1.0)
    a = p.parse_args()

    import store

    root = store.default_root(a.data_root, common.ROOT / "data")
    data_store = store.Store.at(root)
    cat = data_store.child("tornados_chile.xlsx")
    assert cat.exists(), f"falta el catálogo en {cat.root}"
    events = load_events(cat, a.resolucion)
    print_counts_by_year(events)

    out_dir = data_store.child("tables")
    out_dir.mkdir()
    out_file = out_dir.child("eventos.parquet")
    if out_file.is_s3:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            events.to_parquet(tmp_path, index=False)
            out_file.fs.put_file(str(tmp_path), out_file.root)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        Path(out_file.root).parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(out_file.root, index=False)
    print(f"eventos -> {out_file.root} ({len(events)} eventos)", flush=True)


if __name__ == "__main__":
    main()
