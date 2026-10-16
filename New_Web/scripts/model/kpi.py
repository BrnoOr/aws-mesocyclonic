#!/usr/bin/env python3
"""KPIs por **evento** y por **día**: lo que evalúa el desafío (CR2), no la celda.

Las métricas por celda de ``metrics.py`` son diagnósticos secundarios: con el desbalance extremo la
FAR por celda es ≈ 1 por construcción y no dice nada de la operación, y la POD por celda sobrepondera
los eventos que etiquetan varias celdas vecinas. El desafío puntúa **eventos** (¿se detectó el
tornado?) y **días** (¿cuántos días de aviso revisa un experto?). Este módulo agrega las puntuaciones
por celda a esos dos niveles.

KPIs (diapositiva «KPIs y métricas de éxito»):

- **KPI 1 — POD por evento:** fracción de tornados registrados que el modelo señala. Un evento se
  detecta si alguna celda a ≤ 50 km (haversine) y ±1 h de su celda-hora supera el umbral.
- **KPI 2 — FAR por día:** días de aviso sin ningún evento registrado / días de aviso.
- **KPI 3 — Avisos por acierto:** días de aviso / días de aviso con al menos un evento detectado.

KPI 2 y 3 **necesitan días sin evento** (controles) en la partición evaluada. Si no los hay, se
devuelven como *no computable* (nunca 0) con el número de controles que harían falta: con etiquetas
incompletas, un «día sin evento» que no existe no puede fabricar una falsa alarma.

Módulo puro: recibe DataFrames y devuelve números; no lee disco ni entrena.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
NIGHT_HOURS = range(0, 10)  # 00–09 UTC se consideran noche en la hora del evento
SEASON_DAYS = 153  # días de mayo a septiembre (31+30+31+31+30), la temporada severa austral


def haversine(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Distancia en km entre un punto y arreglos de puntos (fórmula del haversine)."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = np.radians(lat2), np.radians(lon2)
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = np.sin(dlat / 2) ** 2 + math.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson (por defecto 95 %) para ``k`` éxitos en ``n`` ensayos.

    Mejor que el normal para proporciones con pocos ensayos (nunca se sale de [0, 1]). Con ``n = 0``
    devuelve ``(nan, nan)``: sin ensayos no hay proporción que acotar.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass(frozen=True)
class Rate:
    """Una tasa (p. ej. POD o FAR) con su conteo y su intervalo de Wilson, o *no computable*."""

    value: float  # la tasa en [0, 1], o nan si no es computable
    k: int  # numerador (p. ej. eventos detectados, o días de aviso sin evento)
    n: int  # denominador (p. ej. eventos totales, o días de aviso)
    low: float  # extremo inferior del intervalo de Wilson
    high: float  # extremo superior del intervalo de Wilson
    computable: bool  # False si falta información (p. ej. no hay días sin evento)
    reason: str = ""  # por qué no es computable, y qué haría falta


def _rate(k: int, n: int) -> Rate:
    """Construye un ``Rate`` computable a partir del numerador y el denominador."""
    low, high = wilson_interval(k, n)
    return Rate(
        value=(k / n if n else float("nan")), k=k, n=n, low=low, high=high, computable=n > 0
    )


def event_pod(
    events: pd.DataFrame,
    cells: pd.DataFrame,
    threshold: float,
    tol_km: float = 50.0,
    tol_hours: int = 1,
) -> Rate:
    """POD por evento: un evento se detecta si una celda a ≤ ``tol_km`` y ±``tol_hours`` lo supera.

    ``events``: una fila por evento con ``lat``, ``lon`` y ``hour_utc`` (la hora de la etiqueta).
    ``cells``: celdas puntuadas con ``lat``, ``lon``, ``hour_utc`` y ``score``. Un evento que etiqueta
    varias celdas cuenta **una sola vez**. Devuelve un ``Rate`` sobre el número de eventos.
    """
    if events.empty:
        return Rate(float("nan"), 0, 0, float("nan"), float("nan"), False, "no hay eventos")
    alarm = cells[cells["score"] >= threshold]
    detected = 0
    for _, e in events.iterrows():
        if alarm.empty:
            break
        near_hour = alarm[(alarm["hour_utc"] - int(e["hour_utc"])).abs() <= tol_hours]
        if near_hour.empty:
            continue
        dist = haversine(
            float(e["lat"]),
            float(e["lon"]),
            near_hour["lat"].to_numpy(),
            near_hour["lon"].to_numpy(),
        )
        if np.any(dist <= tol_km):
            detected += 1
    return _rate(detected, len(events))


def event_pod_label(events: pd.DataFrame, cells: pd.DataFrame, threshold: float) -> Rate:
    """Variante de POD por evento con la tolerancia de la etiqueta de entrenamiento: 0,2° y misma hora."""
    if events.empty:
        return Rate(float("nan"), 0, 0, float("nan"), float("nan"), False, "no hay eventos")
    alarm = cells[cells["score"] >= threshold]
    k = np.cos(np.deg2rad(float(cells["lat"].mean()))) if len(cells) else 1.0
    detected = 0
    for _, e in events.iterrows():
        if alarm.empty:
            break
        same_hour = alarm[alarm["hour_utc"] == int(e["hour_utc"])]
        if same_hour.empty:
            continue
        dist = np.hypot(
            same_hour["lat"].to_numpy() - float(e["lat"]),
            (same_hour["lon"].to_numpy() - float(e["lon"])) * k,
        )
        if np.any(dist <= 0.2):
            detected += 1
    return _rate(detected, len(events))


def _subbox(df: pd.DataFrame, subbox_deg: float) -> pd.Series:
    """Etiqueta de sub-caja de ``subbox_deg`` grados (p. ej. 1×1) a partir de ``lat``/``lon``."""
    bi = np.floor(df["lat"].to_numpy() / subbox_deg).astype(int).astype(str)
    bj = np.floor(df["lon"].to_numpy() / subbox_deg).astype(int).astype(str)
    return pd.Series(np.char.add(np.char.add(bi, "_"), bj), index=df.index)


def alert_days(
    cells: pd.DataFrame, threshold: float, subbox_deg: float | None = None
) -> set[tuple]:
    """Conjunto de días de aviso: ``(date[, subcaja])`` cuyo máximo ``score`` supera el umbral.

    Sin ``subbox_deg`` el aviso es por (fecha, región): una sola marca para toda la región. Con
    ``subbox_deg`` se agrupa además por sub-caja de ese tamaño, más fino para un experto.
    """
    if cells.empty:
        return set()
    df = cells.copy()
    keys: list[str] = ["date"]
    if subbox_deg is not None:
        df["_subbox"] = _subbox(df, subbox_deg)
        keys.append("_subbox")
    peak = df.groupby(keys)["score"].max()
    return {(k if isinstance(k, tuple) else (k,)) for k in peak[peak >= threshold].index}


def _event_days(events: pd.DataFrame, subbox_deg: float | None = None) -> set[tuple]:
    """Días (o día×sub-caja) con al menos un evento registrado."""
    if events.empty:
        return set()
    df = events.copy()
    keys: list[str] = ["date"]
    if subbox_deg is not None:
        df["_subbox"] = _subbox(df, subbox_deg)
        keys.append("_subbox")
    return {tuple(r) for r in df[keys].drop_duplicates().to_numpy()}


def _has_control_days(cells: pd.DataFrame, events: pd.DataFrame) -> bool:
    """``True`` si hay al menos un día de control en las celdas evaluadas.

    Prefiere la columna explícita ``day_kind`` (``control``); si no está, cae a «día sin evento».
    """
    if "day_kind" in cells.columns:
        return bool((cells["day_kind"] == "control").any())
    all_days = set(cells["date"].unique())
    event_days = set(events["date"].unique())
    return len(all_days - event_days) > 0


def _not_computable(cells: pd.DataFrame, events: pd.DataFrame) -> Rate:
    """``Rate`` no computable con el detalle de cuántos días de control faltan."""
    n_event_days = events["date"].nunique()
    msg = (
        "no hay días sin evento (controles) en la partición: la FAR por día y los avisos por acierto "
        f"no se pueden calcular. Añade días de control sin tornado (hay {n_event_days} días con evento; "
        "se recomienda al menos tantos días de control como de evento)."
    )
    return Rate(float("nan"), 0, 0, float("nan"), float("nan"), False, msg)


def day_far(
    cells: pd.DataFrame, events: pd.DataFrame, threshold: float, subbox_deg: float | None = None
) -> Rate:
    """FAR por día (KPI 2): días de aviso sin evento registrado / días de aviso.

    *No computable* si no hay días sin evento en ``cells`` (devuelve el motivo, nunca 0).
    """
    if not _has_control_days(cells, events):
        return _not_computable(cells, events)
    alerts = alert_days(cells, threshold, subbox_deg)
    if not alerts:
        return Rate(float("nan"), 0, 0, float("nan"), float("nan"), False, "no hubo días de aviso")
    event_set = _event_days(events, subbox_deg)
    false_alerts = sum(1 for a in alerts if a not in event_set)
    return _rate(false_alerts, len(alerts))


def alerts_per_hit(
    cells: pd.DataFrame, events: pd.DataFrame, threshold: float, subbox_deg: float | None = None
) -> float:
    """Avisos por acierto (KPI 3): días de aviso / días de aviso con ≥ 1 evento detectado.

    Devuelve ``nan`` si no hay controles (no computable) o si no hay días de aviso con acierto.
    """
    if not _has_control_days(cells, events):
        return float("nan")
    alerts = alert_days(cells, threshold, subbox_deg)
    if not alerts:
        return float("nan")
    event_set = _event_days(events, subbox_deg)
    hits = sum(1 for a in alerts if a in event_set)
    return len(alerts) / hits if hits else float("nan")


@dataclass(frozen=True)
class SeasonFar:
    """FAR por día y avisos por acierto reescalados a una temporada, con el intervalo de ``q``."""

    far: float  # FA / (FA + hits), proyectada a la temporada
    alerts_per_hit: float  # (FA + hits) / hits
    q: float  # tasa de días de aviso entre los días de control
    q_low: float  # extremo inferior del intervalo de Wilson de q
    q_high: float  # extremo superior
    n_control: int  # días de control sobre los que descansa q
    far_low: float  # FAR propagando q_low..q_high
    far_high: float
    note: str  # advertencia (p. ej. pocos controles)


def control_alert_rate(
    cells: pd.DataFrame, events: pd.DataFrame, threshold: float
) -> tuple[int, int]:
    """Días de aviso y días totales **entre los días de control** (sin evento) de ``cells``.

    Si ``cells`` trae la columna ``day_kind``, los controles son los días con ``day_kind="control"``
    (explícito, como pide el diseño). Si no, se cae al criterio «día sin evento en ``events``». Así
    un día de evento cuyas celdas positivas quedaron fuera de la ventana horaria no se cuenta por
    error como control. Devuelve ``(dias_de_aviso_control, dias_de_control)``.
    """
    peak = cells.groupby("date")["score"].max()
    if "day_kind" in cells.columns:
        kind = cells.groupby("date")["day_kind"].first()
        control = peak[peak.index.isin(set(kind[kind == "control"].index))]
    else:
        event_days = set(events["date"].unique())
        control = peak[~peak.index.isin(event_days)]
    return int((control >= threshold).sum()), int(len(control))


def season_rescaled_far(
    cells: pd.DataFrame,
    events: pd.DataFrame,
    threshold: float,
    pod_day: float,
    n_event_days_year: int,
    season_days: int = SEASON_DAYS,
) -> SeasonFar | None:
    """FAR por día y avisos por acierto **proyectados a una temporada** (comparable con la base CR2).

    La FAR cruda depende de cuántos controles frente a eventos haya en la partición, que es
    artificial. Para compararla con la línea base del desafío se reescala con la climatología:

    - ``q`` = días de aviso / días de control (falsas alarmas por día sin tornado), con Wilson.
    - ``N0`` = ``season_days − n_event_days_year`` (días sin evento de una temporada mayo–septiembre).
    - Falsas alarmas esperadas: ``FA = q · N0``; aciertos: ``hits = pod_day · n_event_days_year``.
    - ``FAR = FA / (FA + hits)`` y ``avisos/acierto = (FA + hits) / hits``.

    Devuelve ``None`` si no hay días de control. El intervalo de ``q`` se propaga a la FAR. Con pocos
    controles ``q`` es muy incierto: el resultado es indicativo, no un KPI consolidado.
    """
    alerts, n_control = control_alert_rate(cells, events, threshold)
    if n_control == 0:
        return None
    q = alerts / n_control
    q_low, q_high = wilson_interval(alerts, n_control)
    n0 = max(0, season_days - n_event_days_year)
    hits = pod_day * n_event_days_year

    def _far(qq: float) -> float:
        """FAR proyectada con una tasa de falsas alarmas por día ``qq``."""
        fa = qq * n0
        return fa / (fa + hits) if (fa + hits) > 0 else float("nan")

    fa = q * n0
    aph = (fa + hits) / hits if hits > 0 else float("nan")
    note = (
        f"q descansa en {n_control} día(s) de control: muy incierto, indicativo."
        if n_control < 10
        else f"q sobre {n_control} días de control."
    )
    return SeasonFar(
        far=_far(q),
        alerts_per_hit=aph,
        q=q,
        q_low=q_low,
        q_high=q_high,
        n_control=n_control,
        far_low=_far(q_low),
        far_high=_far(q_high),
        note=note,
    )


@dataclass(frozen=True)
class FlaggedArea:
    """Área marcada a un umbral: fracción de celda-horas en días de evento y de control, y por aviso."""

    frac_event: float  # fracción de celda-horas marcadas en días de evento
    frac_control: float  # fracción de celda-horas marcadas en días de control (nan si no hay)
    mean_cells_per_alert_day: (
        float  # celdas marcadas en promedio por día de aviso (todas las horas)
    )


def flagged_area(cells: pd.DataFrame, events: pd.DataFrame, threshold: float) -> FlaggedArea:
    """Estadísticas del área marcada: cuánta región×tiempo se marca y cuántas celdas por día de aviso.

    - ``frac_event``/``frac_control``: celda-horas marcadas / celda-horas totales, por separado en
      días de evento y de control (``day_kind`` si está; si no, por presencia en ``events``).
    - ``mean_cells_per_alert_day``: celdas marcadas en promedio en cada día que llegó a dar aviso.
    """
    flagged = cells["score"] >= threshold
    if "day_kind" in cells.columns:
        is_control = cells["day_kind"] == "control"
    else:
        is_control = ~cells["date"].isin(set(events["date"].unique()))
    ev = ~is_control

    def _frac(mask: pd.Series) -> float:
        """Fracción de celda-horas marcadas dentro de las filas de ``mask`` (nan si no hay filas)."""
        n = int(mask.sum())
        return float((flagged & mask).sum()) / n if n else float("nan")

    # Celdas marcadas por día de aviso: días cuyo pico supera el umbral, media de celdas marcadas.
    per_day = cells.assign(_f=flagged).groupby("date")["_f"].sum()
    peak = cells.groupby("date")["score"].max()
    alert_days_idx = peak[peak >= threshold].index
    mean_cells = float(per_day.loc[alert_days_idx].mean()) if len(alert_days_idx) else float("nan")
    return FlaggedArea(
        frac_event=_frac(ev), frac_control=_frac(is_control), mean_cells_per_alert_day=mean_cells
    )


def breakdown_event_pod(
    events: pd.DataFrame, cells: pd.DataFrame, threshold: float
) -> dict[str, Rate]:
    """POD por evento desglosada por intensidad (EF), tipo, confirmación y día/noche.

    ``events`` debe traer, además de ``lat``/``lon``/``hour_utc``: ``ef`` (texto, p. ej. ``EF0``),
    ``kind`` (tornado/tromba/…), ``confirmed`` (0/1). Cada subconjunto se evalúa con ``event_pod``.
    """
    out: dict[str, Rate] = {}

    def ef_rank(v: object) -> int | None:
        """Número de la escala EF (0, 1, …) o ``None`` si no hay dato legible."""
        s = "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
        for ch in s:
            if ch.isdigit():
                return int(ch)
        return None

    ranks = events["ef"].map(ef_rank) if "ef" in events else pd.Series([None] * len(events))
    out["EF0"] = event_pod(events[ranks == 0], cells, threshold)
    out["EF1+"] = event_pod(events[ranks.fillna(-1) >= 1], cells, threshold)

    if "kind" in events:
        for label, mask in {
            "tornado": events["kind"].astype(str).str.contains("tornado"),
            "tromba": events["kind"].astype(str).str.contains("tromba"),
        }.items():
            out[label] = event_pod(events[mask], cells, threshold)

    if "confirmed" in events:
        out["confirmado"] = event_pod(events[events["confirmed"] == 1], cells, threshold)
        out["débil"] = event_pod(events[events["confirmed"] == 0], cells, threshold)

    is_night = events["hour_utc"].astype(int).isin(list(NIGHT_HOURS))
    out["noche (00-09 UTC)"] = event_pod(events[is_night], cells, threshold)
    out["día (10-23 UTC)"] = event_pod(events[~is_night], cells, threshold)
    return out
