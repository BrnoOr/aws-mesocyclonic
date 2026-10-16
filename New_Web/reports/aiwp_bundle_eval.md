# Evaluación del modelo sobre el pronóstico AIWP (sin fuga, área igualada)

Modelo **forest** · features wind (AIWP-safe: sí). Eventos 2021–2023 puntuados *out of fold* (modelo que excluyó su año); 2024–2025 con el modelo de solo-train (nunca vistos). Criterio del lote: celda marcada a ≤ 50 km y ±6 h. Umbral del modelo igualado al área de cada regla, elegido por la distribución de scores (sin mirar eventos).

## POD por evento con área igualada a cada regla

| comparación (área) | umbral modelo | fracción modelo | POD modelo | POD regla |
|---|---|---|---|---|
| vs Regla A (con CAPE) · 1,07 % | 0.838 | 1.07% | 10/25 = 40% [23%–59%] | 5/25 = 20% [9%–39%] |
| vs Regla B (sin CAPE) · 10,74 % | 0.177 | 10.74% | 20/25 = 80% [61%–91%] | 8/25 = 32% [17%–52%] |

## Split: años de entrenamiento (OOF) vs 2024–2025 (nunca vistos)

| conjunto | n | POD modelo @área A | POD modelo @área B | POD regla A | POD regla B |
|---|---|---|---|---|---|
| 2021–2023 (OOF) | 18 | 7/18 = 39% [20%–61%] | 15/18 = 83% [61%–94%] | 3/18 = 17% [6%–39%] | 5/18 = 28% [12%–51%] |
| 2024–2025 (nunca vistos) | 7 | 3/7 = 43% [16%–75%] | 5/7 = 71% [36%–92%] | 2/7 = 29% [8%–64%] | 3/7 = 43% [16%–75%] |
| todos | 25 | 10/25 = 40% [23%–59%] | 20/25 = 80% [61%–91%] | 5/25 = 20% [9%–39%] | 8/25 = 32% [17%–52%] |

## Desglose (área igualada a regla B)

| subconjunto | POD modelo | POD regla B |
|---|---|---|
| tornado | 12/14 = 86% [60%–96%] | 6/14 = 43% [21%–67%] |
| tromba | 10/13 = 77% [50%–92%] | 3/13 = 23% [8%–50%] |
| EF0 | 14/17 = 82% [59%–94%] | 4/17 = 24% [10%–47%] |
| EF1+ | 6/8 = 75% [41%–93%] | 4/8 = 50% [22%–78%] |

## Captura por evento (área igualada a regla B)

| evento | año | tipo | EF | modelo | A | B |
|---|---|---|---|---|---|---|
| Llanquihue (OOF) | 2021 | tornado y tromba | EF0 | sí | no | sí |
| Lago Villarrica (OOF) | 2021 | tromba | EF0* | sí | no | no |
| Ancud (2021) (OOF) | 2021 | tornado y tromba | EF0 | sí | sí | sí |
| Mehuín (OOF) | 2021 | tornado y tromba | EF1 | sí | no | no |
| Toltén Viejo (OOF) | 2021 | tornado y tromba | EF1 | sí | no | no |
| Tucapel (OOF) | 2021 | tornado | EF1 | sí | no | no |
| Valle Volcanes (Pto Montt) (OOF) | 2022 | tornado | EF0 | sí | no | sí |
| Peralillo (OOF) | 2022 | tornado | EF0 | sí | no | no |
| Cobquecura (OOF) | 2022 | tromba | EF0* | no | no | no |
| Ancud (2023) (OOF) | 2023 | tornado | EF1 | no | sí | sí |
| Puerto Saavedra (OOF) | 2023 | tromba | EF0* | no | no | no |
| Lago Todos los Santos (OOF) | 2023 | tromba | EF0* | sí | sí | sí |
| Futrono (OOF) | 2023 | tornado | EF0 | sí | no | no |
| Lago Llanquihue (OOF) | 2023 | tromba | EF0* | sí | no | no |
| La Vara (Pto Montt) (OOF) | 2023 | tornado | EF1 | sí | no | no |
| Lago Llanquihue (R225) (OOF) | 2023 | tromba | EF0* | sí | no | no |
| San Pedro de la Paz (OOF) | 2023 | tromba | EF0* | sí | no | no |
| Maiquillahue (OOF) | 2023 | tromba | EF0* | sí | no | no |
| Calbuco (nuevo) | 2024 | tromba | EF0 | no | no | no |
| Penco (nuevo) | 2024 | sin clasificación | EF0 | sí | no | no |
| Folilco (nuevo) | 2024 | tornado | EF1 | no | no | sí |
| Malalhue (Lanco) (nuevo) | 2024 | sin clasificación | EF1 | sí | sí | sí |
| Dadinco (Chillán) (nuevo) | 2024 | tornado | EF0 | sí | no | no |
| Los Ángeles (nuevo) | 2025 | tornado | EF0 | sí | no | no |
| Puerto Varas (nuevo) | 2025 | tornado | EF1 | sí | sí | sí |

