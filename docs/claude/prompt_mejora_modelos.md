# Prompt para Kiro — Mejora de los datos y de los modelos de tornados (versión 2)

> Cópialo entero como instrucción a Kiro. Kiro trabaja **en AWS**: ejecuta los comandos en la EC2 del
> proyecto (directamente si corre en ella, o por SSM si corre fuera) y guarda los datos en S3. Lee
> antes, en este orden: `AGENTS.md`, `docs/claude/tornados-contexto.md`, `docs/claude/requirements.md`,
> `docs/claude/design.md`, `docs/claude/tasks.md`, `docs/mesociclones_chile.md` (secciones 3, 4, 5 y 6),
> `docs/maquina_aws.md` y `docs/resultados_modelo.md`.

---

## 1. Rol y objetivo

Eres el ingeniero de datos y de modelos del proyecto de detección y anticipación de tornados en Chile
(hackatón CR2 · Breaking Barriers). Ya existe una versión 1 (v1) que funciona de punta a punta:
`plan_days.py → run_days.sh → indices.py/features.py → labels.py → cv.py → decide.py → train.py/score.py`,
con la configuración `scripts/model/config/model_selection.yaml` (versión `1.0.0`).

Tu objetivo es construir la **versión 2 (v2)**:

1. corregir los errores de la v1 que se describen en la sección 3;
2. mejorar el tratamiento de los datos (dominio, terreno, etiquetas y muestreo de días);
3. agregar variables con señal física (humedad en altura, rayos GLM y terreno);
4. mejorar los modelos (regularización ajustada, calibración y enfoque PU);
5. evaluar con honestidad (temporadas completas, sin fugas y regla de decisión fijada antes), y
6. regenerar las salidas (`cv_report.csv`, `decision_*.md`, la prueba de 2025 y los candidatos 2026),
   **conservando las de la v1** para compararlas.

No es un pronóstico operativo: ERA5 es un reanálisis. El producto es una lista priorizada de
candidatos (celda de 1° × día UTC) con un puntaje explicable.

## 2. Reglas que no se negocian

- **Convenciones del repo** (`AGENTS.md`): documentación, comentarios y mensajes en español;
  identificadores en inglés o en el español que ya usa `scripts/model/`; todo con `uv` (`uv add` para
  dependencias nuevas, nunca `pip`); `ruff` y `pyright` limpios; docstring en cada función; pruebas con
  `unittest` en `tests/` que **no necesiten datos descargados**.
- **Hemisferio sur**: SRH y STP tornádicos son negativos; se usan `neg_stp = −STP` y
  `neg_srh01 = −SRH₀₋₁`. No apliques valor absoluto. Cualquier índice nuevo debe tener una prueba de signo.
- **Sin fugas**: una variable del corte τ usa solo horas ≤ τ; la validación separa por año completo; el
  umbral se elige con validación interna; nada de 2025 ni de 2026 entra al entrenamiento de la
  selección.
- **Regla de decisión fijada antes**: escribe `model_selection.yaml` versión `2.0.0` (variables,
  hiperparámetros, grilla de búsqueda y regla de decisión) y **haz commit antes de correr la
  validación**. No la cambies después de ver resultados. Si hay que cambiarla, sube la versión y dilo en
  el informe.
- **Pocos positivos**: prefiere modelos simples y regularizados; nada de redes neuronales; scikit-learn
  basta salvo que justifiques otra cosa.
- **Reportar conteos** junto a porcentajes ("30 de 42") y la tasa base.
- **No toques `main`**: trabaja en la rama `mejora-modelos-v2`. No hagas push sin pedir permiso.
- **No borres** las salidas de la v1: muévelas a `data/outputs/v1/` (o al prefijo S3 equivalente)
  antes de generar las de la v2.

## 3. Diagnóstico de la v1 (verifícalo antes de corregir)

Cada punto cita el archivo. Comprueba cada uno con una prueba o una consulta a los datos, y anota en
el informe si lo confirmas.

### 3.1 Errores

