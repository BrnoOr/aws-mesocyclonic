# Checkpoint `vortice.pt` — Documentación

Modelo **Vórtice**: cabezal de *PU learning* sobre índices físicos de ERA5 para
priorizar dónde y cuándo buscar actividad mesociclónica / potencial de tornados.
El modelo produce un **puntaje por celda-hora** (celda de 25 km en una hora dada)
que sirve para **ordenar la revisión**, no una probabilidad calibrada.

- **Archivo:** `data/model/vortice.pt` (~15 KB)
- **Entrenado por:** `scripts/model/train.py`
- **Cargado/usado por:** `scripts/model/infer.py` (clase `Vortice`)
- **Evaluado por:** `scripts/model/metrics.py`

---

## 1. Arquitectura (`PUNet`)

MLP denso pequeño: 11 features → logit escalar. Definido en `train.py`.

| Capa (`state_dict`) | Operación | Forma de pesos | Dimensiones |
|---------------------|-----------|----------------|-------------|
| `net.0` | `Linear` | `(64, 11)` | 11 → 64 |
| `net.1` | `ReLU` | — | — |
| `net.2` | `Dropout(0.2)` | — | — |
| `net.3` | `Linear` | `(32, 64)` | 64 → 32 |
| `net.4` | `ReLU` | — | — |
| `net.5` | `Dropout(0.2)` | — | — |
| `net.6` | `Linear` | `(1, 32)` | 32 → 1 (logit) |

- **Parámetros entrenables totales:** **2 881**
- **Salida:** un logit por fila (la sigmoide se aplica en inferencia).
- **`arch` guardado:** `{ "in_dim": 11, "hidden": 64 }`

---

## 2. Contenido del checkpoint

`torch.save` guarda un `dict` con estas claves:

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `state_dict` | dict (6 tensores) | Pesos y sesgos de las 3 capas lineales |
| `features` | list (11) | Columnas de entrada en el orden esperado |
| `era5_features` | list (11) | Índices base de ERA5 |
| `mean` | ndarray (11) | Media de normalización (estadístico de *train*) |
| `std` | ndarray (11) | Desviación estándar de normalización (de *train*) |
| `pi` | float | Fracción previa de positivos |
| `threshold` | float | Umbral operativo de alerta |
| `use_goes` | bool | Si se usaron embeddings GOES |
| `arch` | dict | `in_dim` y `hidden` para reconstruir la red |

### Valores concretos de este checkpoint

- **`use_goes = False`** → versión **línea base**, solo índices ERA5 (sin embeddings de imágenes satelitales GOES).
- **`pi = 0.0027923`** → ~0,28 % de positivos: clases **muy desbalanceadas** (eventos raros).
- **`threshold = 0.0013774`** → umbral operativo (percentil calibrado para ~20× la tasa base de positivos).

### Features (11 índices ERA5)

```
shear_01, shear_03, shear_06,   # cizalladura del viento (0-1, 0-3, 0-6 km)
srh_01, srh_03,                 # helicidad relativa a la tormenta (0-1, 0-3 km)
lcl,                            # nivel de condensación por ascenso
gamma_03, gamma_75,             # lapse rates (0-3 km, 700-500 hPa)
vgp_01,                         # vorticity generation parameter (0-1 km)
stp_lm,                         # significant tornado parameter
sherbs3                         # SHERB (severe hazards in environments...)
```

### Normalización

| # | feature | mean | std |
|---|---------|------|-----|
| 0 | shear_01 |  8.473 |  5.242 |
| 1 | shear_03 | 12.698 |  6.306 |
| 2 | shear_06 | 18.424 |  8.747 |
| 3 | srh_01   | -81.957 | 90.140 |
| 4 | srh_03   | -135.406 | 115.321 |
| 5 | lcl      | 629.197 | 655.308 |
| 6 | gamma_03 |  5.244 |  1.662 |
| 7 | gamma_75 |  6.475 |  0.809 |
| 8 | vgp_01   |  0.0226 |  0.0416 |
| 9 | stp_lm   | -0.0101 |  0.0363 |
| 10 | sherbs3 |  0.588 |  0.374 |

