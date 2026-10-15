#!/usr/bin/env bash
# Construye y arranca el visor Streamlit en la instancia, dentro de Docker, y
# descarga/procesa un dia de datos para que el visor muestre el caso de estudio.
# Idempotente: se puede volver a correr; recrea el contenedor cada vez.
# Variables de entorno esperadas: REPO_URL, REPO_REF, VIEWER_PORT, CASE_DATE.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/idia-tt/aws-mesocyclonic.git}"
REPO_REF="${REPO_REF:-main}"
VIEWER_PORT="${VIEWER_PORT:-8501}"
CASE_DATE="${CASE_DATE:-2019-05-30}"   # dia con cinco tornados en el Biobio
APP_DIR="/opt/mesocyclonic-viewer"
IMAGE="mesocyclonic-viewer:latest"
CONTAINER="mesocyclonic-viewer"

echo "=== 1/6 Dependencias (git) ==="
command -v git >/dev/null 2>&1 || dnf install -y git

echo "=== 2/6 Repo en ${APP_DIR} (ref ${REPO_REF}) ==="
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" reset --hard "origin/${REPO_REF}" 2>/dev/null || git -C "${APP_DIR}" checkout "${REPO_REF}"
else
  rm -rf "${APP_DIR}"
  git clone "${REPO_URL}" "${APP_DIR}"
  git -C "${APP_DIR}" checkout "${REPO_REF}" 2>/dev/null || true
fi

cd "${APP_DIR}"

echo "=== 3/6 Catalogo de tornados y linea de costa ==="
mkdir -p data
curl -fsSL -o data/tornados_chile.xlsx https://ndownloader.figshare.com/files/56272544 || echo "aviso: no se pudo bajar el catalogo"
curl -fsSL -o data/coast.zip https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip || echo "aviso: no se pudo bajar la costa"

echo "=== 4/6 Build de la imagen Docker (arm64) ==="
docker build -t "${IMAGE}" .

echo "=== 5/6 (Re)arranque del contenedor del visor en el puerto ${VIEWER_PORT} ==="
docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
  --name "${CONTAINER}" \
  --restart unless-stopped \
  -p "${VIEWER_PORT}:8501" \
  -v "${APP_DIR}/data:/app/data" \
  "${IMAGE}" \
  streamlit run scripts/viewer/viewer.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false

echo "=== Esperando a que el visor responda ==="
VISOR_OK=0
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${VIEWER_PORT}/_stcore/health" >/dev/null 2>&1; then
    echo "OK: el visor responde en el puerto ${VIEWER_PORT}"
    docker ps --filter "name=${CONTAINER}" --format "{{.Names}} {{.Status}} {{.Ports}}"
    VISOR_OK=1
    break
  fi
  sleep 3
done
if [ "${VISOR_OK}" != "1" ]; then
  echo "ERROR: el visor no respondio a tiempo. Logs:"
  docker logs --tail 50 "${CONTAINER}" || true
  exit 1
fi

echo "=== 6/6 Descarga y procesamiento del dia ${CASE_DATE} ==="
# Se corre dentro de la misma imagen (trae los scripts del pipeline), con data/
# montado para que lo descargado quede en el host. El visor ya esta arriba y
# releera data/ al recargar la pagina cuando el pipeline termine.
# El orden importa: cada paso usa lo que dejo el anterior.
run_step () {
  echo "--- pipeline: $* ---"
  docker run --rm \
    -v "${APP_DIR}/data:/app/data" \
    --entrypoint python \
    "${IMAGE}" "$@"
}
PIPE_OK=1
run_step scripts/pipeline/download_era5.py --start "${CASE_DATE}" || PIPE_OK=0
run_step scripts/pipeline/download_goes.py --start "${CASE_DATE}" || PIPE_OK=0
run_step scripts/pipeline/process_goes.py  --start "${CASE_DATE}" || PIPE_OK=0
run_step scripts/pipeline/process_era5.py  --start "${CASE_DATE}" || PIPE_OK=0
if [ "${PIPE_OK}" = "1" ]; then
  echo "pipeline OK: datos de ${CASE_DATE} listos"
else
  echo "aviso: el pipeline no termino del todo; el visor sigue arriba con lo que haya"
fi
echo "--- contenido de data/crops ---"
find data/crops -maxdepth 3 -type f 2>/dev/null | head -40 || echo "(sin crops)"
echo "DEPLOY_DONE"
exit 0