| # | Dónde | Problema | Efecto |
|---|---|---|---|
| E1 | `scripts/model/cv.py:148-151` y `:141` | En `bootstrap_vs_m1`, `sub` se re-indexa con `reset_index(drop=True)` y luego `metrics_for` usa `sub.index` para indexar `oof[...]`: los puntajes quedan desalineados con sus filas. | `dFAR_vs_M1` y `dFAR_se` están mal. Por ejemplo, para M2 el ΔFAR real es 0,836 − 0,972 = −0,136, pero el reporte da −0,017. El desempate de la regla de decisión usa ese error estándar. |
| E2 | `scripts/model/models.py:130` y `:164` | M2 y M3 usan `C = 1.0` fijo; la grilla `C_grid_log10` de la configuración no se usa. | No se cumple R3/design §6 («C elegido por validación interna»). |
| E3 | `scripts/model/indices.py:68` | `sherbe` es una copia exacta de `sherbs3`. M1 compara SHERBS3 con el umbral de **SHERBE ≥ 1**, y `docs/mesociclones_chile.md` §5.3 advierte que no se puede trasladar. | La «regla física de Marín et al.» no es la publicada. Además hay dos variables duplicadas en M2 y M4. |
| E4 | `config/model_selection.yaml:12-15` frente a `scripts/common.py:62` | El dominio del modelo es lat −43,5…−21,5, pero el recorte ERA5 `south-central-austral` empieza en −30°. La fila de celdas centrada en −29,5 sale de **una sola fila** de puntos ERA5. Las columnas −74,5 y −69,5 y la fila −43,5 también son celdas parciales. | Los eventos al norte de −30° (por ejemplo, Tocopilla, agosto de 2020) cuentan como no detectados aunque no haya datos. Las celdas de borde tienen promedios sesgados. |
| E5 | `scripts/model/features.py:56-65` | Se promedian todos los puntos de 0,25° de la celda de 1°: mar, valle y alta cordillera juntos, sin máscara de terreno. Sobre los Andes, `gamma_75` usa 700 hPa bajo tierra y los índices de niveles bajos son extrapolaciones (`AGENTS.md`, «Trampas del dominio»). | Los candidatos 2026 con mayor puntaje caen en lon −69,5 / −70,5 y lat −29,5 / −30,5: alta cordillera y borde norte. Es muy probable que sean artefactos. |
| E6 | `scripts/model/models.py:219` | En `M4Boosting.explain`, la mediana se toma de la columna ya transformada con `log1p` y se vuelve a transformar en `score`. | Las contribuciones de `cape` y `vgp` salen mal en M4. |
| E7 | `deploy/steps/39_resumen.sh` (genera `scripts/model/resumen_pitch.py`) | Cuando el modelo elegido es M1, la fila de M1 se repite. | Cosmético, pero aparece en `resumen_pitch.md`. |

### 3.2 Problemas de diseño

| # | Dónde | Problema |
|---|---|---|
| D1 | `plan_days.py` | El entrenamiento usa los días con evento más 200 días de control al azar (diseño caso-control). Los días con evento quedan sobrerrepresentados (~15 % de la muestra frente a ~3 % de la temporada; verifica las cifras exactas). El FAR y las alertas por temporada de la validación **no** representan una temporada real, y los puntajes no son probabilidades. |
| D2 | `plan_days.py:73-74` | La «prueba ciega 2025» usa los días con evento más 1 de cada 7 días, no la temporada completa. Además, **2025 ya se usó**: en la v2 no puede presentarse como prueba ciega. |
| D3 | `labels.py` | Solo se marca la celda exacta del evento. Las 8 vecinas del mismo día, con un ambiente casi idéntico, entran como «no etiquetadas» (y = 0) y meten ruido en el entrenamiento. |
| D4 | `labels.py` | Se usa `Date (Gregorian Calendar)` como fecha UTC sin revisar `Hour (UTC)`. Un evento de noche en hora local puede caer el día UTC siguiente. Tampoco se usan `Register` (confianza) ni `Tornado` / `Waterspout`. |
| D5 | Datos | Solo hay `u v t z` en presión y `10u 10v 2t 2d sp cape` en superficie. Sin humedad en altura no hay MLCAPE, CIN ni capa de *inflow* efectiva, así que no hay SHERBE ni STP efectivo. |
| D6 | Datos | Con solo 42 eventos en 2018–2024, el poder estadístico es bajo. ERA5 cubre desde 1940 y el catálogo tiene 68 eventos desde 2015. |
| D7 | Modelos | No hay calibración, el enfoque PU es solo `class_weight="balanced"` y no se modela el sesgo de reporte (población). |
| D8 | Operación | `deploy/steps/*.sh` copia el código a la EC2 incrustado en base64. Es frágil y deja versiones distintas del código en la máquina y en el repo. |

