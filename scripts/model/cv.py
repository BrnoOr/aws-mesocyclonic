#!/usr/bin/env python3
"""Validación cruzada dejando un año fuera (docs/claude/design.md §7, requirements R4).

Para cada corte y modelo: valida dejando un año fuera 2018–2024, elige el umbral de alerta por
validación interna (el más alto con POD tolerante ≥ 70 % sobre predicciones fuera de pliegue de los
años de entrenamiento), junta las predicciones de prueba de todos los pliegues y calcula POD, FAR,
días por detección y PR-AUC con acierto tolerante. Estima intervalos con bootstrap por fecha (1000
réplicas) para la diferencia de cada modelo contra M1.

Salidas: ``data/outputs/cv_report.csv`` (un renglón por modelo y corte) y
``data/outputs/cv_by_fold.csv``.

Uso::
    uv run python scripts/model/cv.py --corte dia
    uv run python scripts/model/cv.py --corte 12utc
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as features_mod  # noqa: E402
import kpis as kpis_mod  # noqa: E402
import labels as labels_mod  # noqa: E402
import models as models_mod  # noqa: E402

import common  # noqa: E402

MODEL_NAMES = ["M0", "M1", "M2", "M3", "M4"]


def pick_threshold(scores: np.ndarray, df: pd.DataFrame, events: pd.DataFrame, cfg: dict) -> float:
    """Umbral más alto con POD tolerante ≥ pod_objetivo sobre ``scores`` (validación interna)."""
    pod_obj = cfg["validacion"]["pod_objetivo"]
    tol = cfg["tolerancia"]
    cand = np.unique(np.round(scores, 6))
    best = cand.min() if len(cand) else 0.0
    for t in sorted(cand, reverse=True):
        tmp = df.assign(alerta=(scores >= t).astype(int), score=scores)
        pod = kpis_mod.tolerant_metrics(
            tmp, events, tol["vecindad_celdas"], tuple(tol["ventana_dias"])
        )["POD"]
        if pod is not None and not np.isnan(pod) and pod >= pod_obj:
            return float(t)
    return float(best)


def inner_oof(model_name: str, train: pd.DataFrame, cfg: dict, cols: list[str]) -> np.ndarray:
    """Predicciones fuera de pliegue dentro de ``train`` (año-fuera interno) para elegir el umbral."""
    oof = np.full(len(train), np.nan)
    years = sorted(train["anio"].unique())
    for yv in years:
        tr = train[train["anio"] != yv]
        va = train[train["anio"] == yv]
        if tr["y"].sum() == 0 or len(va) == 0:
            continue
        m = models_mod.build_model(model_name, cfg, cols).fit(tr, tr["y"].to_numpy())
        oof[train["anio"].to_numpy() == yv] = m.score(va)
    return oof


def run_cut(corte: str, cfg: dict, data_store: common.Store) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ejecuta la validación de todos los modelos para un corte. Devuelve (reporte, por_pliegue)."""
    feats_file = data_store.child("tables", f"features_{corte}.parquet")
    assert feats_file.exists(), f"falta {feats_file.root} (corre features.py --corte {corte})"
    if feats_file.is_s3:
        df = pd.read_parquet(feats_file.root, storage_options={"anon": False})
    else:
        df = pd.read_parquet(feats_file.root)
    anios = cfg["dominio"]["anios_entrenamiento"]
    df = df[df["completo"] & df["anio"].isin(anios)].reset_index(drop=True)
    events_all = labels_mod.load_events(
        data_store.child("tornados_chile.xlsx"), cfg["dominio"]["resolucion_grados"]
    )
    tol = cfg["tolerancia"]
    cols = [c for c in df.columns if c.endswith(("_max", "_tend6", "_pers", "_max3x3"))]

    by_fold = []
    oof_pred = {m: np.full(len(df), np.nan) for m in MODEL_NAMES}
    thresholds = {m: {} for m in MODEL_NAMES}

    for model_name in MODEL_NAMES:
        for yv in anios:
            tr = df[df["anio"] != yv]
            va_mask = df["anio"].to_numpy() == yv
            va = df[va_mask]
            if tr["y"].sum() == 0 or len(va) == 0:
                continue
            oof = inner_oof(model_name, tr, cfg, cols)
            ev_tr = labels_mod.events_in_range(
                events_all, [y for y in anios if y != yv], tuple(cfg["dominio"]["temporada"])
            )
            thr = pick_threshold(oof[~np.isnan(oof)], tr[~np.isnan(oof)], ev_tr, cfg)
            thresholds[model_name][yv] = thr
            m = models_mod.build_model(model_name, cfg, cols).fit(tr, tr["y"].to_numpy())
            s = m.score(va)
            oof_pred[model_name][va_mask] = s
            ev_va = labels_mod.events_in_range(events_all, [yv], tuple(cfg["dominio"]["temporada"]))
            tmp = va.assign(alerta=(s >= thr).astype(int), score=s)
            k = kpis_mod.tolerant_metrics(
                tmp, ev_va, tol["vecindad_celdas"], tuple(tol["ventana_dias"])
            )
            by_fold.append({"corte": corte, "modelo": model_name, "anio": yv, "umbral": thr, **k})

    # Métricas agrupadas sobre los 7 años (predicciones fuera de pliegue juntas).
    report = []
    events_season = labels_mod.events_in_range(
        events_all, anios, tuple(cfg["dominio"]["temporada"])
    )
    agg_threshold = {
        m: float(np.nanmedian(list(thresholds[m].values()) or [0.0])) for m in MODEL_NAMES
    }
    for model_name in MODEL_NAMES:
        s = oof_pred[model_name]
        mask = ~np.isnan(s)
        thr = agg_threshold[model_name]
        tmp = df[mask].assign(alerta=(s[mask] >= thr).astype(int), score=s[mask])
        k = kpis_mod.tolerant_metrics(
            tmp, events_season, tol["vecindad_celdas"], tuple(tol["ventana_dias"])
        )
        report.append({"corte": corte, "modelo": model_name, "umbral": thr, **k})

    rep = pd.DataFrame(report)

    # Bootstrap por fecha contra M1 (ΔFAR, ΔPOD, ΔPR-AUC) con intervalos.
    boot = bootstrap_vs_m1(df, oof_pred, agg_threshold, events_season, cfg)
    rep = rep.merge(boot, on="modelo", how="left")
    rep["config_version"] = cfg["version"]
    return rep, pd.DataFrame(by_fold)


