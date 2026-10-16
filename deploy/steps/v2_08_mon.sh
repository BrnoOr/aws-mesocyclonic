#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
pgrep -f "scripts/model" >/dev/null && echo "RERUN: EN CURSO" || echo "RERUN: TERMINADO (o no corre)"
echo "=== log ==="
tail -8 data/tables/rerun.log 2>/dev/null || echo "(sin log)"
echo "MON_RERUN_DONE"
