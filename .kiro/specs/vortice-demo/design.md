# Diseño — Vórtice, demo con modelos intercambiables

## 1. Visión general

```
                 objective.yaml (congelado, hash)
                          │
 model_cards/*.yaml ──► registry.py ──► adaptadores ──► ScoringModel
                          │                                  │
 dataset real ─┐          ▼                                  ▼
 (parquet)     ├──► data.py ──► X (solo columnas de la ficha) ──► harness.py
 sintético ────┘                                               │
                                                               ▼
                          data/vortice/runs/<hash>/<model_id>/  +  leaderboard.parquet
                                                               │
                                                     promote.py ──► champion.json
                                                               │
                                                               ▼
                                         app Streamlit (solo lectura, selector de modelo)
```

Tres ideas sostienen el diseño:

1. **El objetivo es un dato, no código.** Todo lo que define «qué es un buen modelo» está en
   `objective.yaml`. El arnés lo interpreta; los modelos no lo conocen.
2. **El arnés es el único que ve etiquetas.** Los adaptadores reciben un `DataFrame` recortado a las
   columnas de su ficha. La fuga queda impedida por construcción, no por disciplina.
3. **La app lee resultados, no modelos.** La arena y los candidatos salen de las corridas. Solo la
   repetición y la ficha cargan el modelo para puntuar un día o explicar.

Antes de escribir código: inspeccionar `scripts/dataset/`, `scripts/model/` (`kpis.py`, `train.py`,
`models.py`, `decide.py`) y `New_Web/scripts/webapp/model_app.py`. Importar lo que ya calcule el
acierto tolerante, la curva de operación o el bootstrap; no duplicarlo.

## 2. `objective.yaml` (versión 1.0.0)

```yaml
version: "1.0.0"
name: "Entorno favorable a tornado o tromba reportado"
unit: {grain: cell_hour, grid_deg: 0.25, region: south-central-austral}
target:
  column: label
  meaning: "tornado o tromba del catálogo a ≤ 0,2° y misma hora (PU: 0 = sin etiqueta)"
  lead_hours: [0, 1, 3, 6]
  primary_lead: 0
features:
  allowed: [shear_01, shear_03, shear_06, srh_01, srh_03, lcl, gamma_03, gamma_75, vgp_01,
            stp_lm, sherbs3, u_06, v_06, u_lm, v_lm, u_rm, v_rm, sfc_height,
            goes_bt_min, goes_bt_mean, goes_bt_trend]
  forbidden: [label, event_uid, confirmed, hour_is_range, partition, group, date, region]
partitions:
  source: scripts/dataset/features.py      # partition_of(); no se redefinen años aquí
  fit_allowed: [train, val]
  threshold_on: val
  evaluate_on: test
  excluded: [dev]
  inference: inference
tolerance: {radius_deg: 0.5, hours: 1, same_day: true}
metrics: [pod_event, far_day, alert_days_per_hit, pr_auc, brier, base_rate]
bootstrap: {unit: group, replicas: 1000, ci: 0.90, seed: 20260115}
pod_target: 0.70
gates:
  beats_climatology_on: pr_auc
  far_le_best_rule: true
champion:
  tie_break: one_standard_error
  order_by: complexity
  fallback: best_rule
display:
  mountain_warning_m: 1500
```

`core/contract.py` define `Objective` (pydantic) con exactamente estos campos. `objective_hash()`
serializa el modelo validado con claves ordenadas y devuelve `sha256[:12]`.

## 3. Contrato (`core/contract.py`)

```python
class ModelCard(BaseModel):
    """Ficha de un modelo registrado."""
    id: str  # patrón ^[a-z][a-z0-9_]*$
    name: str
    version: str
    owner: str
    adapter: Literal["sklearn_joblib", "rule", "onnx", "sagemaker_endpoint", "python_entrypoint"]
    artifact: str | None = None
    params: dict[str, Any] = {}
    features: list[str]
    lead_hours: list[int]
    trained_on: list[str]
    nan_policy: Literal["impute_median", "model_native", "drop_rows"]
    complexity: int
    description: str


class ScoringModel(Protocol):
    """Modelo intercambiable de Vórtice."""
    card: ModelCard
    def score(self, X: pd.DataFrame) -> np.ndarray: ...
    def explain(self, X: pd.DataFrame) -> pd.DataFrame | None: ...


def validate_card(card: ModelCard, objective: Objective) -> list[str]:
    """Lista de errores (vacía si la ficha es válida para el objetivo)."""
```

## 4. Adaptadores (`core/adapters/`)

| Adaptador | Artefacto | `score` | `explain` |
|---|---|---|---|
| `sklearn_joblib` | `.joblib` con estimador o bundle `{model, features, metadata}` | `predict_proba[:, 1]` | Contribución por permutación local o coeficientes si es lineal |
| `rule` | ninguno; `params` con `expr`, `direction`, `scale` | Transformación monótona del índice a [0, 1] (logística con `scale`) | El índice mismo |
| `onnx` | `.onnx` | `onnxruntime`, salida de probabilidad | `None` |
| `sagemaker_endpoint` | nombre de endpoint en `params` | `invoke_endpoint` por lotes CSV | `None` |
| `python_entrypoint` | `"modulo:Clase"` en `params` | La clase cumple `ScoringModel` | Lo que entregue |

