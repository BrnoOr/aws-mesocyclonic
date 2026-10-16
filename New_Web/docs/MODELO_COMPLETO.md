# Modelo de detección de mesociclones — documentación completa

Cómo funciona todo el sistema, de punta a punta: desde los datos crudos (ERA5 + GOES + catálogo)
hasta la evaluación del modelo sobre el pronóstico AIWP, con los KPIs del desafío y las advertencias
que hay que decir antes de presentar cualquier número.

> **Resumen en una línea.** Entrenamos un clasificador tabular que, celda por celda y hora por hora,
> estima la probabilidad de que se reporte un tornado/tromba a partir de índices físicos de ERA5
> (y, opcionalmente, GOES). Se valida por **eventos** y **días** (no por celda), se compara contra
> las reglas físicas del documento y se aplica al pronóstico de Pangu-Weather para pronosticar con
> antelación.

Índice:

1. [Panorama y flujo de datos](#1-panorama-y-flujo-de-datos)
2. [El dataset tabular](#2-el-dataset-tabular)
3. [Validación: brotes, LOYO y caso de desarrollo](#3-validación-brotes-loyo-y-caso-de-desarrollo)
4. [El modelo](#4-el-modelo)
5. [Features y por qué `wind` es la segura para el pronóstico](#5-features-y-por-qué-wind-es-la-segura)
6. [KPIs: por evento y por día](#6-kpis-por-evento-y-por-día)
7. [Líneas base físicas](#7-líneas-base-físicas)
8. [Selección del umbral y honestidad](#8-selección-del-umbral-y-honestidad)
9. [Evaluación sobre el pronóstico AIWP](#9-evaluación-sobre-el-pronóstico-aiwp)
10. [Baseline nulo por permutación](#10-baseline-nulo-por-permutación)
11. [Cómo reproducir todo](#11-cómo-reproducir-todo)
12. [Mapa de archivos](#12-mapa-de-archivos)
13. [Resultados actuales y advertencias](#13-resultados-actuales-y-advertencias)

---

## 1. Panorama y flujo de datos

```
catálogo (xlsx)             ERA5 (S3 nsf-ncar-era5)        GOES-16/19 (S3 noaa-goes*)
      │                            │                              │
 clean_catalog.py            download_era5.py               download_goes.py
      │                      process_era5.py                process_goes.py
      ▼                            ▼                              ▼
 catalog_clean.csv      crops/<region>/era5_indices/   crops/<region>/goes_latlon/
      │                            └──────────────┬───────────────┘
      └───────────────────────────────┬──────────┘
                                       ▼
                              build_dataset.py          (+ días de control)
                                       ▼
                   data/dataset/<region>/dataset_lead{0,1,3,6}h.parquet
                                       ▼
                                   train.py  ──►  modelo.joblib  ──►  reports/train_*.md
                                       │                                   
                                       └──► eval_aiwp.py ──► reports/aiwp_bundle_eval.md
                                               (sobre el pronóstico Pangu-Weather)
```

Cada etapa es un script CLI con el patrón de `scripts/pipeline/` (argparse, `--region`, `--start/--end`,
`--force`, salta lo ya hecho). Los datos pesados (`crops/`, parquet, xlsx) viven en `data/` y están en
`.gitignore`: se descargan o generan, nunca se versionan.

---

## 2. El dataset tabular

**Grano:** una celda de la grilla ERA5 (0,25°, ~25 km) en una hora UTC. Una fila ≠ una tormenta y ≠
una imagen: son los índices ya calculados más un resumen de la banda térmica de GOES y una etiqueta.

**Etiqueta (`label`):** 1 si en esa celda y hora se reportó un tornado o tromba (a ≤ 0,2° del evento,
misma hora redondeada a la hora ERA5). Es un problema **PU (positivos y no etiquetados)**: `label = 0`
significa *sin reporte*, **no** *no ocurrió*. El catálogo solo tiene positivos.

**Un parquet por anticipación** (`lead`): `dataset_lead{0,1,3,6}h.parquet`. En lead *L*, las features
se toman *L* horas antes de la hora del evento y la etiqueta se mantiene en la hora del evento
(«¿se veía venir con *L* h de antelación?»).

**Columnas** (ver `docs/dataset_para_el_equipo.md` para el detalle): identificación
(`date, hour_utc, feat_hour_utc, lead_h, lat, lon, region, partition, group`), features ERA5
(cizalladura, SRH, LCL, VGP, STP, Sherburn, viento, altura), resumen GOES (`goes_bt_min/mean/trend`),
etiqueta y metadatos (`label, event_uid, confirmed, hour_is_range`) y **`day_kind`** (`event` /
`control`).

### Días de evento y días de control

`build_dataset.py` construye **todos** los días pedidos sobre un **conjunto fijo de horas** (`--hours`,
por defecto 0–23; en la práctica usamos 12–23 UTC, la ventana severa austral). Esto es clave: un día
con evento ya **no** se limita a sus horas de evento, así tiene tantas oportunidades de dar aviso como
un día sin evento; de lo contrario la FAR por día quedaría sesgada.

- **Día de evento:** tiene ≥ 1 evento positivo en el catálogo → sus celdas-hora cercanas al evento
  llevan `label = 1`.
- **Día de control:** viene de una **lista explícita** (`data/control_days.csv` o `--controls`), no se
  infiere. Todas sus celdas quedan `label = 0`. Son los días *sin tornado* necesarios para medir las
  falsas alarmas por día (KPIs 2 y 3). Sin ellos, esos KPIs no se pueden calcular.

### Particiones (por año de la fecha)

| partición | años | para qué |
|---|---|---|
| `train` | 2018–2023 | entrenar (y la validación cruzada LOYO) |
| `val` | 2024 | elegir entre modelos una sola vez |
| `test` | 2025 | prueba final, con `--final`, una sola vez |
| `dev` | 30–31 may 2019 | caso de desarrollo; **excluido** de entrenamiento y validación |
| `inference` | 2026 | solo predecir (criterio de éxito del desafío) |

---

## 3. Validación: brotes, LOYO y caso de desarrollo

El catálogo trae horas y días consecutivos del mismo brote. Si se reparten entre entrenamiento y
evaluación, el modelo ve situaciones casi idénticas en ambos lados y parece mejor de lo que es (fuga,
`docs/mesociclones_chile.md` §6.3). Dos defensas (módulo `validation.py`, del equipo):

- **Grupos por brote** (`event_ids`, 24 h de hueco): el 30–31 may 2019 o el 25–27 jun 2023 son **un
  solo grupo**, no varios días. Nunca se parte un brote entre pliegues (`outbreak_groups` en
  `train.py`).
- **Un año fuera por iteración (LOYO)** (`leave_one_year_out`): cada pliegue deja fuera un año
  calendario completo de `train` (2018–2023) y entrena con el resto. Produce predicciones
  *out-of-fold* sin fuga.
- **Caso de desarrollo reservado** (`development_mask`): el brote de mayo 2019 se usó para explorar, así
  que se **excluye** del ajuste y de la validación; nunca es prueba ciega.

---

## 4. El modelo

**Contrato del *bundle* (`modelo.joblib`):** un diccionario `{"model", "features", "metadata"}` donde
`model` expone `predict_proba`. Así la **sección 8 del cuaderno `aiwp_mesociclones`** lo aplica tal
cual al pronóstico: `bundle["model"].predict_proba(df[bundle["features"]])[:, 1]`.

**Dos estimadores** (`--model`, en `train.py`):

- `logistic`: imputación por mediana → estandarización → regresión logística con
  `class_weight="balanced"`. Interpretable y rápida; la referencia lineal.
- `forest` *(recomendado)*: `HistGradientBoostingClassifier` balanceado. Capta los umbrales no
  lineales del régimen HSLC, tolera `NaN` de forma nativa (los `goes_*` ausentes) y no necesita
  escalar.

Ambos compensan el desbalance extremo (decenas de positivos frente a decenas de miles de celdas sin
etiqueta) con pesos de clase. El modelo final se ajusta con **todo `train` (2018–2023), sin `dev`** —
nunca con `val` ni `test`.

---

## 5. Features y por qué `wind` es la segura

Tres conjuntos (`model_features.py`, flag `--features`):

- `era5` (18): todas las variables de `era5_idx_*.nc`.
- **`wind` (16) — recomendado para el pronóstico:** `era5` **sin** las variables dependientes de CAPE
  (`vgp_01`, `stp_lm`). En el lote de 25 eventos con Pangu, la MUCAPE derivada salía 0 en varios
  eventos detectados (los 13 niveles del pronóstico pierden la inestabilidad somera del régimen HSLC),
  así que un modelo que se apoye en esas dos variables **falla en silencio** sobre el pronóstico.
  `is_aiwp_safe()` marca este conjunto como seguro.
- `all` (21): `era5` + resumen de GOES (solo existe en el dataset tabular, no en el pronóstico).

Nunca entran identificadores ni metadatos como feature (`FORBIDDEN`: `event_uid`, `confirmed`,
`partition`, `group`, `day_kind`, …); una guardia (`check_not_forbidden`) lo verifica.

---

## 6. KPIs: por evento y por día

Las métricas por celda (AUC-PR, Brier, en `metrics.py`) son **diagnósticos secundarios**: con el
desbalance extremo la FAR por celda es ≈ 1 por construcción y no dice nada operativo. El desafío (CR2)
puntúa **eventos** y **días** (`kpi.py`):

- **KPI 1 — POD por evento:** un evento se detecta si alguna celda con `p ≥ umbral` cae a ≤ **50 km**
  (haversine) y ±**1 h** de él. Un evento que marca varias celdas cuenta **una vez**. Objetivo ≥ 0,70.
  (También existe la variante 0,2° / misma hora, igual a la etiqueta de entrenamiento.)
- **KPI 2 — FAR por día:** días de aviso **sin** evento registrado / días de aviso. Objetivo ≤ 0,50.
- **KPI 3 — Avisos por acierto:** días de aviso / días de aviso con ≥ 1 evento detectado. Objetivo ≤ 2.

**KPI 2 y 3 necesitan días de control.** Si una partición no tiene días sin evento, se reportan como
**«no computable»** (nunca 0), con cuántos controles harían falta.

Se reportan de **dos formas**:

- **cruda:** sobre los días evaluados tal cual (depende de la proporción control/evento, que es
  artificial).
- **reescalada a temporada** (comparable con la base CR2): tasa de aviso en días de control `q`
  (con intervalo de Wilson) × días sin evento de una temporada mayo–septiembre
  (`N0 = 153 − días_de_evento_del_año`); las falsas alarmas esperadas son `FA = q·N0`, los aciertos
  `hits = POD_día·días_de_evento`, y `FAR = FA/(FA+hits)`, `avisos/acierto = (FA+hits)/hits`.

Todas las tasas llevan **intervalo de Wilson** del 95 % y el conteo al lado. Hay desgloses por EF
(EF0 / EF1+), tipo (tornado / tromba), confirmado / débil y día / noche (hora 00–09 UTC = noche).

---

## 7. Líneas base físicas

Reglas sin ajuste (`baselines.py`), que pasan por el **mismo** código de KPI por evento/día:

- **STP** (detección): `stp_lm ≤ −0,3` (rama *left-mover*, signo austral; Marín et al. 2024).
- **SHERBS3 ≥ 1** (falsas alarmas): proxy de `SHERBE ≥ 1` (usa cizalladura 0–3 km, no capa efectiva).
- **HSLC regla A:** `shear_01 ≥ 12` ∧ `srh_01 ≤ −150` ∧ `vgp_01 > 0` (CAPE > 0).
- **HSLC regla B:** como A pero **sin** la cláusula de CAPE.

El modelo se reporta **al lado** de ellas. Un modelo que no le gane a la regla B en `val` no es una
mejora, y el reporte lo dice.

---

## 8. Selección del umbral y honestidad

El umbral de operación se elige por KPI (`--target`):

- `pod` (por defecto): el umbral **más alto** cuya POD por evento ≥ 0,70; si no se alcanza, el de POD
  máxima (y se dice).
- `alerts`: el umbral **más bajo** con avisos por acierto ≤ 2.

Se elige sobre las predicciones **out-of-fold** de LOYO. **Esto es optimista**: el mismo conjunto
elige y evalúa. Por eso `train.py` reporta además una **selección anidada** (`nested_loyo_pod`): para
cada año reservado, el umbral se elige con las predicciones OOF de **los demás** años y se aplica a ese
año. La POD anidada es la honesta.

> En los datos actuales: POD LOYO **optimista ≈ 0,89** vs POD **anidada ≈ 0,37**. Usar la anidada.

La curva de operación completa (umbral → POD evento, FAR día, avisos/acierto) se guarda en
`reports/operating_curve_*.csv`.

---

## 9. Evaluación sobre el pronóstico AIWP

`eval_aiwp.py` aplica el *bundle* a los índices de pronóstico de Pangu-Weather
(`aiwp_idx_panguweather_*.nc`) y mide la detección por evento con el **criterio del lote**: celda con
`p ≥ umbral` a ≤ **50 km** y ±**6 h** del evento. Dos cuidados que **evitan inflar el número**:

1. **Sin fuga.** Ningún evento se puntúa con un modelo entrenado en su año. Los eventos de 2021–2023
   (dentro de `train`) se puntúan *out of fold* con el modelo LOYO que **excluyó su año**; los de
   2024–2025 (nunca vistos) con el modelo de solo-`train`. Se reporta separado en **años de
   entrenamiento (OOF)** y **2024–2025 (nunca vistos)**.
2. **Área igualada, elegida sin mirar eventos.** Para comparar de forma justa con cada regla, el
   umbral del modelo se fija para que marque **la misma fracción de celda-horas** que la regla
   (A ≈ 1,07 %, B ≈ 10,74 %), usando solo la distribución de puntuaciones OOF.

El *bundle* no se reajusta sobre el pronóstico. El barrido 0,5/0,7/0,9 queda **solo como anexo**,
rotulado «elegido a posteriori, no es un resultado».

---

## 10. Baseline nulo por permutación

A 10,74 % de área, el criterio 50 km/±6 h da ~30 celda-horas de oportunidad por evento: **marcas al
azar con la misma huella capturarían casi todo**. Por eso el número que importa no es la POD absoluta
sino el **exceso sobre un nulo**.

`permutation_null` evalúa cada evento contra los flag-maps de **cada otro** run (misma estructura
espacial y tasa de marcado, alineado por `lead_h`, pero rompiendo el vínculo real con el evento) y da
la **POD nula** (media y rango 5–95 %), el **exceso** (observada − nula) y un **valor-p** de una cola.
Se reporta también la **estructura espacial** (parches conectados por paso y su tamaño) y la
**robustez** con un criterio estricto (**25 km, paso más cercano**).

> Lectura honesta: una POD observada alta a 10,74 % de área es casi toda geometría; lo real es el
> exceso. Ver §13.

---

## 11. Cómo reproducir todo

Requisitos: `uv sync` desde la raíz del repo; acceso anónimo a S3 (sin credenciales). Conviene AWS
us-west-2 (junto a los buckets).

```bash
# 1. Catálogo
uv run python scripts/pipeline/clean_catalog.py           # -> data/catalog_clean.csv

# 2. Recortes de un día (ERA5 ~2 min, GOES ~30 s en south-central)
uv run python scripts/pipeline/download_era5.py  --start 2019-05-30 --region south-central \
    --pl u v t z --sfc 10u 10v 2t 2d sp cape
uv run python scripts/pipeline/process_era5.py   --start 2019-05-30 --region south-central
uv run python scripts/pipeline/download_goes.py  --start 2019-05-30 --region south-central --bands 13 --hours 12 23
uv run python scripts/pipeline/process_goes.py   --start 2019-05-30 --region south-central

# 3. Dataset (eventos + días de control de data/control_days.csv), horas fijas 12–23
uv run python scripts/dataset/build_dataset.py --start 1941-06-13 --end 2025-12-31 \
    --region south-central --hours 12 23 --force

# 4. Entrenar y evaluar (recomendado: forest + wind)
uv run python scripts/model/train.py --region south-central --lead 0 --model forest --features wind --target pod
#   -> modelo.joblib, reports/train_south-central_lead0h.md, reports/operating_curve_*.csv

# 5. Evaluar sobre el pronóstico AIWP (sin fuga + área igualada + nulo)
uv run python scripts/model/eval_aiwp.py --force
#   -> reports/aiwp_bundle_eval.md + .csv

# 6. (opcional) prueba ciega final en test 2025 — una sola vez
uv run python scripts/model/train.py --region south-central --lead 0 --model forest --features wind --final
```

El cuaderno `notebooks/build_dataset_pipeline.ipynb` corre los pasos 1–3 ordenados y verificados.
`make check` (ruff, formato, pyright, pruebas) debe pasar antes de abrir una PR.

---

## 12. Mapa de archivos

| Archivo | Qué hace |
|---|---|
| `scripts/dataset/build_dataset.py` | Arma el parquet tabular (eventos + control, horas fijas, `day_kind`). |
| `scripts/dataset/features.py` | Lógica pura de etiquetas y particiones (equipo). |
| `scripts/pipeline/clean_catalog.py` · `catalog_fixes.py` | Homogeniza el catálogo. |
| `scripts/model/model_features.py` | Conjuntos de features (`era5`/`wind`/`all`), `FORBIDDEN`, `is_aiwp_safe`. |
| `scripts/model/baselines.py` | Reglas físicas sin ajuste (STP, SHERBS3, HSLC A/B). |
| `scripts/model/validation.py` | Brotes (`event_ids`), LOYO, `development_mask` (equipo). |
| `scripts/model/metrics.py` | Métricas por celda: POD, FAR, CSI, AUC-PR, Brier, fiabilidad (equipo). |
| `scripts/model/kpi.py` | KPIs por evento/día, Wilson, área marcada, FAR de temporada. |
| `scripts/model/train.py` | Entrenamiento KPI-driven: grupos, LOYO, umbral, reportes, *bundle*. |
| `scripts/model/eval_aiwp.py` | Evaluación sobre el pronóstico: sin fuga, área igualada, nulo por permutación. |
| `tests/` | Pruebas unitarias sin datos descargados. |
| `docs/dataset_para_*.md` | Contexto del dataset (equipo / Kiro). |
| `reports/` | Salidas generadas (KPIs, curva de operación, evaluación AIWP). |
| `notebooks/build_dataset_pipeline.ipynb` | Pipeline completo del dataset, verificado. |
| `data/control_days.csv` | Lista explícita de días de control. |

---

## 13. Resultados actuales y advertencias

**Configuración del modelo guardado:** `forest` · features `wind` (AIWP-safe) · región
`south-central` · lead 0 · umbral 0,90 (criterio POD ≥ 0,70). Dataset: `train` 640 500 filas / 91
positivas (35 brotes, 3 días de control), `val` 73 200 / 4 (2 control), `test` 36 600 / 4 (0 control),
`dev` excluido.

**Lo que sí se puede afirmar:**

- POD por evento en validación cruzada: **optimista ≈ 0,89**, **anidada (honesta) ≈ 0,37
  [0,23–0,54]**. Usar la anidada.
- Sobre el pronóstico AIWP, **sin fuga y a área igualada**, el modelo supera a las reglas físicas en
  **exceso sobre el nulo por permutación**: +17–18 % (p ≈ 0,056) a áreas A y B y bajo el criterio
  estricto 25 km/paso; las reglas A/B muestran exceso casi nulo (+2–4 %, no significativo).

**Lo que NO se debe afirmar / límites:**

- **No** presentar «80 % vs 32 %» como el resultado: a 10,74 % de área, un nulo con la misma huella ya
  captura ~63 %. Lo honesto es el **exceso** (~+17 %), real pero modesto.
- Los días de control son **pocos** (3 en LOYO, 2 en val, 0 en test): KPI 2/3 son **indicativos**,
  con intervalos de Wilson anchos. `test` (2025) no tiene control → KPI 2/3 no computables ahí.
- El exceso **no se replica** en los 7 eventos nunca vistos de 2024–2025 (n muy chico): no concluir.
- **PU:** `label = 0` es *sin reporte*; el subregistro infla la FAR real. Las métricas se leen sabiendo
  que «no reportado» ≠ «no ocurrió».
- **Cobertura:** 13 eventos del catálogo caen fuera de 12–23 UTC y quedan fuera de la POD tabular
  (listados en `reports/train_*.md`).
- **CAPE del pronóstico:** Pangu (13 niveles) subestima la inestabilidad HSLC; por eso se usa `wind`
  (sin variables de CAPE) para el *bundle* del pronóstico.

**En resumen:** hay señal real y defendible (el modelo supera a las reglas en exceso sobre el azar,
incluso con criterio estricto), pero los números absolutos están inflados por la geometría del
criterio y el `n` es pequeño. Presentar el exceso sobre el nulo, no la POD cruda, y declarar los
límites de datos.
