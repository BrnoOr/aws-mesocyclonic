#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== estado actual ==="
git branch --show-current
git remote -v | head -2

echo "=== apuntar remoto a BrnoOr (fork del usuario) ==="
git remote set-url origin https://github.com/BrnoOr/aws-mesocyclonic.git
git remote -v | head -2

echo "=== fetch ==="
git fetch origin main 2>&1 | tail -3

echo "=== guardar trabajo local no commiteado (por si acaso) y cambiar a main ==="
git stash push -u -m "respaldo-ec2-pre-pull" 2>&1 | tail -2 || true
git checkout main 2>&1 | tail -2 || git checkout -b main origin/main 2>&1 | tail -2

echo "=== pull (fast-forward o reset a origin/main) ==="
git reset --hard origin/main 2>&1 | tail -2

echo "=== estado tras pull ==="
git log --oneline -2
echo "=== archivos clave presentes? ==="
ls scripts/model/ | head
ls scripts/dataset/ 2>/dev/null && echo "scripts/dataset OK" || echo "falta scripts/dataset"
ls docs/presentacion_producto_final.pptx 2>/dev/null && echo "pptx OK" || echo "falta pptx"
echo "PULL_DONE"
