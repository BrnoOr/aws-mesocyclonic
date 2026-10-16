"""Métricas de evaluación del modelo tabular (docs, sección 6.2).

El catálogo es muy desbalanceado: los eventos registrados son poquísimos frente al número de celdas
y horas sin etiqueta. Un modelo que siempre diga «sin evento» tendría una exactitud altísima y no
detectaría ningún caso, así que la *accuracy* no sirve. Aquí se calculan las medidas que sí informan
en este régimen, con las advertencias que da la sección 6.2:

- **POD** (probabilidad de detección): fracción de casos registrados que el modelo señala.
- **FAR** (proporción de falsas alarmas): fracción de avisos sin un evento registrado asociado. Con
  etiquetas incompletas, parte de esos «falsos» pueden ser eventos sin registro, no errores.
- **AUC-PR** (área bajo la curva de precisión–exhaustividad): resume el compromiso entre avisos
  respaldados y casos detectados a distintos umbrales. Se prefiere a AUC-ROC porque, con tantísimos
  ejemplos sin evento, el ROC puede verse alto aunque casi ningún aviso tenga respaldo.
- **Brier** (error cuadrático medio de las probabilidades) y **curva de fiabilidad**: comprueban si
  una probabilidad de, por ejemplo, 0,2 corresponde a observar el evento una de cada cinco veces.

Ninguna métrica elimina la incertidumbre de las etiquetas: FAR, fiabilidad y Brier se interpretan
sabiendo que «no reportado» no equivale a «no ocurrió» (secciones 6.1–6.2).

Convención: ``y_true`` son 0/1 (1 = evento registrado) y ``y_score`` es una puntuación o
probabilidad en la que un valor mayor indica más riesgo. El módulo es puro y usa solo NumPy; no
depende de scikit-learn para no sumar una dependencia pesada al repositorio.
"""

from dataclasses import dataclass

import numpy as np


