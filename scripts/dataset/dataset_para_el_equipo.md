# El dataset de entrenamiento: guía para el equipo de modelos

Esta guía explica qué producen los scripts de `scripts/dataset/`, cómo es el dataset final y qué
tener en cuenta antes de entrenar. El objetivo es que puedas cargar un parquet y empezar a trabajar
sin leer el código. Si tu Kiro va a tocar estos scripts, pásale además `docs/dataset_para_kiro.md`.

## 1. Qué hace cada script

| Archivo | Qué hace |
|---|---|
| `scripts/dataset/build_dataset.py` | El punto de entrada. Para cada día cruza, celda por celda y hora por hora, las variables físicas de ERA5, un resumen de GOES y la etiqueta del catálogo. Escribe un parquet por conjunto de anticipación y un `summary.csv`. |
| `scripts/dataset/features.py` | La lógica de etiquetas y particiones, separada para poder probarla sin datos: a qué partición va cada día, qué celdas se marcan como positivas y de qué eventos del catálogo salen. |
| `tests/test_build_dataset.py` | Pruebas (`unittest`) de esa lógica. No necesitan datos descargados. |

Una fila del dataset es **una celda de la grilla ERA5 (0,25°, ~25 km) en una hora UTC**. No es una
imagen ni un perfil vertical: son las variables ya calculadas (cizalladura, SRH, LCL, VGP, STP…) más
tres resúmenes de la imagen GOES sobre esa celda. Si tu modelo necesita las imágenes GOES completas
o los perfiles ERA5, esos siguen en `data/crops/` (ver `AGENTS.md`); este dataset es la versión
tabular lista para modelos clásicos (árboles, regresión, etc.).

### Cómo generarlo

```bash
# El día de desarrollo, que ya tienes descargado:
uv run python scripts/dataset/build_dataset.py --start 2019-05-30

# Todo el rango de entrenamiento, una vez descargados ERA5 y GOES de esos días:
uv run python scripts/dataset/build_dataset.py --start 2018-01-01 --end 2025-12-31
```

Salida en `data/dataset/south-central-austral/`:

```
dataset_lead0h.parquet   diagnóstico (variables de la misma hora del evento)
dataset_lead1h.parquet   variables 1 h antes, etiqueta de la hora del evento
dataset_lead3h.parquet   variables 3 h antes
dataset_lead6h.parquet   variables 6 h antes
summary.csv              filas y positivos por partición y anticipación
```

## 2. Columnas del dataset

| Columna | Tipo | Qué es |
|---|---|---|
| `date` | texto | Fecha del día (`AAAA-MM-DD`). |
| `hour_utc` | int | Hora UTC del evento que se predice (la hora de la etiqueta). |
| `feat_hour_utc` | int | Hora UTC de la que salen las variables. Igual a `hour_utc` en diagnóstico; `lead_h` horas antes en los demás. |
| `lead_h` | int | Horas de anticipación: 0, 1, 3 o 6. |
| `lat`, `lon` | float | Centro de la celda, en grados. |
| `shear_01`, `shear_03`, `shear_06` | float | Cizalladura 0–1, 0–3 y 0–6 km (m/s). |
| `srh_01`, `srh_03` | float | Helicidad relativa a la tormenta 0–1 y 0–3 km (m²/s²). **Negativa** en casos tornádicos (hemisferio sur). |
| `lcl` | float | Altura del nivel de condensación (m). |
| `gamma_03`, `gamma_75` | float | Gradiente térmico 0–3 km y 700–500 hPa (K/km). |
| `vgp_01` | float | Parámetro de generación de vorticidad 0–1 km (m/s²). |
| `stp_lm` | float | Significant Tornado Parameter, rama *left-mover*. **Negativo** en el sur. |
| `sherbs3` | float | Índice de Sherburn (SHERBS3). |
| `u_06`, `v_06`, `u_lm`, `v_lm`, `u_rm`, `v_rm` | float | Viento medio 0–6 km y movimiento de Bunkers (left/right mover). |
| `sfc_height` | float | Altura del terreno estimada desde la presión de superficie (m). |
| `goes_bt_min` | float | Temperatura de brillo mínima (K) de la banda 13 sobre la celda: el tope más frío. |
| `goes_bt_mean` | float | Temperatura de brillo media (K) sobre la celda. |
| `goes_bt_trend` | float | Cambio de la temperatura de brillo en los últimos 10 min (K). Negativo = la nube se enfría (crece). |
| `label` | int | **1** si en esa celda y hora se reportó un tornado o tromba; **0** si no. |
| `event_uid` | texto | `uid` del evento del catálogo que marcó la celda (vacío si `label = 0`). |
| `confirmed` | int | 1 si ese evento es un registro confirmado (`register = 1`); 0 si es débil o sin evaluar. |
| `hour_is_range` | bool | True si la hora del evento venía de un rango impreciso (trátalos aparte en validación/prueba). |
| `region` | texto | Región del recorte (`south-central-austral`). |
| `partition` | texto | `train`, `val`, `test`, `dev` o `inference`. |
| `group` | texto | El día del brote. **Úsalo para no mezclar un mismo día entre entrenamiento y evaluación.** |

### Tabla de ejemplo (dos filas reales del 2019-05-30, diagnóstico)

