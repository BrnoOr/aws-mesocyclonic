#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
APP=/opt/mesocyclonic-viewer
cd "$APP"

echo "=== prueba del etiquetado (sin datos) ==="
uv run python -m unittest tests.test_model_dataset -v 2>&1 | tail -20

echo "=== build_dataset (2019-05-30) ==="
uv run python scripts/model/build_dataset.py --start 2019-05-30 --force 2>&1 | tail -20

echo "=== train ==="
uv run python scripts/model/train.py 2>&1 | tail -40

echo "=== score (genera proyecciones) ==="
uv run python scripts/model/score.py --start 2019-05-30 --top 50 2>&1 | tail -20

echo "=== artefactos generados ==="
ls -la data/model/ 2>/dev/null
find data/crops -name 'score_*.nc' 2>/dev/null
echo "RUN_DONE"
