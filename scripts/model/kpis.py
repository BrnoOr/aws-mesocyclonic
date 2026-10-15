#!/usr/bin/env python3
"""Métricas con acierto tolerante (docs/claude/design.md §7, requirements R4.3).

Un evento se considera detectado si hay una alerta en su celda o en las 8 vecinas, el mismo día o el
día anterior (tolerancia configurable). Las métricas:

- **POD** = eventos detectados / eventos.
- **FAR** = alertas que no corresponden a ningún evento (con tolerancia) / alertas.
- **días por detección** = fechas distintas con al menos una alerta / eventos detectados.
- **PR-AUC** = área bajo la curva precisión-recall (por celda-día, sin tolerancia espacial, como
  medida de ordenamiento del puntaje).

El FAR se mide sobre días de evento y de control, así que sobrestima el real (se anota en el reporte).
"""

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score


def _cells_near(lat: float, lon: float, vecindad: int, res: float = 1.0) -> set:
    """Celdas (lat, lon) en la vecindad ``vecindad`` (en celdas) de ``(lat, lon)``, redondeadas."""
    out = set()
    for i in range(-vecindad, vecindad + 1):
        for j in range(-vecindad, vecindad + 1):
            out.add((round(lat + i * res, 3), round(lon + j * res, 3)))
    return out


def tolerant_metrics(
    df: pd.DataFrame,
    events: pd.DataFrame,
    vecindad: int = 1,
    ventana_dias: tuple[int, int] = (-1, 0),
    res: float = 1.0,
) -> dict:
    """POD, FAR, días por detección y PR-AUC con acierto tolerante.

    ``df`` tiene ``fecha, lat, lon, y, alerta`` (y opcional ``score`` para PR-AUC). ``events`` tiene
    ``fecha, lat, lon`` por evento (centro de celda). ``ventana_dias`` relativo al día del evento.
    """
    alerts = df[df["alerta"] == 1][["fecha", "lat", "lon"]].copy()
    alerts["fecha"] = pd.to_datetime(alerts["fecha"])
    alert_set = {
        (f.normalize(), round(la, 3), round(lo, 3))
        for f, la, lo in zip(alerts["fecha"], alerts["lat"], alerts["lon"], strict=True)
    }

    ev = events.copy()
    ev["fecha"] = pd.to_datetime(ev["fecha"])

    detected = 0
    for _, e in ev.iterrows():
        cells = _cells_near(e["lat"], e["lon"], vecindad, res)
        hit = False
        for dd in range(ventana_dias[0], ventana_dias[1] + 1):
            fday = (e["fecha"] + pd.Timedelta(days=dd)).normalize()
            if any((fday, la, lo) in alert_set for (la, lo) in cells):
                hit = True
                break
        detected += int(hit)
    n_events = len(ev)
    pod = detected / n_events if n_events else float("nan")

    # FAR: alertas que no caen cerca (tolerancia) de ningún evento.
    ev_cells_days = set()
    for _, e in ev.iterrows():
        cells = _cells_near(e["lat"], e["lon"], vecindad, res)
        for dd in range(ventana_dias[0], ventana_dias[1] + 1):
            fday = (e["fecha"] + pd.Timedelta(days=dd)).normalize()
            for (la, lo) in cells:
                ev_cells_days.add((fday, la, lo))
    n_alertas = len(alert_set)
    falsas = sum(1 for a in alert_set if a not in ev_cells_days)
    far = falsas / n_alertas if n_alertas else float("nan")

    dias_alerta = alerts["fecha"].dt.normalize().nunique()
    dias_por_det = dias_alerta / detected if detected else float("nan")

    if "score" in df.columns and df["y"].sum() > 0:
        pr_auc = float(average_precision_score(df["y"].to_numpy(), df["score"].to_numpy()))
    else:
        pr_auc = float("nan")

    return {
        "POD": pod,
        "FAR": far,
        "dias_por_deteccion": dias_por_det,
        "PR_AUC": pr_auc,
        "eventos": n_events,
        "detectados": detected,
        "alertas": n_alertas,
        "dias_alerta": int(dias_alerta),
    }
