#!/usr/bin/env python3
"""Entrena y evalúa el clasificador de celdas mesociclónicas con KPIs por evento y por día.

Flujo (ver ``docs/mesociclones_chile.md`` §6 y la diapositiva de KPIs del desafío):

1. Carga un parquet de ``data/dataset/<región>/`` y arma **grupos por brote** (``validation.event_ids``,
   24 h de hueco): el 30–31 de mayo de 2019 o el 25–27 de junio de 2023 son un solo grupo, no tres.
2. **Excluye el caso de desarrollo** (30–31 mayo 2019) del ajuste y de la validación (``development_mask``).
3. Selección de modelo con **un año fuera por iteración (LOYO)** sobre ``train`` (2018–2023), que
   produce probabilidades *out-of-fold* sin fuga. Con ellas se elige el umbral por KPI.
4. Evalúa **una vez** en ``val`` (2024). ``test`` (2025) solo con ``--final``, con una advertencia de
   no ajustar nada ahí.
5. Compara el modelo contra las líneas base físicas (STP, SHERBS3, HSLC A/B) en las mismas métricas.

Las métricas por evento/día están en ``kpi.py``; las por celda (AUC-PR, Brier) en ``metrics.py``, y
se reportan como diagnóstico secundario y sesgado por PU.

El modelo guardado conserva el contrato ``{"model", "features", "metadata"}`` con ``predict_proba``,
para que la sección 8 del cuaderno AIWP lo siga aplicando al pronóstico.

Salida (salta lo existente salvo ``--force``)::

    modelo.joblib
    reports/train_<región>_lead<L>h.md
    reports/operating_curve_<región>_lead<L>h.csv

Uso::

    uv run python scripts/model/train.py --region south-central --lead 0 --model forest --features wind
    uv run python scripts/model/train.py --region south-central --lead 0 --final   # usa test, una vez
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))
import baselines as bl  # noqa: E402
import kpi as kpimod  # noqa: E402
import metrics as mx  # noqa: E402
import model_features as mf  # noqa: E402
import validation as vd  # noqa: E402

import common  # noqa: E402

MODELS = ("logistic", "forest")
POD_TARGET = 0.70  # KPI 1: objetivo de detección por evento
ALERTS_TARGET = 2.0  # KPI 3: objetivo de avisos por acierto
CURVE_THRESHOLDS = np.round(np.linspace(0.05, 0.95, 19), 3)


def build_estimator(kind: str) -> Pipeline:
    """Estimador según ``kind``; ambos exponen ``predict_proba`` (contrato de la sección 8).

    ``logistic``: imputa, estandariza y ajusta una regresión logística balanceada. ``forest``:
    *histogram gradient boosting*, capta umbrales no lineales (HSLC), tolera ``NaN`` y no escala.
    """
    if kind == "logistic":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, solver="lbfgs")),
            ]
        )
    if kind == "forest":
        return Pipeline(
            [
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        class_weight="balanced",
                        max_iter=300,
                        learning_rate=0.05,
                        max_leaf_nodes=15,
                        l2_regularization=1.0,
                        random_state=0,
                    ),
                )
            ]
        )
    raise ValueError(f"modelo desconocido: {kind!r}; usa uno de {MODELS}")


def _dates(df: pd.DataFrame) -> list[dt.date]:
    """Fechas (``datetime.date``) de cada fila del DataFrame."""
    return [d.date() for d in pd.to_datetime(df["date"])]


def _coverage_excluded(catalog: pd.DataFrame, label_hours: range) -> tuple[list[str], list[str]]:
    """Eventos usables del catálogo cuya hora cae fuera de ``label_hours`` (excluidos de la POD).

    Un evento es usable si reporta tornado/tromba y tiene hora y coordenada. Devuelve ``(uids,
    etiquetas)`` donde la etiqueta es ``uid fecha HHz`` para listarlos en el informe.
    """
    import features as dsfeat  # el módulo de scripts/dataset

    uids: list[str] = []
    labels: list[str] = []
    for _, r in catalog.iterrows():
        if not (dsfeat._is_one(r.get("tornado")) or dsfeat._is_one(r.get("waterspout"))):
            continue
        h = dsfeat.round_hour(r.get("hour_utc"))
        if h is None or h in label_hours:
            continue
        uids.append(str(r.get("uid", "")))
        labels.append(f"{r.get('uid', '')} {r.get('date', '')} {h:02d}z")
    return uids, labels


def outbreak_groups(df: pd.DataFrame) -> np.ndarray:
    """Grupo por brote de cada fila: días de un mismo brote comparten id; los demás, su fecha.

    Usa ``validation.event_ids`` (24 h de hueco) sobre las fechas presentes, de modo que un brote de
    varios días no se parta entre pliegues. Devuelve un arreglo de etiquetas de grupo alineado a ``df``.
    """
    dates = _dates(df)
    unique_days = sorted(set(dates))
    stamps = [dt.datetime(d.year, d.month, d.day) for d in unique_days]
    ids = vd.event_ids(stamps)
    day_to_group = {d: int(g) for d, g in zip(unique_days, ids, strict=True)}
    return np.array([day_to_group[d] for d in dates])


def event_table(cells: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Una fila por evento (``event_uid``) con su celda, hora, EF, tipo y confirmación.

    Toma del parquet la celda/hora de cada ``event_uid`` positivo y le une ``ef``/``kind`` del
    catálogo. Sirve para los KPIs por evento (no por celda).
    """
    pos = cells[(cells["label"] == 1) & (cells["event_uid"].astype(str) != "")]
    if pos.empty:
        return pd.DataFrame(columns=["event_uid", "lat", "lon", "hour_utc", "confirmed", "date"])
    ev = pos.groupby("event_uid", as_index=False).agg(
        lat=("lat", "mean"),
        lon=("lon", "mean"),
        hour_utc=("hour_utc", "first"),
        confirmed=("confirmed", "first"),
        date=("date", "first"),
    )
    cat = catalog[["uid", "ef", "kind"]].rename(columns={"uid": "event_uid"})
    return ev.merge(cat, on="event_uid", how="left")


