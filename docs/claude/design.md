# Diseño — Selección de modelo para detección y anticipación de tornados

## 1. Visión general

```
ERA5 horario procesado (run_days.sh)
        │
        ▼
indices.py ── índices horarios por celda (convención hemisferio sur)
        │
        ▼
features.py --corte {dia,12utc,00utc} ── agregados celda-día ──► data/tables/features_<corte>.parquet
        │                                                         + labels.py (y, eventos)
        ▼
cv.py ── validación dejando un año fuera, 2018–2024, modelos M0–M4 (+M5)
        │      └─ kpis.py (acierto tolerante, POD, FAR, días por detección, PR-AUC)
        ▼
decide.py ── regla fijada en config ──► decision_<corte>.md
        │
        ▼
train.py / score.py ── prueba ciega 2025 ──► blind_2025_<corte>.csv
                    └─ puntaje 2026      ──► candidatos_2026_<corte>.csv
```

Antes de escribir código, **inspeccionar lo que ya existe** en `scripts/model/` (`plan_days.py`,
`run_days.sh`, `baselines.py`, `train.py`, `score.py`, `kpis.py`) y en las salidas que deja `run_days.sh`.
Reutilizar los índices, nombres de columnas y métricas que ya estén calculados; este diseño describe la
interfaz esperada, no obliga a reescribir lo que funciona.

## 2. Módulos

| Archivo | Responsabilidad | Nuevo o existente |
|---|---|---|
| `scripts/model/indices.py` | Índices horarios por celda a partir de los perfiles ERA5 | Nuevo, salvo que el pipeline ya los entregue |
| `scripts/model/features.py` | Agregados celda-día por corte | Nuevo |
| `scripts/model/labels.py` | Etiquetas por celda-día y tabla de eventos | Nuevo o extraer de `baselines.py` |
| `scripts/model/models.py` | M0–M5 con interfaz común | Nuevo |
| `scripts/model/cv.py` | Validación cruzada, umbrales, bootstrap | Nuevo |
| `scripts/model/decide.py` | Regla de decisión | Nuevo |
| `scripts/model/kpis.py` | Métricas con acierto tolerante | Existente: extender |
| `scripts/model/train.py`, `score.py` | Entrenar y puntuar el modelo elegido | Existentes: agregar `--modelo` y `--corte` |
| `scripts/model/config/model_selection.yaml` | Variables, hiperparámetros, regla de decisión | Nuevo |
| `tests/` | Pruebas antifuga, de signo y de pliegues | Nuevo |

## 3. Índices horarios (`indices.py`)

Los perfiles vienen en niveles de presión (`u`, `v`, `t`, `z`). La altura sobre el suelo es
`h = z/g − z_sfc/g`. Interpolar linealmente en `h` a 0, 0,5, 1, 1,5, 3 y 6 km.

| Índice | Definición | Nota |
|---|---|---|
| Cizalle 0–6 km, `bwd06` | ‖V(6 km) − V(0)‖ (m/s) | V(0): viento a 10 m si está entre las variables de superficie; si no, el nivel más bajo sobre el suelo |
| Cizalle 0–3 km, `s03` | ‖V(3 km) − V(0)‖ (m/s) | |
| Gradiente 0–3 km, `lr03` | −(T(3 km) − T(0))/3 (K/km) | T(0): temperatura a 2 m |
| Gradiente 700–500 hPa, `lr75` | −(T₅₀₀ − T₇₀₀)/((z₅₀₀ − z₇₀₀)/g) × 1000 (K/km) | |
| SRH 0–1 km, `srh01` | −∫₀^{1 km} k̂ · ((V − c) × ∂V/∂z) dz (m²/s²) | c: movimiento de tormenta de Bunkers. En el hemisferio sur usar la **supercelda izquierda** (ciclónica). Si el pipeline ya trae SRH, reutilizarla |
| STP (capa fija) | (CAPE/1500) · ((2000 − LCL)/1000) · (SRH01/150) · (BWD06/20) | Término LCL = 1 si LCL < 1000 m y 0 si > 2000 m. Término BWD = 0 si < 12,5 m/s y 1,5 si > 30 m/s. Con SRH01 negativa, STP < 0 |
| SHERBS3 | (s03/26) · (lr03/5,2) · (lr75/5,6) | Sherburn y Parker (2014). **Verificar constantes contra el paper** |
| SHERBE | (ESHR/27) · (lr03/5,2) · (lr75/5,6) | ESHR exige capa de inflow efectiva (requiere humedad en altura). Si no se puede, usar `bwd06` como aproximación, llamar la columna `sherbe_aprox` y documentarlo |
| VGP | (s03/3000 m) · √CAPE (adimensional) | Verificar contra la definición usada en Vicencio et al. (2021) y Caballero-Morán y Rondanelli (2025) |

