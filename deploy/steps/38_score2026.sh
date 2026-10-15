#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer

for CORTE in dia 12utc; do
  echo "=== features $CORTE (2018-2026) ==="
  uv run python scripts/model/features.py --corte "$CORTE" --start 2018-04-01 --end 2026-07-31 2>&1 | tail -2
  echo "=== puntaje 2026 $CORTE ==="
  uv run python scripts/model/score.py --start 2026-04-01 --end 2026-07-31 --corte "$CORTE" 2>&1 | grep -v Warning | tail -3
done
echo "=== salidas ==="
ls -la data/outputs/
echo "SCORE2026_DONE"
