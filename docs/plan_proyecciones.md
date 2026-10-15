# Plan de trabajo: proyecciones (modelo predictivo de mesociclones)

Plan para construir las **proyecciones** del proyecto: un modelo que, a partir de los índices de
ERA5 (y, opcionalmente, variables de GOES), asigna a cada celda y hora una **puntuación de propensión
a tiempo severo tornádico** sobre el centro-sur y la zona austral de Chile. El resultado son mapas de
puntuación por hora y una lista de días/lugares candidatos para revisión, como describe
`docs/mesociclones_chile.md` (secciones 6 y 7).

Este documento parte del estado real del repositorio y lo complementa; no repite la física, que está
en `docs/mesociclones_chile.md`.

## 1. Estado actual (lo que ya existe)

| Componente | Estado | Dónde |
|---|---|---|
| Descarga ERA5 (niveles de presión + superficie) recortada a Chile | Listo | `scripts/pipeline/download_era5.py` |
| Descarga GOES recortada a Chile | Listo | `scripts/pipeline/download_goes.py` |
| Reproyección GOES a lat/lon | Listo | `scripts/pipeline/process_goes.py` |
| Índices australes (cizalladura, Bunkers, SRH, LCL, γ, VGP, STP, SHERBS3) | Listo | `scripts/pipeline/process_era5.py` |
| Catálogo de tornados/trombas (102 eventos) | Se descarga | `data/tornados_chile.xlsx` |
| EDA exploratorio del catálogo | Listo (solo exploración) | `notebooks/eda_mesociclones.ipynb` |
| Visor Streamlit | Listo y desplegado | `scripts/viewer/`, EC2 `i-0ea9664c5e9ada5a0` |
| Capa de almacenamiento local/S3 (`MESO_DATA_ROOT`) | Listo | `scripts/store.py`, `scripts/common.py` |
| **Tabla de ejemplos (features + etiquetas)** | **No existe** | — |
| **Modelo predictivo y scoring** | **No existe** | — |

**Conclusión:** el pipeline de datos y los índices físicos están completos. Falta todo lo relativo al
modelado: construir la tabla de ejemplos, generar negativos/controles, entrenar un clasificador bajo
el enfoque *Positive-Unlabeled* (PU) con validación por eventos, y producir las proyecciones (mapas de
puntuación). Esto encaja con las etapas "Variables derivadas → Entrenamiento → Consulta y
visualización" de la sección 7 del documento.

## 2. Objetivo y alcance

- **Objetivo:** entregar un primer modelo tabular reproducible (*gradient boosting* sobre árboles) que
  puntúe cada celda/hora y permita (a) comparar casos documentados con el resto y (b) listar
  candidatos sin reporte. Es un prototipo exploratorio, no un pronóstico operativo (ERA5 es
  reanálisis, no tiempo real).
- **Fuera de alcance (por ahora):** modelos *end-to-end* sobre imágenes, autosupervisado sobre GOES,
  corrección de paralaje, recalibración de STP/SCP. Quedan como extensiones (sección 8).

## 3. Decisiones de diseño (hay que fijarlas antes de entrenar)

1. **Unidad de ejemplo:** una celda de la grilla ERA5 (~0,25°) en una hora. Alternativa agregada:
   máximo por día y subregión. Se parte por celda-hora y se documenta.
2. **Etiqueta positiva:** celdas-hora cercanas en espacio y tiempo a un evento del catálogo con
   `Hour (UTC)` utilizable. Ventana propuesta: ±1 celda y ±1 h alrededor del evento. Se registra el
   `Register` (confianza) para ponderar o filtrar.
3. **Negativos / no etiquetados:** no hay negativos confirmados. Se usa PU learning. Como conjunto no
   etiquetado se muestrean celdas-hora de días con convección (y "controles difíciles": días con
   tormenta profunda sin reporte). Nunca se afirma que un no-etiquetado es negativo.
