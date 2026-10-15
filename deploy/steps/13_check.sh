#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== ruff check (scripts/model y tests) ==="
uv run ruff check scripts/model tests/test_model_dataset.py 2>&1 | tail -30 || true
echo "=== ruff format --check ==="
uv run ruff format --check scripts/model tests/test_model_dataset.py 2>&1 | tail -10 || true
echo "=== pruebas del modelo ==="
uv run python -m unittest tests.test_model_dataset -v 2>&1 | tail -10
echo "CHECK_DONE"
