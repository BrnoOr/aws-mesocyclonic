# Informe de entrenamiento — south-central · lead 0 h

Modelo: **forest** · features: **wind** (AIWP-safe: sí) · umbral 0.900 (POD≥0.7).

## Reparto por partición

| partición | filas | positivas | eventos | brotes |
|---|---|---|---|---|
| dev | 36600 | 16 | 7 | 1 |
| test | 36600 | 4 | 2 | 2 |
| train | 640500 | 91 | 35 | 33 |
| val | 73200 | 4 | 2 | 4 |

## KPIs: modelo vs líneas base vs objetivo

| KPI | objetivo | base | modelo (LOYO) | modelo (val) | STP | SHERBS3 | regla A | regla B |
|---|---|---|---|---|---|---|---|---|
| POD por evento (≥0,70) | 0,70 | STP=0/7 (mayo 2019) | 0.89 [0.74–0.95] (31/35) | 0.50 [0.09–0.91] (1/2) | 0.50 [0.09–0.91] (1/2) | 0.50 [0.09–0.91] (1/2) | 0.50 [0.09–0.91] (1/2) | 0.50 [0.09–0.91] (1/2) |
| FAR por día (≤0,50) | 0,50 | ≈0,70 | 0.12 [0.03–0.34] (2/17) | 0.00 [0.00–0.79] (0/1) | 0.50 [0.09–0.91] (1/2) | 0.50 [0.15–0.85] (2/4) | 0.50 [0.15–0.85] (2/4) | 0.50 [0.15–0.85] (2/4) |
| Avisos por acierto (≤2) | 2 | ≈4 | 1.13 | 1.00 | 2.00 | 2.00 | 2.00 | 2.00 |

## Desglose de POD por evento (val)

| subconjunto | POD |
|---|---|
| EF0 | 0.50 [0.09–0.91] (1/2) |
| EF1+ | no computable |
| tornado | 1.00 [0.21–1.00] (1/1) |
| tromba | 0.00 [0.00–0.79] (0/1) |
| confirmado | 0.50 [0.09–0.91] (1/2) |
| débil | no computable |
| noche (00-09 UTC) | no computable |
| día (10-23 UTC) | 0.50 [0.09–0.91] (1/2) |

## Diagnósticos por celda (secundarios, sesgados por PU)

- AUC-PR (LOYO, celda): 0.0010
- Brier (LOYO, celda): 0.0380

## Advertencias

- **PU:** `label=0` es *sin reporte*, no negativo confirmado; el subregistro infla la FAR real.
- **n pequeño:** pocos eventos por partición; los intervalos de Wilson son anchos.
- **Curva de operación:** ver `operating_curve_south-central_lead0h.csv`.
- Línea base stp: POD evento 0.50; FAR temporada≈0.97 [0.88–0.99], avisos/acierto≈38.25; celda-horas marcadas 0.22% (evento)/1.25% (control).
- Línea base sherbs3: POD evento 0.50; FAR temporada≈0.99 [0.96–0.99], avisos/acierto≈75.50; celda-horas marcadas 10.78% (evento)/8.46% (control).
- Línea base hslc_a: POD evento 0.50; FAR temporada≈0.99 [0.96–0.99], avisos/acierto≈75.50; celda-horas marcadas 8.86% (evento)/9.45% (control).
- Línea base hslc_b: POD evento 0.50; FAR temporada≈0.99 [0.96–0.99], avisos/acierto≈75.50; celda-horas marcadas 10.16% (evento)/11.59% (control).
- FAR reescalada a temporada (loyo): q=0.667 [0.208–0.939] sobre 3 control(es) → FAR≈0.60 [0.32–0.68], avisos/acierto≈2.51. q descansa en 3 día(s) de control: muy incierto, indicativo.
- FAR reescalada a temporada (val): q=0.000 [0.000–0.658] sobre 2 control(es) → FAR≈0.00 [0.00–0.98], avisos/acierto≈1.00. q descansa en 2 día(s) de control: muy incierto, indicativo.
- Área marcada (LOYO): celda-horas marcadas 0.18% en días de evento, 0.04% en días de control; ≈64 celdas marcadas por día de aviso.
- Cobertura: 13 evento(s) del catálogo con hora fuera de 12–23 UTC quedan fuera de la POD. Lista: CL0011 1927-06-07 02z, CL0012 1934-05-27 09z, CL0013 1934-05-29 04z, CL0022 2005-02-22 10z, CL0024 2007-06-21 00z, CL0025 2008-08-26 04z, CL0036 2015-08-08 06z, CL0047 2017-07-17 10z, CL0051 2018-03-23 06z, CL0063 2020-04-25 07z, CL0077 2021-06-09 11z, CL0078 2021-08-19 07z, CL0095 2024-06-20 03z.
- Honestidad del umbral: el umbral se elige y se reporta sobre las MISMAS predicciones out-of-fold de LOYO, así que la POD de LOYO es optimista. La selección anidada da la versión sin ese sesgo:
- POD por evento con selección anidada: 0.37 [0.23–0.54] (13/35).
