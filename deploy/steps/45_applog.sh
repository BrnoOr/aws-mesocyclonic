#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "=== últimas 25 líneas del log de la app ==="
tail -25 data/tables/app.log
echo "=== outputs que lee la app ==="
ls -la data/outputs/*.csv data/outputs/*.md 2>/dev/null | awk '{print $5, $9}'
echo "LOG_DONE"
