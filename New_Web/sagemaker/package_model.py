#!/usr/bin/env python3
"""Empaqueta el checkpoint de Vórtice como ``model.tar.gz`` para un endpoint de SageMaker.

Estructura que espera el contenedor de scikit-learn de SageMaker::

    model.tar.gz
    ├── modelo.joblib
    └── code/
        ├── inference.py
        └── requirements.txt

Prueba además el manejador en local (``model_fn`` → ``input_fn`` → ``predict_fn``) con filas
sintéticas antes de escribir el paquete. No sube nada a AWS: los pasos para subirlo y crear el
endpoint están en ``sagemaker/README.md``.

Uso::

    uv run python sagemaker/package_model.py
"""

import importlib.util
import io
import tarfile
import tempfile
from pathlib import Path

import joblib
import numpy as np
import sklearn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECKPOINT = ROOT / "modelo.joblib"
OUT = HERE / "model.tar.gz"


def smoke_test() -> None:
    """Corre el manejador sobre 3 filas CSV y verifica que salgan 3 probabilidades en [0, 1]."""
    spec = importlib.util.spec_from_file_location("inference", HERE / "inference.py")
    assert spec and spec.loader
    inference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inference)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = joblib.load(CHECKPOINT)
        joblib.dump(bundle, Path(tmp) / "modelo.joblib")
        loaded = inference.model_fn(tmp)
        rows = np.random.default_rng(0).normal(size=(3, len(loaded["features"])))
        csv = "\n".join(",".join(f"{v:.3f}" for v in r) for r in rows)
        probs = inference.predict_fn(inference.input_fn(csv, "text/csv"), loaded)
        body, _ = inference.output_fn(probs, "application/json")
    assert len(probs) == 3 and all(0.0 <= p <= 1.0 for p in probs), probs
    print(f"manejador OK: {body}")


def main() -> None:
    """Prueba el manejador y escribe ``model.tar.gz``."""
    smoke_test()
    requirements = f"scikit-learn=={sklearn.__version__}\njoblib\npandas\n"
    with tarfile.open(OUT, "w:gz") as tar:
        tar.add(CHECKPOINT, arcname="modelo.joblib")
        tar.add(HERE / "inference.py", arcname="code/inference.py")
        info = tarfile.TarInfo("code/requirements.txt")
        data = requirements.encode("utf-8")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    print(f"{OUT} ({OUT.stat().st_size / 1e6:.1f} MB) · scikit-learn {sklearn.__version__}")


if __name__ == "__main__":
    main()
