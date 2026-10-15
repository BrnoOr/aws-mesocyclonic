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

echo "=== esperando a que responda ==="
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:8502/_stcore/health" >/dev/null 2>&1; then
    echo "OK: la app responde en 8502"
    break
  fi
  sleep 3
done
curl -s "http://localhost:8502/_stcore/health" || echo "(sin respuesta)"
echo ""
echo "=== log ==="
tail -20 data/tables/app.log
echo "APP_DONE"
