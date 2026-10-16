"""Motores de inferencia de Vórtice: el mismo contrato para el checkpoint local y para SageMaker.

La API y la web no saben dónde corre el modelo. Piden probabilidades a un ``Predictor``:

- ``LocalPredictor``: carga ``modelo.joblib`` (el checkpoint actual) en el mismo proceso.
- ``SageMakerPredictor``: llama a un endpoint de Amazon SageMaker que sirve el mismo checkpoint
  empaquetado con ``sagemaker/package_model.py``. Es el camino futuro; hoy no hay endpoint desplegado.

Se elige con variables de entorno:

- ``VORTICE_PREDICTOR``: ``local`` (por omisión) o ``sagemaker``.
- ``VORTICE_SAGEMAKER_ENDPOINT``: nombre del endpoint (obligatorio con ``sagemaker``).
- ``AWS_REGION``: región del endpoint (por omisión ``us-east-1``).

El contrato del endpoint es el de ``sagemaker/inference.py``: entra un CSV sin encabezado con las
columnas en el orden de ``features`` y sale ``{"probabilities": [...]}``.
"""

import io
import json
import os
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "modelo.joblib"
VORTICE_MLP = ROOT / "vortice_model.npz"


class Predictor(Protocol):
    """Lo que la API necesita de un motor: nombre, variables de entrada y probabilidades."""

    kind: str
    features: list[str]
    metadata: dict

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Probabilidad de mesociclón por fila de ``x`` (columnas en el orden de ``features``)."""
        ...

    def describe(self) -> dict:
        """Resumen para la interfaz: tipo de motor y dónde corre."""
        ...


class LocalPredictor:
    """El checkpoint ``modelo.joblib`` cargado en el proceso de la API."""

    kind = "local"

    def __init__(self, path: Path = CHECKPOINT) -> None:
        """Carga el bundle (``model``, ``features``, ``metadata``) que deja ``train.py``."""
        bundle = joblib.load(path)
        self.model = bundle["model"]
        self.features = list(bundle["features"])
        self.metadata = dict(bundle["metadata"])
        self.path = path

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Probabilidades del clasificador para la clase positiva."""
        return self.model.predict_proba(x[self.features])[:, 1]

    def describe(self) -> dict:
        """Motor local: el archivo del checkpoint."""
        return {"kind": self.kind, "where": f"checkpoint local ({self.path.name})"}


