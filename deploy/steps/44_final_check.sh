#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer
echo "=== ruff --fix sobre todo el módulo ==="
uv run ruff check --fix scripts/model tests/test_model_selection.py 2>&1 | tail -4 || true
uv run ruff format scripts/model tests/test_model_selection.py 2>&1 | tail -2 || true
echo "=== check final ==="
uv run ruff check scripts/model tests/test_model_selection.py 2>&1 | tail -8 && echo RUFF_OK || echo "RUFF: quedan avisos"
echo "=== tests ==="
uv run python -m unittest tests.test_model_selection 2>&1 | tail -5
echo "=== app viva? ==="
pgrep -f app_resultados.py >/dev/null && echo "SI (8502)" || echo "NO"
curl -fsS http://localhost:8502/_stcore/health && echo " <- health OK" || echo "sin health"
echo "FINAL_DONE"
