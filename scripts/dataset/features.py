#!/usr/bin/env python3
"""Funciones puras para armar la tabla de ejemplos del dataset: celdas, etiquetas y particiones.

Separadas de ``build_dataset.py`` (que lee los NetCDF y escribe el parquet) para poder probarlas sin
datos descargados. Un **ejemplo** es una celda de la grilla ERA5 (0,25°) en una hora UTC: sus
variables físicas de ERA5, un resumen de GOES sobre esa celda y una etiqueta derivada del catálogo.

Convenciones del equipo (ver ``docs/mesociclones_chile.md`` secciones 6.1–6.3 y el kit):

- La **etiqueta** (``label``) es 1 si en esa celda y hora se reportó un tornado o una tromba. El
  catálogo solo tiene positivos: las demás celdas quedan como 0 (*sin etiqueta*, no negativo
  confirmado). Es un planteamiento PU (positivos y datos sin etiqueta).
- El **mesociclón inferido** es variable de apoyo, nunca etiqueta (kit, decisiones tomadas).
- La **anticipación** toma las variables ``lead`` horas antes de la hora del evento y conserva la
  etiqueta de la hora del evento, para estudiar con cuánto adelanto se separa un día tornádico.
- Las **particiones** se asignan por año de la fecha, y el **grupo** de no fuga es la fecha del
  brote: todas las horas y celdas de un mismo día caen en la misma partición (sección 6.3).
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Particiones por año de la fecha del evento (kit, decisiones tomadas):
# train 2018–2023 · val 2024 · test 2025 · dev 30–31 mayo 2019 · 2026 solo inferencia.
DEV_DATES = (dt.date(2019, 5, 30), dt.date(2019, 5, 31))
TRAIN_YEARS = range(2018, 2024)  # 2018–2023 inclusive
VAL_YEAR = 2024
TEST_YEAR = 2025
INFERENCE_YEAR = 2026

# Horas de anticipación del dataset (diagnóstico = 0 h): la hora del evento y 1, 3 y 6 h antes.
LEAD_HOURS = (0, 1, 3, 6)

# Radio de asociación evento → celda, en grados. Una celda ERA5 mide 0,25°; con 0,2° se etiqueta la
# celda que contiene el evento y sus vecinas inmediatas, cubriendo el error de posición del reporte
# y el desplazamiento de la tormenta dentro de la hora sin pintar un área grande de positivos.
MATCH_RADIUS_DEG = 0.2


@dataclass(frozen=True)
class Event:
    """Un evento positivo del catálogo, ya con la hora y la celda con que se cruza GOES/ERA5."""

    uid: str
    date: dt.date
    hour_utc: int  # hora UTC entera del evento (la de ``hour_utc`` redondeada a la hora ERA5)
    lat: float
    lon: float
    register: float  # 1 confirmado, 0 débil; NaN sin evaluar
    is_range: bool  # hora imprecisa (venía de un rango): se trata aparte en validación/test


def partition_of(date: dt.date) -> str:
    """Partición (``train``/``val``/``test``/``dev``/``inference``) de una fecha, por su año.

    ``dev`` tiene prioridad: el brote del 30–31 de mayo de 2019 es caso de desarrollo y no debe
    reaparecer como prueba ciega (sección 6.3). Los años fuera del plan quedan como ``train`` por
    defecto, para no perder días al azar previos a 2018 si el equipo decidiera incluirlos.
    """
    if date in DEV_DATES:
        return "dev"
    y = date.year
    if y == INFERENCE_YEAR:
        return "inference"
    if y == TEST_YEAR:
        return "test"
    if y == VAL_YEAR:
        return "val"
    if y in TRAIN_YEARS:
        return "train"
    return "train"


def round_hour(hour_utc: str | float | None) -> int | None:
    """Hora UTC entera (0–23) de un ``HH:MM`` del catálogo, redondeando al minuto 30.

    La grilla de ERA5 es horaria, así que cada evento se cruza con la hora redonda más cercana. Un
    redondeo que llegara a 24 se queda en 23 para no cambiar de día (igual criterio que GOES en
    ``clean_catalog``). Un valor vacío o ilegible devuelve ``None``.
    """
    if hour_utc is None or (isinstance(hour_utc, float) and np.isnan(hour_utc)):
        return None
    s = str(hour_utc)
    if ":" not in s:
        return None
    h, m = (int(x) for x in s.split(":")[:2])
    hh = h + (1 if m >= 30 else 0)
    return min(hh, 23)


def events_from_catalog(catalog: pd.DataFrame, date: dt.date) -> list[Event]:
    """Eventos positivos del catálogo en ``date`` con hora y coordenada legibles.

    Un evento es positivo si reporta tornado o tromba (el catálogo no tiene negativos). Se descartan
    los que no tienen hora UTC o coordenada, porque sin ellas no se puede ubicar la celda y la hora
    que etiquetar.
    """
    iso = date.isoformat()
    rows = catalog[catalog["date"].astype(str) == iso]
    events = []
    for _, r in rows.iterrows():
        tornado = _is_one(r.get("tornado"))
        waterspout = _is_one(r.get("waterspout"))
        if not (tornado or waterspout):
            continue
        hour = round_hour(r.get("hour_utc"))
        lat, lon = float(r.get("lat", np.nan)), float(r.get("lon", np.nan))
        if hour is None or np.isnan(lat) or np.isnan(lon):
            continue
        events.append(
            Event(
                uid=str(r.get("uid", "")),
                date=date,
                hour_utc=hour,
                lat=lat,
                lon=lon,
                register=float(r.get("register", np.nan)),
                is_range=bool(r.get("hour_is_range", False)),
            )
        )
    return events


def _is_one(v: object) -> bool:
    """Si la marca ``v`` del catálogo vale 1 (vacío o cualquier otro valor cuenta como no)."""
    try:
        return not pd.isna(v) and int(v) == 1  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def label_grid(
    lat: np.ndarray, lon: np.ndarray, events: list[Event], hour_utc: int, radius: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Etiqueta cada celda de la grilla (``lat`` × ``lon``) para la hora ``hour_utc``.

    Devuelve tres rejillas 2D con forma ``(len(lat), len(lon))``:

    - ``label``: 1 si una celda está a ``radius`` grados o menos de un evento cuya hora coincide con
      ``hour_utc``; 0 en el resto (sin etiqueta, no negativo confirmado).
    - ``event_uid``: el ``uid`` del evento más cercano que etiquetó la celda, o ``""``.
    - ``confirmed``: 1 si ese evento tiene ``register == 1`` (registro confirmado), si no 0.

    La longitud se escala por el coseno de la latitud media para medir la distancia en grados de
    forma aproximadamente isótropa, igual que en la reproyección de GOES.
    """
    label = np.zeros((len(lat), len(lon)), dtype="int8")
    uid = np.full((len(lat), len(lon)), "", dtype=object)
    confirmed = np.zeros((len(lat), len(lon)), dtype="int8")
    k = np.cos(np.deg2rad(float(np.mean(lat))))
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    for e in events:
        if e.hour_utc != hour_utc:
            continue
        dist = np.hypot(LA - e.lat, (LO - e.lon) * k)
        hit = dist <= radius
        label[hit] = 1
        is_conf = 1 if e.register == 1 else 0
        # Si una celda cae en el radio de varios eventos, se queda con el más cercano.
        closer = hit & ((uid == "") | (dist < _dist_to_assigned(dist, uid)))
        uid[closer] = e.uid
        confirmed[closer] = is_conf
    return label, uid, confirmed


def _dist_to_assigned(dist: np.ndarray, uid: np.ndarray) -> np.ndarray:
    """Distancia de referencia para comparar: ``inf`` donde aún no hay evento asignado.

    Permite que, al recorrer los eventos, una celda ya etiquetada se reasigne solo a un evento más
    cercano. Se evalúa de forma perezosa por evento, suficiente para los pocos eventos de un día.
    """
    return np.where(uid == "", np.inf, dist)


def assign_cell(lat: np.ndarray, lon: np.ndarray, ev_lat: float, ev_lon: float) -> tuple[int, int]:
    """Índice ``(i, j)`` de la celda de la grilla más cercana al punto (``ev_lat``, ``ev_lon``)."""
    i = int(np.argmin(np.abs(lat - ev_lat)))
    j = int(np.argmin(np.abs(lon - ev_lon)))
    return i, j
