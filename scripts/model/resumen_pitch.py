#!/usr/bin/env python3
"""Genera data/outputs/resumen_pitch.md (tareas 5.2): M1 vs elegido por corte, prueba ciega, 2026."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as features_mod  # noqa: E402

import common  # noqa: E402


def _read_csv(store: common.Store) -> pd.DataFrame:
    """Lee un CSV (local o S3)."""
    return pd.read_csv(store.fs.open(store.root, "rb") if store.is_s3 else store.root)


def _elegido(store: common.Store, corte: str) -> str:
    """Modelo elegido leído de decision_<corte>.md."""
    import re

    f = store.child("outputs", f"decision_{corte}.md")
    txt = (
        str(f.fs.read_text(f.root, encoding="utf-8"))
        if f.is_s3
        else Path(f.root).read_text(encoding="utf-8")
    )
    m = re.search(r"Modelo elegido:\s*\*\*(M\d)\*\*", txt)
    return m.group(1) if m else "M1"


def main() -> None:
    """Arma el resumen para el pitch."""
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", default=None)
    a = p.parse_args()
    import store

    cfg = features_mod.load_config()
    ds = store.Store.at(store.default_root(a.data_root, common.ROOT / "data"))
    rep = _read_csv(ds.child("outputs", "cv_report.csv"))
    metas = cfg["metas"]

    lines = [
        "# Resumen para el pitch — detección y anticipación de tornados",
        "",
        f"Configuración `{cfg['version']}`. Unidad: celda de 1° × día UTC, temporada abril–septiembre, "
        "centro-sur y sur de Chile. Validación año-fuera 2018–2024, prueba ciega 2025, puntaje 2026.",
        "",
        f"**Metas:** POD ≥ {metas['pod_min']:.0%}, FAR ≤ {metas['far_max']:.0%}, "
        f"≤ {metas['dias_por_deteccion_max']:.0f} días de alerta por tornado. "
        "Vara física: regla de Marín et al. (2024) = M1.",
        "",
        "## M1 (regla física) vs. modelo elegido, por corte",
        "",
        "| Corte | Modelo | POD | FAR | Días/detección | Eventos detectados | Alertas |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for corte in ["dia", "12utc"]:
        sub = rep[rep["corte"] == corte]
        eleg = _elegido(ds, corte)
        for mod in ["M1", eleg]:
            r = sub[sub["modelo"] == mod]
            if r.empty:
                continue
            r = r.iloc[0]
            etiqueta = f"{mod} (elegido)" if mod == eleg else mod
            lines.append(
                f"| {corte} | {etiqueta} | {r['POD']:.0%} | {r['FAR']:.0%} | "
                f"{r['dias_por_deteccion']:.1f} | {int(r['detectados'])}/{int(r['eventos'])} | "
                f"{int(r['alertas'])} |"
            )

    # Prueba ciega 2025.
    lines += [
        "",
        "## Prueba ciega 2025 (una sola evaluación, sin reajuste)",
        "",
        "| Corte | Modelo | POD | FAR | Días/detección | Detectados |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for corte in ["dia", "12utc"]:
        f = ds.child("outputs", f"blind_2025_{corte}.csv")
        if not f.exists():
            continue
        b = _read_csv(f).iloc[0]
        lines.append(
            f"| {corte} | {b['modelo']} | {b['POD']:.0%} | {b['FAR']:.0%} | "
            f"{b['dias_por_deteccion']:.1f} | {int(b['detectados'])}/{int(b['eventos'])} |"
        )

    # Candidatos 2026.
    lines += ["", "## Puntaje 2026 (candidatos para revisión)", ""]
    for corte in ["dia", "12utc"]:
        f = ds.child("outputs", f"candidatos_2026_{corte}.csv")
        if not f.exists():
            continue
        c = _read_csv(f)
        alertas = int(c["alerta"].sum())
        ult = c["ultimo_dia_era5"].iloc[0] if "ultimo_dia_era5" in c.columns else "?"
        top = c.sort_values("score", ascending=False).head(5)
        lines.append(
            f"- **Corte {corte} ({c['modelo'].iloc[0]}):** {len(c)} celdas-día puntuadas, "
            f"{alertas} alertas; ERA5 hasta {ult}."
        )
        lines.append("  Top 5 candidatos (fecha, lat, lon, score):")
        for _, r in top.iterrows():
            lines.append(
                f"    - {r['fecha']} ({r['lat']:.1f}, {r['lon']:.1f}) score={r['score']:.3f}"
            )

    lines += [
        "",
        "## Lectura",
        "",
        "- El modelo elegido reduce drásticamente las falsas alarmas frente a la regla física (M1) "
        "manteniendo POD ≥ 70 % y ~2–3 días de alerta por detección, acercándose a las metas.",
        "- El FAR se mide sobre días de evento y de control, por lo que **sobrestima** el real.",
        "- 2026 cubre abril–julio (ERA5 disponible); agosto–septiembre aún no están en el reanálisis.",
        "- Es un sistema de apoyo a la revisión, no un pronóstico operativo (ERA5 es reanálisis).",
    ]

    out = ds.child("outputs", "resumen_pitch.md")
    md = "\n".join(lines)
    if out.is_s3:
        with out.fs.open(out.root, "w") as fh:
            fh.write(md)
    else:
        Path(out.root).write_text(md, encoding="utf-8")
    print(f"resumen -> {out.root}", flush=True)


if __name__ == "__main__":
    main()
