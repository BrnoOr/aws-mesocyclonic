#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== ruff --fix ==="
uv run ruff check --fix scripts/model tests/test_model_selection.py 2>&1 | tail -3 || true
uv run ruff format scripts/model tests/test_model_selection.py 2>&1 | tail -2 || true

echo "=== generar listas de días ==="
uv run python scripts/model/plan_days.py --n-control 200 2>&1 | tail -10
echo "=== conteos ==="
for g in eventos control ciego2025; do
  echo "$g: $(grep -c . data/tables/dias_${g}.txt 2>/dev/null || echo 0) días"
done
echo "=== índices ya existentes ==="
ls data/crops/south-central-austral/era5_indices/ 2>/dev/null | wc -l
echo "PLAN_DONE"