## Baseline nulo por permutación (50 km / ±6 h)

Cada evento se evalúa contra los flag-maps de **cada otro** run (misma estructura espacial y tasa de marcado, alineado por lead_h, pero sin el vínculo real). El exceso = observada − nula; valor-p de una cola. A 10,74 % de área el nulo es alto por diseño: lo que importa es el exceso.

**todos**

| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |
|---|---|---|---|---|
| modelo@A | 40% (10/25) | 22% [15%–33%] | +18% | 0.056 |
| modelo@B | 80% (20/25) | 63% [52%–73%] | +17% | 0.056 |
| regla A | 20% (5/25) | 16% [11%–24%] | +4% | 0.333 |
| regla B | 32% (8/25) | 30% [20%–41%] | +2% | 0.444 |

**2024-25**

| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |
|---|---|---|---|---|
| modelo@A | 43% (3/7) | 26% [14%–43%] | +17% | 0.333 |
| modelo@B | 71% (5/7) | 64% [40%–86%] | +8% | 0.556 |
| regla A | 29% (2/7) | 19% [0%–43%] | +9% | 0.444 |
| regla B | 43% (3/7) | 34% [0%–60%] | +9% | 0.556 |

## Estructura espacial (por paso, a cada umbral)

| fuente | parches/paso (media) | tamaño medio de parche (celdas) |
|---|---|---|
| modelo@A | 2.8 | 5.8 |
| modelo@B | 10.7 | 15.3 |
| regla A | 1.9 | 8.8 |
| regla B | 4.7 | 34.8 |

## Robustez — criterio estricto (25 km, paso más cercano)

**todos**

| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |
|---|---|---|---|---|
| modelo@A | 20% (5/25) | 9% [0%–18%] | +11% | 0.111 |
| modelo@B | 60% (15/25) | 42% [34%–53%] | +18% | 0.056 |
| regla A | 16% (4/25) | 8% [0%–21%] | +8% | 0.278 |
| regla B | 16% (4/25) | 18% [11%–28%] | -2% | 0.667 |

**2024-25**

| fuente | POD observada | POD nula [5–95 %] | exceso | valor-p |
|---|---|---|---|---|
| modelo@A | 14% (1/7) | 11% [0%–43%] | +3% | 0.500 |
| modelo@B | 29% (2/7) | 45% [29%–60%] | -16% | 1.000 |
| regla A | 29% (2/7) | 11% [0%–31%] | +18% | 0.222 |
| regla B | 29% (2/7) | 21% [0%–43%] | +8% | 0.500 |

## Anexo — barrido de umbral (elegido a posteriori, NO es un resultado)

Solo para ver la sensibilidad; el umbral se escoge mirando el resultado, así que no es honesto.

| umbral | fracción marcada | POD modelo (todos, OOF) |
|---|---|---|
| 0.5 | 4.94% | 13/25 = 52% [33%–70%] |
| 0.7 | 2.64% | 11/25 = 44% [27%–63%] |
| 0.9 | 0.20% | 3/25 = 12% [4%–30%] |

## Advertencias

- Sin fuga: 2021–2023 out-of-fold, 2024–2025 con el modelo de solo-train (no vio esos años).
- Umbral del modelo igualado al área de cada regla por la distribución de scores, no por los eventos.
- n = 25 eventos (OOF: 18, nunca vistos: 7); Wilson ancho.
- Pangu (13 niveles) subestima la MUCAPE HSLC: por eso las features/reglas con CAPE fallan.
- CSV por evento: `aiwp_bundle_eval.csv`.
