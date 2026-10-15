# Resultados en la nube — cómo verlos y recuperarlos

Los resultados del modelo viven en la **EC2 de AWS** (`i-0ea9664c5e9ada5a0`, us-east-1), en
`/opt/mesocyclonic-viewer/data/outputs/`. Los archivos pesados (candidatos 2026 ≈ 2,6 MB, features)
no se versionan en git (`data/` está en `.gitignore`); este documento explica cómo verlos y traerlos.

## 1. La web (lo más rápido)

**App de resultados (producto final):**
<https://d1y31u1kylukz6.cloudfront.net>

Es una app Streamlit servida por CloudFront (HTTPS) desde la EC2 (puerto 8502). Muestra, alineado con
`docs/presentacion_producto_final.pptx`:

- **El problema**: por qué en Chile casi nadie ve los tornados (régimen HSLC, catálogo solo positivos).
- **Modelos**: tabla M0–M4 por corte, POD vs FAR, modelo elegido.
- **Año a año**: eventos detectados por año, regla física vs modelo elegido.
- **Prueba ciega 2025**: una sola evaluación, sin reajuste.
- **Metas**: POD / FAR / días por detección con semáforo frente a las metas del proyecto.
- **Candidatos 2026**: mapa interactivo, top-15 con sus variables, y el aviso de que varios de mayor
  puntaje caen cerca de la cordillera (posibles artefactos; la v2 lo corrige).
- **Decisión**: `decision_<corte>.md` y `resumen_pitch.md`.

> El link es estable mientras la EC2 esté encendida. Si no responde, la instancia pudo apagarse o la
> app detenerse (ver sección 4).

El visor de datos y el caso 2019 están en la misma EC2, puerto 8501 (otra CloudFront del proyecto).

## 2. Qué resultados hay (cifras clave de esta corrida)

Validación cruzada año-fuera 2018–2024, acierto tolerante. Modelo elegido corte «día»: **M2**
(logística penalizada); corte «12utc»: **M1** (regla física).

| Corte | Modelo elegido | POD | FAR | Días/det | Alertas | PR-AUC |
|---|---|---|---|---|---|---|
| día | **M2** | 71% (30/42) | 84% | 2,5 | 537 | 0,026 |
| 12utc | **M1** | 74% (31/42) | 97% | 5,6 | 3.261 | 0,004 |

- **Prueba ciega 2025** (corte día, M2): 2 de 2 eventos detectados, FAR 83%, 64 alertas en 9 días.
- **Candidatos 2026** (corte día, M2): 10.980 celdas-día puntuadas, **285 alertas**, ERA5 hasta 2026-07-31.
- **Metas**: POD ✅ cumple (≥70%); FAR ❌ 84% (sobrestimado, el control es sin etiqueta); días por
  detección 🟡 2,5 (cerca de la meta de 2).

## 3. Archivos en la EC2 (`data/outputs/`)

| Archivo | Qué es |
|---|---|
| `cv_report.csv` | Métricas por modelo y corte (5 modelos × 2 cortes). |
| `cv_by_fold.csv` | Métricas por año (para el detalle año a año). |
| `decision_dia.md`, `decision_12utc.md` | Modelo elegido y razón, por corte. |
| `blind_2025_dia.csv`, `blind_2025_12utc.csv` | Prueba ciega 2025. |
| `candidatos_2026_dia.csv`, `candidatos_2026_12utc.csv` | Lista priorizada 2026 con top1–top3. |
| `resumen_pitch.md` | Resumen para el pitch. |
| `modelo_dia.pkl`, `modelo_12utc.pkl` | Modelos entrenados hasta 2025. |
| `v1/` | Respaldo de las salidas de la versión 1. |

## 4. Cómo recuperarlos sin pasar por la web

Requiere credenciales AWS de la cuenta `620965032345` y acceso SSM. Desde una terminal con el AWS
CLI configurado:

**Opción A — copiar un archivo por SSM (base64):**

```bash
# Ejemplo: traer cv_report.csv
aws ssm send-command --region us-east-1 --instance-ids i-0ea9664c5e9ada5a0 \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["base64 -w0 /opt/mesocyclonic-viewer/data/outputs/cv_report.csv"]' \
  --query "Command.CommandId" --output text
# luego: aws ssm get-command-invocation --command-id <ID> --instance-id i-0ea9664c5e9ada5a0 \
#        --query StandardOutputContent --output text  | base64 -d > cv_report.csv
```

**Opción B — túnel y descarga por la app** (los CSV también se ven en la web).

**Opción C — recomendada si se quiere persistencia:** sincronizar a un bucket S3. Hoy la cuenta no
tiene bucket (quedó pendiente de aprobación). Cuando exista uno:

```bash
# En la EC2 (por SSM):
aws s3 sync /opt/mesocyclonic-viewer/data/outputs s3://<bucket>/outputs/
# En local:
aws s3 sync s3://<bucket>/outputs/ ./data/outputs/
```

Los 7 resultados pequeños (cv_report, decision_*, blind_*, resumen_pitch) ya están respaldados en el
repo local en `data/outputs/`; los pesados (candidatos completos, features, modelos .pkl) quedan en la
EC2.

## 5. Reproducir desde cero

Código en el repo (`scripts/model/`), rama `main` del fork `BrnoOr/aws-mesocyclonic`. En la EC2:

```bash
cd /opt/mesocyclonic-viewer && git pull
uv run python scripts/model/features.py --corte dia  --start 2018-04-01 --end 2026-07-31
uv run python scripts/model/cv.py       --corte dia
uv run python scripts/model/decide.py   --corte dia
uv run python scripts/model/train.py    --until 2025 --modelo elegido --corte dia
uv run python scripts/model/score.py    --start 2026-04-01 --end 2026-07-31 --corte dia
uv run python scripts/model/resumen_pitch.py
```

## 6. Qué quedó encendido en AWS

- **EC2** `i-0ea9664c5e9ada5a0` (la del hackatón) — encendida, sirve la app y el visor.
- **CloudFront** `d1y31u1kylukz6.cloudfront.net` (app) y la del visor (8501) — activas.
- **Security group** `sg-04785182a7e53344c` (abre 8502 solo a CloudFront).
- No se crearon buckets, instancias nuevas ni volúmenes adicionales.
