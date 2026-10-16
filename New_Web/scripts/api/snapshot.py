#!/usr/bin/env python3
"""Guarda en ``site/assets/`` lo que la consola necesita para funcionar sin la API (modo demostración).

Escribe ``days.json``, ``model.json`` y un ``day_AAAAMMDD.json`` por cada recorte ERA5 disponible,
con el mismo formato que devuelve la API. Copia además la foto de la portada.

Uso::

    uv run python scripts/api/snapshot.py
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import predictors  # noqa: E402
import service  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "assets"
PHOTO = ROOT.parent / "scripts" / "viewer" / "assets" / "tornado_los_angeles.webp"


def main() -> None:
    """Puntúa cada día disponible con el checkpoint local y escribe los JSON de respaldo."""
    OUT.mkdir(parents=True, exist_ok=True)
    pred = predictors.LocalPredictor()
    days = service.available_days()
    for day in days:
        payload = service.day_payload(day, pred)
        (OUT / f"day_{day}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"day_{day}.json: {len(payload['hours'])} horas, {len(payload['events'])} eventos")
    (OUT / "days.json").write_text(json.dumps({"days": days}), encoding="utf-8")
    m = pred.metadata
    model = {
        "predictor": {
            "kind": "snapshot",
            "where": "puntajes precalculados con el checkpoint local",
        },
        "model": m.get("model"),
        "feature_set": m.get("feature_set"),
        "features": pred.features,
        "threshold": m.get("threshold"),
    }
    (OUT / "model.json").write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    if PHOTO.exists():
        shutil.copy2(PHOTO, OUT / PHOTO.name)
    print(f"listo en {OUT}")


if __name__ == "__main__":
    main()
