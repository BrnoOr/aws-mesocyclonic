#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer/data/outputs
for f in cv_report.csv cv_by_fold.csv decision_dia.md decision_12utc.md blind_2025_dia.csv blind_2025_12utc.csv resumen_pitch.md; do
  echo "===FILE:$f==="
  base64 -w0 "$f"
  echo ""
done
# Candidatos: solo las primeras 300 filas (top por score ya ordenado) para respaldo local liviano.
for c in candidatos_2026_dia.csv candidatos_2026_12utc.csv; do
  echo "===FILE:$c==="
  head -301 "$c" | base64 -w0
  echo ""
done
echo "END_ALL"
