#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
echo "=== git log ==="
git log -1 --oneline
echo "=== download_era5 main (lineas 270-285) ==="
sed -n '270,285p' scripts/pipeline/download_era5.py
echo "=== common.folder ==="
grep -n "def folder" -A 4 scripts/common.py
echo "=== store tiene __truediv__? ==="
grep -n "truediv\|def child" scripts/store.py
echo "=== process_era5 usa .child o / ? ==="
grep -n "folder\|\.child\|out_file" scripts/pipeline/process_era5.py | head
echo "VER_DONE"
