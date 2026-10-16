---
inclusion: always
---

# Estructura

## Lo que ya existe y Vórtice reutiliza (no reescribir)

| Ruta | Para qué sirve en Vórtice |
|---|---|
| `scripts/common.py` | Regiones, rutas, fechas, S3 anónimo |
| `scripts/dataset/features.py` | `partition_of`, constantes de particiones, `LEAD_HOURS`, `MATCH_RADIUS_DEG` |
| `scripts/dataset/build_dataset.py` | Genera `data/dataset/<region>/dataset_lead{0,1,3,6}h.parquet` (entrada real de Vórtice) |
| `scripts/dataset/dataset_para_kiro.md` | Esquema del parquet y reglas para entrenar (#[[file:scripts/dataset/dataset_para_kiro.md]]) |
| `scripts/model/kpis.py`, `scripts/model/config/model_selection.yaml` | Acierto tolerante, POD/FAR, regla de decisión ya acordada |
| `New_Web/` | App Vórtice v1 (solo un modelo) y `modelo.joblib` de ejemplo: fuente para migrar páginas |
| `deploy/deploy_vortice.ps1`, `deploy/steps/vortice_deploy.sh` | Despliegue a la EC2 por SSM |

## Lo nuevo de Vórtice

```
scripts/vortice/
├── objective.yaml          objetivo congelado (versión + hash): lo que manda
├── registry.yaml           modelos registrados (id → ficha)
├── model_cards/<id>.yaml   ficha de cada modelo (versionada)
├── core/
│   ├── contract.py         Protocol ScoringModel, ModelCard, Objective (pydantic)
│   ├── adapters/           sklearn_joblib, rule, onnx, sagemaker_endpoint, python_entrypoint
│   ├── registry.py         carga fichas y construye adaptadores
│   ├── store.py            lectura/escritura local o s3:// (VORTICE_STORE)
│   ├── data.py             carga el dataset real o el sintético; recorta columnas permitidas
│   ├── synthetic.py        dataset sintético con el esquema real (semilla fija)
│   ├── harness.py          evaluación con el protocolo del objetivo
│   └── champion.py         regla de campeón del objetivo
├── register.py             CLI: valida y registra un modelo
├── evaluate.py             CLI: evalúa uno o todos contra el objetivo
├── promote.py              CLI: aplica la regla y escribe el campeón
└── app/
    ├── app.py              entrada Streamlit
    └── pages/              objetivo, repetición 2019, arena, candidatos, ficha, sumar modelo
data/vortice/               (ignorado) runs/, leaderboard.parquet, champion.json, artefactos
tests/test_vortice_*.py
```

Los nombres anteriores son el punto de partida del diseño; si al inspeccionar el código aparece una
función que ya hace lo mismo, se importa en vez de duplicarla.
