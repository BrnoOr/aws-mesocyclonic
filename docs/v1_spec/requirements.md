# Requisitos — Selección de modelo para detección y anticipación de tornados

## Introducción

Esta especificación cubre la construcción de variables, el entrenamiento de varios modelos candidatos, su
comparación con una regla de decisión fijada de antemano, la prueba ciega de 2025 y el puntaje de 2026.
Aplica a dos usos del mismo sistema:

- **Diagnóstico:** con el día completo, ¿hubo un tornado en esta celda y día?
- **Anticipación (O7):** con datos solo hasta un corte τ, ¿cuánta habilidad queda?

La unidad de análisis es la celda de 1° × día UTC. Hay unos 40 positivos en 2018–2025.

## Glosario

- **Celda-día:** par (fecha UTC, celda de 1° identificada por su latitud y longitud de centro).
- **Corte (τ):** última hora UTC de ERA5 que puede usar una variable. Cortes: `dia` (23 UTC del día d),
  `12utc` (12 UTC del día d) y `00utc` (00 UTC del día d, que exige horas del día d−1).
- **Positivo:** celda-día con un tornado o tromba del catálogo.
- **Control:** celda-día de los días de comparación; sin etiqueta.
- **Acierto tolerante:** un evento se considera detectado si hay una alerta en su celda o en las 8 vecinas,
  el mismo día o el día anterior.
- **M0–M5:** modelos candidatos definidos en `design.md`.

## Requisitos

### R1. Tabla de variables por corte

**Historia:** Como analista, quiero una tabla celda-día por cada corte temporal, para entrenar y comparar
modelos con la misma información disponible.

1. CUANDO se ejecute `features.py --corte <c>`, el sistema DEBERÁ escribir
   `data/tables/features_<c>.parquet` con una fila por celda-día y las columnas clave `fecha`, `lat`, `lon`.
2. El sistema DEBERÁ calcular cada variable usando solo horas de ERA5 ≤ τ del corte pedido.
3. El sistema DEBERÁ calcular los índices horarios −STP, SHERBS3, SHERBE (o su aproximación documentada),
   VGP, −SRH 0–1 km y cizalle 0–6 km, con la convención del hemisferio sur.
4. Para cada índice, el sistema DEBERÁ calcular por celda-día el máximo horario, la tendencia (máximo
   aumento en 6 h, calculado hacia atrás), la persistencia (horas sobre un umbral de configuración) y el
   máximo del índice en la vecindad 3×3.
5. SI falta una variable de ERA5 necesaria para un índice, ENTONCES el sistema DEBERÁ dejar el índice en
   NaN, registrar una advertencia con la variable faltante y continuar, sin inventar valores.
6. SI el corte es `00utc` y faltan las horas del día d−1 para una celda-día, ENTONCES el sistema DEBERÁ
   marcar esa fila como incompleta (columna `completo = False`) y excluirla del entrenamiento.

### R2. Etiquetas

**Historia:** Como analista, quiero etiquetas consistentes con el catálogo para que todas las métricas
cuenten lo mismo.

1. El sistema DEBERÁ asignar `y = 1` a las celdas-día con al menos un evento del catálogo y `y = 0` a las
   celdas-día de control.
2. El sistema DEBERÁ conservar, por evento, su identificador, celda y fecha, para calcular el acierto
   tolerante por evento y no solo por celda-día.
3. El sistema DEBERÁ reportar el conteo de positivos por año antes de entrenar.

### R3. Modelos candidatos

**Historia:** Como analista, quiero varios modelos con una interfaz común para compararlos con el mismo
protocolo.

1. El sistema DEBERÁ implementar M0 (climatología), M1 (regla física), M2 (logística penalizada),
   M3 (logística con splines) y M4 (gradient boosting poco profundo con restricciones monótonas).
2. Cada modelo DEBERÁ exponer `fit(X, y)`, `score(X)` (puntaje para ordenar) y `explain(X)`
   (contribución por variable para cada fila).
3. El sistema DEBERÁ leer de `config/model_selection.yaml` las variables y los hiperparámetros de cada
   modelo.
4. DONDE esté habilitado M5, el sistema DEBERÁ aplicar el filtro de rayos GLM sobre el modelo elegido,
   solo en el corte `dia`.