4. **Features de partida (de `era5_indices`):** `vgp_01`, `stp_lm`, `sherbs3`, `srh_01`, `srh_03`,
   `shear_01`, `shear_06`, `lcl`, `gamma_03`, `gamma_75`, más `cape` de superficie. Más adelante:
   variables geográficas (distancia a costa/Andes, altura) y temporales (seno/coseno de hora y día).
5. **Región y período:** `south-central-austral` sobre el recuadro 33°S–45°S. Período inicial: los
   días tornádicos documentados + un conjunto de días de control, para medir volumen/tiempo/costo
   antes de ampliar.
6. **Validación:** separación **por eventos completos** (todas las horas de un brote en el mismo
   grupo) y por bloques temporales (dejar un año fuera). El brote del 30–31 mayo 2019 es caso de
   desarrollo, no prueba ciega.
7. **Métricas:** AUC-PR, POD/FAR, curva de fiabilidad y Brier. La *accuracy* no sirve por el
   desbalance.

## 4. Arquitectura de ejecución en AWS

- **Dónde se corre:** EC2 `i-0ea9664c5e9ada5a0` (`c6g.8xlarge`, arm64/Graviton2, 32 vCPU, 64 GiB,
  **us-east-1**), acceso por **SSM Session Manager** (no hay SSH). Es la misma máquina del visor.
- **Datos:** `data/crops/south-central-austral/` ya tiene los recortes del caso 2019 generados por el
  despliegue. Restricción crítica: **disco raíz de 40 GiB**. Para más días conviene apuntar
  `MESO_DATA_ROOT` a un bucket S3 del equipo o limpiar entre días.
- **Regiones de datos:** GOES en us-east-1 (misma región, sin egreso); ERA5 en us-west-2 (cruza
  región: más lento, con costo de transferencia). Para trabajo intensivo de ERA5, considerar una
  máquina/SageMaker en us-west-2 (`docs/sagemaker.md`).
- **arm64:** cualquier dependencia nueva (p. ej. el motor de *gradient boosting*) debe resolver para
  arm64. `uv add` sobre PyPI lo soporta en las ruedas habituales.

## 5. Fases de trabajo

### Fase 0 — Preparación y acceso (medio día)
- [ ] Renovar credenciales AWS en el entorno local (hoy expiradas) y confirmar con
  `aws sts get-caller-identity`.
- [ ] Confirmar acceso a la instancia por SSM: `aws ssm start-session --target i-0ea9664c5e9ada5a0`
  (o `send-command` con `AWS-RunShellScript`).
- [ ] En la instancia: repo clonado en `/opt/mesocyclonic-viewer`, `uv sync`, y decidir
  `MESO_DATA_ROOT` (disco local vs. bucket S3).

### Fase 1 — Datos de entrenamiento (1–2 días)
- [ ] Elegir el conjunto de días: tornádicos documentados + controles. Generar índices con el
  pipeline existente para cada día (`download_era5.py` → `process_era5.py`; GOES si se usa).
- [ ] **Nuevo script `scripts/model/build_dataset.py`**: lee `era5_indices` (+ `era5_sfc` para CAPE),
  cruza con el catálogo para etiquetar positivos (ventana espacio-temporal), muestrea no-etiquetados
  y escribe una tabla `data/model/dataset.parquet` (un ejemplo por fila; columnas: features, lat, lon,
  time, event_id, label, register). Sigue el patrón de `scripts/pipeline/` (argparse, `--start/--end/
  --region/--force`, salida en `data/`, salta lo existente).
- [ ] Prueba en `tests/` del etiquetado (ventana, signos, cruce con catálogo) sin datos descargados.

### Fase 2 — Modelo base (1–2 días)
- [ ] `uv add` del motor de *gradient boosting* (p. ej. una librería de árboles con rueda arm64) o
  usar el *HistGradientBoostingClassifier* de scikit-learn (habría que `uv add scikit-learn`).
- [ ] **Nuevo script `scripts/model/train.py`**: carga `dataset.parquet`, arma los *folds* por evento,
  entrena el clasificador PU (ponderando positivos por `register` o estimando propensión), reporta
  AUC-PR, POD/FAR, curva de fiabilidad y Brier, y guarda el modelo en `data/model/model.pkl` y las
  métricas en `data/model/metrics.json`.
