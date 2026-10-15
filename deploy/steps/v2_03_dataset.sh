#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== scripts/dataset en la EC2 ==="
ls -la scripts/dataset/ 2>/dev/null || echo "no existe scripts/dataset/"
echo "=== buscar clean_catalog en todo el repo ==="
find . -name "clean_catalog*" -not -path "./.git/*" 2>/dev/null || echo "no hay clean_catalog"
echo "=== catalog_clean.csv ==="
ls -la data/catalog_clean.csv 2>/dev/null || echo "no existe data/catalog_clean.csv"
echo "=== dataset generado? ==="
ls -la data/dataset/ 2>/dev/null || echo "no existe data/dataset/"
echo "=== goes_latlon procesado? ==="
ls data/crops/south-central-austral/ 2>/dev/null
echo "=== en git (otras ramas/HEAD) hay dataset? ==="
git ls-files scripts/dataset/ 2>/dev/null | head
git log --oneline --all -- scripts/dataset/ 2>/dev/null | head -5 || true
echo "INSPECT_DATASET_DONE"