def _check(y_true: np.ndarray, y_score: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Valida y normaliza las entradas: mismo largo, etiquetas 0/1, puntuaciones finitas."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    if y_true.shape != y_score.shape:
        raise ValueError("y_true y y_score deben tener la misma forma")
    if y_true.ndim != 1:
        raise ValueError("se esperan arreglos 1D")
    if not np.isin(y_true, (0, 1)).all():
        raise ValueError("y_true debe contener solo 0 y 1")
    if not np.isfinite(y_score).all():
        raise ValueError("y_score no puede tener NaN ni infinitos")
    return y_true.astype(int), y_score


def confusion(
    y_true: np.ndarray, y_score: np.ndarray, threshold: float
) -> tuple[int, int, int, int]:
    """Cuenta (aciertos, falsas alarmas, omisiones, rechazos correctos) al umbral ``threshold``.

    Un aviso es ``y_score >= threshold``. Devuelve ``(hits, false_alarms, misses, correct_neg)``,
    los cuatro recuentos de la tabla de contingencia que usan POD, FAR, CSI y ETS.
    """
    y_true, y_score = _check(y_true, y_score)
    alarm = y_score >= threshold
    hits = int(np.sum(alarm & (y_true == 1)))
    false_alarms = int(np.sum(alarm & (y_true == 0)))
    misses = int(np.sum(~alarm & (y_true == 1)))
    correct_neg = int(np.sum(~alarm & (y_true == 0)))
    return hits, false_alarms, misses, correct_neg


def pod(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> float:
    """Probabilidad de detección: aciertos / casos registrados (``nan`` si no hay positivos)."""
    hits, _, misses, _ = confusion(y_true, y_score, threshold)
    denom = hits + misses
    return hits / denom if denom else float("nan")


def far(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> float:
    """Proporción de falsas alarmas: falsas alarmas / avisos emitidos (``nan`` si no hay avisos)."""
    hits, false_alarms, _, _ = confusion(y_true, y_score, threshold)
    denom = hits + false_alarms
    return false_alarms / denom if denom else float("nan")


def csi(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> float:
    """Índice crítico de éxito: aciertos / (aciertos + omisiones + falsas alarmas) (sección 6.2)."""
    hits, false_alarms, misses, _ = confusion(y_true, y_score, threshold)
    denom = hits + misses + false_alarms
    return hits / denom if denom else float("nan")


def precision_recall_curve(
    y_true: np.ndarray, y_score: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Curva de precisión y exhaustividad barriendo todos los umbrales presentes en ``y_score``.

    Devuelve ``(precision, recall, thresholds)``. Sigue la convención de scikit-learn: ``precision``
    y ``recall`` traen un punto final añadido (precisión 1, exhaustividad 0) sin umbral asociado, de
    modo que ``len(precision) == len(thresholds) + 1``.
    """
    y_true, y_score = _check(y_true, y_score)
    positives = int(y_true.sum())
    if positives == 0:
        raise ValueError("no hay positivos: la curva de precisión–exhaustividad no está definida")

    order = np.argsort(-y_score, kind="stable")
    y_sorted = y_true[order]
    s_sorted = y_score[order]
    # Umbrales en los puntos donde cambia la puntuación (último índice de cada valor distinto).
    distinct = np.flatnonzero(np.diff(s_sorted)) if s_sorted.size > 1 else np.array([], int)
    last = np.r_[distinct, s_sorted.size - 1]

    tp = np.cumsum(y_sorted)[last]
    fp = (last + 1) - tp
    precision = tp / (tp + fp)
    recall = tp / positives

    precision = np.r_[precision, 1.0]
    recall = np.r_[recall, 0.0]
    return precision, recall, s_sorted[last]


def auc_pr(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Área bajo la curva de precisión–exhaustividad (precisión media), por suma de rectángulos.

    Es la *average precision*: suma de ``precision[k] * (recall[k] − recall[k−1])``. Más robusta que
    la regla del trapecio cuando la curva salta, que es lo habitual con pocos positivos.
    """
    precision, recall, _ = precision_recall_curve(y_true, y_score)
    # Se descarta el punto final añadido (precisión 1, exhaustividad 0) de la convención sklearn: en
    # la curva real la exhaustividad crece del umbral más alto (recall bajo) al más bajo (recall 1).
    recall = recall[:-1]
    precision = precision[:-1]
    # AP = Σ (recall[k] − recall[k−1]) · precision[k], con recall₀ = 0 como línea base.
    delta = np.diff(recall, prepend=0.0)
    return float(np.sum(delta * precision))


def brier_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Error cuadrático medio entre la probabilidad predicha y la etiqueta 0/1 (menor es mejor)."""
    y_true, y_score = _check(y_true, y_score)
    if (y_score < 0).any() or (y_score > 1).any():
        raise ValueError("el Brier score espera probabilidades en [0, 1]")
    return float(np.mean((y_score - y_true) ** 2))


@dataclass(frozen=True)
class Reliability:
    """Curva de fiabilidad: por tramo de probabilidad, su centro, la frecuencia observada y el conteo."""

    mean_predicted: np.ndarray  # probabilidad media predicha en cada tramo
    observed_frequency: np.ndarray  # fracción de positivos observada en cada tramo
    count: np.ndarray  # ejemplos en cada tramo (los vacíos salen como NaN en las dos primeras)


def reliability_curve(y_true: np.ndarray, y_score: np.ndarray, bins: int = 10) -> Reliability:
    """Agrupa las predicciones en ``bins`` tramos de igual ancho en [0, 1] y mide la calibración.

    Para cada tramo compara la probabilidad media predicha con la frecuencia de positivos observada:
    un modelo bien calibrado las deja cerca de la diagonal. Los tramos sin ejemplos quedan como NaN
    para no inventar puntos. La interpretación debe considerar el subregistro (sección 6.2).
    """
    y_true, y_score = _check(y_true, y_score)
    if (y_score < 0).any() or (y_score > 1).any():
        raise ValueError("la curva de fiabilidad espera probabilidades en [0, 1]")
    if bins < 1:
        raise ValueError("bins debe ser al menos 1")

    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(y_score, edges[1:-1], right=False), 0, bins - 1)
    mean_pred = np.full(bins, np.nan)
    obs_freq = np.full(bins, np.nan)
    count = np.zeros(bins, dtype=int)
    for b in range(bins):
        sel = idx == b
        count[b] = int(sel.sum())
        if count[b]:
            mean_pred[b] = float(y_score[sel].mean())
            obs_freq[b] = float(y_true[sel].mean())
    return Reliability(mean_predicted=mean_pred, observed_frequency=obs_freq, count=count)