def scored_cells(df: pd.DataFrame, prob: np.ndarray) -> pd.DataFrame:
    """DataFrame mínimo de celdas puntuadas para los KPIs: fecha, hora, lat/lon, ``day_kind`` y ``score``."""
    return pd.DataFrame(
        {
            "date": df["date"].to_numpy(),
            "hour_utc": df["hour_utc"].to_numpy(),
            "lat": df["lat"].to_numpy(),
            "lon": df["lon"].to_numpy(),
            "day_kind": df["day_kind"].to_numpy() if "day_kind" in df else "event",
            "score": prob,
        }
    )


def loyo_oof(
    x: pd.DataFrame, y: pd.Series, dates: list[dt.date], groups: np.ndarray, kind: str
) -> np.ndarray:
    """Probabilidades *out-of-fold* por LOYO sobre ``train``; ``nan`` donde una fila no se evaluó.

    Cada pliegue deja fuera un año y entrena con el resto, sin partir ningún brote (``groups``). El
    caso de desarrollo ya viene excluido antes de llamar aquí.
    """
    oof = np.full(len(y), np.nan)
    for fold in vd.leave_one_year_out(dates, groups, hold_out_development=False):
        est = build_estimator(kind)
        est.fit(x.iloc[fold.train], y.iloc[fold.train])
        oof[fold.test] = est.predict_proba(x.iloc[fold.test])[:, 1]
    return oof


