"""Pruebas de la API de Vórtice y del contrato con SageMaker, sin AWS ni red.

- La API responde sus rutas con el checkpoint local y los recortes de ``data/``.
- ``SageMakerPredictor`` y ``sagemaker/inference.py`` hablan el mismo idioma: un endpoint simulado
  que corre el manejador real devuelve lo mismo que el checkpoint local.
"""

import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "api"))

import predictors  # noqa: E402


def _load_inference() -> object:
    """Importa ``sagemaker/inference.py`` como módulo (la carpeta no es un paquete)."""
    spec = importlib.util.spec_from_file_location("inference", ROOT / "sagemaker" / "inference.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    """Cliente ``sagemaker-runtime`` falso: pasa el cuerpo por el manejador real del endpoint."""

    def __init__(self) -> None:
        """Carga el manejador y el checkpoint como lo haría el contenedor de SageMaker."""
        self.inference = _load_inference()
        self.bundle = self.inference.model_fn(str(ROOT))
        self.calls = 0

    def invoke_endpoint(self, **kw: object) -> dict:
        """Imita ``invoke_endpoint``: CSV de entrada, JSON de salida."""
        self.calls += 1
        x = self.inference.input_fn(kw["Body"], kw["ContentType"])
        body, _ = self.inference.output_fn(self.inference.predict_fn(x, self.bundle), kw["Accept"])
        return {"Body": io.BytesIO(body.encode("utf-8"))}


class PredictorTest(unittest.TestCase):
    """Elección del motor y equivalencia entre el checkpoint local y el endpoint."""

    def test_default_is_local(self) -> None:
        """Sin variables de entorno, el motor es el checkpoint local."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(predictors.from_env().kind, "local")

    def test_sagemaker_needs_endpoint(self) -> None:
        """Pedir SageMaker sin nombre de endpoint corta con un mensaje claro."""
        with (
            patch.dict(os.environ, {"VORTICE_PREDICTOR": "sagemaker"}, clear=True),
            self.assertRaises(SystemExit),
        ):
            predictors.from_env()

    def test_sagemaker_matches_local(self) -> None:
        """El endpoint (simulado con el manejador real) da las mismas probabilidades, por lotes."""
        local = predictors.LocalPredictor()
        x = pd.DataFrame(
            np.random.default_rng(1).normal(size=(5, len(local.features))) * 10,
            columns=local.features,
        )
        with patch("botocore.session.get_session") as session:
            fake = FakeRuntime()
            session.return_value.create_client.return_value = fake
            remote = predictors.SageMakerPredictor("vortice-test", "us-east-1")
            remote.batch_rows = 2
            got = remote.predict(x)
        np.testing.assert_allclose(got, local.predict(x), atol=1e-4)
        self.assertEqual(fake.calls, 3)


class ApiTest(unittest.TestCase):
    """Rutas de la API con el checkpoint local."""

    @classmethod
    def setUpClass(cls) -> None:
        """Levanta la app de FastAPI en memoria."""
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {"VORTICE_PREDICTOR": "local"}):
            import server
        cls.client = TestClient(server.app)
        cls.features = server.PREDICTOR.features

    def test_health_and_model(self) -> None:
        """``/api/health`` y ``/api/model`` dicen qué motor y qué checkpoint hay."""
        self.assertEqual(self.client.get("/api/health").json()["predictor"]["kind"], "local")
        model = self.client.get("/api/model").json()
        self.assertEqual(model["features"], self.features)

    def test_day_payload_shape(self) -> None:
        """Un día trae una grilla por hora con puntaje, reglas e índices del mismo largo."""
        days = self.client.get("/api/days").json()["days"]
        self.assertIn("20190530", days)
        d = self.client.get("/api/day/20190530").json()
        n = len(d["lats"]) * len(d["lons"])
        self.assertEqual(len(d["terrain"]), n)
        for h in d["hours"]:
            self.assertEqual(len(h["score"]), n)
            self.assertEqual(len(h["stp"]), n)
            self.assertTrue(all(len(v) == n for v in h["features"].values()))
            self.assertTrue(all(-1 <= s <= 100 for s in h["score"]))
        self.assertEqual(len(d["events"]), 5)

    def test_bad_requests(self) -> None:
        """Fecha mal escrita → 400; día sin recorte → 404; variables faltantes → 422."""
        self.assertEqual(self.client.get("/api/day/2019-05-30").status_code, 400)
        self.assertEqual(self.client.get("/api/day/20000101").status_code, 404)
        r = self.client.post("/api/predict", json={"rows": [{"shear_01": 10.0}]})
        self.assertEqual(r.status_code, 422)

    def test_predict(self) -> None:
        """``/api/predict`` devuelve una probabilidad por fila."""
        row = dict.fromkeys(self.features, 1.0)
        r = self.client.post("/api/predict", json={"rows": [row, row]})
        probs = r.json()["probabilities"]
        self.assertEqual(len(probs), 2)
        self.assertTrue(all(0.0 <= p <= 1.0 for p in probs))

    def test_snapshot_matches_api(self) -> None:
        """Los puntajes de respaldo de ``site/assets`` son los mismos que da la API (motor MLP).

        Los respaldos se generan con el motor desplegado (``vortice_mlp``), así que se comparan
        contra ese mismo motor, no contra el checkpoint local por omisión.
        """
        snap = ROOT / "site" / "assets" / "day_20190530.json"
        if not snap.exists():
            self.skipTest("falta site/assets; corre scripts/api/snapshot.py")
        import service

        pred = predictors.VortexMLPPredictor()
        api = service.day_payload("20190530", pred)
        self.assertEqual(json.loads(snap.read_text(encoding="utf-8"))["hours"], api["hours"])


class VortexMLPTest(unittest.TestCase):
    """El motor Vórtice (MLP de PU learning) servido con numpy, sin PyTorch."""

    @classmethod
    def setUpClass(cls) -> None:
        """Carga el motor del paquete numpy."""
        cls.pred = predictors.VortexMLPPredictor()

    def test_from_env_selects_mlp(self) -> None:
        """``VORTICE_PREDICTOR=vortice_mlp`` elige este motor."""
        with patch.dict(os.environ, {"VORTICE_PREDICTOR": "vortice_mlp"}, clear=True):
            self.assertEqual(predictors.from_env().kind, "vortice_mlp")

    def test_contract(self) -> None:
        """Expone las 11 variables y metadatos del checkpoint."""
        self.assertEqual(len(self.pred.features), 11)
        self.assertIn("shear_01", self.pred.features)
        self.assertEqual(self.pred.metadata["model"], "vortice-pu-mlp")

    def test_predict_is_probability(self) -> None:
        """``predict`` devuelve una probabilidad cruda en [0, 1] por fila."""
        x = pd.DataFrame(
            np.random.default_rng(3).normal(size=(8, 11)) * 5, columns=self.pred.features
        )
        p = self.pred.predict(x)
        self.assertEqual(len(p), 8)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in p))

    def test_display_score_is_percentile(self) -> None:
        """``display_score`` ordena igual que ``predict`` y cubre el rango [0, 1]."""
        x = pd.DataFrame(
            np.random.default_rng(4).normal(size=(50, 11)) * 5, columns=self.pred.features
        )
        raw, disp = self.pred.predict(x), self.pred.display_score(x)
        self.assertAlmostEqual(float(disp.min()), 0.0)
        self.assertAlmostEqual(float(disp.max()), 1.0)
        # El orden del percentil coincide con el del puntaje crudo.
        self.assertEqual(raw.argsort().tolist(), disp.argsort().tolist())


if __name__ == "__main__":
    unittest.main()