`registry.py` mapea `adapter → clase` en un diccionario; agregar un adaptador es una entrada más.

Líneas base como fichas `rule`:

| id | `expr` | Nota |
|---|---|---|
| `climatology` | tasa base por mes y banda de 2° de latitud, estimada en `train` | `complexity: 0` |
| `rule_stp` | `-stp_lm`, umbral de referencia 0,3 | rama *left-mover* |
| `rule_sherbs3` | `sherbs3`, referencia 1,0 | |
| `rule_vgp` | `vgp_01`, referencia 0,1 | |

`climatology` necesita `month` y `lat`: el arnés las deriva de `date`/`lat` solo para ese adaptador
(se declara `uses_context: true` en `params`); no entran en `features.allowed` de otros modelos.

## 5. Datos (`core/data.py`, `core/synthetic.py`)

- `load_dataset(lead_h, mode)` → `DataFrame` con el esquema de `dataset_para_kiro.md`.
  `mode="real"` lee `data/dataset/<region>/dataset_lead{h}h.parquet`; `mode="synthetic"` llama a
  `synthetic.make(seed)`; `mode="auto"` usa real si existe.
- `synthetic.make` genera ~20 días por partición sobre una grilla de 40×20 celdas, con eventos cuya
  probabilidad crece con `-stp_lm` y `shear_06`, valores negativos de SRH en los positivos, `NaN` en
  10 % de `goes_*` y algunas celdas con `sfc_height > 1500`. Así las pruebas ejercitan signos, NaN y
  aviso de cordillera.
- `feature_view(df, card)` devuelve `df[card.features]` y nada más.

## 6. Arnés (`core/harness.py`)

```
for lead in card.lead_hours ∩ objective.target.lead_hours:
    df = load_dataset(lead); df = df[partition != dev]
    s_val  = model.score(feature_view(df_val));  thr = choose_threshold(events_val, s_val, pod_target)
    s_test = model.score(feature_view(df_test)); m = metrics(events_test, s_test, thr)
    ci = bootstrap_by_group(...)
    write run
```

- `choose_threshold`: el umbral más alto con POD por evento ≥ `pod_target`; si no lo alcanza, el
  que maximiza POD, marcado `pod_target_reached: false`.
- Acierto tolerante: un evento se detecta si alguna celda-hora a ≤ `radius_deg` y ± `hours` supera el
  umbral. Reutilizar `scripts/model/kpis.py` si ya lo implementa.
- FAR por día: días con alguna alerta y sin evento detectado / días con alerta.
- `metrics.json`: cifras, IC, `n_events`, `n_days`, `threshold`, `objective_hash`, `card.version`,
  duración, versión de dependencias.

## 7. Campeón (`core/champion.py`)

Función pura `pick_champion(rows: pd.DataFrame, objective: Objective) -> ChampionDecision` sobre la
arena del hash vigente. Implementa R4 tal cual. Probada con tablas construidas a mano.

## 8. App (`scripts/vortice/app/`)

| Página | Fuente | Contenido |
|---|---|---|
| Objetivo | `objective.yaml` | Pregunta, unidad, etiqueta, particiones, métricas, compuertas, «lo que no se puede concluir» |
| Repetición 30-may-2019 | dataset `dev` + modelo + regla | Dos mapas lado a lado por hora, eventos encima, deslizador, rótulo de desarrollo |
| Arena | `leaderboard.parquet`, `champion.json` | Tabla, gráfico POD vs FAR con IC, compuertas ✓/✗, insignia |
| Candidatos | `scores_*` del campeón | Tabla y mapa; aviso de cordillera |
| Ficha del modelo | ficha + `explain` | Metadatos, variables, contribuciones medias |
| Sumar un modelo | `contrato-modelos.md` | Pasos y plantilla de ficha para copiar |

- Barra lateral: selector de modelo (registrados con corrida en el hash vigente), selector de
  `lead_h`, rótulo de modo (real / sintético) y hash corto del objetivo.
- Tema en `app/theme.py` (un solo lugar), columnas con un ayudante que apila en ancho < 900 px,
  siguiendo el patrón de `scripts/viewer/viewer_app/theme.py`.
- Migrar desde `New_Web/scripts/webapp/model_app.py` las funciones de mapa y curva que sirvan.

## 9. Almacén (`core/store.py`)

`Store(root)` con `read_parquet`, `write_parquet`, `read_json`, `write_json`, `exists`, `open`.
Usa `fsspec` para que `root` sea local o `s3://`. La app lo crea con
`Store(os.environ.get("VORTICE_STORE", "data/vortice"))`.

## 10. Despliegue

- `scripts/vortice/Dockerfile` (o adaptar el `Dockerfile` raíz): `uv sync --frozen --no-dev`,
  `streamlit run scripts/vortice/app/app.py --server.port 8502`.
- `deploy/steps/vortice_deploy.sh`: cambiar la ruta de entrada y exportar `VORTICE_STORE`.
- Opción S3: `aws s3 sync data/vortice s3://<bucket>/vortice/` desde quien evalúa; la app solo lee.

## 11. Decisiones abiertas

- Si el dataset real no trae `lead_h > 0` completo, la arena muestra solo `lead_h = 0`.
- El adaptador `sagemaker_endpoint` es opcional para la demo; queda implementado y probado con un
  cliente falso.