## 4. Entorno AWS

Verifica todo en la fase 0; no lo des por hecho.

- **EC2 actual**: `i-0ea9664c5e9ada5a0`, `c6g.8xlarge` (Graviton2, arm64, 32 vCPU, 64 GiB), us-east-1,
  disco de **40 GiB** y acceso **solo por SSM** (sin SSH). El repo está en `/opt/mesocyclonic-viewer`.
  Los datos están en `data/` de esa ruta. Para enviar pasos desde fuera se usa
  `deploy/ssm_run.ps1 -ScriptPath <archivo.sh>`.
- **ERA5** vive en `s3://nsf-ncar-era5/` (**us-west-2**) y **GOES/GLM** en `noaa-goes16` /
  `noaa-goes19` (us-east-1). La lectura es anónima (`common.s3()`).
- **Almacenamiento**: `scripts/store.py` trata disco local y S3 con la misma interfaz mediante
  `MESO_DATA_ROOT` o `--data-root`.
- **Bucket del equipo**: PENDIENTE. Pregunta al usuario el nombre o, con su aprobación, crea uno en
  la misma región donde corras el cómputo pesado. Guarda en él `crops/`, `tables/` y `outputs/`.
- **Presupuesto**: PENDIENTE. Pregunta el tope de gasto antes de la fase 2.

**Puertas de aprobación** (detente y pide confirmación explícita):

1. antes de crear cualquier recurso (instancia, bucket, volumen, rol IAM, Batch);
2. antes de lanzar una descarga de más de 50 días, con la estimación de tiempo, GB y costo medida en
   un piloto de 5 días;
3. antes de hacer push o abrir una PR.

Etiqueta todo lo que crees con `project=mesocyclonic` y `owner=kiro`. Apaga o termina lo que
crees cuando termine su trabajo e informa qué quedó encendido.

## 5. Plan de trabajo

Cada fase termina con `make check` (o sus comandos equivalentes) en verde y un commit en la rama
`mejora-modelos-v2`.

### Fase 0 — Reconocimiento y sincronización (P0)

1. Confirma la identidad (`aws sts get-caller-identity`), la instancia, su espacio libre en disco y la
   versión del código en `/opt/mesocyclonic-viewer`.
2. Reemplaza la copia en base64 por un flujo reproducible: el repo en la EC2 debe ser un clon de git
   en la rama `mejora-modelos-v2` (si la máquina no tiene credenciales de GitHub, usa un bundle de git
   o `aws s3 sync` del repo a un prefijo del bucket). Documéntalo en `docs/maquina_aws.md`.
3. Inventario: cuántos días hay hoy en `era5_indices`, cuáles son y qué variables trae `era5_sfc`.
   Revisa también las columnas reales de `tornados_chile.xlsx` (formato de `Hour (UTC)`, `Register`,
   `Tornado`, `Waterspout`) y cuántos eventos hay por año entre 2015 y 2025 en abril–septiembre.
   Escríbelo en `docs/claude/inventario_v2.md`.
4. Respalda las salidas de la v1 en `outputs/v1/`.

### Fase 1 — Corrección de errores (P0)

Por cada error, primero una prueba que falle y después la corrección:

- **E1**: conserva un índice de fila original (por ejemplo, la columna `_row`) dentro del bootstrap.
  Prueba: con puntajes sintéticos donde M2 tiene ΔFAR conocido, el bootstrap lo recupera ± 1 EE.
