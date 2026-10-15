#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
export PYTHONWARNINGS="ignore::FutureWarning"
cd /opt/mesocyclonic-viewer

echo "===================== DECIDE dia ====================="
uv run python scripts/model/decide.py --corte dia 2>&1 | tail -6
echo "===================== CV 12utc ====================="
uv run python scripts/model/cv.py --corte 12utc 2>&1 | grep -v FutureWarning | tail -12
echo "===================== DECIDE 12utc ====================="
uv run python scripts/model/decide.py --corte 12utc 2>&1 | tail -6
echo "=== cv_report.csv ==="
cat data/outputs/cv_report.csv
echo "=== salidas ==="
ls data/outputs/
echo "CVALL_DONE"