- CAPE: usar la variable `cape` de superficie de ERA5 si está entre las seis descargadas. Si no está,
  dejar STP y VGP en NaN y avisar (R1.5); no reconstruir CAPE sin humedad en altura.
- LCL: aproximar con 125 · (T₂ₘ − Td₂ₘ) m si existen `2t` y `2d`; si no, fijar el término LCL en 1 y
  documentarlo.
- Variables del modelo: `neg_stp = −STP`, `neg_srh01 = −SRH01`. Los demás índices ya son positivos cuando
  son favorables.

## 4. Variables celda-día (`features.py`)

### Cortes

| Corte | τ | Ventana usada | Requiere día d−1 |
|---|---|---|---|
| `dia` | 23 UTC del día d | 00–23 UTC del día d | No |
| `12utc` | 12 UTC del día d | 00–12 UTC del día d | No |
| `00utc` | 00 UTC del día d | 00 UTC del día d−1 a 00 UTC del día d | **Sí**: hay que agregar los días d−1 a las listas de `run_days.sh` (tarea opcional) |

Si el catálogo trae hora del evento, agregar más adelante el corte `evento_menos_L` (τ = hora del evento −
L); queda fuera del alcance inicial.

### Agregados por índice I (dentro de la ventana)

- `I_max`: máximo horario.
- `I_tend6`: máx_h (I_h − I_{h−6}), solo con pares de horas dentro de la ventana.
- `I_pers`: número de horas con I_h sobre el umbral de configuración (por defecto: `neg_stp` > 0,3,
  `sherbe` > 1, `sherbs3` > 1).
- `I_max3x3`: máximo de `I_max` en la celda y sus 8 vecinas.

Variables de contexto (para M0 y como control): `mes`, `banda_lat` (bandas de 2°).

### Contrato de salida

`data/tables/features_<corte>.parquet`: `fecha` (date), `lat`, `lon` (centro de celda, float),
`anio`, `mes`, `banda_lat`, las variables anteriores, `completo` (bool), `y` (int, desde `labels.py`),
`n_eventos` (int).

## 5. Etiquetas (`labels.py`)

- Leer `data/tornados_chile.xlsx`. Asignar cada evento a la celda de 1° que contiene su punto inicial y a
  su fecha UTC (si el catálogo trae hora local, convertir a UTC; si solo trae fecha, usarla tal cual y
  documentarlo).
- Salidas: `y` por celda-día y `data/tables/eventos.parquet` con `id_evento`, `fecha`, `lat`, `lon`.
- Imprimir positivos por año.

## 6. Modelos (`models.py`)

Interfaz común:

```python
class Modelo:
    nombre: str
    complejidad: int           # para la regla de decisión: M2=1, M3=2, M4=3
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "Modelo": ...
    def score(self, X: pd.DataFrame) -> np.ndarray: ...       # mayor = más probable
    def explain(self, X: pd.DataFrame) -> pd.DataFrame: ...   # contribución por variable
```

| Modelo | Implementación | Variables por defecto | `explain` |
|---|---|---|---|
| M0 climatología | (positivos + α)/(celdas-día + α + β) por `mes` × `banda_lat`, con α = 1 y β = 50 | `mes`, `banda_lat` | Constante por grupo |
| M1 regla física | score = máx(`neg_stp_max`/0,3, `sherbe_max`/1); alerta si score ≥ 1 | `neg_stp_max`, `sherbe_max` | Cuál de los dos términos domina |
| M2 logística L2 | `StandardScaler` + `LogisticRegression(penalty="l2")`; C elegido por validación interna dejando un año fuera en una grilla logarítmica de 10⁻² a 10² | `neg_stp_max`, `sherbe_max`, `vgp_max`, `neg_srh01_tend6`, `sherbe_max3x3` | β_k · z_k |
| M3 splines | `SplineTransformer(n_knots=4, degree=3)` + `LogisticRegression(l2)` | `neg_stp_max`, `sherbe_max`, `vgp_max` | Suma de contribuciones de las bases de cada variable |
| M4 boosting | `HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=20, l2_regularization=1.0, monotonic_cst=+1 para índices)`, pesos de clase balanceados | Todas las `*_max`, `*_tend6`, `*_pers`, `*_max3x3` (~15) | Importancia por permutación global; por fila, SHAP solo si ya está instalado |
| M5 filtro GLM | score del modelo elegido × 1[`n_destellos` en celda o vecinas ≥ 1] | Las del elegido + `n_destellos` | La del elegido |

