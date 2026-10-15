# Inventario v2 — reconocimiento (Fase 0)

Verificado el 2026-10-15 en la EC2 `i-0ea9664c5e9ada5a0` (us-east-1) vía SSM. Cada dato viene de un
comando ejecutado, no de supuestos.

## Entorno AWS

- **Identidad:** cuenta `620965032345`, rol `WSParticipantRole/Participant` (`aws sts get-caller-identity`).
- **Instancia:** `i-0ea9664c5e9ada5a0`, Amazon Linux 2023, arm64. Disco raíz 40 GiB, **26 GiB libres**
  (`df -h /` → 15G usados, 37%).
- **Repo:** `/opt/mesocyclonic-viewer`, remoto `github.com/idia-tt/aws-mesocyclonic`. Partía de `main`
  (commit `3798cd3`) con el código v1 **sin commitear**. Se creó la rama **`mejora-modelos-v2`** y se
  commiteó el estado v1 (commit `eb470ee`). `data/` está en `.gitignore`, así que los datos no se
  versionan (correcto).
- **Flujo reproducible:** el repo en la EC2 es ahora un clon de git en la rama de trabajo; los pasos
  de `deploy/steps/*.sh` se siguen enviando por `deploy/ssm_run.ps1`, pero el código de referencia es
  el del repo versionado, no el base64 (se migrará por completo a `git`/`aws s3 sync` en Fase 2).

## Datos ERA5 ya procesados

- **`era5_indices`:** 382 días. Cobertura por año: 2018=33, 2019=29, 2020=35, 2021=35, 2022=37,
  2023=35, 2024=27, 2025=29, **2026=122** (abril–julio). **Faltan 2015, 2016, 2017** (los añade la
  Fase 2 para ganar poder estadístico, D6).
- **Dominio del recorte ERA5:** lat **−56..−30**, lon **−76..−66** (grilla 0,25°). 
- **Variables `era5_indices`:** `shear_01, shear_03, shear_06, u_lm, v_lm, u_rm, v_rm, u_06, v_06,
  srh_01, srh_03, lcl, gamma_03, gamma_75, vgp_01, stp_lm, sherbs3, sfc_height`.
  `sfc_height` permite la máscara de terreno (Fase 2).
- **Variables `era5_sfc`:** `10u, 10v, 2t, 2d, sp, cape`. **Sin humedad en altura ni en superficie**
  (ni `q`, ni `cin`, ni `tcwv`, ni `blh`): confirma D5. La Fase 3 debe añadir `q` (presión) y, si
  están, `cin/tcwv/blh` (superficie) para MLCAPE, CIN, SHERBE real y STP efectivo.

## Confirmación de los errores/diagnósticos del prompt

- **E4 (dominio incoherente) — CONFIRMADO.** El dominio del modelo en `model_selection.yaml` v1 es
  lat −43,5..−21,5, pero el recorte ERA5 empieza en **−30**. Los eventos al norte de −30 no tienen
  datos. El catálogo tiene eventos hasta **lat −22,09**, con varios al norte de −30 → cuentan como no
  detectados sin datos. Fila −29,5 sale de una sola fila de puntos ERA5.
- **D5 (sin humedad) — CONFIRMADO** por las variables de `era5_sfc`.
- **D6 (pocos positivos) — CONFIRMADO/AMPLIADO.** Catálogo abril–sep: 2015=5, 2016=3, 2017=6, 2018=2,
  2019=8, 2020=10, 2021=6, 2022=2, 2023=9, 2024=5, 2025=2. **Total 2015–2024 = 56 eventos** (la v1 usó
  solo 2018–2024 ≈ 42). Añadir 2015–2017 suma 14 eventos.
- **D4 (fecha/hora) — VERIFICABLE.** `Hour (UTC)` está presente en los **102** registros (ejemplos:
  `12:00:00`, `22:00:00`, `02:00:00`). Se puede convertir a UTC real en vez de usar solo la fecha.
  `Register`: 50 con confianza alta (1.0), 49 baja (0.0), 3 sin dato.

## Salidas v1

Respaldadas en `data/outputs/v1/` (11 archivos: `cv_report.csv`, `cv_by_fold.csv`,
`decision_{dia,12utc}.md`, `blind_2025_*.csv`, `candidatos_2026_*.csv`, `resumen_pitch.md`,
`modelo_*.pkl`). No se tocan al generar la v2.

## Estudio de `scripts/dataset/` (construcción de catálogos) y qué sirve para la v2

`scripts/dataset/` existe **solo en el repo local** (no en la EC2, no commiteado). Trae un enfoque de
dataset más maduro para el tratamiento del catálogo. Su grano es **celda 0,25° × hora** (fino),
distinto del de la selección de modelos v2 (**celda 1° × día**, caso-control); no se mezclan, pero la
lógica del catálogo es directamente reutilizable y resuelve varios diagnósticos del prompt:

| De `scripts/dataset/features.py` | Resuelve | Uso en v2 |
|---|---|---|
| `round_hour()` — `HH:MM` → hora ERA5 entera, tope 23 (no cruza de día) | D4 (hora UTC) | `labels.py` v2 |
| `events_from_catalog()` — positivos con `register`, `tornado`, `waterspout`, `hour_is_range` | D4 (metadatos) | `labels.py` v2 |
| `label_grid()` — radio `MATCH_RADIUS_DEG = 0,2°`, escala por cos(lat), evento más cercano | D3 (vecindad) | adaptar a 1° (zona de exclusión 3×3) |
| `confirmed` (= `register == 1`) | D7 / PU | ponderar M6 por confianza |
| `summarize_goes()` — `goes_bt_min/mean/trend` de la banda C13 por celda | Fase 3 (GOES opcional) | reutilizar |
| particiones + `group` + `check_no_leakage` + `GroupKFold` | antifuga | ya en `cv.py` v2; confirmar coherencia |
| `LEAD_HOURS = (0,1,3,6)` | O7 anticipación | complementa los cortes `dia`/`12utc` |

**Lo que falta y hay que crear** (lo referencian los docs pero no existe en el repo):
`clean_catalog.py` que produce `data/catalog_clean.csv` con `date, hour_utc, lat, lon, uid, register,
tornado, waterspout, hour_is_range`. Se construirá en la Fase 2 (etiquetas) reutilizando `round_hour`
y `events_from_catalog`. En la EC2 ya existe `goes_latlon` del día dev (2019-05-30), así que el
resumen GOES es viable para la Fase 3.

## Pendientes para el usuario (puerta de aprobación 1)

- **Bucket S3 del equipo:** PENDIENTE. Necesario para guardar `crops/`, `tables/` y `outputs/` de
  temporadas completas (no caben en el disco de 40 GiB).
- **Presupuesto:** PENDIENTE. Tope de gasto antes de la Fase 2 (descarga masiva ~2.000 días y, con
  humedad, ~1,4 GB extra/día).
- **Región de cómputo pesado:** recomendado us-west-2 (región de ERA5) para evitar tráfico entre
  regiones; requiere crear una instancia nueva (puerta de aprobación 1).
