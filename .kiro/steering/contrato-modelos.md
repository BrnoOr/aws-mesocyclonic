---
inclusion: fileMatch
fileMatchPattern: ["scripts/vortice/core/**", "scripts/vortice/model_cards/**", "scripts/vortice/registry.yaml", "scripts/vortice/objective.yaml"]
---

# Contrato de modelos de Vórtice

## La idea

El **objetivo** es fijo y el **modelo** es intercambiable. Un modelo nuevo entra a Vórtice con una
ficha YAML y un artefacto; no se toca la app, el arnés ni el objetivo.

## Interfaz mínima (`core/contract.py`)

```python
class ScoringModel(Protocol):
    """Modelo que ordena celdas-hora según lo favorable del entorno."""

    card: ModelCard

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Puntaje en [0, 1], uno por fila, mismo orden que X. Mayor = más favorable."""

    def explain(self, X: pd.DataFrame) -> pd.DataFrame | None:
        """Contribución por variable y fila (opcional; None si el modelo no la ofrece)."""
```

- `X` trae **solo** las columnas que la ficha declara en `features`, y el arnés comprueba que sean
  un subconjunto de `objective.features.allowed`. El modelo nunca ve etiquetas ni metadatos.
- `score` debe ser determinista, sin `NaN` en la salida y con valores en [0, 1]. Si el modelo
  entrega otra escala, el adaptador la calibra o la transforma y lo dice en la ficha.

## Ficha (`model_cards/<id>.yaml`)

```yaml
id: forest_wind_v1            # snake_case, único
name: Bosque aleatorio (viento)
version: 1.0.0
owner: equipo-mesociclones
adapter: sklearn_joblib        # sklearn_joblib | rule | onnx | sagemaker_endpoint | python_entrypoint
artifact: data/vortice/artifacts/forest_wind_v1/modelo.joblib   # ruta local o s3://
features: [shear_01, shear_03, srh_01, stp_lm, vgp_01, sherbs3]
lead_hours: [0]                # anticipaciones para las que sirve
trained_on: [train]            # particiones usadas para ajustar (nunca test)
nan_policy: impute_median      # impute_median | model_native | drop_rows
complexity: 3                  # para el desempate "el más simple a un error estándar"
description: >
  Texto en español: qué es, con qué se entrenó y sus límites.
```

## Reglas del arnés

1. Rechaza una ficha con `trained_on` que incluya `test`, o con variables prohibidas.
2. Elige el umbral en `val` y lo aplica una sola vez a `test`.
3. Guarda cada corrida bajo el **hash del objetivo**; si el objetivo cambia, las corridas viejas no
   se mezclan con las nuevas.
4. Las líneas base (`climatology`, `rule_stp`, `rule_sherbs3`, `rule_vgp`) se registran siempre.
