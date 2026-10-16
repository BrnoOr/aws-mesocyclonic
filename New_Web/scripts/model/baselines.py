#!/usr/bin/env python3
"""Líneas base físicas (sin ajuste): reglas de umbral que compiten con el modelo en las mismas métricas.

Cada línea base toma el DataFrame de celdas y devuelve una pseudoprobabilidad por celda (1.0 si la
regla se dispara, 0.0 si no), de modo que pasa por el mismo código de KPI por evento y por día que el
modelo. No se ajustan: son los umbrales del documento y del lote AIWP.

Reglas (``docs/mesociclones_chile.md`` §5 y Marín et al. 2024):

- **STP** (KPI-1, detección): ``stp_lm <= -0.3`` (rama *left-mover*, signo austral).
- **SHERBS3 ≥ 1** (KPI-2, falsas alarmas): el proxy más cercano disponible a ``SHERBE ≥ 1``. **Es un
  proxy**: SHERBS3 usa la cizalladura 0–3 km, no la capa efectiva de SHERBE.
- **HSLC regla A**: ``shear_01 >= 12`` **y** ``srh_01 <= -150`` **y** ``vgp_01 > 0`` (``vgp_01 > 0``
  equivale a CAPE > 0). Es la regla usada en el lote AIWP.
- **HSLC regla B**: igual que A pero **sin** la cláusula de CAPE (``vgp_01 > 0``), para no depender de
  una variable que el pronóstico pierde.
"""

import numpy as np
import pandas as pd

BASELINES = ("stp", "sherbs3", "hslc_a", "hslc_b")


def _as_prob(fires: pd.Series | np.ndarray) -> np.ndarray:
    """Convierte una máscara booleana de «la regla se dispara» en pseudoprobabilidad 0/1."""
    return np.asarray(fires, dtype=float)


def stp(df: pd.DataFrame) -> np.ndarray:
    """STP de rama *left-mover* ``<= -0.3`` (línea base de detección, Marín et al. 2024)."""
    return _as_prob(df["stp_lm"] <= -0.3)


def sherbs3(df: pd.DataFrame) -> np.ndarray:
    """``SHERBS3 >= 1`` como proxy de ``SHERBE >= 1`` (línea base de falsas alarmas; es un proxy)."""
    return _as_prob(df["sherbs3"] >= 1.0)


def hslc_a(df: pd.DataFrame) -> np.ndarray:
    """HSLC regla A: cizalladura 0–1 km ≥ 12, SRH 0–1 km ≤ −150 y CAPE > 0 (``vgp_01 > 0``)."""
    return _as_prob((df["shear_01"] >= 12.0) & (df["srh_01"] <= -150.0) & (df["vgp_01"] > 0.0))


def hslc_b(df: pd.DataFrame) -> np.ndarray:
    """HSLC regla B: como A pero sin la cláusula de CAPE (no depende de ``vgp_01``)."""
    return _as_prob((df["shear_01"] >= 12.0) & (df["srh_01"] <= -150.0))


def score_baseline(name: str, df: pd.DataFrame) -> np.ndarray:
    """Pseudoprobabilidad por celda de la línea base ``name`` sobre ``df``."""
    fns = {"stp": stp, "sherbs3": sherbs3, "hslc_a": hslc_a, "hslc_b": hslc_b}
    if name not in fns:
        raise ValueError(f"línea base desconocida: {name!r}; usa una de {BASELINES}")
    return fns[name](df)
