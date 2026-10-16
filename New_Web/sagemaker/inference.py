"""Manejador de inferencia de Vórtice para el contenedor de scikit-learn de Amazon SageMaker.

SageMaker llama a estas cuatro funciones. El checkpoint (``modelo.joblib``) viaja en la raíz de
``model.tar.gz`` y este archivo en ``code/`` (lo arma ``package_model.py``).

Contrato (el mismo que usa ``scripts/api/predictors.py``):

- Entrada ``text/csv``: filas sin encabezado, columnas en el orden de ``features`` del checkpoint.
- Entrada ``application/json``: ``{"rows": [{variable: valor, ...}, ...]}``.
- Salida ``application/json``: ``{"probabilities": [p, ...]}``.
"""

import io
import json
import os

import joblib
import pandas as pd


def model_fn(model_dir: str) -> dict:
    """Carga el bundle ``{model, features, metadata}``."""
    return joblib.load(os.path.join(model_dir, "modelo.joblib"))


def input_fn(body: str | bytes, content_type: str) -> pd.DataFrame:
    """Convierte el cuerpo de la petición en un DataFrame (sin ordenar columnas todavía)."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    if content_type == "text/csv":
        return pd.read_csv(io.StringIO(text), header=None)
    if content_type == "application/json":
        return pd.DataFrame(json.loads(text)["rows"])
    raise ValueError(f"tipo de contenido no soportado: {content_type}")


def predict_fn(x: pd.DataFrame, bundle: dict) -> list[float]:
    """Probabilidad de la clase positiva, con las columnas en el orden del checkpoint."""
    feats = list(bundle["features"])
    if list(x.columns) == list(range(len(feats))):
        x.columns = feats
    return bundle["model"].predict_proba(x[feats])[:, 1].round(4).tolist()


def output_fn(probabilities: list[float], accept: str) -> tuple[str, str]:
    """Respuesta JSON."""
    return json.dumps({"probabilities": probabilities}), "application/json"
