#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
APP=/opt/mesocyclonic-viewer
cd "$APP"

echo "=== 1/3 instalar uv (si falta) ==="
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "=== 2/3 añadir scikit-learn a pyproject si no está ==="
if ! grep -q "scikit-learn" pyproject.toml; then
  # Inserta scikit-learn tras la línea de scipy
  sed -i 's/\("scipy>=1.18.1",\)/"scikit-learn>=1.5.0",\n    \1/' pyproject.toml
fi
grep -n "scikit-learn\|scipy" pyproject.toml | head

echo "=== 3/3 uv sync (crea .venv arm64) ==="
uv sync 2>&1 | tail -15
echo "--- python del venv ---"
.venv/bin/python --version
.venv/bin/python -c "import sklearn, pandas, xarray, pyarrow; print('sklearn', sklearn.__version__)"
echo "SETUP_DONE"
