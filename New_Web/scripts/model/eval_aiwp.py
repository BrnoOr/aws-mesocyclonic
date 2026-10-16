#!/usr/bin/env python3
"""Evalúa el modelo sobre el **pronóstico AIWP** (Pangu-Weather) sin fuga y con umbrales de área igualada.

Dos cuidados frente a una evaluación ingenua:

1. **Sin fuga.** Ningún evento se puntúa con un modelo entrenado en su año. Los eventos de 2021–2023
   (años dentro de ``train``) se puntúan *out of fold*: con el modelo LOYO que **excluyó ese año**.
   Los de 2024–2025 (nunca vistos) se puntúan con el modelo de solo-``train`` (2018–2023), que es el
   del *bundle*. Se reporta todo separado en «años de entrenamiento (OOF)» y «2024–2025 (nunca
   vistos)».
2. **Área igualada, elegida sin mirar los eventos.** Para comparar de forma justa con cada regla, el
   umbral del modelo se fija para que marque **la misma fracción de celda-horas del pronóstico** que
   la regla (A: 1,07 %, B: 10,74 %), usando solo la distribución de puntuaciones *out of fold*, no
   los eventos. Luego se cuenta cuántos eventos captura (criterio del lote: 50 km, ±6 h).

El barrido 0,5/0,7/0,9 queda **solo como anexo**, rotulado «umbral elegido a posteriori, no es un
resultado». El *bundle* no se reajusta.

Salida::

    reports/aiwp_bundle_eval.md
    reports/aiwp_bundle_eval.csv

Uso::

    uv run python scripts/model/eval_aiwp.py --model modelo.joblib --forecasts /tmp/aiwp_output
"""

import argparse
import glob
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xarray as xr
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kpi as kpimod  # noqa: E402
import train as tr  # noqa: E402

import common  # noqa: E402

R_KM = 50.0
DT_HOURS = 6
SHEAR_MIN = 12.0
SRH_MAX = -150.0
TRAIN_YEARS = range(2018, 2024)  # años dentro de train: se puntúan out-of-fold
SWEEP = (0.5, 0.7, 0.9)  # solo anexo, no es un resultado

BATCH_EVENTS = [
    ("Llanquihue", "2021-04-08 17:00", -41.268268, -72.993278),
    ("Lago Villarrica", "2021-05-03 22:20", -39.256323, -72.157715),
    ("Ancud (2021)", "2021-06-09 10:30", -41.861558, -73.819029),
    ("Mehuín", "2021-06-09 15:00", -39.433, -73.1999),
    ("Toltén Viejo", "2021-06-09 17:00", -39.2062, -73.2108),
    ("Tucapel", "2021-08-19 07:00", -37.289254, -71.951077),
    ("Valle Volcanes (Pto Montt)", "2022-03-08 16:59", -41.4592, -72.9112),
    ("Peralillo", "2022-07-01 18:10", -34.476, -71.464),
    ("Cobquecura", "2022-08-15 17:59", -36.077, -72.797),
    ("Ancud (2023)", "2023-06-02 21:50", -41.885724, -73.842669),
    ("Puerto Saavedra", "2023-06-07 13:53", -38.813995, -73.403686),
    ("Lago Todos los Santos", "2023-06-25 17:48", -41.110048, -72.352376),
    ("Futrono", "2023-06-26 16:20", -40.12569, -72.383452),
    ("Lago Llanquihue", "2023-06-26 19:35", -41.104851, -72.75763),
    ("La Vara (Pto Montt)", "2023-06-27 19:28", -41.422427, -72.907528),
    ("Lago Llanquihue (R225)", "2023-07-14 20:04", -41.224, -72.6574),
    ("San Pedro de la Paz", "2023-09-06 15:45", -36.858005, -73.161822),
    ("Maiquillahue", "2023-09-11 19:45", -39.45966, -73.25942),
    ("Calbuco", "2024-05-25 18:00", -41.778723, -73.108264),
    ("Penco", "2024-06-18 09:00", -36.73685, -73.000576),
    ("Folilco", "2024-06-20 03:00", -39.871718, -72.65955),
    ("Malalhue (Lanco)", "2024-06-20 21:01", -39.539336, -72.497421),
    ("Dadinco (Chillán)", "2024-06-21 20:30", -36.640966, -71.985331),
    ("Los Ángeles", "2025-05-17 17:20", -37.4856, -72.3155),
    ("Puerto Varas", "2025-05-25 19:05", -41.321875, -72.985342),
]


