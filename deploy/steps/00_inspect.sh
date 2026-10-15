#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
APP=/opt/mesocyclonic-viewer
echo "=== uv ==="
for p in "$HOME/.local/bin/uv" /usr/local/bin/uv /root/.cargo/bin/uv; do
  [ -x "$p" ] && echo "uv en $p" && "$p" --version && break
done
command -v uv >/dev/null 2>&1 && echo "uv en PATH: $(uv --version)" || echo "uv no en PATH"
echo "=== .venv del repo ==="
ls -la "$APP/.venv/bin/python" 2>/dev/null && "$APP/.venv/bin/python" --version || echo "sin .venv"
echo "=== datos crops ==="
find "$APP/data/crops" -maxdepth 3 -type f 2>/dev/null | head -40 || echo "sin crops"
echo "=== catalogo / costa ==="
ls -la "$APP/data/"*.xlsx "$APP/data/"*.zip 2>/dev/null || echo "sin catalogo/costa"
echo "=== imagen docker ==="
docker images --format "{{.Repository}}:{{.Tag}} {{.Size}}" 2>/dev/null | head || echo "sin docker"
echo "DONE_INSPECT"