- **E2**: elige `C` con validación interna dejando un año fuera, sobre la grilla de la configuración,
  maximizando PR-AUC. Registra el `C` elegido en cada pliegue (`cv_by_fold.csv`).
- **E3**: separa `sherbs3` de `sherbe`. Mientras no exista SHERBE real (fase 3), M1 se llama
  «regla física aproximada» y lo dice en el informe. Quita la variable duplicada de M2 y M4.
- **E4 y E5**: ver la fase 2.
- **E6**: calcula la mediana sobre la columna cruda y aplica `log1p` una sola vez.
- **E7**: elimina la fila duplicada en `resumen_pitch.py`, que pasa a ser un script versionado del
  repo y no algo que se genera desde base64.

### Fase 2 — Tratamiento de los datos (P0)

1. **Dominio coherente.** El dominio del modelo debe estar contenido en el recorte ERA5. Elige una
   de dos opciones y documéntala:
   - recortar el dominio a lat −30…−43,5, dejando fuera del POD los eventos sin datos y reportándolos
     aparte; o
   - ampliar el recorte ERA5 hacia el norte (por ejemplo, con `--bbox` o una región nueva en
     `common.REGIONS`, hasta −21°) y reprocesar.

   En ambos casos, ninguna celda de 1° puede quedar parcial: ajusta los bordes a múltiplos enteros de
   grado.
2. **Máscara de terreno.** Usa `sfc_height` (ya está en `era5_indices`) o la orografía de
   `e5.oper.invariant`. Anula los índices en los puntos de 0,25° con terreno sobre **1.500 m**
   (el umbral va en la configuración) y también los niveles bajo tierra en `gamma_75` (700 hPa con
   `sp < 700 hPa`). Agrega por celda tanto el **máximo** como el **promedio** de los puntos válidos, y
   la fracción de puntos válidos. Las celdas con menos del 25 % de puntos válidos quedan como
   `completo = False`. Prueba: un perfil sintético con superficie a 3.000 m queda enmascarado.
3. **Variables estáticas por celda**: altura media, fracción de tierra, distancia a la costa y
   latitud. Se usan en los modelos y para estratificar las métricas (costa, valle y cordillera).
4. **Etiquetas.**
   - Convierte la fecha del evento a **UTC** con `Hour (UTC)` cuando exista (los rangos como
     `22-23:25` usan la hora inicial). Si no hay hora, usa la fecha y márcalo
     (`fecha_fuente = local|utc`).
   - Conserva `Register`, `Tornado` y `Waterspout` en `eventos.parquet`.
   - **Zona de exclusión**: las celdas vecinas (3×3) de un positivo, los días d−1, d y d+1, no
     entran al entrenamiento como no etiquetadas (`peso = 0`). Siguen contando en la evaluación según la
     tolerancia. La alternativa (etiqueta suavizada) va como variante en la configuración.
   - Pruebas: conversión de hora local a UTC, rango horario y zona de exclusión.
5. **Temporadas completas.** Procesa **todos** los días de abril a septiembre de 2015–2025 (unos
   2.000 días; parte ya existe). Esto corrige D1 y D2 y suma los eventos de 2015–2017 (D6).
   - Primero un **piloto de 5 días** en la máquina que vayas a usar: mide tiempo por día, GB leídos y
     espacio ocupado, y extrapola al total. **Puerta de aprobación 2.**
   - Recomendación: corre el procesamiento pesado de ERA5 en **us-west-2** (la región de ERA5), en
     una instancia arm64 con gp3 de 200 GB o más y escribiendo los índices directo al bucket del equipo
     (`MESO_DATA_ROOT=s3://...`). Así evitas el tráfico entre regiones y el límite de 40 GiB. Si el
     usuario prefiere no crear recursos, usa la EC2 actual con `run_days_par.sh`, borrando los crudos
     por día (ya lo hace).
   - Todo debe ser idempotente: salta los días ya procesados y deja un registro de fallos para
     reintentarlos.

### Fase 3 — Variables con más señal física (P1)