def batch_events(catalog: pd.DataFrame) -> pd.DataFrame:
    """Los 25 eventos del lote con tipo y EF unidos del catálogo por cercanía del mismo día."""
    ev = pd.DataFrame(BATCH_EVENTS, columns=["name", "time", "lat", "lon"])
    ev["time"] = pd.to_datetime(ev["time"])
    ev["year"] = ev["time"].dt.year
    cat = catalog.dropna(subset=["lat", "lon", "date"]).copy()
    cat["cdate"] = pd.to_datetime(cat["date"], errors="coerce")
    kinds, efs = [], []
    for _, e in ev.iterrows():
        same_day = cat[cat["cdate"].dt.date == e["time"].date()]
        if same_day.empty:
            kinds.append("desconocido")
            efs.append(None)
            continue
        d = kpimod.haversine(
            e["lat"], e["lon"], same_day["lat"].to_numpy(), same_day["lon"].to_numpy()
        )
        row = same_day.iloc[int(np.argmin(d))]
        kinds.append(str(row.get("kind", "desconocido")))
        efs.append(row.get("ef"))
    ev["kind"] = kinds
    ev["ef"] = efs
    return ev


def cells_long(ds: xr.Dataset, values: np.ndarray) -> pd.DataFrame:
    """Celdas (tiempo × lat × lon) en formato largo con una columna ``value``."""
    da = xr.DataArray(
        values,
        coords={"time": ds["time"], "latitude": ds["latitude"], "longitude": ds["longitude"]},
        dims=("time", "latitude", "longitude"),
    )
    df = da.to_dataframe(name="value").reset_index()
    df["time"] = pd.to_datetime(df["time"])
    return df


def score_grid(ds: xr.Dataset, model: Pipeline, feats: list[str]) -> np.ndarray:
    """Probabilidad del modelo por celda-hora (``NaN`` donde falta alguna feature)."""
    stack = ds[feats].to_dataframe().reset_index()
    ok = stack[feats].notna().all(axis=1)
    prob = np.full(len(stack), np.nan)
    if ok.any():
        prob[ok.to_numpy()] = model.predict_proba(stack.loc[ok, feats])[:, 1]
    return prob.reshape(ds.sizes["time"], ds.sizes["latitude"], ds.sizes["longitude"])


def rule_mask(ds: xr.Dataset, variant: str) -> np.ndarray:
    """Máscara 0/1 por celda-hora de la regla A o B del lote (usa ``mucape`` del pronóstico)."""
    base = (ds["shear_01"].values >= SHEAR_MIN) & (ds["srh_01"].values <= SRH_MAX)
    if variant == "A":
        base = base & (ds["mucape"].values > 0)
    return base.astype(float)


def model_for_year(year: int, fold_models: dict[int, Pipeline], train_only: Pipeline) -> Pipeline:
    """Modelo *out-of-fold* para un año: el que excluyó ese año si está en train; si no, el de solo-train."""
    if year in TRAIN_YEARS and year in fold_models:
        return fold_models[year]
    return train_only  # 2024–2025 nunca vistos