### R4. Validación cruzada por año

**Historia:** Como analista, quiero estimar el desempeño fuera de muestra sin fugas, para elegir el modelo
con evidencia y no por azar.

1. El sistema DEBERÁ validar dejando un año fuera para 2018–2024, por cada modelo y cada corte.
2. En cada pliegue, el sistema DEBERÁ elegir el umbral de alerta con predicciones fuera de pliegue de los
   años de entrenamiento (validación interna), como el umbral más alto que logra POD ≥ 70 %.
3. El sistema DEBERÁ juntar las predicciones de prueba de todos los pliegues y calcular POD, FAR, días de
   alerta por tornado detectado y el área bajo la curva precisión-recall, con acierto tolerante.
4. El sistema DEBERÁ estimar intervalos con bootstrap por día completo (remuestreando fechas, no celdas)
   para la diferencia de cada modelo contra M1.
5. El sistema DEBERÁ escribir `data/outputs/cv_report.csv` (un renglón por modelo y corte) y
   `data/outputs/cv_by_fold.csv`.

### R5. Regla de decisión fijada de antemano

**Historia:** Como equipo, queremos que la elección del modelo no dependa de mirar los resultados.

1. La regla DEBERÁ estar escrita en `config/model_selection.yaml` antes de ejecutar la validación cruzada.
2. El sistema DEBERÁ declarar elegible un modelo si supera a M0 en área bajo la curva precisión-recall y si,
   con POD ≥ 70 %, su FAR es menor o igual que el de M1.
3. Entre los elegibles, el sistema DEBERÁ elegir el más simple cuyo FAR esté a menos de un error estándar
   (bootstrap) del mejor, con el orden de simplicidad M2 < M3 < M4.
4. SI ningún modelo es elegible, ENTONCES el sistema DEBERÁ elegir M1 y dejarlo dicho.
5. El sistema DEBERÁ escribir la decisión y sus cifras en `data/outputs/decision_<corte>.md`.

### R6. Prueba ciega 2025

1. El sistema DEBERÁ entrenar el modelo elegido con 2018–2024, aplicarlo una sola vez a 2025 con el umbral
   fijado en la validación, y escribir `data/outputs/blind_2025_<corte>.csv` con sus métricas.
2. El sistema NO DEBERÁ reajustar variables, hiperparámetros ni umbral después de ver 2025.

### R7. Puntaje 2026 y explicación

1. El sistema DEBERÁ reentrenar el modelo elegido con 2018–2025 y puntuar todas las celdas-día de 2026
   disponibles en ERA5.
2. El sistema DEBERÁ escribir `data/outputs/candidatos_2026_<corte>.csv` ordenado por puntaje, con el
   umbral, la indicación de alerta, los índices y las tres variables con mayor contribución por fila.
3. El sistema DEBERÁ registrar el último día de 2026 con ERA5 disponible.

### R8. Antifuga y pruebas

1. El sistema DEBERÁ incluir una prueba que altere los datos horarios posteriores a τ y verifique que las
   variables del corte no cambian.
2. El sistema DEBERÁ incluir una prueba que verifique que ningún pliegue tiene la misma fecha en
   entrenamiento y prueba.
3. El sistema DEBERÁ incluir una prueba del signo: en un perfil sintético con giro antihorario del viento
   con la altura (hemisferio sur, ciclónico), `neg_srh01 > 0`.

### R9. Reproducibilidad y compatibilidad

1. El sistema DEBERÁ fijar semillas y registrar en cada salida la versión del archivo de configuración.
2. Los comandos existentes (`train.py --until`, `score.py --start --end --evaluate`) DEBERÁN seguir
   funcionando; las opciones `--modelo` y `--corte` se agregan con valores por defecto (`elegido`, `dia`).

### R10. M5 con rayos GLM (opcional)

1. DONDE exista `data/tables/glm_celda_dia.parquet` (columnas `fecha`, `lat`, `lon`, `n_destellos`), el
   sistema DEBERÁ calcular la fracción de eventos con al menos un destello en su celda o vecinas.
2. SI esa fracción es ≥ 0,8, ENTONCES el sistema DEBERÁ evaluar M5 como el modelo elegido con puntaje
   nulo en celdas-día sin destellos, y compararlo con el elegido sin filtro.
