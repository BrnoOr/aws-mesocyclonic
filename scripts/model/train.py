#!/usr/bin/env python3
"""Entrena el modelo elegido con los datos hasta un año (requirements R6, R7, R9.2).

Lee ``features_<corte>.parquet`` y ``decision_<corte>.md`` (para saber el modelo elegido), entrena
con las celdas-día completas de temporada hasta ``--until`` (inclusive) y guarda el modelo entrenado
y su umbral en ``data/outputs/modelo_<corte>.pkl``.

Mantiene la opción ``--until`` que ya usaba el equipo; agrega ``--modelo`` (por defecto ``elegido``,
que lo lee de decision_<corte>.md) y ``--corte`` (por defecto ``dia``).

Uso::
    uv run python scripts/model/train.py --until 2024 --corte dia
    uv run python scripts/model/train.py --until 2025 --modelo M4 --corte 12utc
"""

import argparse
import pickle
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv as cv_mod  # noqa: E402
import features as features_mod  # noqa: E402
import labels as labels_mod  # noqa: E402
import models as models_mod  # noqa: E402

import common  # noqa: E402


def elegido_de_decision(data_store: common.Store, corte: str) -> str:
    """Lee el modelo elegido de ``decision_<corte>.md`` (o M1 si no existe)."""
    f = data_store.child("outputs", f"decision_{corte}.md")
    if not f.exists():
        return "M1"
    txt = (
        str(f.fs.read_text(f.root, encoding="utf-8"))
        if f.is_s3
        else Path(f.root).read_text(encoding="utf-8")
    )
    m = re.search(r"Modelo elegido:\s*\*\*(M\d)\*\*", txt)
    return m.group(1) if m else "M1"


def read_features(data_store: common.Store, corte: str) -> pd.DataFrame:
    """Lee features_<corte>.parquet (local o S3)."""
    f = data_store.child("tables", f"features_{corte}.parquet")
    assert f.exists(), f"falta {f.root}"
    return pd.read_parquet(f.root, storage_options={"anon": False} if f.is_s3 else None)


def train_until(data_store: common.Store, corte: str, modelo: str, until: int, cfg: dict) -> dict:
    """Entrena el modelo con temporada hasta ``until`` y calcula su umbral (POD≥objetivo interno)."""
    df = read_features(data_store, corte)
    m0, m1 = cfg["dominio"]["temporada"]
    df = df[
        df["completo"] & (df["mes"] >= m0) & (df["mes"] <= m1) & (df["anio"] <= until)
    ].reset_index(drop=True)
    cols = [c for c in df.columns if c.endswith(("_max", "_tend6", "_pers", "_max3x3"))]
    events = labels_mod.load_events(
        data_store.child("tornados_chile.xlsx"), cfg["dominio"]["resolucion_grados"]
    )
    ev = labels_mod.events_in_range(events, sorted(df["anio"].unique()), (m0, m1))

    # Umbral: validación interna año-fuera sobre los datos de entrenamiento.
    oof = cv_mod.inner_oof(modelo, df, cfg, cols)
    thr = cv_mod.pick_threshold(oof[~np.isnan(oof)], df[~np.isnan(oof)], ev, cfg)

    model = models_mod.build_model(modelo, cfg, cols).fit(df, df["y"].to_numpy())
    return {
        "model": model,
        "umbral": thr,
        "modelo": modelo,
        "corte": corte,
        "cols": cols,
        "until": until,
        "config_version": cfg["version"],
    }


def main() -> None:
    """Punto de entrada: entrena y guarda modelo_<corte>.pkl."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--until", type=int, required=True, help="último año de entrenamiento (inclusive)"
    )
    p.add_argument(
        "--modelo", default="elegido", help="M0..M4 o 'elegido' (lee decision_<corte>.md)"
    )
    p.add_argument("--corte", choices=["dia", "12utc", "00utc"], default="dia")
    p.add_argument("--data-root", default=None)
    a = p.parse_args()

    import store

    cfg = features_mod.load_config()
    data_store = store.Store.at(store.default_root(a.data_root, common.ROOT / "data"))
    modelo = elegido_de_decision(data_store, a.corte) if a.modelo == "elegido" else a.modelo
    payload = train_until(data_store, a.corte, modelo, a.until, cfg)

    out = data_store.child("outputs", f"modelo_{a.corte}.pkl")
    data_store.child("outputs").mkdir()
    blob = pickle.dumps(payload)
    if out.is_s3:
        out.fs.pipe_file(out.root, blob)
    else:
        Path(out.root).parent.mkdir(parents=True, exist_ok=True)
        Path(out.root).write_bytes(blob)
    print(
        f"entrenado {modelo} ({a.corte}) hasta {a.until}, umbral={payload['umbral']:.4f} -> {out.root}",
        flush=True,
    )


if __name__ == "__main__":
    main()
