#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

echo "=== probar disponibilidad ERA5 2026 (abril) ==="
uv run python - <<'PY'
import sys; sys.path.insert(0,"scripts")
import common, s3fs, datetime as dt
fs = common.s3()
# Prueba meses de 2026 en el bucket de niveles de presión
for m in range(1, 13):
    key = f"nsf-ncar-era5/e5.oper.an.pl/2026{m:02d}"
    try:
        hits = fs.ls(key)
        print(f"2026-{m:02d}: {len(hits)} objetos")
    except Exception as e:
        print(f"2026-{m:02d}: no disponible ({str(e)[:40]})")
PY
echo "PROBE_DONE"
