# Resultados del primer modelo de proyecciones

Ejecución del plan de `docs/plan_proyecciones.md` (fases 1–4) sobre la instancia EC2
`i-0ea9664c5e9ada5a0` (us-east-1, Amazon Linux 2023, arm64/Graviton2), vía SSM. Este documento resume
qué se corrió, con qué datos y qué resultó. Es un **prototipo exploratorio**, no un pronóstico.

## Qué se ejecutó

Pipeline nuevo en `scripts/model/` (entorno `uv` + scikit-learn, arm64):

1. `build_dataset.py` — tabla de ejemplos (una fila por celda-hora) con las 12 features del entorno y
   la etiqueta PU, cruzando los índices ERA5 con el catálogo de tornados.
2. `train.py` — `HistGradientBoostingClassifier` con validación cruzada **agrupada por evento** y
   ponderación de positivos.
3. `score.py` — proyecciones: mapa de puntuación por celda-hora (NetCDF) y lista de candidatos.

## Datos usados

Índices ERA5 (`era5_indices`) de la región `south-central-austral`, 3 días:

| Día | Rol | Positivas (celdas-hora) |
|---|---|---|
| 2019-05-30 | Brote del Biobío (desarrollo) | 137 |
| 2019-05-31 | Continuación del brote | 112 |
| 2019-02-15 | Control de verano | 0 |

- **Tabla:** 309.960 celdas-hora; **249 positivas** de **7 eventos** del catálogo; el resto, no
  etiquetadas (PU). Positivos marcados con ventana de ±0,5° y ±1 h alrededor de cada evento con hora
  UTC utilizable.
- **Features (12):** `shear_01/03/06`, `srh_01/03`, `lcl`, `gamma_03`, `gamma_75`, `vgp_01`,
  `stp_lm`, `sherbs3`, `cape`.
- Los archivos `era5_pl` crudos se borraron tras calcular los índices por el límite de disco (40 GiB);
  se conservó `era5_sfc` para el CAPE.

## Métricas (validación cruzada por evento, 3 pliegues)

De `data/model/metrics.json`:

| Métrica | Valor | Lectura |
|---|---|---|
| AUC-PR | **0,087** | Tasa base de positivos = 0,00083 → el modelo ordena ~100× mejor que el azar |
| POD (umbral 0,5) | **0,80** | Detecta el 80 % de las celdas-hora positivas (198/249) |
| FAR vs. no-etiquetados | 0,95 | Esperable en PU: muchos "falsos positivos" pueden ser eventos sin registro |
| Brier | 0,012 | — |
| tp / fn / fp | 198 / 51 / 3960 | — |

El FAR alto no es necesariamente malo: por construcción PU, las celdas-hora "no etiquetadas" con
puntuación alta son justamente las **candidatas a revisión** (días/lugares con entorno favorable y sin
reporte), no errores confirmados.

## Coherencia física

Puntuación media por día (de los NetCDF `model_score/score_*.nc`):

| Día | Score medio | Score máx | Celdas > 0,5 |
|---|---|---|---|
| 2019-02-15 (control) | 0,0125 | 0,56 | 3 |
| 2019-05-30 (brote) | 0,041 | 0,98 | 2596 |
| 2019-05-31 (brote) | 0,042 | 0,98 | 2450 |

El modelo se activa fuertemente en los días del brote y casi no en el control de verano, como se
espera.

**Importancia de variables (permutación sobre AUC-PR):** `gamma_03` (gradiente térmico 0–3 km),
`srh_01` (helicidad 0–1 km) y `shear_01` (cizalladura 0–1 km) dominan, seguidas de `vgp_01` y `lcl`.
Son los índices de niveles bajos que `docs/mesociclones_chile.md` destaca para el régimen HSLC
austral: el modelo aprendió señales físicamente razonables.

Los **candidatos** de mayor puntuación (`data/model/candidates.csv`) caen en el Biobío (lat −35 a −39,
lon −71 a −73), la zona de los tornados documentados del 30–31 de mayo de 2019.

## Artefactos generados

En la instancia (`/opt/mesocyclonic-viewer/data/`) y respaldados en el repo local
(`data/model/`, en `.gitignore`):

- `data/model/dataset.parquet` — tabla de ejemplos (309.960 filas).
- `data/model/model.pkl` — modelo entrenado + lista de features.
- `data/model/metrics.json` — métricas de validación.
- `data/model/candidates.csv` — 90 celdas-hora de mayor puntuación.
- `data/crops/south-central-austral/model_score/score_{20190215,20190530,20190531}.nc` — mapas de
  puntuación en la grilla ERA5 (superponibles en el visor).

## Verificación de calidad

- `ruff check scripts/model tests/test_model_dataset.py` → sin errores.
- `ruff format` aplicado a los 4 archivos nuevos.
- `python -m unittest tests.test_model_dataset` → 3/3 OK (pruebas del etiquetado sin datos).

## Limitaciones

- **Pocos eventos y pocos días.** 7 eventos de un solo brote + 1 día de control. La CV por evento es
  válida pero el poder estadístico es bajo; las métricas son orientativas.
- **Etiquetas incompletas (PU).** No hay negativos confirmados; el FAR mezcla errores reales con
  posibles eventos sin registro.
- **Solo ERA5.** No se usaron variables de GOES ni geográficas/temporales (extensiones del plan).
- **No es pronóstico.** ERA5 es reanálisis; la puntuación es relativa, no una probabilidad calibrada.

## Siguientes pasos (del plan)

1. Ampliar a más días del catálogo (otros brotes) y más controles difíciles, idealmente con el
   pipeline ERA5 corriendo en us-west-2 o guardando índices en un bucket S3 del equipo.
2. Añadir features de GOES por celda-hora y variables geográficas/temporales.
3. Integrar el producto de puntuación en el visor (`viewer_app/products.py` + `variables.py`).
4. Calibrar probabilidades y estudiar el sesgo de reporte (PU con propensión de etiquetado).
