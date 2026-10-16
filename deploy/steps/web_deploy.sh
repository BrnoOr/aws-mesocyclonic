#!/usr/bin/env bash
# Despliega la página del proyecto (New_Web/landing) y la app Vórtice detrás de un solo puerto:
#   /       página del proyecto (nginx, contenedor vortice-web)
#   /app/   app Streamlit de Vórtice (contenedor vortice, sin puerto publicado)
# El puerto publicado es WEB_PORT (8502), el mismo que usa la distribución CloudFront (cf_app.json),
# así que el enlace público no cambia. Idempotente: recrea los contenedores cada vez.
# Variables de entorno esperadas: REPO_URL, REPO_REF, WEB_PORT.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/BrnoOr/aws-mesocyclonic.git}"
REPO_REF="${REPO_REF:-main}"
WEB_PORT="${WEB_PORT:-8502}"
APP_DIR="/opt/vortice"
NET="vortice-net"

echo "=== 1/6 Dependencias (git, docker) ==="
command -v git >/dev/null 2>&1 || dnf install -y git
command -v docker >/dev/null 2>&1 || { echo "ERROR: falta docker en la instancia"; exit 1; }

echo "=== 2/6 Repo en ${APP_DIR} (ref ${REPO_REF}) ==="
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" reset --hard "origin/${REPO_REF}" 2>/dev/null || git -C "${APP_DIR}" checkout "${REPO_REF}"
else
  rm -rf "${APP_DIR}"
  git clone "${REPO_URL}" "${APP_DIR}"
  git -C "${APP_DIR}" checkout "${REPO_REF}" 2>/dev/null || true
fi
git -C "${APP_DIR}" log -1 --oneline
ls -la "${APP_DIR}/New_Web/landing" "${APP_DIR}/New_Web/landing/assets"

echo "=== 3/6 Build de las imágenes (arquitectura del host) ==="
docker build -t vortice:latest "${APP_DIR}/New_Web"
docker build -t vortice-web:latest "${APP_DIR}/New_Web/landing"

echo "=== 4/6 Red Docker ${NET} y app Vórtice en /app/ ==="
docker network inspect "${NET}" >/dev/null 2>&1 || docker network create "${NET}"
docker rm -f vortice >/dev/null 2>&1 || true
docker run -d \
  --name vortice \
  --network "${NET}" \
  --restart unless-stopped \
  -e STREAMLIT_SERVER_BASE_URL_PATH=app \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8501/app/_stcore/health')\"" \
  vortice:latest

echo "=== 5/6 Página del proyecto en el puerto ${WEB_PORT} ==="
# Libera el puerto de cualquier contenedor previo (el deploy anterior publicaba Vórtice en 8502).
PREV=$(docker ps -q --filter "publish=${WEB_PORT}")
if [ -n "${PREV}" ]; then
  echo "Deteniendo contenedor(es) que ocupaban el puerto ${WEB_PORT}: ${PREV}"
  docker rm -f ${PREV} >/dev/null 2>&1 || true
fi
docker rm -f vortice-web >/dev/null 2>&1 || true
docker run -d \
  --name vortice-web \
  --network "${NET}" \
  --restart unless-stopped \
  -p "${WEB_PORT}:80" \
  vortice-web:latest

echo "=== 6/6 Esperando a que respondan la página y la app ==="
OK=0
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:${WEB_PORT}/" >/dev/null 2>&1 \
     && curl -fsS "http://localhost:${WEB_PORT}/app/_stcore/health" >/dev/null 2>&1; then
    echo "OK: página en / y app en /app/ (puerto ${WEB_PORT})"
    docker ps --filter "name=vortice" --format "{{.Names}} {{.Status}} {{.Ports}}"
    OK=1
    break
  fi
  sleep 3
done
if [ "${OK}" != "1" ]; then
  echo "ERROR: no respondieron a tiempo. Logs:"
  docker logs --tail 60 vortice-web || true
  docker logs --tail 60 vortice || true
  exit 1
fi
echo "WEB_DEPLOY_DONE"
exit 0