def bootstrap_vs_m1(
    df: pd.DataFrame, oof: dict, thr: dict, events: pd.DataFrame, cfg: dict
) -> pd.DataFrame:
    """Bootstrap por fecha (remuestrea fechas, no celdas) para ΔFAR/ΔPOD/ΔPR-AUC vs M1 (R4.4)."""
    rng = np.random.default_rng(cfg["semilla"])
    n_rep = cfg["validacion"]["bootstrap_replicas"]
    tol = cfg["tolerancia"]
    fechas = df["fecha"].unique()
    rows = {m: {"dFAR": [], "dPOD": [], "dPR_AUC": []} for m in MODEL_NAMES}

    def metrics_for(model_name: str, sub: pd.DataFrame, ev: pd.DataFrame) -> dict:
        """Métricas tolerantes de un modelo sobre un subconjunto de fechas."""
        s = oof[model_name][sub.index.to_numpy()]
        m = ~np.isnan(s)
        if m.sum() == 0:
            return {"POD": np.nan, "FAR": np.nan, "PR_AUC": np.nan}
        tmp = sub[m].assign(alerta=(s[m] >= thr[model_name]).astype(int), score=s[m])
        return kpis_mod.tolerant_metrics(
            tmp, ev, tol["vecindad_celdas"], tuple(tol["ventana_dias"])
        )

    df_idx = df.reset_index(drop=True)
    for _ in range(n_rep):
        samp_fechas = rng.choice(fechas, size=len(fechas), replace=True)
        sub = pd.concat([df_idx[df_idx["fecha"] == f] for f in samp_fechas]).reset_index(drop=True)
        ev = events[pd.to_datetime(events["fecha"]).dt.date.isin(set(samp_fechas))]
        base = metrics_for("M1", sub, ev)
        for model_name in MODEL_NAMES:
            mk = metrics_for(model_name, sub, ev)
            rows[model_name]["dFAR"].append(mk["FAR"] - base["FAR"])
            rows[model_name]["dPOD"].append(mk["POD"] - base["POD"])
            rows[model_name]["dPR_AUC"].append(mk["PR_AUC"] - base["PR_AUC"])

    out = []
    for model_name in MODEL_NAMES:
        r = rows[model_name]
        out.append(
            {
                "modelo": model_name,
                "dFAR_vs_M1": float(np.nanmean(r["dFAR"])),
                "dFAR_se": float(np.nanstd(r["dFAR"])),
                "dPOD_vs_M1": float(np.nanmean(r["dPOD"])),
                "dPR_AUC_vs_M1": float(np.nanmean(r["dPR_AUC"])),
                "dPR_AUC_se": float(np.nanstd(r["dPR_AUC"])),
            }
        )
    return pd.DataFrame(out)


def main() -> None:
    """Punto de entrada: corre la validación de un corte y escribe los CSV."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corte", choices=["dia", "12utc", "00utc"], default="dia")
    p.add_argument("--data-root", default=None)
    a = p.parse_args()

    import store

    cfg = features_mod.load_config()
    root = store.default_root(a.data_root, common.ROOT / "data")
    data_store = store.Store.at(root)

    rep, by_fold = run_cut(a.corte, cfg, data_store)
    out_dir = data_store.child("outputs")
    out_dir.mkdir()
    _write_csv(rep, out_dir.child("cv_report.csv"), a.corte)
    _write_csv(by_fold, out_dir.child("cv_by_fold.csv"), a.corte)
    print(f"=== cv_report ({a.corte}) ===", flush=True)
    print(rep.to_string(index=False), flush=True)


def _write_csv(df: pd.DataFrame, out: common.Store, corte: str) -> None:
    """Escribe/añade un CSV por corte (acumula cortes en el mismo archivo)."""
    if out.is_s3:
        existing = pd.read_csv(out.fs.open(out.root, "rb")) if out.exists() else pd.DataFrame()
    else:
        existing = pd.read_csv(out.root) if Path(out.root).exists() else pd.DataFrame()
    if not existing.empty and "corte" in existing.columns:
        existing = existing[existing["corte"] != corte]
    combined = pd.concat([existing, df], ignore_index=True)
    if out.is_s3:
        with out.fs.open(out.root, "w") as f:
            combined.to_csv(f, index=False)
    else:
        Path(out.root).parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(out.root, index=False)


if __name__ == "__main__":
    main()