- [ ] Explicabilidad: importancia de variables y, si da el tiempo, SHAP sobre un subconjunto.
- [ ] Prueba de humo en `tests/` (entrena con datos sintéticos pequeños y verifica que corre).

### Fase 3 — Proyecciones / scoring (1 día)
- [ ] **Nuevo script `scripts/model/score.py`**: aplica el modelo a todas las celdas-hora de un día y
  escribe un NetCDF `data/crops/<region>/model_score/score_AAAAMMDD.nc` con la misma grilla que
  `era5_indices`, para que el visor pueda superponerlo.
- [ ] Generar la lista de **candidatos**: días/lugares con puntuación alta sin reporte, en
  `data/model/candidates.csv`.
- [ ] (Opcional) Añadir el producto de puntuación al visor (`viewer_app/products.py` +
  `variables.py`), respetando las convenciones de `AGENTS.md`.

### Fase 4 — Validación y entrega (medio día)
- [ ] `make check` (ruff, formato, pyright, pruebas) debe pasar.
- [ ] Documentar resultados y limitaciones (etiquetas incompletas, PU, régimen HSLC) en un breve
  `docs/resultados_modelo.md`.
- [ ] Dejar en S3 (o en disco) `dataset.parquet`, `model.pkl`, `metrics.json`, los `score_*.nc` y
  `candidates.csv`.

## 6. Entregables

- `scripts/model/build_dataset.py`, `train.py`, `score.py` (con sus pruebas en `tests/`).
- `data/model/dataset.parquet`, `model.pkl`, `metrics.json`, `candidates.csv`.
- `data/crops/<region>/model_score/score_*.nc`.
- `docs/resultados_modelo.md`.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Disco de 40 GiB en la EC2 | `MESO_DATA_ROOT=s3://...`; limpiar recortes por día; procesar día a día |
| ERA5 cruza región (us-west-2 ↔ us-east-1): lento y con costo | Lotes pequeños; medir bytes/tiempo antes de ampliar; evaluar SageMaker en us-west-2 |
| Fuga de información entre horas de un mismo brote | *Split* por evento completo y por bloques de año |
| Desbalance extremo y falta de negativos | PU learning; métricas AUC-PR/POD/FAR; controles difíciles como no-etiquetados |
| Signos del hemisferio sur (SRH/STP) | Reusar `process_era5.py`, que ya los maneja; no reinvertir signos |
| Dependencia nueva no arm64 | Preferir scikit-learn `HistGradientBoosting`; verificar rueda arm64 antes de `uv add` |
| Credenciales AWS expiradas | Renovar antes de la Fase 0; bloquea toda ejecución en la EC2 |

## 8. Extensiones (después del prototipo)

- Variables de GOES por celda/hora (BT banda 13, diferencias entre bandas, tasa de enfriamiento).
- Modelo híbrido ERA5 + patrones de GOES (CNN).
- Autosupervisado sobre GOES; preentrenamiento con datos del hemisferio norte y *fine-tuning*.
- Corrección de paralaje de GOES.
- Recalibración exploratoria de STP/SCP para el régimen chileno.

## 9. Comandos de referencia

```bash
# Local / en la EC2 (dentro del repo)
uv sync

# Pipeline de datos (ya existe)
uv run python scripts/pipeline/download_era5.py --start 2019-05-30 --end 2019-05-31
uv run python scripts/pipeline/process_era5.py  --start 2019-05-30 --end 2019-05-31

# Modelo (a crear)
uv run python scripts/model/build_dataset.py --start 2019-05-30 --end 2019-05-31
uv run python scripts/model/train.py
uv run python scripts/model/score.py --start 2019-05-30 --end 2019-05-31

# Calidad
make check   # o los comandos equivalentes de ruff/pyright/unittest en Windows

# Acceso a la EC2 (us-east-1), sin SSH
aws ssm start-session --target i-0ea9664c5e9ada5a0 --region us-east-1
```
