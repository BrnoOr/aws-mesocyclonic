#!/usr/bin/env bash
# Despliega la web "Vórtice" (New_Web/scripts/webapp/model_app.py) en la EC2, dentro de Docker.
# Clona/actualiza el repo, construye la imagen autocontenida de New_Web (arm64) y (re)arranca el
# contenedor en VORTICE_PORT. Idempotente: se puede volver a correr; recrea el contenedor cada vez.
# Variables de entorno esperadas: REPO_URL, REPO_REF, VORTICE_PORT.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/BrnoOr/aws-mesocyclonic.git}"
REPO_REF="${REPO_REF:-main}"
VORTICE_PORT="${VORTICE_PORT:-8502}"   # alineado con la distribución CloudFront (cf_app.json)
APP_DIR="/opt/vortice"
WEB_SUBDIR="New_Web"
IMAGE="vortice:latest"
CONTAINER="vortice"

echo "=== 1/5 Dependencias (git, docker) ==="
command -v git >/dev/null 2>&1 || dnf install -y git
command -v docker >/dev/null 2>&1 || { echo "ERROR: falta docker en la instancia"; exit 1; }

echo "=== 2/5 Repo en ${APP_DIR} (ref ${REPO_REF}) ==="
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" reset --hard "origin/${REPO_REF}" 2>/dev/null || git -C "${APP_DIR}" checkout "${REPO_REF}"
else
  rm -rf "${APP_DIR}"
  git clone "${REPO_URL}" "${APP_DIR}"
  git -C "${APP_DIR}" checkout "${REPO_REF}" 2>/dev/null || true
fi

cd "${APP_DIR}/${WEB_SUBDIR}"
echo "--- contenido del paquete New_Web ---"
ls -la
echo "--- artefactos clave ---"
ls -la modelo.joblib reports/ data/ 2>/dev/null || echo "(aviso: falta algún artefacto)"

echo "=== 3/5 Build de la imagen Docker (arquitectura del host) ==="
docker build -t "${IMAGE}" .

echo "=== 4/5 (Re)arranque del contenedor Vórtice en el puerto ${VORTICE_PORT} ==="
docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
  --name "${CONTAINER}" \
  --restart unless-stopped \
  -p "${VORTICE_PORT}:8501" \
  "${IMAGE}"

echo "=== 5/5 Esperando a que Vórtice responda ==="
OK=0
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:${VORTICE_PORT}/_stcore/health" >/dev/null 2>&1; then
    echo "OK: Vórtice responde en el puerto ${VORTICE_PORT}"
    docker ps --filter "name=${CONTAINER}" --format "{{.Names}} {{.Status}} {{.Ports}}"
    OK=1
    break
  fi
  sleep 3
done
if [ "${OK}" != "1" ]; then
  echo "ERROR: Vórtice no respondió a tiempo. Logs:"
  docker logs --tail 80 "${CONTAINER}" || true
  exit 1
fi
echo "VORTICE_DEPLOY_DONE"
exit 0