1. **Humedad en altura (D5).** Agrega `q` en niveles de presión (`download_era5.py` ya lo admite:
   `--pl u v t z q`) y, en superficie, `cin`, `tcwv` y `blh` si están en `e5.oper.an.sfc` (verifica
   las claves con `ListBucket`; `download_era5.SFC` ya trae `tcwv` y `blh`). Con eso calcula en
   `process_era5.py`, vectorizado sobre la grilla:
   - MLCAPE y MLCIN (capa de mezcla de 100 hPa);
   - la capa de *inflow* efectiva y el ESHR, para tener **SHERBE real**;
   - el STP de capa efectiva (Thompson et al. 2012) con el término de CIN, rama *left-mover*;
   - el agua precipitable.

   Antes de lanzar el reprocesamiento masivo, valida contra MetPy en 20 perfiles al azar (error
   relativo menor al 5 %) y contra los valores del brote de 2019 en `docs/mesociclones_chile.md` §3.2.
   Mide el costo extra de `q` (cerca de 1,4 GB más por día) en el piloto.
2. **Rayos GLM (M5).** Desde `GLM-L2-LCFA` (goes16 hasta el 6 de abril de 2025 y goes19 después),
   cuenta los flashes por celda de 1° y día UTC, y por corte (solo horas ≤ τ). Escribe
   `tables/glm_celda_dia.parquet`. Reporta la fracción de eventos con al menos un flash en su celda o
   vecinas (R10). Ojo: la eficiencia de detección cae al sur de unos 40°S; agrégala como covariable o
   estratifica.
3. **GOES (opcional si sobra tiempo).** Temperatura de brillo mínima de la banda 13 y área bajo −50 °C
   por celda-día. Sin corrección de paralaje no se pueden usar en vecindades menores a 3×3.
4. **Sesgo de reporte (D7).** Agrega una covariable de población o de distancia a la ciudad más
   cercana con más de 20.000 habitantes. La fuente es PENDIENTE: propón una fuente pública y
   documéntala. Úsala **solo en el término de propensión** (ver la fase 4), no como predictor del
   ambiente.

### Fase 4 — Modelos (P1)

Fija todo en `model_selection.yaml` 2.0.0 antes de validar:

- **M1**: regla de Marín et al. (2024) fiel (STP efectivo ≤ −0,3 o SHERBE ≥ 1) si la fase 3 está
  hecha; si no, la aproximada, con ese nombre.
- **M2**: logística L2 con `C` ajustado (E2). Haz un diagnóstico de colinealidad (VIF) entre
  `neg_stp`, `sherbe` y `vgp`, porque comparten la cizalle, y elige como máximo 6 variables.
- **M3**: splines + L2, con `C` ajustado.
- **M4**: boosting monótono, con monotonicidad solo en los índices físicos (no en las estáticas).
- **M6 (nuevo)**: logística PU con propensión de etiquetado (Elkan y Noto 2008): P(reportado) =
  P(tornado | ambiente) × c(población, año, hora). Compárala con M2.
- **M5**: el modelo elegido multiplicado por un filtro de GLM, solo en el corte «día» y solo si la
  fracción de eventos con flashes es ≥ 0,8.
- **Calibración**: calibración isotónica o de Platt sobre las predicciones fuera de pliegue, ya con
  temporadas completas. Reporta la curva de fiabilidad y el Brier score.
- **Variabilidad**: repite la validación con 5 semillas (submuestreo de no etiquetados) y reporta la
  media ± desviación estándar.

### Fase 5 — Validación y decisión (P0 cuando las fases 1–2 estén listas)

1. Validación dejando un año fuera para **2015–2024**, cortes «día» y «12utc», sobre **temporadas
   completas**.
2. Métricas tolerantes (vecindad 1 y ventana {d−1, d}): POD, FAR, días por detección, PR-AUC, CSI,
   **alertas por temporada** y Brier. Repórtalas también estratificadas por zona (costa, valle y
   cordillera) y por tipo (tornado o tromba).
