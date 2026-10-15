#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "===TRAIN==="
base64 -w0 scripts/model/train.py
echo ""
echo "===SCORE==="
base64 -w0 scripts/model/score.py
echo ""
echo "===TEST==="
base64 -w0 tests/test_model_dataset.py
echo ""
echo "END"
