#!/usr/bin/env bash
# Despliega el sitio de producto de Vórtice detrás de un solo puerto:
#   /       página con la consola (nginx, contenedor vortice-site)
#   /api/   API de inferencia (FastAPI, contenedor vortice-api, sin puerto publicado)
# El puerto publicado es WEB_PORT (8502), el que usa la distribución CloudFront (cf_app.json), así que
# el enlace público no cambia. Reemplaza lo que hubiera en ese puerto (la app Streamlit o la landing).
# Idempotente: recrea los contenedores cada vez.
# Variables de entorno: REPO_URL, REPO_REF, WEB_PORT, VORTICE_PREDICTOR, VORTICE_SAGEMAKER_ENDPOINT,
# AWS_REGION (las tres últimas eligen el motor de la API; por omisión, el checkpoint local).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/BrnoOr/aws-mesocyclonic.git}"
REPO_REF="${REPO_REF:-main}"
WEB_PORT="${WEB_PORT:-8502}"
VORTICE_PREDICTOR="${VORTICE_PREDICTOR:-local}"
VORTICE_SAGEMAKER_ENDPOINT="${VORTICE_SAGEMAKER_ENDPOINT:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"
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
ls -la "${APP_DIR}/New_Web/site" "${APP_DIR}/New_Web/site/assets"

echo "=== 3/6 Build de las imágenes (arquitectura del host) ==="
docker build -t vortice:latest "${APP_DIR}/New_Web"
docker build -t vortice-site:latest "${APP_DIR}/New_Web/site"

echo "=== 4/6 API de inferencia (motor: ${VORTICE_PREDICTOR}) ==="
docker network inspect "${NET}" >/dev/null 2>&1 || docker network create "${NET}"
docker rm -f vortice-api >/dev/null 2>&1 || true
docker run -d \
  --name vortice-api \
  --network "${NET}" \
  --restart unless-stopped \
  -e VORTICE_PREDICTOR="${VORTICE_PREDICTOR}" \
  -e VORTICE_SAGEMAKER_ENDPOINT="${VORTICE_SAGEMAKER_ENDPOINT}" \
  -e AWS_REGION="${AWS_REGION}" \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')\"" \
  vortice:latest \
  uvicorn server:app --app-dir scripts/api --host 0.0.0.0 --port 8000

echo "=== 5/6 Sitio en el puerto ${WEB_PORT} ==="
# Libera el puerto (antes lo ocupaban vortice o vortice-web) y retira la app Streamlit y la landing.
PREV=$(docker ps -q --filter "publish=${WEB_PORT}")
if [ -n "${PREV}" ]; then
  echo "Deteniendo contenedor(es) que ocupaban el puerto ${WEB_PORT}: ${PREV}"
  docker rm -f ${PREV} >/dev/null 2>&1 || true
fi
docker rm -f vortice vortice-web vortice-site >/dev/null 2>&1 || true
docker run -d \
  --name vortice-site \
  --network "${NET}" \
  --restart unless-stopped \
  -p "${WEB_PORT}:80" \
  vortice-site:latest

echo "=== 6/6 Esperando a que respondan el sitio y la API ==="
OK=0
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:${WEB_PORT}/" >/dev/null 2>&1 \
     && curl -fsS "http://localhost:${WEB_PORT}/api/health" >/dev/null 2>&1; then
    echo "OK: sitio en / y API en /api/ (puerto ${WEB_PORT})"
    curl -fsS "http://localhost:${WEB_PORT}/api/health"; echo
    docker ps --filter "name=vortice" --format "{{.Names}} {{.Status}} {{.Ports}}"
    OK=1
    break
  fi
  sleep 3
done
if [ "${OK}" != "1" ]; then
  echo "ERROR: no respondieron a tiempo. Logs:"
  docker logs --tail 60 vortice-site || true
  docker logs --tail 60 vortice-api || true
  exit 1
fi
echo "SITE_DEPLOY_DONE"
exit 0
