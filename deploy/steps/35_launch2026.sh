#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

# Temporada 2026 disponible en ERA5: abril 1 a julio 31.
uv run python - <<'PY'
import datetime as dt
start = dt.date(2026,4,1); end = dt.date(2026,7,31)
days = [start+dt.timedelta(days=i) for i in range((end-start).days+1)]
open("data/tables/dias_2026.txt","w").write("\n".join(d.isoformat() for d in days)+"\n")
print(f"2026: {len(days)} días (abril-julio)")
PY

nohup bash scripts/model/run_days_par.sh data/tables/dias_2026.txt 6 > data/tables/run_2026.log 2>&1 &
echo "PID: $!"
sleep 8
ls data/crops/south-central-austral/era5_indices/era5_idx_2026*.nc 2>/dev/null | wc -l
echo "LAUNCH2026_DONE"