def forecast_cells(
    forecasts: Path, feats: list[str], fold_models: dict[int, Pipeline], train_only: Pipeline
) -> tuple[dict[str, pd.DataFrame], int]:
    """Puntúa cada archivo de pronóstico con el modelo OOF de su año; añade las máscaras A/B.

    Devuelve ``({archivo: celdas_largas_con_model/A/B}, total_celda_horas)``. El año del archivo sale
    de su nombre (``aiwp_idx_panguweather_AAAAMMDDHH``).
    """
    files = sorted(glob.glob(str(forecasts / "aiwp_idx_panguweather_*.nc")))
    out: dict[str, pd.DataFrame] = {}
    total = 0
    for f in files:
        year = int(Path(f).stem.split("_")[-1][:4])
        model = model_for_year(year, fold_models, train_only)
        ds = xr.open_dataset(f, engine="h5netcdf")
        base = cells_long(ds, score_grid(ds, model, feats)).rename(columns={"value": "model"})
        base["A"] = cells_long(ds, rule_mask(ds, "A"))["value"].to_numpy()
        base["B"] = cells_long(ds, rule_mask(ds, "B"))["value"].to_numpy()
        base["year"] = year
        out[f] = base
        total += ds.sizes["time"] * ds.sizes["latitude"] * ds.sizes["longitude"]
    return out, total


def matched_threshold(cells: dict[str, pd.DataFrame], target_frac: float) -> float:
    """Umbral del modelo que marca ``target_frac`` de las celda-horas, por la distribución de scores.

    Se elige con la distribución de puntuaciones *out of fold* de todas las celdas (sin NaN), **sin
    mirar los eventos**: el cuantil que deja ``target_frac`` de la masa por encima.
    """
    scores = np.concatenate([c["model"].to_numpy() for c in cells.values()])
    scores = scores[np.isfinite(scores)]
    if scores.size == 0:
        return 1.0
    return float(np.quantile(scores, 1.0 - target_frac))


def flagged_fraction(
    cells: dict[str, pd.DataFrame], column: str, threshold: float, total: int
) -> float:
    """Fracción de celda-horas marcadas de ``column`` (``model`` por umbral; ``A``/``B`` por ==1)."""
    if column == "model":
        n = sum(int((c["model"] >= threshold).sum()) for c in cells.values())
    else:
        n = sum(int((c[column] >= 0.5).sum()) for c in cells.values())
    return n / total if total else float("nan")


def caught(event: pd.Series, cells: dict[str, pd.DataFrame], column: str, threshold: float) -> bool:
    """¿Captura el evento? Celda marcada de ``column`` a ≤ 50 km y ±6 h (criterio del lote)."""
    lo = event["time"] - pd.Timedelta(hours=DT_HOURS)
    hi = event["time"] + pd.Timedelta(hours=DT_HOURS)
    for c in cells.values():
        flag = (c["model"] >= threshold) if column == "model" else (c[column] >= 0.5)
        win = c[flag & (c["time"] >= lo) & (c["time"] <= hi)]
        if win.empty:
            continue
        d = kpimod.haversine(
            event["lat"], event["lon"], win["latitude"].to_numpy(), win["longitude"].to_numpy()
        )
        if np.any(d <= R_KM):
            return True
    return False


def pod_block(
    events: pd.DataFrame, cells: dict, column: str, threshold: float
) -> dict[str, object]:
    """POD con Wilson de un subconjunto de eventos para una fuente a un umbral dado."""
    if events.empty:
        return {"k": 0, "n": 0, "pod": float("nan"), "low": float("nan"), "high": float("nan")}
    k = int(sum(caught(e, cells, column, threshold) for _, e in events.iterrows()))
    n = len(events)
    low, high = kpimod.wilson_interval(k, n)
    return {"k": k, "n": n, "pod": k / n, "low": low, "high": high}


def _fmt(b: dict[str, object]) -> str:
    """Formatea un bloque POD como ``k/n = pct [low–high]``."""
    if b["n"] == 0:
        return "0/0 (sin eventos)"
    return f"{b['k']}/{b['n']} = {b['pod']:.0%} [{b['low']:.0%}–{b['high']:.0%}]"


def ef_rank(v: object) -> int:
    """Número de la escala EF (0, 1, …) o −1 si no hay dato."""
    s = "" if v is None or (isinstance(v, float) and v != v) else str(v)
    return next((int(ch) for ch in s if ch.isdigit()), -1)


