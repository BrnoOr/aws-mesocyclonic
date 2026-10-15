#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "===CVREPORT==="
base64 -w0 data/outputs/cv_report.csv
echo ""
echo "===DECISION_DIA==="
base64 -w0 data/outputs/decision_dia.md
echo ""
echo "===DECISION_12UTC==="
base64 -w0 data/outputs/decision_12utc.md
echo ""
echo "===LS==="
ls data/outputs/
echo "END"