Usar scikit-learn para todo (no agregar LightGBM, pygam ni redes neuronales). Transformar con
`log1p` los índices muy asimétricos (CAPE, VGP), y declararlo en la configuración.

## 7. Validación (`cv.py`)

```
para cada corte c:
  datos = features_c[completo & anio <= 2024]
  para cada modelo m:
    para cada anio_prueba en 2018..2024:
      entren = datos[anio != anio_prueba]; prueba = datos[anio == anio_prueba]
      # umbral con validación interna sobre entren
      oof = predicciones dejando un año fuera dentro de entren
      umbral = máx t tal que POD_tolerante(oof ≥ t) ≥ 0,70
      m.fit(entren); s = m.score(prueba)
      guardar (fila, s, s ≥ umbral, anio_prueba)
    métricas agrupadas sobre los 7 años (kpis.py)
    bootstrap: 1000 remuestreos de fechas con reemplazo → ΔFAR(m − M1), ΔPOD, ΔPR-AUC
```

- Métricas con acierto tolerante (configurable: vecindad 1 celda, ventana de días {d−1, d}).
  - POD = eventos detectados / eventos.
  - FAR = alertas que no corresponden a ningún evento / alertas.
  - Días por detección = fechas distintas con al menos una alerta / eventos detectados.
- Si `kpis.py` ya define estas métricas, reutilizarlas y solo agregar la tolerancia.
- Recordar en el reporte que el FAR se mide sobre días de evento y de control, y sobrestima el real.

## 8. Regla de decisión (`decide.py`)

Leída de `config/model_selection.yaml`, que se escribe antes de correr la validación:

```yaml
decision:
  pod_objetivo: 0.70
  elegible:
    supera_m0_en: pr_auc
    far_max_vs_m1: 0.0        # FAR(m) − FAR(M1) ≤ 0
  desempate: un_error_estandar
  orden_simplicidad: [M2, M3, M4]
  si_ninguno: M1
```

Salida `decision_<corte>.md`: tabla de modelos con POD, FAR, días por detección, PR-AUC, intervalos, modelo
elegido y razón en una línea.

## 9. Prueba ciega, puntaje y explicación

- `train.py --until 2024 --modelo elegido --corte <c>`, luego `score.py --start 2025-04-01 --end
  2025-09-30 --evaluate --corte <c>`. El umbral es el de la validación cruzada.
- `train.py --until 2025` y `score.py --start 2026-04-01 --end 2026-09-30 --corte <c>`.
- `candidatos_2026_<corte>.csv`: `fecha`, `lat`, `lon`, `score`, `alerta`, índices `*_max`, `top1`–`top3`
  (variable y contribución), `ultimo_dia_era5`.
- En las fichas, leer en conjunto las contribuciones de `neg_stp`, `sherbe` y `vgp`, porque comparten la
  componente de cizalle.

## 10. Errores y casos borde

- Celda sin datos ERA5 en una hora: el agregado usa las horas disponibles; si faltan más del 25 % de las
  horas de la ventana, `completo = False`.
- Años con 0 positivos en prueba: el pliegue se mantiene en la agrupación, pero no se calcula POD por año.
- Umbral imposible (POD 70 % no alcanzable en la validación interna): usar el umbral mínimo y anotarlo.

## 11. Pruebas (`tests/`)

| Prueba | Qué verifica |
|---|---|
| `test_corte_sin_futuro` | Alterar horas > τ no cambia las variables del corte |
| `test_pliegues_sin_fecha_compartida` | Ninguna fecha aparece en entrenamiento y prueba del mismo pliegue |
| `test_signo_hemisferio_sur` | Perfil sintético ciclónico del hemisferio sur produce `neg_srh01 > 0` y `neg_stp ≥ 0` |
| `test_regla_decision` | Con métricas simuladas, `decide.py` elige el modelo esperado |
| `test_kpis_tolerancia` | Una alerta en celda vecina el día anterior cuenta como acierto |

## 12. Supuestos a verificar al inicio

1. Qué índices y columnas entrega hoy `run_days.sh` (puede que STP o SRH ya estén).
2. Si las seis variables de superficie incluyen `cape`, `2t`, `2d`, `10u`, `10v`.
3. Si el catálogo trae hora y en qué zona horaria.
4. Constantes de SHERB y definición de VGP contra los papers.
