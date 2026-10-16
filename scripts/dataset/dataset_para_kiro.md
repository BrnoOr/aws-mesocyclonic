# Dataset de entrenamiento: contexto para Kiro

Documento para agentes (Kiro, Claude Code, Codex) que vayan a **entrenar modelos** sobre el dataset
que produce `scripts/dataset/`. No reescribas los scripts de generación salvo que te lo pidan;
tu trabajo normal es *consumir* los parquet. Lee también `AGENTS.md` (convenciones del repo) y
`docs/mesociclones_chile.md` (física; secciones 5 y 6 son las relevantes para modelar).

## Resumen de los archivos

### `scripts/dataset/features.py`
Lógica pura, sin E/S, probada en `tests/test_build_dataset.py`. Firmas públicas:

- `partition_of(date: dt.date) -> str` — devuelve `train`/`val`/`test`/`dev`/`inference` por el año,
  con `dev` (2019-05-30 y 2019-05-31) con prioridad. Constantes: `DEV_DATES`, `TRAIN_YEARS` (2018–2023),
  `VAL_YEAR` (2024), `TEST_YEAR` (2025), `INFERENCE_YEAR` (2026).
- `round_hour(hour_utc) -> int | None` — `HH:MM` del catálogo a hora ERA5 entera (redondeo al minuto
  30, tope en 23 para no cruzar de día).
- `events_from_catalog(catalog: pd.DataFrame, date: dt.date) -> list[Event]` — positivos (tornado o
  tromba) con hora y coordenada legibles. `Event` es un dataclass: `uid, date, hour_utc, lat, lon,
  register, is_range`.
- `label_grid(lat, lon, events, hour_utc, radius) -> (label, event_uid, confirmed)` — tres rejillas
  2D. Una celda se marca `label=1` si está a ≤ `radius` grados (constante `MATCH_RADIUS_DEG = 0.2`)
  de un evento cuya hora coincide con `hour_utc`. `LEAD_HOURS = (0, 1, 3, 6)`.

### `scripts/dataset/build_dataset.py`
Punto de entrada CLI (patrón de `scripts/pipeline/`: `--start/--end/--region/--bbox/--force` de
`common`). Lee `data/catalog_clean.csv` y los recortes de `data/crops/<region>/`, escribe parquet en
`data/dataset/<region>/`. Funciones clave:

- `summarize_goes(ds, lat, lon, half)` — agrega la banda `C13` de GOES (0,02°) a la grilla ERA5
  (0,25°): por celda calcula mínimo, media y tendencia a 10 min. `NaN` donde no hay píxeles.
- `hour_frame(...)` — construye la tabla de una hora: variables de `feat_hour`, etiqueta de
  `label_hour` (difieren cuando `lead > 0`).
- `build_day(date, base, catalog, region) -> dict[int, pd.DataFrame]` — un DataFrame por `lead`.
- `add_partition(df)` — añade `partition` y `group` (= `date`).
- `check_no_leakage(frames)` — asegura que ningún `group` cae en dos particiones (lanza AssertionError).

### `tests/test_build_dataset.py`
`unittest`, sin datos descargados. Cubre particiones, redondeo de hora, lectura del catálogo,
etiquetado por radio y hora, no-fuga y el resumen de GOES. Si cambias la lógica, actualiza estas
pruebas y corre `make check`.

## Esquema del parquet

Grano: una celda ERA5 (0,25°) × una hora UTC. Un parquet por anticipación:
`dataset_lead{0,1,3,6}h.parquet`.

Columnas (ver `docs/dataset_para_el_equipo.md` para la descripción legible):

- **ID / split:** `date`, `hour_utc`, `feat_hour_utc`, `lead_h`, `lat`, `lon`, `region`,
  `partition`, `group`.
- **Features ERA5:** `shear_01`, `shear_03`, `shear_06`, `srh_01`, `srh_03`, `lcl`, `gamma_03`,
  `gamma_75`, `vgp_01`, `stp_lm`, `sherbs3`, `u_06`, `v_06`, `u_lm`, `v_lm`, `u_rm`, `v_rm`,
  `sfc_height`.
- **Features GOES:** `goes_bt_min`, `goes_bt_mean`, `goes_bt_trend`.
- **Etiqueta y metadatos:** `label` (0/1), `event_uid`, `confirmed` (0/1), `hour_is_range` (bool).

## Reglas que no debes romper al entrenar

1. **PU, no clasificación binaria limpia.** `label = 0` es *sin etiqueta*, no negativo confirmado
   (`docs/` §6.1). No asumas que los ceros son verdaderos negativos; si aplicas pérdidas o métricas
   que lo supongan, dilo explícitamente.
2. **Agrupa por `group` al partir o validar.** Nunca pongas filas del mismo `group` (día/brote) en
   train y en val/test a la vez: es fuga de datos (`docs/` §6.3). Para validación cruzada usa
   `GroupKFold` sobre `group`.
3. **No uses `event_uid`, `confirmed`, `hour_is_range`, `partition`, `group`, `date`, `region` como
   features.** Son identificadores/metadatos; filtrarían la respuesta. Las features son solo las
   columnas ERA5 y GOES listadas arriba.
4. **La etiqueta es tornado/tromba reportado.** No construyas una etiqueta a partir de `srh_01`,
   `stp_lm` ni de ningún índice: eso sería circular. Si aparecen columnas `meso_proxy_*`, son de
   apoyo, nunca el objetivo.
5. **Métricas:** POD, FAR, AUC-PR, Brier; no *accuracy* (`docs/` §6.2). El desbalance es extremo
   (decenas de celdas positivas frente a decenas de miles sin etiqueta).
6. **Signos australes:** `srh_01`, `srh_03`, `stp_lm` son negativos en los positivos. No los
   inviertas. Si combinas con datos del hemisferio norte, documenta la convención de giro.
7. **`NaN` en `goes_*`** cuando falta la imagen GOES de esa hora. Elige una estrategia (imputar /
   modelo tolerante / descartar) y déjala escrita.
8. **Datos nunca al git.** `data/` está en `.gitignore` (parquet, csv de salida incluidos). No
   versiones el dataset ni muevas los parquet fuera de `data/`.
9. **Dependencias con `uv add`,** nunca `pip`. Código en inglés, documentación y comentarios en
   español (`AGENTS.md`). Antes de abrir PR: `make check`.

## Carga típica

```python
import pandas as pd

df = pd.read_parquet("data/dataset/south-central-austral/dataset_lead0h.parquet")

FEATURES = [
    "shear_01",
    "shear_03",
    "shear_06",
    "srh_01",
    "srh_03",
    "lcl",
    "gamma_03",
    "gamma_75",
    "vgp_01",
    "stp_lm",
    "sherbs3",
    "u_06",
    "v_06",
    "u_lm",
    "v_lm",
    "u_rm",
    "v_rm",
    "sfc_height",
    "goes_bt_min",
    "goes_bt_mean",
    "goes_bt_trend",
]

train = df[df.partition == "train"]
val = df[df.partition == "val"]
X_train, y_train, groups = train[FEATURES], train["label"], train["group"]
# validación cruzada: GroupKFold sobre `groups`
```

## Estado actual

Solo está generado el día `dev` (2019-05-30): ~17.220 filas por anticipación, 14 celdas positivas
(8 confirmadas), un único `group`. El resto del dataset aparece cuando el Miembro 2 termina de
descargar y procesar ERA5+GOES de los días del plan de extracción. Desarrolla y prueba tu modelo
contra `dev` mientras tanto; no lo uses como prueba ciega final.