def fit_fold_models(
    df: pd.DataFrame, feats: list[str], kind: str
) -> tuple[dict[int, Pipeline], Pipeline]:
    """Modelos para puntuar el pronóstico **sin fuga**: uno por año excluido y el de solo-train.

    Carga la partición ``train`` (sin el caso de desarrollo) y ajusta, por LOYO, un modelo que deja
    fuera cada año (``{año: modelo_sin_ese_año}``) para puntuar eventos de pronóstico de ese año *out
    of fold*. Además ajusta el modelo con todo ``train`` (2018–2023), que es el del *bundle* y el que
    puntúa los años nunca vistos (2024–2025). No toca ``val`` ni ``test``.
    """
    train = df[df["partition"] == "train"].copy()
    train = train[~vd.development_mask(_dates(train))]
    x, y = train[feats], train["label"].astype(int)
    dates = _dates(train)
    groups = outbreak_groups(train)

    fold_models: dict[int, Pipeline] = {}
    for fold in vd.leave_one_year_out(dates, groups, hold_out_development=False):
        est = build_estimator(kind)
        est.fit(x.iloc[fold.train], y.iloc[fold.train])
        fold_models[int(fold.year)] = est

    train_only = build_estimator(kind)
    train_only.fit(x, y)
    return fold_models, train_only


def nested_loyo_pod(
    train: pd.DataFrame, oof: np.ndarray, seen: np.ndarray, catalog: pd.DataFrame, target: str
) -> kpimod.Rate:
    """POD por evento con **selección anidada** del umbral (no optimista).

    Para cada año reservado se elige el umbral con las predicciones *out-of-fold* de **los demás
    años** (no del propio año reservado) y se aplica a los eventos de ese año. Al unir los eventos
    detectados de todos los años se obtiene una POD sin la ventaja de haber elegido el umbral sobre
    los mismos datos que se evalúan. Reutiliza el vector ``oof`` ya calculado (una pasada LOYO).
    """
    tr = train[seen].copy()
    tr["score"] = oof[seen]
    years = pd.to_datetime(tr["date"]).dt.year
    detected = 0
    total = 0
    for yr in sorted(years.unique()):
        inner = tr[years != yr]  # los demás años: eligen el umbral
        outer = tr[years == yr]  # el año reservado: se evalúa
        inner_cells = scored_cells(inner, inner["score"].to_numpy())
        inner_events = event_table(inner, catalog)
        if inner_events.empty:
            continue
        curve = operating_curve(inner_events, inner_cells)
        thr, _ = choose_threshold(curve, target)
        outer_cells = scored_cells(outer, outer["score"].to_numpy())
        outer_events = event_table(outer, catalog)
        r = kpimod.event_pod(outer_events, outer_cells, thr)
        if r.n:
            detected += r.k
            total += r.n
    low, high = kpimod.wilson_interval(detected, total)
    return kpimod.Rate(
        value=(detected / total if total else float("nan")),
        k=detected,
        n=total,
        low=low,
        high=high,
        computable=total > 0,
    )