Normalización aplicada: `x_norm = (nan_to_num(x) - mean) / std`.

---

## 3. Entrenamiento

- **Pérdida:** *non-negative PU learning* (nnPU, Kiryo et al. 2017), con sigmoide
  como pérdida sustituta. Diseñada para el caso **Positive–Unlabeled**: solo hay
  ejemplos positivos y datos sin etiquetar, y corrige el término de riesgo negativo
  para que no se vuelva negativo.
- **Optimizador:** Adam (`lr=1e-3`, `weight_decay=1e-5`).
- **Semilla:** `torch.manual_seed(0)`.
- **Hiperparámetros por defecto:** `--epochs 60`, `--batch 4096`.
- **Selección de modelo:** se guarda el mejor estado según un *proxy* de POD en
  validación (`metrics.pod_proxy`).
- **Normalización:** media/std calculadas solo sobre el conjunto de *train*.
- **`pi`:** se pasa con `--pi` o se estima como la tasa de positivos en *train*.

### Comandos

```bash
# Entrenamiento completo (si existieran embeddings GOES, se usarían)
uv run python scripts/model/train.py --epochs 60

# Línea base: solo índices ERA5 (coincide con este checkpoint, use_goes=False)
uv run python scripts/model/train.py --epochs 60 --no-goes
```

### Salidas del entrenamiento

- `data/model/vortice.pt` — este checkpoint.
- `data/model/scores.parquet` — puntaje por celda-hora del conjunto de prueba (para EDA).

---

## 4. Inferencia

La clase `Vortice` (en `infer.py`) reconstruye la red y sus metadatos desde el
checkpoint. Las columnas de embedding GOES ausentes se rellenan con cero.

### Como biblioteca

```python
from model.infer import Vortice

v = Vortice.load("data/model/vortice.pt")
df["score"] = v.score_frame(df)          # puntaje 0–1 por fila
alerts = df[df["score"] >= v.threshold]  # celdas sobre el umbral operativo
```

### Como CLI (puntúa un día ya procesado y escribe alertas)

```bash
uv run python scripts/model/infer.py --date 2024-06-20
# -> data/model/alerts_20240620.parquet
```

---

## 5. Evaluación (metas de Vórtice, sobre el conjunto de prueba)

Definidas en `metrics.py` y calculadas **por evento** y **por día** (no por celda):

| # | Meta | Definición | Objetivo |
|---|------|-----------|----------|
| 1 | **POD por evento** | Un tornado cuenta como detectado si alguna celda marcada (`score ≥ umbral`) cae a ≤ 50 km y ± 6 h de él | ≥ 70 % |
| 2 | **FAR por día** | Fracción de días de alerta cuyas celdas marcadas no tienen evento asociado | ≤ 50 % |
| 3 | **Días por acierto** | Días de alerta por cada tornado detectado (eficiencia) | ≤ 2 |

> Nota: con etiquetas incompletas, algunas "falsas alarmas" pueden ser eventos
> reales sin registro. El puntaje ordena, no certifica.

---

## 6. Notas de reproducibilidad

- El checkpoint es **autocontenido**: incluye pesos + normalización + lista de
  features + `pi` + umbral + arquitectura. No requiere los datos de entrenamiento
  para inferir.
- Para puntuar datos nuevos solo hacen falta los **índices ERA5** producidos por
  `scripts/pipeline/process_era5.py`.
- Versión actual: **línea base ERA5** (`use_goes=False`). Para incorporar GOES se
  entrenaría sin `--no-goes` y con embeddings presentes en `cells.parquet`.

---

*Generado a partir de la inspección del checkpoint y de `scripts/model/{train,infer,metrics}.py`.*
