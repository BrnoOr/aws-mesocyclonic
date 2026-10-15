#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "===METRICS_B64==="
base64 -w0 data/model/metrics.json
echo ""
echo "===CANDIDATES_B64==="
base64 -w0 data/model/candidates.csv
echo ""
echo "===END==="
