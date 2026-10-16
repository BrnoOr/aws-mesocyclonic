#!/usr/bin/env python3
"""Columnas de entrada del modelo: conjuntos de *features* y la guardia contra fugas.

Lógica pura (listas y comprobaciones), separada de ``train.py`` para probarla sin el dataset. Las
reglas vienen de ``docs/mesociclones_chile.md`` §6 y de ``docs/dataset_para_kiro.md``:

- Las *features* son solo variables físicas; nunca identificadores ni metadatos (``FORBIDDEN``), que
  filtrarían la respuesta.
- Hay tres conjuntos:
  - ``era5``: las 18 variables de ERA5 (idénticas a las de ``era5_idx_*.nc``).
  - ``wind``: ``era5`` **sin las variables que dependen de CAPE** (``vgp_01``, ``stp_lm``). En el
    lote de 25 eventos con Pangu, la MUCAPE derivada salía 0 en varios eventos detectados (los 13
    niveles del pronóstico pierden la inestabilidad somera del régimen HSLC), así que un modelo que
    se apoye en esas dos variables falla en silencio sobre el pronóstico. ``wind`` es *AIWP-safe*.
  - ``all``: ``era5`` más el resumen de GOES (solo existe en el dataset tabular, no en el pronóstico).

Las métricas (POD, FAR, AUC-PR, Brier, …) viven en ``metrics.py`` (módulo del equipo); aquí no se
repiten.
"""

# Variables físicas de ERA5 (idénticas a las de era5_idx_*.nc).
ERA5_FEATURES = [
    "shear_01", "shear_03", "shear_06", "srh_01", "srh_03", "lcl",
    "gamma_03", "gamma_75", "vgp_01", "stp_lm", "sherbs3",
    "u_06", "v_06", "u_lm", "v_lm", "u_rm", "v_rm", "sfc_height",
]  # fmt: skip

# Variables que dependen de CAPE y no transfieren bien al pronóstico AIWP (MUCAPE del pronóstico ≈ 0).
CAPE_DEPENDENT = ("vgp_01", "stp_lm")

# ``wind``: ERA5 sin las variables dependientes de CAPE. Es el conjunto seguro para el pronóstico.
WIND_FEATURES = [f for f in ERA5_FEATURES if f not in CAPE_DEPENDENT]

# Resumen de la banda térmica de GOES: solo existe en el dataset tabular, no en el pronóstico AIWP.
GOES_FEATURES = ["goes_bt_min", "goes_bt_mean", "goes_bt_trend"]

FEATURE_SETS = ("era5", "wind", "all")

# Columnas que nunca entran como features (identificadores y metadatos): filtrarían la respuesta.
FORBIDDEN = frozenset(
    {
        "date", "hour_utc", "feat_hour_utc", "lead_h", "lat", "lon", "region",
        "partition", "group", "label", "event_uid", "confirmed", "hour_is_range", "day_kind",
    }
)  # fmt: skip


def feature_names(kind: str) -> list[str]:
    """Lista de features del conjunto ``kind`` (``era5``, ``wind`` o ``all``).

    ``wind`` quita las variables dependientes de CAPE; ``all`` añade el resumen de GOES.
    """
    if kind == "era5":
        return list(ERA5_FEATURES)
    if kind == "wind":
        return list(WIND_FEATURES)
    if kind == "all":
        return ERA5_FEATURES + GOES_FEATURES
    raise ValueError(f"conjunto de features desconocido: {kind!r}; usa uno de {FEATURE_SETS}")


def is_aiwp_safe(feats: list[str]) -> bool:
    """``True`` si ninguna feature depende de CAPE (``vgp_01``/``stp_lm``): aplicable al pronóstico AIWP.

    Las variables GOES no están en el pronóstico, pero esta bandera solo juzga la transferencia
    física de las variables ERA5; un conjunto con GOES se marca aparte en los metadatos del modelo.
    """
    return not any(f in CAPE_DEPENDENT for f in feats)


def check_not_forbidden(feats: list[str]) -> None:
    """Falla si alguna feature es un identificador o metadato (``FORBIDDEN``)."""
    forbidden = [f for f in feats if f in FORBIDDEN]
    if forbidden:
        raise AssertionError(f"features prohibidas (identificadores/metadatos): {forbidden}")
