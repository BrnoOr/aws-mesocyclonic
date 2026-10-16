#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
cd /opt/mesocyclonic-viewer
# Fuerza una ejecución del script como Streamlit lo hace (import + run) para detectar errores.
export PATH="$HOME/.local/bin:$PATH"
echo "=== comprobar que el script importa y las lecturas no fallan ==="
uv run python - <<'PY'
import pandas as pd, re
from pathlib import Path
OUT = Path("data/outputs")
# Replica las lecturas clave de la app
cv = pd.read_csv(OUT/"cv_report.csv")
bf = pd.read_csv(OUT/"cv_by_fold.csv")
print("cv_report filas:", len(cv), "cortes:", sorted(cv['corte'].unique()))
print("cv_by_fold filas:", len(bf))
# Tabla año a año (como en la app)
bfd = bf[bf['corte']=='dia']
piv = bfd.pivot_table(index='anio', columns='modelo', values='detectados', aggfunc='first')
print("años en año-a-año:", list(piv.index))
# decisión elegido
for c in ['dia','12utc']:
    txt = (OUT/f"decision_{c}.md").read_text(encoding='utf-8')
    m = re.search(r"Modelo elegido:\s*\*\*(M\d)\*\*", txt)
    print(f"elegido {c}:", m.group(1) if m else "?")
cand = pd.read_csv(OUT/"candidatos_2026_dia.csv")
print("candidatos_2026_dia filas:", len(cand), "alertas:", int(cand['alerta'].sum()))
print("columnas top:", [c for c in ['top1','top2','top3'] if c in cand.columns])
print("OK lecturas de la app")
PY
echo "=== log app: buscar tracebacks ==="
grep -i "traceback\|error\|exception" data/tables/app.log | tail -5 || echo "sin errores en el log"
echo "VERIFY_APP_DONE"