def operating_curve(events: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """Tabla umbral → POD por evento, FAR por día y avisos por acierto, para el barrido de umbrales."""
    rows = []
    for thr in CURVE_THRESHOLDS:
        pod = kpimod.event_pod(events, cells, float(thr))
        far = kpimod.day_far(cells, events, float(thr))
        aph = kpimod.alerts_per_hit(cells, events, float(thr))
        rows.append(
            {
                "threshold": float(thr),
                "event_pod": pod.value,
                "day_far": far.value if far.computable else np.nan,
                "alerts_per_hit": aph,
            }
        )
    return pd.DataFrame(rows)


def choose_threshold(curve: pd.DataFrame, target: str) -> tuple[float, str]:
    """Elige el umbral según el KPI objetivo, a partir de la curva de operación LOYO.

    - ``pod``: el umbral **más alto** cuya POD por evento ≥ 0,70; si ninguno llega, el de POD máxima.
    - ``alerts``: el umbral **más bajo** con avisos por acierto ≤ 2; si no es computable, cae a ``pod``.
    """
    if target == "pod":
        ok = curve[curve["event_pod"] >= POD_TARGET]
        if not ok.empty:
            return float(ok["threshold"].max()), f"POD≥{POD_TARGET}"
        best = curve.sort_values("event_pod", ascending=False).iloc[0]
        return float(best["threshold"]), "POD máxima (no se alcanzó 0,70)"
    if target == "alerts":
        valid = curve.dropna(subset=["alerts_per_hit"])
        ok = valid[valid["alerts_per_hit"] <= ALERTS_TARGET]
        if not ok.empty:
            return float(ok["threshold"].min()), f"avisos/acierto≤{ALERTS_TARGET}"
        return choose_threshold(curve, "pod")
    raise ValueError(f"objetivo desconocido: {target!r}")


def kpi_row(events: pd.DataFrame, cells: pd.DataFrame, threshold: float) -> dict[str, Any]:
    """Fila de KPIs (POD evento, FAR día, avisos/acierto) de una fuente de puntuación a un umbral."""
    pod = kpimod.event_pod(events, cells, threshold)
    far = kpimod.day_far(cells, events, threshold)
    aph = kpimod.alerts_per_hit(cells, events, threshold)
    return {
        "pod": pod,
        "far": far,
        "alerts_per_hit": aph,
    }


def _fmt_rate(r: kpimod.Rate) -> str:
    """Formatea un ``Rate`` como ``valor [low–high] (k/n)`` o ``no computable``."""
    if not r.computable:
        return "no computable"
    return f"{r.value:.2f} [{r.low:.2f}–{r.high:.2f}] ({r.k}/{r.n})"


def _fmt_aph(v: float) -> str:
    """Formatea los avisos por acierto, o ``no computable`` si es ``nan``."""
    return "no computable" if (v is None or np.isnan(v)) else f"{v:.2f}"


def baseline_rows(events: pd.DataFrame, df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """KPIs de cada línea base física sobre las mismas celdas (umbral 0,5 sobre su pseudoprob 0/1)."""
    out: dict[str, dict[str, Any]] = {}
    for name in bl.BASELINES:
        cells = scored_cells(df, bl.score_baseline(name, df))
        out[name] = kpi_row(events, cells, 0.5)
    return out


def write_report(path: Path, ctx: dict[str, Any]) -> None:
    """Escribe el informe en español con la tabla de KPIs, desgloses y advertencias."""
    lines: list[str] = []
    lines.append(f"# Informe de entrenamiento — {ctx['region']} · lead {ctx['lead']} h\n")
    lines.append(
        f"Modelo: **{ctx['model']}** · features: **{ctx['features']}** "
        f"(AIWP-safe: {'sí' if ctx['aiwp_safe'] else 'no'}) · "
        f"umbral {ctx['threshold']:.3f} ({ctx['criterion']}).\n"
    )
    lines.append("## Reparto por partición\n")
    lines.append("| partición | filas | positivas | eventos | brotes |")
    lines.append("|---|---|---|---|---|")
    for p, s in ctx["splits"].items():
        lines.append(f"| {p} | {s['rows']} | {s['pos']} | {s['events']} | {s['groups']} |")
    lines.append("")
    lines.append("## KPIs: modelo vs líneas base vs objetivo\n")
    lines.append(
        "| KPI | objetivo | base | modelo (LOYO) | modelo (val) | STP | SHERBS3 | regla A | regla B |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    k = ctx["kpi"]
    lines.append(
        f"| POD por evento (≥0,70) | 0,70 | STP=0/7 (mayo 2019) | {_fmt_rate(k['loyo']['pod'])} | "
        f"{_fmt_rate(k['val']['pod'])} | {_fmt_rate(k['stp']['pod'])} | {_fmt_rate(k['sherbs3']['pod'])} | "
        f"{_fmt_rate(k['hslc_a']['pod'])} | {_fmt_rate(k['hslc_b']['pod'])} |"
    )
    lines.append(
        f"| FAR por día (≤0,50) | 0,50 | ≈0,70 | {_fmt_rate(k['loyo']['far'])} | "
        f"{_fmt_rate(k['val']['far'])} | {_fmt_rate(k['stp']['far'])} | {_fmt_rate(k['sherbs3']['far'])} | "
        f"{_fmt_rate(k['hslc_a']['far'])} | {_fmt_rate(k['hslc_b']['far'])} |"
    )
    lines.append(
        f"| Avisos por acierto (≤2) | 2 | ≈4 | {_fmt_aph(k['loyo']['alerts_per_hit'])} | "
        f"{_fmt_aph(k['val']['alerts_per_hit'])} | {_fmt_aph(k['stp']['alerts_per_hit'])} | "
        f"{_fmt_aph(k['sherbs3']['alerts_per_hit'])} | {_fmt_aph(k['hslc_a']['alerts_per_hit'])} | "
        f"{_fmt_aph(k['hslc_b']['alerts_per_hit'])} |"
    )
    lines.append("")
    lines.append("## Desglose de POD por evento (val)\n")
    lines.append("| subconjunto | POD |")
    lines.append("|---|---|")
    for name, r in ctx["breakdown"].items():
        lines.append(f"| {name} | {_fmt_rate(r)} |")
    lines.append("")
    lines.append("## Diagnósticos por celda (secundarios, sesgados por PU)\n")
    lines.append(f"- AUC-PR (LOYO, celda): {ctx['auc_pr']:.4f}")
    lines.append(f"- Brier (LOYO, celda): {ctx['brier']:.4f}")
    lines.append("")
    lines.append("## Advertencias\n")
    lines.append(
        "- **PU:** `label=0` es *sin reporte*, no negativo confirmado; el subregistro infla la FAR real."
    )
    lines.append(
        "- **n pequeño:** pocos eventos por partición; los intervalos de Wilson son anchos."
    )
    lines.append(f"- **Curva de operación:** ver `{ctx['curve_csv']}`.")
    for note in ctx.get("notes", []):
        lines.append(f"- {note}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def split_frames(df: pd.DataFrame, feats: list[str]) -> dict[str, dict[str, Any]]:
    """Resumen por partición: filas, positivas, eventos y brotes (para el informe y el hash)."""
    out: dict[str, dict[str, Any]] = {}
    for part, g in df.groupby("partition"):
        pos = g[g["label"] == 1]
        uids = pos.loc[pos["event_uid"].astype(str) != "", "event_uid"]
        out[str(part)] = {
            "rows": int(len(g)),
            "pos": int((g["label"] == 1).sum()),
            "events": int(uids.nunique()),
            "groups": int(pd.Series(outbreak_groups(g)).nunique()),
        }
    return out


def main() -> None:
    """Punto de entrada: entrena, elige umbral por KPI, evalúa en val (y test con --final) y reporta."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--region", default="south-central-austral", help="región del dataset")
    p.add_argument("--lead", type=int, default=0, choices=(0, 1, 3, 6), help="anticipación (h)")
    p.add_argument("--model", choices=MODELS, default="forest", help="logistic o forest")
    p.add_argument("--features", choices=mf.FEATURE_SETS, default="wind", help="era5, wind o all")
    p.add_argument(
        "--target", choices=("pod", "alerts"), default="pod", help="KPI que fija el umbral"
    )
    p.add_argument(
        "--pu", choices=("none", "elkan-noto"), default="none", help="anexo de calibración PU"
    )
    p.add_argument(
        "--final", action="store_true", help="evalúa test (2025); solo tras congelar todo"
    )
    p.add_argument("--force", action="store_true", help="rehace salidas que ya existen")
    p.add_argument(
        "--out", type=Path, default=common.ROOT / "modelo.joblib", help="ruta del modelo"
    )
    a = p.parse_args()

    data_file = common.DATA / "dataset" / a.region / f"dataset_lead{a.lead}h.parquet"
    if not data_file.exists():
        raise SystemExit(f"no existe {data_file}; corre build_dataset.py antes")
    report_dir = common.ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"train_{a.region}_lead{a.lead}h.md"
    curve_file = report_dir / f"operating_curve_{a.region}_lead{a.lead}h.csv"
    if report_file.exists() and a.out.exists() and not a.force:
        print(f"ya existen {report_file.name} y {a.out.name}; usa --force para rehacer", flush=True)
        return

    feats = mf.feature_names(a.features)
    mf.check_not_forbidden(feats)
    df = pd.read_parquet(data_file)
    if any(f not in df.columns for f in feats):
        raise SystemExit(
            f"al parquet le faltan features: {[f for f in feats if f not in df.columns]}"
        )

    catalog = pd.read_csv(common.DATA / "catalog_clean.csv")
    cat_dates = [d.date() for d in pd.to_datetime(catalog["date"], errors="coerce").dropna()]

    # train sin el caso de desarrollo (development_mask); dev se reserva para comprobaciones cualitativas.
    train = df[df["partition"] == "train"].copy()
    dev_mask = vd.development_mask(_dates(train))
    train = train[~dev_mask]
    if train.empty:
        raise SystemExit("la partición train quedó vacía tras excluir el caso de desarrollo")

    notes: list[str] = []
    x_tr, y_tr = train[feats], train["label"].astype(int)
    dates_tr = _dates(train)
    groups_tr = outbreak_groups(train)
    loyo_years = sorted({d.year for d in dates_tr})
    n_event_days_train = len({d for d in cat_dates if d.year in loyo_years})

    print(
        f"{data_file.name}: train {len(train)} filas, {int(y_tr.sum())} positivas, "
        f"{pd.Series(groups_tr).nunique()} brotes · modelo {a.model} · features {a.features} ({len(feats)})",
        flush=True,
    )

    oof = loyo_oof(x_tr, y_tr, dates_tr, groups_tr, a.model)
    seen = ~np.isnan(oof)
    oof_cells = scored_cells(train[seen], oof[seen])
    oof_events = event_table(train[seen], catalog)

    curve = operating_curve(oof_events, oof_cells)
    threshold, criterion = choose_threshold(curve, a.target)
    print(curve.to_string(index=False), flush=True)
    print(f"umbral elegido: {threshold:.3f} ({criterion})", flush=True)

    # Diagnósticos por celda (secundarios), solo con filas evaluadas y positivos presentes.
    auc = (
        mx.auc_pr(y_tr.to_numpy()[seen], oof[seen])
        if int(y_tr.to_numpy()[seen].sum())
        else float("nan")
    )
    brier = mx.brier_score(y_tr.to_numpy()[seen], np.clip(oof[seen], 0, 1))

    kpi: dict[str, dict[str, Any]] = {}
    kpi["loyo"] = kpi_row(oof_events, oof_cells, threshold)

    # val (2024): se ajusta con todo train (sin dev) y se evalúa una vez.
    final_model = build_estimator(a.model)
    final_model.fit(x_tr, y_tr)
    val = df[df["partition"] == "val"].copy()
    if not val.empty:
        vprob = final_model.predict_proba(val[feats])[:, 1]
        vcells, vevents = scored_cells(val, vprob), event_table(val, catalog)
        kpi["val"] = kpi_row(vevents, vcells, threshold)
        breakdown = kpimod.breakdown_event_pod(vevents, vcells, threshold)
    else:
        kpi["val"] = kpi_row(pd.DataFrame(columns=oof_events.columns), oof_cells, threshold)
        breakdown = {}
        notes.append("no hay partición val (2024) en el dataset; KPIs de val vacíos.")

    # Líneas base sobre val (misma partición de comparación); si no hay val, sobre LOYO.
    base_df = val if not val.empty else train[seen]
    base_events = event_table(base_df, catalog)
    base_year = 2024 if not val.empty else max({d.year for d in dates_tr})
    n_event_days_base = (
        len({d for d in cat_dates if d.year == base_year}) if not val.empty else n_event_days_train
    )
    for name, row in baseline_rows(base_events, base_df).items():
        kpi[name] = row
        bcells = scored_cells(base_df, bl.score_baseline(name, base_df))
        pod_b = row["pod"].value
        sf = kpimod.season_rescaled_far(bcells, base_events, 0.5, pod_b, n_event_days_base)
        fa = kpimod.flagged_area(bcells, base_events, 0.5)
        season_txt = (
            f"FAR temporada≈{sf.far:.2f} [{sf.far_low:.2f}–{sf.far_high:.2f}], avisos/acierto≈{sf.alerts_per_hit:.2f}"
            if sf is not None
            else "FAR temporada no computable (sin controles)"
        )
        notes.append(
            f"Línea base {name}: POD evento {pod_b:.2f}; {season_txt}; "
            f"celda-horas marcadas {fa.frac_event:.2%} (evento)/{fa.frac_control:.2%} (control)."
        )

    # test solo con --final, con advertencia.
    if a.final:
        test = df[df["partition"] == "test"].copy()
        if not test.empty:
            tprob = final_model.predict_proba(test[feats])[:, 1]
            kpi["test"] = kpi_row(event_table(test, catalog), scored_cells(test, tprob), threshold)
            print(
                "ADVERTENCIA: test (2025) evaluado. No ajustes nada a partir de este número.",
                flush=True,
            )
            notes.append(
                "test (2025) evaluado con --final; usado solo para el número final, no para ajustar."
            )

    # Anexo PU (Elkan–Noto): c = media de la prob OOF en los positivos retenidos.
    pu_c = None
    if a.pu == "elkan-noto":
        pos_oof = oof[seen & (y_tr.to_numpy() == 1)]
        pu_c = float(np.mean(pos_oof)) if pos_oof.size else float("nan")
        notes.append(
            f"anexo PU Elkan–Noto: c≈{pu_c:.3f} (media de p en positivos retenidos). La prob "
            "calibrada p/c es solo anexo; no cambia el ordenamiento ni los KPIs y supone que la "
            "probabilidad de reporte es constante en espacio/tiempo (no lo es: población, hora, año)."
        )

    # KPI 2/3 reescalados a temporada (comparables con la base CR2): tasa de aviso en días de
    # control × días sin evento de la temporada. q descansa en pocos controles: indicativo.
    season = {}
    sf_loyo = kpimod.season_rescaled_far(
        oof_cells, oof_events, threshold, kpi["loyo"]["pod"].value, n_event_days_train
    )
    season["loyo"] = sf_loyo
    if not val.empty:
        n_event_days_2024 = len({d for d in cat_dates if d.year == 2024})
        season["val"] = kpimod.season_rescaled_far(
            vcells, vevents, threshold, kpi["val"]["pod"].value, n_event_days_2024
        )
    for scope, sf in season.items():
        if sf is not None:
            notes.append(
                f"FAR reescalada a temporada ({scope}): q={sf.q:.3f} "
                f"[{sf.q_low:.3f}–{sf.q_high:.3f}] sobre {sf.n_control} control(es) → "
                f"FAR≈{sf.far:.2f} [{sf.far_low:.2f}–{sf.far_high:.2f}], "
                f"avisos/acierto≈{sf.alerts_per_hit:.2f}. {sf.note}"
            )
        else:
            notes.append(
                f"FAR reescalada a temporada ({scope}): sin días de control, no computable."
            )

    # Item 2: área marcada (fracción de celda-horas en días de evento vs control, celdas por aviso).
    fa_loyo = kpimod.flagged_area(oof_cells, oof_events, threshold)
    notes.append(
        f"Área marcada (LOYO): celda-horas marcadas {fa_loyo.frac_event:.2%} en días de evento, "
        f"{fa_loyo.frac_control:.2%} en días de control; "
        f"≈{fa_loyo.mean_cells_per_alert_day:.0f} celdas marcadas por día de aviso."
    )

    # Item 3: cobertura. Eventos del catálogo fuera de la ventana horaria del dataset.
    hrs = sorted(int(h) for h in df["hour_utc"].unique())
    label_hours = range(min(hrs), max(hrs) + 1)
    out_lo, out_hi = _coverage_excluded(catalog, label_hours)
    notes.append(
        f"Cobertura: {len(out_lo)} evento(s) del catálogo con hora fuera de "
        f"{label_hours.start}–{label_hours.stop - 1} UTC quedan fuera de la POD. "
        f"Lista: {', '.join(out_hi) if out_hi else '—'}."
    )

    # Item 4: honestidad del umbral + selección anidada (no optimista).
    notes.append(
        "Honestidad del umbral: el umbral se elige y se reporta sobre las MISMAS predicciones "
        "out-of-fold de LOYO, así que la POD de LOYO es optimista. La selección anidada da la "
        "versión sin ese sesgo:"
    )
    nested = nested_loyo_pod(train, oof, seen, catalog, a.target)
    if nested.computable:
        notes.append(
            f"POD por evento con selección anidada: {nested.value:.2f} "
            f"[{nested.low:.2f}–{nested.high:.2f}] ({nested.k}/{nested.n})."
        )
    else:
        notes.append(
            "POD anidada no computable (faltan años con eventos para la selección interna)."
        )

    splits = split_frames(df, feats)
    curve.to_csv(curve_file, index=False)

    aiwp_safe = mf.is_aiwp_safe(feats)
    bundle = {
        "model": final_model,
        "features": feats,
        "metadata": {
            "region": a.region,
            "lead_h": a.lead,
            "model": a.model,
            "feature_set": a.features,
            "aiwp_safe": aiwp_safe,
            "groups": "outbreak (event_ids 24h)",
            "folds": "leave-one-year-out sobre train 2018-2023",
            "threshold": float(threshold),
            "criterion": criterion,
            "target": a.target,
            "pu_c": pu_c,
            "kpi_loyo": _kpi_meta(kpi["loyo"]),
            "kpi_val": _kpi_meta(kpi["val"]),
            "baselines": {n: _kpi_meta(kpi[n]) for n in bl.BASELINES if n in kpi},
            "dataset_hash": {p: {"rows": s["rows"], "pos": s["pos"]} for p, s in splits.items()},
            "cell_diagnostics": {"auc_pr": auc, "brier": brier},
        },
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, a.out)

    write_report(
        report_file,
        {
            "region": a.region,
            "lead": a.lead,
            "model": a.model,
            "features": a.features,
            "aiwp_safe": aiwp_safe,
            "threshold": threshold,
            "criterion": criterion,
            "splits": splits,
            "kpi": kpi,
            "breakdown": breakdown,
            "auc_pr": auc,
            "brier": brier,
            "curve_csv": curve_file.name,
            "notes": notes,
        },
    )
    print(
        f"modelo → {a.out.name} · informe → {report_file} · curva → {curve_file.name}", flush=True
    )


def _kpi_meta(row: dict[str, Any]) -> dict[str, Any]:
    """Serializa una fila de KPIs (POD, FAR, avisos/acierto) a tipos simples para los metadatos."""
    pod: kpimod.Rate = row["pod"]
    far: kpimod.Rate = row["far"]
    aph = row["alerts_per_hit"]
    return {
        "event_pod": {
            "value": pod.value,
            "k": pod.k,
            "n": pod.n,
            "low": pod.low,
            "high": pod.high,
            "computable": pod.computable,
        },
        "day_far": {
            "value": far.value,
            "k": far.k,
            "n": far.n,
            "computable": far.computable,
            "reason": far.reason,
        },
        "alerts_per_hit": None if (aph is None or np.isnan(aph)) else float(aph),
    }


if __name__ == "__main__":
    main()