def write_report(
    path: Path, csv_path: Path, ev: pd.DataFrame, cells: dict, total: int, meta: dict
) -> None:
    """Escribe el informe: POD out-of-fold por regla de área igualada, split por años, desgloses y anexo."""
    in_tr = ev[ev["year"].isin(list(TRAIN_YEARS))]
    unseen = ev[~ev["year"].isin(list(TRAIN_YEARS))]
    rules = {
        "A": {"frac": 0.0107, "label": "Regla A (con CAPE) · 1,07 %"},
        "B": {"frac": 0.1074, "label": "Regla B (sin CAPE) · 10,74 %"},
    }
    thr = {r: matched_threshold(cells, rules[r]["frac"]) for r in rules}

    lines = ["# Evaluación del modelo sobre el pronóstico AIWP (sin fuga, área igualada)\n"]
    lines.append(
        f"Modelo **{meta['model']}** · features {meta['features']} (AIWP-safe: "
        f"{'sí' if meta['aiwp_safe'] else 'no'}). Eventos 2021–2023 puntuados *out of fold* (modelo "
        f"que excluyó su año); 2024–2025 con el modelo de solo-train (nunca vistos). Criterio del "
        f"lote: celda marcada a ≤ 50 km y ±6 h. Umbral del modelo igualado al área de cada regla, "
        f"elegido por la distribución de scores (sin mirar eventos).\n"
    )
    lines.append("## POD por evento con área igualada a cada regla\n")
    lines.append(
        "| comparación (área) | umbral modelo | fracción modelo | POD modelo | POD regla |"
    )
    lines.append("|---|---|---|---|---|")
    for r in ("A", "B"):
        fm = flagged_fraction(cells, "model", thr[r], total)
        mod = pod_block(ev, cells, "model", thr[r])
        rule = pod_block(ev, cells, r, 0.5)
        lines.append(
            f"| vs {rules[r]['label']} | {thr[r]:.3f} | {fm:.2%} | {_fmt(mod)} | {_fmt(rule)} |"
        )
    lines.append("")
    lines.append("## Split: años de entrenamiento (OOF) vs 2024–2025 (nunca vistos)\n")
    lines.append(
        "| conjunto | n | POD modelo @área A | POD modelo @área B | POD regla A | POD regla B |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name, sub in (
        ("2021–2023 (OOF)", in_tr),
        ("2024–2025 (nunca vistos)", unseen),
        ("todos", ev),
    ):
        lines.append(
            f"| {name} | {len(sub)} | {_fmt(pod_block(sub, cells, 'model', thr['A']))} | "
            f"{_fmt(pod_block(sub, cells, 'model', thr['B']))} | "
            f"{_fmt(pod_block(sub, cells, 'A', 0.5))} | {_fmt(pod_block(sub, cells, 'B', 0.5))} |"
        )
    lines.append("")
    lines.append("## Desglose (área igualada a regla B)\n")
    lines.append("| subconjunto | POD modelo | POD regla B |")
    lines.append("|---|---|---|")
    ranks = ev["ef"].map(ef_rank)
    subsets = {
        "tornado": ev[ev["kind"].str.contains("tornado", na=False)],
        "tromba": ev[ev["kind"].str.contains("tromba", na=False)],
        "EF0": ev[ranks == 0],
        "EF1+": ev[ranks >= 1],
    }
    for label, sub in subsets.items():
        lines.append(
            f"| {label} | {_fmt(pod_block(sub, cells, 'model', thr['B']))} | {_fmt(pod_block(sub, cells, 'B', 0.5))} |"
        )
    lines.append("")
    lines.append("## Captura por evento (área igualada a regla B)\n")
    lines.append("| evento | año | tipo | EF | modelo | A | B |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, e in ev.iterrows():
        oof = "OOF" if e["year"] in TRAIN_YEARS else "nuevo"
        m = "sí" if caught(e, cells, "model", thr["B"]) else "no"
        ca = "sí" if caught(e, cells, "A", 0.5) else "no"
        cb = "sí" if caught(e, cells, "B", 0.5) else "no"
        lines.append(
            f"| {e['name']} ({oof}) | {e['year']} | {e['kind']} | {e['ef'] or '—'} | {m} | {ca} | {cb} |"
        )
    lines.append("")
    an: Any = meta.get("analyses")
    if an is not None:
        nd: dict[Any, Any] = an["null"]
        patches: dict[Any, Any] = an["patches"]

        def _null_row(label: str, crit: str, scope: str) -> str:
            """Fila de la tabla de nulo: observada, nula (media y 5–95 %), exceso y valor-p."""
            r = nd[(label, crit, scope)]
            return (
                f"| {label} | {r['observed']:.0%} ({r['obs_k']}/{r['obs_n']}) | "
                f"{r['null_mean']:.0%} [{r['null_lo']:.0%}–{r['null_hi']:.0%}] | "
                f"{r['excess']:+.0%} | {r['pvalue']:.3f} |"
            )

        lines.append("## Baseline nulo por permutación (50 km / ±6 h)\n")
        lines.append(
            "Cada evento se evalúa contra los flag-maps de **cada otro** run (misma estructura espacial "
            "y tasa de marcado, alineado por lead_h, pero sin el vínculo real). El exceso = observada − "
            "nula; valor-p de una cola. A 10,74 % de área el nulo es alto por diseño: lo que importa es "
            "el exceso.\n"
        )
        for scope in ("todos", "2024-25"):
            lines.append(f"**{scope}**\n")
            lines.append("| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |")
            lines.append("|---|---|---|---|---|")
            for label in ("modelo@A", "modelo@B", "regla A", "regla B"):
                lines.append(_null_row(label, "50km/±6h", scope))
            lines.append("")

        lines.append("## Estructura espacial (por paso, a cada umbral)\n")
        lines.append("| fuente | parches/paso (media) | tamaño medio de parche (celdas) |")
        lines.append("|---|---|---|")
        for label in ("modelo@A", "modelo@B", "regla A", "regla B"):
            npatch, size = patches[label]
            lines.append(f"| {label} | {npatch:.1f} | {size:.1f} |")
        lines.append("")

        lines.append("## Robustez — criterio estricto (25 km, paso más cercano)\n")
        for scope in ("todos", "2024-25"):
            lines.append(f"**{scope}**\n")
            lines.append("| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |")
            lines.append("|---|---|---|---|---|")
            for label in ("modelo@A", "modelo@B", "regla A", "regla B"):
                lines.append(_null_row(label, "25km/paso", scope))
            lines.append("")

    lines.append("## Anexo — barrido de umbral (elegido a posteriori, NO es un resultado)\n")
    lines.append(
        "Solo para ver la sensibilidad; el umbral se escoge mirando el resultado, así que no es honesto.\n"
    )
    lines.append("| umbral | fracción marcada | POD modelo (todos, OOF) |")
    lines.append("|---|---|---|")
    for t in SWEEP:
        lines.append(
            f"| {t} | {flagged_fraction(cells, 'model', t, total):.2%} | {_fmt(pod_block(ev, cells, 'model', t))} |"
        )
    lines.append("")
    lines.append("## Advertencias\n")
    lines.append(
        "- Sin fuga: 2021–2023 out-of-fold, 2024–2025 con el modelo de solo-train (no vio esos años)."
    )
    lines.append(
        "- Umbral del modelo igualado al área de cada regla por la distribución de scores, no por los eventos."
    )
    lines.append(
        f"- n = {len(ev)} eventos (OOF: {len(in_tr)}, nunca vistos: {len(unseen)}); Wilson ancho."
    )
    lines.append(
        "- Pangu (13 niveles) subestima la MUCAPE HSLC: por eso las features/reglas con CAPE fallan."
    )
    lines.append(f"- CSV por evento: `{csv_path.name}`.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Punto de entrada: puntúa el pronóstico sin fuga, iguala el área y escribe informe + CSV."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--model", type=Path, default=common.ROOT / "modelo.joblib", help="bundle a evaluar"
    )
    p.add_argument(
        "--forecasts", type=Path, default=Path("/tmp/aiwp_output"), help="carpeta de aiwp_idx_*.nc"
    )
    p.add_argument("--force", action="store_true", help="rehace las salidas si ya existen")
    a = p.parse_args()

    report = common.ROOT / "reports" / "aiwp_bundle_eval.md"
    csv_path = common.ROOT / "reports" / "aiwp_bundle_eval.csv"
    if report.exists() and not a.force:
        print(f"ya existe {report.name}; usa --force para rehacer", flush=True)
        return
    if not a.model.exists():
        raise SystemExit(f"no existe {a.model}; entrena el modelo antes")

    bundle = joblib.load(a.model)
    feats = bundle["features"]
    kind = bundle["metadata"].get("model", "forest")
    region = bundle["metadata"].get("region", "south-central")
    catalog = pd.read_csv(common.DATA / "catalog_clean.csv")
    df = pd.read_parquet(
        common.DATA
        / "dataset"
        / region
        / f"dataset_lead{bundle['metadata'].get('lead_h', 0)}h.parquet"
    )

    print("ajustando modelos LOYO por año (sin fuga)…", flush=True)
    fold_models, train_only = tr.fit_fold_models(df, feats, kind)
    events = batch_events(catalog)
    cells, total = forecast_cells(a.forecasts, feats, fold_models, train_only)

    report.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    thr_b = matched_threshold(cells, 0.1074)
    thr_a = matched_threshold(cells, 0.0107)
    for _, e in events.iterrows():
        rows.append(
            {
                "name": e["name"],
                "time": e["time"],
                "year": e["year"],
                "kind": e["kind"],
                "ef": e["ef"],
                "oof": e["year"] in TRAIN_YEARS,
                "caught_model_areaA": caught(e, cells, "model", thr_a),
                "caught_model_areaB": caught(e, cells, "model", thr_b),
                "caught_A": caught(e, cells, "A", 0.5),
                "caught_B": caught(e, cells, "B", 0.5),
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    # Baseline nulo, estructura espacial y robustez (criterio estricto 25 km, paso más cercano).
    print("construyendo mapas 2D y baseline nulo por permutación…", flush=True)
    grids = grid_maps(a.forecasts, feats, fold_models, train_only)
    unseen = events[~events["year"].isin(list(TRAIN_YEARS))]
    analyses: dict[str, Any] = {
        "thr_a": thr_a,
        "thr_b": thr_b,
        "null": {},  # (fuente, umbral, criterio, conjunto) -> dict del nulo
        "patches": {},  # (fuente, umbral) -> (n_parches, tamaño)
    }
    srcs = [
        ("model", thr_a, "modelo@A"),
        ("model", thr_b, "modelo@B"),
        ("A", 0.5, "regla A"),
        ("B", 0.5, "regla B"),
    ]
    nd: dict[Any, Any] = analyses["null"]
    for col, thr, label in srcs:
        nd[(label, "50km/±6h", "todos")] = permutation_null(events, grids, col, thr)
        nd[(label, "50km/±6h", "2024-25")] = permutation_null(unseen, grids, col, thr)
        nd[(label, "25km/paso", "todos")] = permutation_null(
            events, grids, col, thr, r_km=25.0, nearest_only=True
        )
        nd[(label, "25km/paso", "2024-25")] = permutation_null(
            unseen, grids, col, thr, r_km=25.0, nearest_only=True
        )
        analyses["patches"][label] = patch_stats(grids, col, thr)  # type: ignore[index]

    write_report(
        report,
        csv_path,
        events,
        cells,
        total,
        {
            "model": kind,
            "features": bundle["metadata"].get("feature_set"),
            "aiwp_safe": bundle["metadata"].get("aiwp_safe"),
            "analyses": analyses,
        },
    )
    mA = pod_block(events, cells, "model", thr_a)
    mB = pod_block(events, cells, "model", thr_b)
    print(
        f"área A ({thr_a:.3f}): modelo {_fmt(mA)} vs A {_fmt(pod_block(events, cells, 'A', 0.5))}",
        flush=True,
    )
    print(
        f"área B ({thr_b:.3f}): modelo {_fmt(mB)} vs B {_fmt(pod_block(events, cells, 'B', 0.5))}",
        flush=True,
    )
    print(f"informe → {report} · csv → {csv_path.name}", flush=True)


# ------------------------------------------------------------------------------------------------
# Baseline nulo por permutación, estructura espacial y robustez (criterio más estricto).
# A 10,74 % de área, el criterio 50 km/±6 h da ~30 celda-horas de oportunidad por evento, así que
# marcas al azar capturarían casi todo. El nulo mide cuánto de la POD observada es señal real.
# ------------------------------------------------------------------------------------------------


def grid_maps(
    forecasts: Path, feats: list[str], fold_models: dict[int, Pipeline], train_only: Pipeline
) -> dict[str, dict]:
    """Mapas 2D por archivo y por paso: scores del modelo (OOF) y máscaras A/B, con init y lat/lon.

    Devuelve ``{archivo: {init, lat, lon, steps:{lead_h:{model,A,B}}}}``. Base para el nulo (alinear
    por valor de ``lead_h``) y para las estadísticas de parches espaciales.
    """
    out: dict[str, dict] = {}
    for f in sorted(glob.glob(str(forecasts / "aiwp_idx_panguweather_*.nc"))):
        year = int(Path(f).stem.split("_")[-1][:4])
        model = model_for_year(year, fold_models, train_only)
        ds = xr.open_dataset(f, engine="h5netcdf")
        t = pd.to_datetime(ds["time"].values)
        leads = [int(x) for x in np.ravel(ds["lead_h"].values)]
        sc = score_grid(ds, model, feats)
        ma, mb = rule_mask(ds, "A"), rule_mask(ds, "B")
        steps = {
            leads[i]: {"model": sc[i], "A": ma[i], "B": mb[i]} for i in range(ds.sizes["time"])
        }
        out[f] = {
            "init": t.min(),
            "lat": ds["latitude"].values,
            "lon": ds["longitude"].values,
            "year": year,
            "steps": steps,
        }
    return out


def _event_window_steps(event: pd.Series, run: dict, tol_h: int) -> list[int]:
    """Valores de ``lead_h`` del ``run`` dentro de ±``tol_h`` del desfase del evento desde el init."""
    off = (event["time"] - run["init"]) / pd.Timedelta(hours=1)
    return [lh for lh in run["steps"] if abs(lh - off) <= tol_h]


def _flag_at(run: dict, lead_h: int, column: str, thr: float) -> np.ndarray:
    """Máscara booleana 2D de celdas marcadas de ``column`` en el paso ``lead_h`` del ``run``."""
    g = run["steps"][lead_h][column]
    return (g >= thr) if column == "model" else (g >= 0.5)


def _hit_in_run(
    event: pd.Series,
    run: dict,
    steps: list[int],
    column: str,
    thr: float,
    r_km: float,
    nearest_only: bool,
) -> bool:
    """¿Captura el evento con las marcas de ``run`` en ``steps`` (celda a ≤ r_km de su posición)?"""
    if nearest_only and steps:
        off = (event["time"] - run["init"]) / pd.Timedelta(hours=1)
        steps = [min(steps, key=lambda lh: abs(lh - off))]
    LA, LO = np.meshgrid(run["lat"], run["lon"], indexing="ij")
    for lh in steps:
        if lh not in run["steps"]:
            continue
        flag = _flag_at(run, lh, column, thr)
        if not flag.any():
            continue
        d = kpimod.haversine(event["lat"], event["lon"], LA[flag], LO[flag])
        if np.any(d <= r_km):
            return True
    return False


def observed_pod(
    events: pd.DataFrame,
    grids: dict,
    column: str,
    thr: float,
    r_km: float = R_KM,
    nearest_only: bool = False,
) -> dict[str, Any]:
    """POD observada: cada evento contra su propio run (la asociación verdadera)."""
    files = list(grids)
    k = n = 0
    for _, e in events.iterrows():
        own = next((f for f in files if _event_window_steps(e, grids[f], 6)), None)
        if own is None:
            continue
        n += 1
        steps = _event_window_steps(e, grids[own], 6 if not nearest_only else 6)
        k += int(_hit_in_run(e, grids[own], steps, column, thr, r_km, nearest_only))
    low, high = kpimod.wilson_interval(k, n)
    return {"k": k, "n": n, "pod": (k / n if n else float("nan")), "low": low, "high": high}


def permutation_null(
    events: pd.DataFrame,
    grids: dict,
    column: str,
    thr: float,
    r_km: float = R_KM,
    nearest_only: bool = False,
) -> dict[str, Any]:
    """Nulo por permutación: cada evento contra los flag-maps de **cada otro** run, alineado por lead_h.

    Mantiene la estructura espacial y la tasa de marcado de cada método, pero rompe el vínculo con el
    evento. Para cada run alternativo se usan los pasos de ``lead_h`` que caían en la ventana ±6 h del
    evento en su run real, en la posición (lat/lon) real del evento. Devuelve la POD nula media y el
    rango 5–95 % sobre runs, más el valor-p de permutación de una cola (fracción de permutaciones con
    POD ≥ la observada).
    """
    files = list(grids)
    own_of = {}
    for _, e in events.iterrows():
        own_of[e["name"]] = next((f for f in files if _event_window_steps(e, grids[f], 6)), None)
    obs = observed_pod(events, grids, column, thr, r_km, nearest_only)

    # Para cada permutación global (desplazar el emparejamiento evento→run), POD media sobre eventos.
    perm_pods = []
    ge = 0  # cuántas permutaciones igualan o superan la observada
    for shift in range(1, len(files)):
        k = n = 0
        for _, e in events.iterrows():
            own = own_of[e["name"]]
            if own is None:
                continue
            other = files[(files.index(own) + shift) % len(files)]
            # pasos de la ventana del evento (en su run real) reusados por valor de lead_h en el otro run.
            steps = _event_window_steps(e, grids[own], 6)
            n += 1
            k += int(_hit_in_run(e, grids[other], steps, column, thr, r_km, nearest_only))
        if n:
            perm_pods.append(k / n)
            if (k / n) >= float(obs["pod"]):
                ge += 1
    arr = np.array(perm_pods) if perm_pods else np.array([float("nan")])
    pval = (ge + 1) / (len(perm_pods) + 1) if perm_pods else float("nan")
    return {
        "observed": obs["pod"],
        "obs_k": obs["k"],
        "obs_n": obs["n"],
        "null_mean": float(np.nanmean(arr)),
        "null_lo": float(np.nanpercentile(arr, 5)),
        "null_hi": float(np.nanpercentile(arr, 95)),
        "excess": float(obs["pod"]) - float(np.nanmean(arr)),
        "pvalue": pval,
    }


def patch_stats(grids: dict, column: str, thr: float) -> tuple[float, float]:
    """Parches conectados marcados por paso (media) y tamaño medio de parche (celdas) de una fuente."""
    from scipy.ndimage import label

    n_patches, sizes = [], []
    for run in grids.values():
        for lh in run["steps"]:
            flag = _flag_at(run, lh, column, thr)
            lab, n = label(flag)  # type: ignore[misc]
            n_patches.append(n)
            if n:
                sizes.extend(int((lab == i).sum()) for i in range(1, n + 1))
    mean_patches = float(np.mean(n_patches)) if n_patches else float("nan")
    mean_size = float(np.mean(sizes)) if sizes else float("nan")
    return mean_patches, mean_size


if __name__ == "__main__":
    main()
