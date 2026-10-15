# Tareas — Selección de modelo para detección y anticipación de tornados

Prioridades:
- **P0**: hoy, jueves 15, antes de terminar el día.
- **P1**: mañana temprano, antes de congelar el código a media jornada.
- **P2**: solo si sobra tiempo.

Antes de cada tarea, revisar el código existente en `scripts/model/` y reutilizar lo que ya funcione.

## Fase 0 — Reconocimiento (P0)

- [ ] 0.1 Inspeccionar `scripts/model/` y una salida real de `run_days.sh`; listar en
  `docs/inventario_variables.md` las variables ERA5 y los índices que ya existen, con nombres de columna.
  - _Requisitos: R1.3, R1.5_
- [ ] 0.2 Revisar `data/tornados_chile.xlsx`: columnas, si trae hora y zona horaria, número de eventos por
  año 2018–2025. Anotar en el mismo archivo.
  - _Requisitos: R2.3_
- [ ] 0.3 Crear `scripts/model/config/model_selection.yaml` con variables, hiperparámetros, umbrales de
  persistencia, tolerancia y la **regla de decisión** (sección 8 de `design.md`). Hacer commit antes de
  correr cualquier validación.
  - _Requisitos: R5.1, R9.1_

## Fase 1 — Variables y etiquetas (P0)

- [ ] 1.1 Implementar `indices.py` con los índices de la sección 3 de `design.md`, reutilizando los que ya
  calcule el pipeline. Columnas `neg_stp` y `neg_srh01` con la convención del hemisferio sur.
  - _Requisitos: R1.3, R1.5_
- [ ] 1.2 Escribir `tests/test_signo_hemisferio_sur.py` y hacerlo pasar.
  - _Requisitos: R8.3_
- [ ] 1.3 Implementar `labels.py`: asignación de eventos a celda-día UTC, `eventos.parquet`, conteo de
  positivos por año.
  - _Requisitos: R2.1, R2.2, R2.3_
- [ ] 1.4 Implementar `features.py --corte {dia,12utc}`: agregados `_max`, `_tend6`, `_pers`,
  `_max3x3`, columnas de contexto y `completo`. Escribir `features_dia.parquet` y `features_12utc.parquet`.
  - _Requisitos: R1.1, R1.2, R1.4_
- [ ] 1.5 Escribir `tests/test_corte_sin_futuro.py` (alterar horas > τ no cambia variables) y hacerlo pasar.
  - _Requisitos: R8.1_

## Fase 2 — Métricas y modelos (P0)

- [ ] 2.1 Extender `kpis.py` con acierto tolerante (vecindad y ventana de días configurables), POD, FAR,
  días de alerta por tornado detectado y PR-AUC. Mantener las funciones existentes.
  - _Requisitos: R4.3_
- [ ] 2.2 Escribir `tests/test_kpis_tolerancia.py`.
  - _Requisitos: R4.3_
- [ ] 2.3 Implementar en `models.py` la interfaz común y M0, M1 y M2, con `explain`.
  - _Requisitos: R3.1, R3.2, R3.3_
- [ ] 2.4 Implementar M3 (splines) y M4 (`HistGradientBoostingClassifier` con restricciones monótonas).
  - _Requisitos: R3.1, R3.2_

## Fase 3 — Validación y decisión (P0)

- [ ] 3.1 Implementar `cv.py`: validación dejando un año fuera 2018–2024, umbral por validación interna
  (POD ≥ 70 %), métricas agrupadas, bootstrap por fecha (1000 réplicas) contra M1. Salidas
  `cv_report.csv` y `cv_by_fold.csv`.
  - _Requisitos: R4.1, R4.2, R4.3, R4.4, R4.5_
- [ ] 3.2 Escribir `tests/test_pliegues_sin_fecha_compartida.py`.
  - _Requisitos: R8.2_
- [ ] 3.3 Implementar `decide.py` y `tests/test_regla_decision.py`; generar `decision_dia.md` y
  `decision_12utc.md`.
  - _Requisitos: R5.2, R5.3, R5.4, R5.5_
- [ ] 3.4 Correr la validación para los cortes `dia` y `12utc`. Antes de mostrar cifras, pedir revisión al
  subagente `auditor-fugas` con `cv_report.csv` y `decision_*.md`.
  - _Requisitos: R4, R5_

## Fase 4 — Prueba ciega 2025 (P0, cierre del día)

- [ ] 4.1 Agregar `--modelo` y `--corte` a `train.py` y `score.py` sin romper los comandos actuales.
  - _Requisitos: R9.2_
- [ ] 4.2 Entrenar el modelo elegido hasta 2024 y evaluarlo una sola vez en abril–septiembre 2025 para cada
  corte; escribir `blind_2025_<corte>.csv`. No reajustar nada después.
  - _Requisitos: R6.1, R6.2_

## Fase 5 — Puntaje 2026 (P1)

- [ ] 5.1 Reentrenar el elegido hasta 2025 y puntuar 2026 para cada corte; escribir
  `candidatos_2026_<corte>.csv` con `top1`–`top3` y `ultimo_dia_era5`.
  - _Requisitos: R7.1, R7.2, R7.3_
- [ ] 5.2 Generar `data/outputs/resumen_pitch.md`: tabla de M1 contra el elegido por corte (POD, FAR,
  días por detección, con conteos y tasa base), resultado de la prueba ciega y cobertura de ERA5 2026.
  - _Requisitos: R4.3, R6.1, R7.3_

## Fase 6 — Opcionales (P2)

- [ ] 6.1 M5: si existe `glm_celda_dia.parquet`, calcular la fracción de eventos con destellos y, si es
  ≥ 0,8, evaluar el elegido con filtro GLM en el corte `dia`.
  - _Requisitos: R10.1, R10.2_
- [ ] 6.2 Corte `00utc`: generar las listas de días d−1 para `run_days.sh`, procesarlas y repetir las
  fases 1.4, 3 y 4 para ese corte.
  - _Requisitos: R1.6_
- [ ] 6.3 Si el catálogo trae hora, agregar el corte `evento_menos_L` con L ∈ {6, 12} h y la curva de
  habilidad versus anticipación.
  - _Requisitos: R1.2, R4.3_

## Criterio de término

- `pytest` pasa.
- Existen `cv_report.csv`, `decision_dia.md`, `decision_12utc.md`, `blind_2025_*.csv`,
  `candidatos_2026_*.csv` y `resumen_pitch.md`.
- `auditor-fugas` revisó las cifras antes del pitch.
