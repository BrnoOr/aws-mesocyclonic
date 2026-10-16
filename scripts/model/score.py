#!/usr/bin/env python3
"""Puntúa celdas-día con el modelo entrenado: prueba ciega 2025 y candidatos 2026 (R6, R7).

Carga ``modelo_<corte>.pkl`` (de ``train.py``) y puntúa las celdas-día de ``features_<corte>.parquet``
en el rango de fechas pedido:

- Con ``--evaluate`` (prueba ciega 2025): calcula las métricas tolerantes y escribe
  ``data/outputs/blind_2025_<corte>.csv``. No reajusta nada (R6.2).
- Sin ``--evaluate`` (puntaje 2026): escribe ``data/outputs/candidatos_2026_<corte>.csv`` ordenado por
  puntaje, con umbral, alerta, los índices ``*_max`` y las tres variables de mayor contribución por
  fila, más el último día de 2026 con ERA5.

Mantiene la forma de la CLI que ya usaba el equipo (``--start --end --evaluate``); agrega ``--corte``.

Uso::
    uv run python scripts/model/score.py --start 2025-04-01 --end 2025-09-30 --evaluate --corte dia
    uv run python scripts/model/score.py --start 2026-04-01 --end 2026-09-30 --corte dia
"""

import argparse
import datetime as dt
import pickle
import sys
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as features_mod  # noqa: E402
import kpis as kpis_mod  # noqa: E402
import labels as labels_mod  # noqa: E402

import common  # noqa: E402


def load_model(data_store: common.Store, corte: str) -> dict:
    """Carga ``modelo_<corte>.pkl``."""
    f = data_store.child("outputs", f"modelo_{corte}.pkl")
    assert f.exists(), f"falta {f.root} (corre train.py)"
    blob = cast(bytes, f.fs.read_bytes(f.root)) if f.is_s3 else Path(f.root).read_bytes()
    return pickle.loads(blob)


def read_features(data_store: common.Store, corte: str) -> pd.DataFrame:
    """Lee features_<corte>.parquet."""
    f = data_store.child("tables", f"features_{corte}.parquet")
    assert f.exists(), f"falta {f.root}"
    return pd.read_parquet(f.root, storage_options={"anon": False} if f.is_s3 else None)


def top_contribs(model: object, X: pd.DataFrame) -> pd.DataFrame:
    """Devuelve top1–top3 (variable y contribución) por fila a partir de ``model.explain``."""
    contrib = model.explain(X)  # type: ignore[attr-defined]
    out = {}
    arr = contrib.to_numpy()
    cols = np.array(contrib.columns)
    order = np.argsort(-arr, axis=1)
    for rank in range(3):
        idx = order[:, rank] if arr.shape[1] > rank else np.zeros(len(X), int)
        out[f"top{rank + 1}"] = cols[idx]
        out[f"top{rank + 1}_contrib"] = (
            arr[np.arange(len(X)), idx] if arr.shape[1] > rank else np.nan
        )
    return pd.DataFrame(out, index=X.index)


def main() -> None:
    """Punto de entrada: evalúa 2025 o puntúa 2026 según ``--evaluate``."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=dt.date.fromisoformat, required=True)
    p.add_argument("--end", type=dt.date.fromisoformat, required=True)
    p.add_argument("--evaluate", action="store_true", help="prueba ciega: calcula métricas (2025)")
    p.add_argument("--corte", choices=["dia", "12utc", "00utc"], default="dia")
    p.add_argument("--data-root", default=None)
    a = p.parse_args()

    import store

    cfg = features_mod.load_config()
    data_store = store.Store.at(store.default_root(a.data_root, common.ROOT / "data"))
    payload = load_model(data_store, a.corte)
    model, thr = payload["model"], payload["umbral"]

    df = read_features(data_store, a.corte)
    f = pd.to_datetime(df["fecha"])
    mask = (f.dt.date >= a.start) & (f.dt.date <= a.end) & df["completo"]
    sub = df[mask].reset_index(drop=True)
    if sub.empty:
        raise SystemExit(f"no hay celdas-día completas entre {a.start} y {a.end} (corte {a.corte})")

    s = model.score(sub)
    sub = sub.assign(score=s, alerta=(s >= thr).astype(int))
    tol = cfg["tolerancia"]

    out_dir = data_store.child("outputs")
    out_dir.mkdir()

    if a.evaluate:
        events = labels_mod.load_events(
            data_store.child("tornados_chile.xlsx"), cfg["dominio"]["resolucion_grados"]
        )
        ev = events[
            (pd.to_datetime(events["fecha"]).dt.date >= a.start)
            & (pd.to_datetime(events["fecha"]).dt.date <= a.end)
        ]
        k = kpis_mod.tolerant_metrics(sub, ev, tol["vecindad_celdas"], tuple(tol["ventana_dias"]))
        k.update(
            {
                "corte": a.corte,
                "modelo": payload["modelo"],
                "umbral": thr,
                "config_version": payload["config_version"],
            }
        )
        res = pd.DataFrame([k])
        out = out_dir.child(f"blind_2025_{a.corte}.csv")
        _write_csv(res, out)
        print(f"=== prueba ciega 2025 ({a.corte}) ===", flush=True)
        print(res.to_string(index=False), flush=True)
    else:
        tops = top_contribs(model, sub)
        idx_cols = [c for c in sub.columns if c.endswith("_max")]
        cand = pd.concat([sub[["fecha", "lat", "lon", "score", "alerta", *idx_cols]], tops], axis=1)
        cand = cand.sort_values("score", ascending=False).reset_index(drop=True)
        cand["umbral"] = thr
        cand["ultimo_dia_era5"] = str(sub["fecha"].max())
        cand["modelo"] = payload["modelo"]
        out = out_dir.child(f"candidatos_2026_{a.corte}.csv")
        _write_csv(cand, out)
        print(
            f"candidatos 2026 ({a.corte}): {len(cand)} filas, {int(cand['alerta'].sum())} alertas; "
            f"último día ERA5 {sub['fecha'].max()} -> {out.root}",
            flush=True,
        )


def _write_csv(df: pd.DataFrame, out: common.Store) -> None:
    """Escribe un CSV (local o S3)."""
    if out.is_s3:
        with out.fs.open(out.root, "w") as fh:
            df.to_csv(fh, index=False)
    else:
        Path(out.root).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out.root, index=False)


if __name__ == "__main__":
    main()
