#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer/data/outputs
echo "BEGIN_DIA"
head -301 candidatos_2026_dia.csv | base64 -w0
echo ""
echo "END_DIA"
