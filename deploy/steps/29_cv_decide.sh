#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

for CORTE in dia 12utc; do
  echo "===================== CV $CORTE ====================="
  uv run python scripts/model/cv.py --corte "$CORTE" 2>&1 | tail -20
  echo "===================== DECIDE $CORTE ====================="
  uv run python scripts/model/decide.py --corte "$CORTE" 2>&1 | tail -8
done
echo "=== salidas ==="
ls -la data/outputs/
echo "CV_DONE"