| columna | fila positiva | fila negativa |
|---|---|---|
| `date` | 2019-05-30 | 2019-05-30 |
| `hour_utc` | 19 | 20 |
| `lead_h` | 0 | 0 |
| `lat`, `lon` | −36.5, −72.0 | −34.25, −75.0 |
| `shear_01` | 11.30 | 6.75 |
| `srh_01` | −216.8 | −54.5 |
| `lcl` | 272.2 | 227.3 |
| `vgp_01` | 0.186 | 0.134 |
| `stp_lm` | −0.286 | −0.069 |
| `goes_bt_min` | 240.4 | 275.2 |
| `goes_bt_trend` | +6.6 | +0.2 |
| `label` | **1** | **0** |
| `event_uid` | CL0054 | *(vacío)* |
| `confirmed` | 0 | 0 |
| `partition` | dev | dev |
| `group` | 2019-05-30 | 2019-05-30 |

La fila positiva (celda de Quilelto/San Carlos) tiene cizalladura y SRH mucho más fuertes y un tope
GOES mucho más frío que la celda negativa, sobre el mar frente a la costa norte. Es el tipo de
contraste que el modelo tiene que aprender.

## 3. Las particiones

El reparto está decidido por el equipo (kit, sección 6) y lo asigna el año de la fecha:

| Partición | Años | Para qué |
|---|---|---|
| `train` | 2018–2023 | Entrenar. |
| `val` | 2024 | Elegir entre modelos e hiperparámetros. |
| `test` | 2025 | Prueba final, una sola vez. |
| `dev` | 30–31 mayo 2019 | Caso de desarrollo (el brote del documento). **No lo uses como prueba ciega.** |
| `inference` | 2026 | Solo para predecir, no tiene etiquetas de confianza. |

Carga una partición con un filtro sencillo:

```python
import pandas as pd

df = pd.read_parquet("data/dataset/south-central-austral/dataset_lead0h.parquet")
train = df[df.partition == "train"]
val = df[df.partition == "val"]
```

## 4. Cuánto tarda crearlo

Hay dos tiempos muy distintos:

- **Armar el dataset** (lo que hacen estos scripts, con ERA5 y GOES ya en disco): **~6–7 s por día**
  (los cuatro parquet de anticipación a la vez). Para los ~110 días del plan son unos **15–20
  minutos**. Es barato: la parte cara es tener los recortes descargados.
- **Descargar y procesar ERA5 + GOES** (lo que hace el Miembro 2 con `scripts/pipeline/`, antes de
  esto): aquí está casi todo el tiempo. El kit estima **~1,2 TB de transferencia de ERA5** para los
  ~110 días. En la EC2 de `us-west-2` (junto al bucket) se transfieren ~350 MB por hora de datos; a
  ritmo de descarga, el conjunto completo son **varias horas, no minutos**. El cálculo de las
  variables de parcela (CAPE, CIN, DCAPE) es lo más lento del proceso.

**En resumen:** una vez que el Miembro 2 termina la descarga, tú tienes el dataset tabular en menos
de media hora. Mientras tanto, puedes desarrollar y probar tu modelo con el día `dev` (2019-05-30),
que ya está disponible.

## 5. Consideraciones importantes

- **Es un problema PU (positivos y datos sin etiqueta), no clasificación normal.** El catálogo solo
  tiene positivos. Un `label = 0` significa *no hay evento reportado en esa celda*, **no** *no hubo
  tornado*. Muchas celdas sin reporte pueden haber tenido convección sin testigos. Trata los ceros
  como «sin etiqueta» y mira la sección 6.1 del documento (`docs/mesociclones_chile.md`) para las
  técnicas de PU learning.

- **No evalúes con exactitud (*accuracy*).** Con tan pocos positivos, predecir siempre «no» da >99 %
  de aciertos y cero utilidad. Usa POD (detección), FAR (falsas alarmas) y la curva precisión-exhaustividad
  (AUC-PR). La sección 6.2 del documento lo detalla.

- **No mezcles un día entre particiones.** Las horas consecutivas de un mismo brote son casi
  idénticas; si una queda en train y otra en val, el modelo parecerá mejor de lo que es. Agrupa
  **siempre por la columna `group`** (el día) al partir o al hacer validación cruzada.

- **Los signos del hemisferio sur son correctos, no un error.** `srh_01`, `srh_03` y `stp_lm` son
  negativos en los casos tornádicos chilenos. Las supercélulas favorecidas aquí son *left-movers*.
  Si vienes de datos del hemisferio norte, no inviertas el signo a mano.

- **`event_uid`, `confirmed` y `hour_is_range` son metadatos, no variables de entrada.** Sirven para
  pesar o filtrar ejemplos (p. ej. entrenar solo con `confirmed = 1`, o apartar `hour_is_range` de
  la evaluación), pero no deben entrar como *features* del modelo: filtrarían la respuesta.

- **El mesociclón inferido nunca es la etiqueta.** La etiqueta es tornado o tromba reportado. Si en
  el futuro se añaden columnas `meso_proxy_*`, son de apoyo, no el objetivo.

- **Faltantes de GOES.** Si en una hora no hay imagen GOES, las tres columnas `goes_*` quedan en
  `NaN`. Decide cómo tratarlas (imputar, usar un modelo que acepte faltantes, o descartar la fila).

- **El dataset crece por días, sin duplicar.** Correr `build_dataset.py` con más días añade filas a
  los parquet existentes y deduplica por `(date, hour_utc, lead_h, lat, lon)`. Usa `--force` solo si
  quieres rehacer desde cero.