class SageMakerPredictor:
    """Un endpoint de SageMaker que sirve el mismo checkpoint (``sagemaker/inference.py``)."""

    kind = "sagemaker"
    batch_rows = 2000  # el cuerpo de una invocación tiene un límite de 6 MB

    def __init__(self, endpoint: str, region: str, path: Path = CHECKPOINT) -> None:
        """Lee las variables y metadatos del checkpoint local y prepara el cliente del endpoint."""
        import botocore.session

        bundle = joblib.load(path)
        self.features = list(bundle["features"])
        self.metadata = dict(bundle["metadata"])
        self.endpoint = endpoint
        self.region = region
        self.client = botocore.session.get_session().create_client(
            "sagemaker-runtime", region_name=region
        )

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Envía ``x`` por lotes al endpoint como CSV y junta las probabilidades."""
        out: list[float] = []
        for start in range(0, len(x), self.batch_rows):
            buf = io.StringIO()
            x[self.features].iloc[start : start + self.batch_rows].to_csv(
                buf, header=False, index=False
            )
            resp = self.client.invoke_endpoint(
                EndpointName=self.endpoint,
                ContentType="text/csv",
                Accept="application/json",
                Body=buf.getvalue().encode("utf-8"),
            )
            out.extend(json.loads(resp["Body"].read())["probabilities"])
        return np.asarray(out, dtype=float)

    def describe(self) -> dict:
        """Motor remoto: el endpoint y su región."""
        return {"kind": self.kind, "where": f"endpoint {self.endpoint} ({self.region})"}


class VortexMLPPredictor:
    """El modelo Vórtice (MLP de *PU learning*) servido con numpy, sin PyTorch.

    Carga ``vortice_model.npz`` (lo genera ``convert_vortice.py`` desde ``vortice.pt``) y reproduce
    el paso hacia adelante del MLP 11 → 64 → 32 → 1. El *dropout* es identidad en inferencia.

    El modelo está entrenado con *PU learning*: su salida es un **puntaje de orden**, no una
    probabilidad calibrada, y como los eventos son rarísimos (``pi`` ≈ 0,3 %) las probabilidades son
    diminutas (del orden de 0,001). Por eso:

    - ``predict`` devuelve la **probabilidad cruda** (sigmoide del logit): el contrato honesto para
      ``/api/predict`` y para comparar con otros motores.
    - ``display_score`` devuelve el **percentil dentro de la llamada** (0–1), que es lo que el mapa
      necesita para pintar un rango legible 0–100 conservando el orden del modelo.
    """

    kind = "vortice_mlp"

    def __init__(self, path: Path = VORTICE_MLP) -> None:
        """Lee pesos, normalización y metadatos del paquete numpy."""
        z = np.load(path, allow_pickle=True)
        self.w0, self.b0 = z["w0"], z["b0"]
        self.w3, self.b3 = z["w3"], z["b3"]
        self.w6, self.b6 = z["w6"], z["b6"]
        self.mean, self.std = z["mean"], z["std"]
        self.features = [str(f) for f in z["features"]]
        self.path = path
        self.metadata = {
            "model": "vortice-pu-mlp",
            "feature_set": "era5-11" + ("-goes" if bool(z["use_goes"]) else ""),
            "region": "south-central",
            # El umbral crudo del checkpoint ordena ~top 5 % del dominio; en el mapa el puntaje es
            # percentil, así que se muestra como tal (95) para que la lectura 0–100 tenga sentido.
            "threshold": 0.95,
            "raw_threshold": float(z["threshold"]),
            "pi": float(z["pi"]),
            "score": "percentil del puntaje crudo del modelo dentro de cada hora (0–100)",
        }

    def _logit(self, x: pd.DataFrame) -> np.ndarray:
        """Logit del MLP para ``x`` (columnas en el orden de ``features``)."""
        xn = (np.nan_to_num(x[self.features].to_numpy(dtype=float)) - self.mean) / self.std
        h = np.maximum(xn @ self.w0.T + self.b0, 0.0)
        h = np.maximum(h @ self.w3.T + self.b3, 0.0)
        return (h @ self.w6.T + self.b6).ravel()

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Probabilidad cruda (sigmoide estable del logit) por fila."""
        z = self._logit(x)
        with np.errstate(over="ignore"):
            return np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))

    def display_score(self, x: pd.DataFrame) -> np.ndarray:
        """Percentil (0–1) del puntaje crudo dentro de esta llamada, para pintar el mapa."""
        p = self.predict(x)
        if len(p) <= 1:
            return p
        rank = p.argsort().argsort().astype(float)
        return rank / (len(p) - 1)

    def describe(self) -> dict:
        """Motor local del MLP de Vórtice."""
        return {"kind": self.kind, "where": f"MLP PU numpy ({self.path.name})"}


def from_env() -> Predictor:
    """El motor que piden las variables de entorno (``local`` si no se pide nada)."""
    kind = os.environ.get("VORTICE_PREDICTOR", "local").strip().lower()
    if kind == "local":
        return LocalPredictor()
    if kind in ("vortice_mlp", "vortice", "mlp"):
        return VortexMLPPredictor()
    if kind == "sagemaker":
        endpoint = os.environ.get("VORTICE_SAGEMAKER_ENDPOINT", "").strip()
        if not endpoint:
            raise SystemExit("VORTICE_PREDICTOR=sagemaker necesita VORTICE_SAGEMAKER_ENDPOINT")
        return SageMakerPredictor(endpoint, os.environ.get("AWS_REGION", "us-east-1"))
    raise SystemExit(
        f"VORTICE_PREDICTOR desconocido: {kind!r} (usa local, vortice_mlp o sagemaker)"
    )
