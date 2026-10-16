#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

pkill -f "app_resultados.py" 2>/dev/null || true
sleep 2
nohup uv run streamlit run scripts/model/app_resultados.py \
  --server.address=0.0.0.0 --server.port=8502 --server.headless=true \
  --server.enableCORS=false --server.enableXsrfProtection=false \
  --browser.gatherUsageStats=false > data/tables/app.log 2>&1 &
echo "PID: $!"
for i in $(seq 1 40); do
  curl -fsS "http://localhost:8502/_stcore/health" >/dev/null 2>&1 && { echo "OK health 8502"; break; }
  sleep 3
done
echo "=== log app (errores?) ==="
tail -12 data/tables/app.log
echo "=== outputs frescos ==="
ls -la --time-style=+%H:%M data/outputs/*.csv data/outputs/*.md | awk '{print $6, $7}'
echo "APP_RELAUNCH_DONE"
