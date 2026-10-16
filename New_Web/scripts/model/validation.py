"""Esquema de validación por eventos completos para el modelo tabular (docs, sección 6.3).

El catálogo trae horas consecutivas del mismo brote (p. ej. los siete tornados del 30–31 de mayo de
2019). Si esas horas se reparten entre entrenamiento y evaluación, el modelo ve situaciones casi
idénticas en ambos lados y aparenta un rendimiento mayor del real: es la *fuga de información* que
describe la sección 6.3. Para evitarla, aquí la unidad que nunca se separa es el **evento completo**,
y los pliegues se arman dejando **un año fuera por iteración**.

Decisiones de diseño (todas documentadas, como pide la sección 6.1):

- **Agrupación por evento.** Un evento reúne todas las horas de un mismo brote. Por defecto se
  agrupan los registros del catálogo que caen dentro de ``gap`` horas unos de otros (brote = racha
  de actividad continua); así el 30 y 31 de mayo de 2019 quedan en un solo grupo. Quien ya tenga un
  identificador de evento puede pasarlo y se respeta tal cual.
- **Un año fuera por iteración (LOYO).** Cada pliegue deja fuera un año calendario completo y entrena
  con el resto. Compara temporadas entre sí y es el bloque temporal natural de una climatología.
- **Caso de desarrollo reservado.** El brote del 30 de mayo de 2019 se usa en todo el documento para
  explorar y comprobar cálculos, así que **no** puede volver a aparecer como prueba ciega: se retira
  de los pliegues y se marca aparte. Es una decisión, no un parámetro que convenga apagar sin avisar.

Los controles difíciles (días con convección profunda sin rotación documentada, sección 6.2) entran
como ejemplos **no etiquetados**, no como negativos confirmados: aquí se tratan como filas con
``event_id`` propio y ``year`` el de su fecha, de modo que la separación temporal los cubre igual.

Este módulo es puro: recibe arreglos y fechas, no lee disco ni depende de un modelo entrenado.
"""

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np

# Caso de desarrollo del documento: el brote del 30–31 de mayo de 2019 (sección 6.3).
DEVELOPMENT_CASE = (dt.date(2019, 5, 30), dt.date(2019, 5, 31))
EVENT_GAP_HOURS = 24.0  # separación máxima dentro de un mismo brote


@dataclass(frozen=True)
class Fold:
    """Un pliegue de la validación: índices de entrenamiento y de prueba de un año reservado."""

    year: int
    train: np.ndarray
    test: np.ndarray


def event_ids(
    times: Sequence[dt.datetime | np.datetime64], gap: float = EVENT_GAP_HOURS
) -> np.ndarray:
    """Agrupa marcas de tiempo en eventos: una racha nueva empieza al superar ``gap`` horas de hueco.

    Devuelve un arreglo de enteros (0, 1, 2, …) con un identificador por fila, en el orden de
    ``times``. Las filas de un mismo brote comparten identificador aunque no estén ordenadas en la
    entrada; se ordenan internamente para medir los huecos.
    """
    stamps = np.array([np.datetime64(t) for t in times], dtype="datetime64[s]")
    order = np.argsort(stamps, kind="stable")
    gaps = np.diff(stamps[order]).astype("timedelta64[s]").astype(float) / 3600.0
    group_sorted = np.concatenate(([0], np.cumsum(gaps > gap).astype(int)))
    ids = np.empty(len(stamps), dtype=int)
    ids[order] = group_sorted
    return ids


def _as_dates(dates: Sequence[dt.date | dt.datetime | np.datetime64]) -> np.ndarray:
    """Normaliza una secuencia de fechas a ``datetime64[D]`` para comparar y extraer el año."""
    return np.array([np.datetime64(d, "D") for d in dates], dtype="datetime64[D]")


def development_mask(dates: Sequence[dt.date | dt.datetime | np.datetime64]) -> np.ndarray:
    """Máscara booleana de las filas que caen en el caso de desarrollo (30–31 de mayo de 2019)."""
    days = _as_dates(dates)
    reserved = _as_dates(DEVELOPMENT_CASE)
    return np.isin(days, reserved)


def leave_one_year_out(
    dates: Sequence[dt.date | dt.datetime | np.datetime64],
    groups: Sequence[int] | np.ndarray,
    *,
    hold_out_development: bool = True,
) -> Iterator[Fold]:
    """Genera un pliegue por año: prueba el año reservado, entrena con los demás.

    - ``dates``: fecha de cada fila (define el año del bloque temporal).
    - ``groups``: identificador de evento de cada fila; ningún evento se parte entre entrenamiento y
      prueba. Si un evento cruzara el cambio de año, se asigna al año de su primera fila para que no
      quede en ambos lados.
    - ``hold_out_development``: si es ``True`` (por defecto), las filas del caso de desarrollo no
      entran a ningún pliegue, ni de entrenamiento ni de prueba (sección 6.3).

    Rechaza que una misma fecha aparezca con dos eventos distintos solo cuando eso partiría el año;
    el control real es que cada evento viva en un único año.
    """
    days = _as_dates(dates)
    groups = np.asarray(groups)
    if len(days) != len(groups):
        raise ValueError("dates y groups deben tener el mismo largo")

    keep = ~development_mask(dates) if hold_out_development else np.ones(len(days), bool)
    years = days.astype("datetime64[Y]").astype(int) + 1970

    # Año de cada evento = año de su fecha más temprana, para no partir un brote que cruza el 1 de enero.
    event_year: dict[int, int] = {}
    first_seen: dict[int, np.datetime64] = {}
    for g, day, y in zip(groups, days, years, strict=True):
        g = int(g)
        if g not in first_seen or day < first_seen[g]:
            first_seen[g] = day
            event_year[g] = int(y)
    row_year = np.array([event_year[int(g)] for g in groups])

    for year in sorted({int(y) for y, k in zip(row_year, keep, strict=True) if k}):
        test = np.flatnonzero(keep & (row_year == year))
        train = np.flatnonzero(keep & (row_year != year))
        if test.size:
            yield Fold(year=year, train=train, test=test)


def split_development(
    dates: Sequence[dt.date | dt.datetime | np.datetime64],
) -> tuple[np.ndarray, np.ndarray]:
    """Separa los índices en (resto, caso de desarrollo).

    El primer arreglo alimenta la validación cruzada; el segundo se guarda para la comparación
    cualitativa de la sección 6.5 (comparar un caso con el 30 de mayo de 2019), nunca como prueba
    ciega.
    """
    dev = development_mask(dates)
    return np.flatnonzero(~dev), np.flatnonzero(dev)
