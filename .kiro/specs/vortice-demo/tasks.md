# Tareas — Vórtice, demo con modelos intercambiables

Cada tarea termina con `make check` en verde. Antes de cada una, revisar el código existente y
reutilizarlo.

## Fase 0 — Reconocimiento

- [ ] 0.1 Leer `scripts/dataset/features.py`, `scripts/dataset/dataset_para_kiro.md`,
  `scripts/model/kpis.py`, `scripts/model/config/model_selection.yaml` y
  `New_Web/scripts/webapp/model_app.py`. Anotar en `scripts/vortice/README.md` (sección
  «Reutilizado») qué funciones se importan y cuáles faltan.
  - _Requisitos: R1.5, R3.3_
- [ ] 0.2 Comprobar si existe `data/dataset/*/dataset_lead*h.parquet`; si no, dejarlo dicho: la demo
  arranca en modo sintético.
  - _Requisitos: R5.8_

## Fase 1 — Objetivo y contrato

- [ ] 1.1 Crear `scripts/vortice/objective.yaml` (design §2) y `core/contract.py` con `Objective`,
  `ModelCard`, `ScoringModel`, `objective_hash` y `validate_card`.
  - _Requisitos: R1.1, R1.2, R1.3, R2.1, R2.4, R2.5_
- [ ] 1.2 `tests/test_vortice_contract.py`: hash estable ante reordenar claves, rechazo de variable
  prohibida, rechazo de `trained_on: [test]`, error claro con YAML inválido.
  - _Requisitos: R8.2_
- [ ] 1.3 Commit del objetivo **antes** de evaluar cualquier modelo.
  - _Requisitos: R1_

## Fase 2 — Datos

- [ ] 2.1 `core/synthetic.py` y `core/data.py` (design §5), con `feature_view`.
  - _Requisitos: R2.6, R5.8_
- [ ] 2.2 `tests/test_vortice_data.py`: esquema igual al real, signos negativos de SRH en positivos,
  `NaN` en GOES, `feature_view` no deja pasar columnas extra.
  - _Requisitos: R8.1_

## Fase 3 — Adaptadores y registro

- [ ] 3.1 Adaptadores `rule` y `sklearn_joblib` (acepta estimador o bundle `{model, features,
  metadata}`), y `registry.py`.
  - _Requisitos: R2.2, R2.7_
- [ ] 3.2 Fichas de líneas base (`climatology`, `rule_stp`, `rule_sherbs3`, `rule_vgp`) y de
  `forest_wind_v1` apuntando a una copia de `New_Web/modelo.joblib` en `data/vortice/artifacts/`.
  - _Requisitos: R2.7, R2.8_
- [ ] 3.3 CLI `register.py --card [--dry-run]` con las comprobaciones de R2.3 (`--dry-run` valida
  sin tocar `registry.yaml`; lo usa el hook «Validar ficha de modelo»).
  - _Requisitos: R2.3, R2.4, R2.5_
- [ ] 3.4 Adaptadores `python_entrypoint`, `onnx` (import opcional) y `sagemaker_endpoint` (cliente
  inyectable, probado con uno falso).
  - _Requisitos: R2.2_
- [ ] 3.5 `tests/test_vortice_adapters.py`: rango [0, 1], determinismo, orden de filas, regla con
  dirección negativa (`-stp_lm`).
  - _Requisitos: R8.1_

## Fase 4 — Arnés y campeón

- [ ] 4.1 `core/store.py` (local y `s3://` vía fsspec).
  - _Requisitos: R6.1_
- [ ] 4.2 `core/harness.py` y CLI `evaluate.py --model/--all --lead --force`.
  - _Requisitos: R3.1–R3.7_
- [ ] 4.3 `tests/test_vortice_harness.py`: el umbral no cambia si se alteran las etiquetas de test;
  `dev` no aparece en métricas; bootstrap remuestrea días completos; corrida existente se salta.
  - _Requisitos: R8.2_
- [ ] 4.4 `core/champion.py` y CLI `promote.py`; `tests/test_vortice_champion.py` con tablas
  construidas (ninguno elegible → regla; empate a un error estándar → el más simple).
  - _Requisitos: R4.1–R4.4, R8.2_

## Fase 5 — App

- [ ] 5.1 `app/app.py`, `app/theme.py`, barra lateral (selector de modelo, `lead_h`, modo, hash).
  - _Requisitos: R5.7, R5.8, R5.10, R6.2_
- [ ] 5.2 Páginas Objetivo y Sumar un modelo.
  - _Requisitos: R5.2_
- [ ] 5.3 Página Arena.
  - _Requisitos: R5.4, R1.4_
- [ ] 5.4 Página Repetición 30-may-2019 (migrar el mapa de `New_Web`).
  - _Requisitos: R5.3_
- [ ] 5.5 Páginas Candidatos y Ficha del modelo.
  - _Requisitos: R5.5, R5.6_
- [ ] 5.6 `tests/test_vortice_app.py` con AppTest: cada página en modo sintético sin excepción y con
  el rótulo «sintético» visible.
  - _Requisitos: R8.3_

## Fase 6 — Despliegue y documentación

- [ ] 6.1 Dockerfile de Vórtice y ajuste de `deploy/steps/vortice_deploy.sh` (ruta de entrada,
  `VORTICE_STORE`, puerto 8502). No ejecutar el despliegue: dejarlo listo para
  `deploy/deploy_vortice.ps1`.
  - _Requisitos: R7.1, R7.2_
- [ ] 6.2 `scripts/vortice/README.md`: correr local, sumar un modelo en 4 pasos, publicar; y objetivos
  `vortice-demo`, `vortice-eval` en el `Makefile`.
  - _Requisitos: R7.3_
- [ ] 6.3 Revisar si `docs/mesociclones_chile.md` o los textos del visor deben citar a Vórtice.
  - _Requisitos: AGENTS.md_

## Criterio de término

- `make check` pasa.
- `uv run streamlit run scripts/vortice/app/app.py` abre las seis páginas en modo sintético.
- `register.py` + `evaluate.py --all` + `promote.py` dejan arena y campeón con al menos las cuatro
  líneas base y `forest_wind_v1`.
- Sumar un modelo nuevo solo requirió una ficha y un artefacto.
