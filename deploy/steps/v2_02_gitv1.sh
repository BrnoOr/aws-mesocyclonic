#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== respaldar salidas v1 en outputs/v1 ==="
mkdir -p data/outputs/v1
for f in cv_report.csv cv_by_fold.csv decision_dia.md decision_12utc.md \
         blind_2025_dia.csv blind_2025_12utc.csv candidatos_2026_dia.csv \
         candidatos_2026_12utc.csv resumen_pitch.md modelo_dia.pkl modelo_12utc.pkl; do
  [ -f "data/outputs/$f" ] && cp -n "data/outputs/$f" "data/outputs/v1/$f" 2>/dev/null || true
done
echo "contenido outputs/v1:"
ls data/outputs/v1/

echo "=== configurar git (identidad local, sin tocar remoto) ==="
git config user.email "kiro@mesocyclonic.local" 2>/dev/null || true
git config user.name "kiro" 2>/dev/null || true

echo "=== crear rama mejora-modelos-v2 ==="
git rev-parse --verify mejora-modelos-v2 >/dev/null 2>&1 && git checkout mejora-modelos-v2 || git checkout -b mejora-modelos-v2
git branch --show-current

echo "=== commit del estado v1 (código ya existente) ==="
git add -A
git commit -m "v1: sistema de selección de modelos de tornados (base para v2)" 2>&1 | tail -3 || echo "(nada que commitear o ya commiteado)"
git log --oneline -3
echo "GITV1_DONE"
