#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== uv sync (pyyaml) ==="
uv sync 2>&1 | tail -3
echo "=== ruff check ==="
uv run ruff check scripts/model tests/test_model_selection.py 2>&1 | tail -25 || true
echo "=== pruebas del sistema de selección ==="
uv run python -m unittest tests.test_model_selection -v 2>&1 | tail -25
echo "TEST_DONE"
