"""API de inferencia de Vórtice (FastAPI): la consola de la web le pide los puntajes a esta API.

Rutas (todas bajo ``/api``, que es lo que nginx pasa a este proceso):

- ``GET /api/health``: estado y motor en uso.
- ``GET /api/model``: el checkpoint (modelo, variables, umbral, KPIs) y dónde corre.
- ``GET /api/days``: días con recorte ERA5 que se pueden puntuar.
- ``GET /api/day/{AAAAMMDD}``: puntaje, reglas físicas, índices clave y eventos, de 12 a 23 UTC.
- ``POST /api/predict``: probabilidades para filas de variables; el mismo contrato que el endpoint
  de SageMaker, para integraciones de terceros.

El motor (checkpoint local o endpoint de SageMaker) se elige con ``VORTICE_PREDICTOR``; ver
``predictors.py``.

Uso local::

    uv run uvicorn server:app --app-dir scripts/api --port 8000
"""

import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import predictors  # noqa: E402
import service  # noqa: E402

PREDICTOR = predictors.from_env()
_CACHE: dict[str, dict] = {}

app = FastAPI(
    title="Vórtice API",
    description="Puntaje de condiciones para mesociclones en el centro-sur de Chile.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


class PredictRequest(BaseModel):
    """Filas de variables, cada una con las columnas de ``/api/model`` → ``features``."""

    rows: list[dict[str, float]]


@app.get("/api/health")
def health() -> dict:
    """Responde si el proceso está arriba y con qué motor."""
    return {"status": "ok", "predictor": PREDICTOR.describe()}


@app.get("/api/model")
def model() -> dict:
    """Checkpoint en uso: tipo de modelo, variables, umbral, KPIs de validación y motor."""
    m = PREDICTOR.metadata
    return {
        "predictor": PREDICTOR.describe(),
        "model": m.get("model"),
        "feature_set": m.get("feature_set"),
        "features": PREDICTOR.features,
        "threshold": m.get("threshold"),
        "region": m.get("region"),
        "validation": m.get("folds"),
        "kpi_loyo": m.get("kpi_loyo"),
    }


@app.get("/api/days")
def days() -> dict:
    """Días disponibles para la consola."""
    return {"days": service.available_days()}


@app.get("/api/day/{day}")
def day(day: str) -> dict:
    """Puntaje del día completo; se calcula una vez por día y queda en memoria."""
    if not (day.isdigit() and len(day) == 8):
        raise HTTPException(400, "el día va como AAAAMMDD")
    if day not in _CACHE:
        try:
            _CACHE[day] = service.day_payload(day, PREDICTOR)
        except FileNotFoundError as err:
            raise HTTPException(404, f"no hay recorte ERA5 para {day}") from err
    return _CACHE[day]


@app.post("/api/predict")
def predict(req: PredictRequest) -> dict:
    """Probabilidad por fila; faltan columnas → 422 con la lista de lo que falta."""
    if not req.rows:
        return {"probabilities": []}
    x = pd.DataFrame(req.rows)
    missing = [f for f in PREDICTOR.features if f not in x.columns]
    if missing:
        raise HTTPException(422, f"faltan variables: {missing}")
    return {"probabilities": PREDICTOR.predict(x).round(4).tolist()}