3. Bootstrap por fecha corregido (E1), con 1.000 réplicas.
4. La regla de decisión de la 2.0.0 debe agregar a la de la v1 una condición de **alertas por
   temporada** (propón el tope y fíjalo antes de validar).
5. **Comparación v1 frente a v2** con la misma vara: una tabla con la v1 recalculada sobre temporadas
   completas.
6. **Revisión antifuga**: antes de mostrar cifras, revisa `cv_report.csv` y `decision_*.md` con la
   lista de `tornados-contexto.md` (sin futuro, sin fechas compartidas y sin 2025 en la selección).
   Deja el resultado escrito en el informe.

### Fase 6 — 2025, 2026 y entrega (P1)

1. **2025**: evalúa la temporada **completa** (abril–septiembre) con el modelo entrenado hasta 2024.
   Etiquétalo como «evaluación de seguimiento (2025 ya fue usado por la v1)», no como prueba ciega.
2. **2026**: reentrena hasta 2025 y puntúa abril–julio (y agosto–septiembre si ERA5 ya los publicó;
   verifícalo). Escribe `candidatos_2026_<corte>.csv` con `top1`–`top3`, la zona y la fracción de
   terreno válido. Revisa a mano los 20 primeros: ¿alguno es un artefacto de borde o de cordillera?
3. Propón cómo hacer una **prueba ciega real** en la v2. Por ejemplo, fijar hoy el modelo y el umbral
   y evaluarlos cuando el catálogo incorpore los eventos de 2026.
4. Actualiza `docs/resultados_modelo.md` (sección v2), `resumen_pitch.md` y la app
   `scripts/model/app_resultados.py`, que muestra v1 y v2 lado a lado.
5. Copia las salidas al bucket y trae a local `outputs/` (los candidatos completos, no solo las
   primeras 300 filas).

## 6. Entregables

- Código: `scripts/model/*` corregido y extendido; cambios en `scripts/pipeline/process_era5.py`
  (índices con humedad y máscara), `labels.py` (UTC, exclusión y metadatos) y el nuevo
  `scripts/model/glm.py`. `resumen_pitch.py` queda versionado.
- Configuración: `scripts/model/config/model_selection.yaml` versión 2.0.0, con su commit **previo**
  a la validación.
- Pruebas nuevas en `tests/`: bootstrap alineado, `C` elegido por validación interna, SHERBE ≠
  SHERBS3, máscara de terreno, celdas sin bordes parciales, conversión a UTC, zona de exclusión, signo
  de los índices nuevos, corte sin futuro para GLM y la mediana de `explain` en M4.
- Datos en el bucket: `crops/<región>/era5_indices/` (temporadas completas 2015–2026),
  `tables/features_<corte>.parquet`, `tables/eventos.parquet`, `tables/glm_celda_dia.parquet`,
  `outputs/v1/` y `outputs/v2/`.
- Documentos: `docs/claude/inventario_v2.md` y `docs/resultados_modelo.md` actualizado con la tabla
  v1 frente a v2, las limitaciones, los costos medidos (horas de instancia, GB leídos y almacenamiento
  en S3) y qué recursos de AWS quedaron encendidos.

## 7. Criterio de término

- `make check` pasa (ruff, formato, pyright y pruebas).
- Existen `outputs/v2/cv_report.csv`, `cv_by_fold.csv`, `decision_dia.md`, `decision_12utc.md`,
  `seguimiento_2025_<corte>.csv`, `candidatos_2026_<corte>.csv` y `resumen_pitch.md`.
- El informe explica, con conteos, si la v2 mejora a la v1 en POD, FAR, alertas por temporada y
  PR-AUC, y si los candidatos 2026 de mayor puntaje dejaron de estar en cordillera o en bordes.
- No quedan recursos de AWS encendidos sin que el usuario lo sepa.

## 8. Cómo reportar el avance

Al terminar cada fase, escribe un resumen corto: qué hiciste, qué verificaste (comando y resultado),
qué cifras cambiaron y qué queda pendiente. Si algo de este documento resulta falso al verificarlo
(un número de línea, una variable o un bucket), dilo y ajusta el plan en vez de forzarlo.
