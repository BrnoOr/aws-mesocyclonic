#!/usr/bin/env python3
"""Regla de decisión fijada de antemano (docs/claude/design.md §8, requirements R5).

Lee ``cv_report.csv`` y la regla de ``config/model_selection.yaml`` y elige el modelo:

- **Elegible** si supera a M0 en PR-AUC y si, con POD ≥ objetivo, su FAR ≤ FAR(M1).
- Entre los elegibles, el **más simple** cuyo FAR esté a menos de un error estándar (bootstrap) del
  mejor, con el orden M2 < M3 < M4.
- Si ninguno es elegible, elige M1.

Escribe ``data/outputs/decision_<corte>.md``.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as features_mod  # noqa: E402

import common  # noqa: E402


def decide(rep: pd.DataFrame, cfg: dict) -> tuple[str, str]:
    """Aplica la regla y devuelve (modelo_elegido, razón en una línea)."""
    dec = cfg["decision"]
    pod_obj = dec["pod_objetivo"]
    orden = dec["orden_simplicidad"]
    by = {r["modelo"]: r for _, r in rep.iterrows()}

    pr_auc_m0 = by["M0"]["PR_AUC"] if "M0" in by else 0.0
    far_m1 = by["M1"]["FAR"] if "M1" in by else float("inf")

    elegibles = []
    for m in orden:
        if m not in by:
            continue
        r = by[m]
        supera_m0 = pd.notna(r["PR_AUC"]) and r["PR_AUC"] > pr_auc_m0
        pod_ok = pd.notna(r["POD"]) and r["POD"] >= pod_obj
        far_ok = pd.notna(r["FAR"]) and r["FAR"] <= far_m1 + dec["elegible"]["far_max_vs_m1"]
        if supera_m0 and pod_ok and far_ok:
            elegibles.append(m)

    if not elegibles:
        return dec["si_ninguno"], (
            f"Ningún modelo elegible (ninguno supera M0 en PR-AUC con POD≥{pod_obj:.0%} "
            f"y FAR≤FAR(M1)={far_m1:.2f}); se elige {dec['si_ninguno']}."
        )

    # Mejor FAR entre elegibles y desempate por un error estándar hacia el más simple.
    far_elig = {m: by[m]["FAR"] for m in elegibles}
    mejor = min(far_elig, key=lambda m: far_elig[m])
    se = by[mejor].get("dFAR_se", 0.0) or 0.0
    umbral_far = far_elig[mejor] + se
    for m in orden:  # orden de simplicidad
        if m in elegibles and far_elig[m] <= umbral_far:
            return m, (
                f"{m} elegido: FAR={far_elig[m]:.2f} dentro de 1 EE ({se:.2f}) del mejor "
                f"({mejor}, FAR={far_elig[mejor]:.2f}), POD={by[m]['POD']:.0%}, "
                f"PR-AUC={by[m]['PR_AUC']:.3f} > M0 ({pr_auc_m0:.3f})."
            )
    return mejor, f"{mejor} elegido por mejor FAR entre elegibles ({far_elig[mejor]:.2f})."


def to_markdown(rep: pd.DataFrame, elegido: str, razon: str, corte: str, cfg: dict) -> str:
    """Arma el documento decision_<corte>.md con la tabla y la decisión."""
    cols = [
        "modelo",
        "POD",
        "FAR",
        "dias_por_deteccion",
        "PR_AUC",
        "eventos",
        "detectados",
        "alertas",
        "dFAR_vs_M1",
        "dFAR_se",
    ]
    cols = [c for c in cols if c in rep.columns]
    t = rep[cols].copy()
    for c in ("POD", "FAR", "PR_AUC", "dias_por_deteccion", "dFAR_vs_M1", "dFAR_se"):
        if c in t.columns:
            t[c] = t[c].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
    lines = [
        f"# Decisión de modelo — corte `{corte}`",
        "",
        f"Configuración: versión `{cfg['version']}`. Regla fijada antes de validar (R5.1).",
        "",
        "## Resultados de validación cruzada (año-fuera 2018–2024, acierto tolerante)",
        "",
        _df_to_md(t),
        "",
        f"## Modelo elegido: **{elegido}**",
        "",
        razon,
        "",
        "> El FAR se mide sobre días de evento y de control, por lo que sobrestima el real.",
        f"> Metas del proyecto: POD ≥ {cfg['metas']['pod_min']:.0%}, FAR ≤ {cfg['metas']['far_max']:.0%}, "
        f"≤ {cfg['metas']['dias_por_deteccion_max']:.0f} días por detección.",
    ]
    return "\n".join(lines)


def _df_to_md(t: pd.DataFrame) -> str:
    """Tabla markdown simple sin depender de ``tabulate``."""
    cols = list(t.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in t.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def main() -> None:
    """Punto de entrada: decide para un corte y escribe decision_<corte>.md."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corte", choices=["dia", "12utc", "00utc"], default="dia")
    p.add_argument("--data-root", default=None)
    a = p.parse_args()

    import store

    cfg = features_mod.load_config()
    root = store.default_root(a.data_root, common.ROOT / "data")
    data_store = store.Store.at(root)
    rep_file = data_store.child("outputs", "cv_report.csv")
    assert rep_file.exists(), f"falta {rep_file.root} (corre cv.py --corte {a.corte})"
    rep_all = pd.read_csv(
        rep_file.fs.open(rep_file.root, "rb") if rep_file.is_s3 else rep_file.root
    )
    rep = rep_all[rep_all["corte"] == a.corte].reset_index(drop=True)

    elegido, razon = decide(rep, cfg)
    md = to_markdown(rep, elegido, razon, a.corte, cfg)
    out = data_store.child("outputs", f"decision_{a.corte}.md")
    if out.is_s3:
        with out.fs.open(out.root, "w") as f:
            f.write(md)
    else:
        Path(out.root).parent.mkdir(parents=True, exist_ok=True)
        Path(out.root).write_text(md, encoding="utf-8")
    print(f"elegido para {a.corte}: {elegido}", flush=True)
    print(razon, flush=True)
    print(f"-> {out.root}", flush=True)


if __name__ == "__main__":
    main()
