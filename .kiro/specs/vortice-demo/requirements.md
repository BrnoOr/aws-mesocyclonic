# Requisitos — Vórtice, demo con modelos intercambiables

## Introducción

Vórtice es la demo web del proyecto. Muestra en un mapa del centro-sur de Chile qué celdas ERA5
(0,25°) y horas tienen un entorno parecido al de los tornados y trombas del catálogo, y compara
modelos distintos bajo **un objetivo fijo**. El objetivo vive en `scripts/vortice/objective.yaml`;
los modelos entran y salen con una ficha YAML, sin tocar la app.

**Objetivo inicial (congelado en la versión 1.0.0):** dada una celda-hora con las variables de
entorno de ERA5 (y GOES si existe) disponibles `lead_h` horas antes, entregar un puntaje en [0, 1]
que ordene las celdas-hora según la probabilidad de que haya un tornado o tromba **reportado** en
un radio de 0,2° y la misma hora. Se mide por evento con acierto tolerante, por día de alerta y con
AUC-PR, en la prueba 2025, con umbral fijado en validación 2024.

## Glosario

- **Celda-hora:** fila del dataset (`date`, `hour_utc`, `lat`, `lon`, `lead_h`).
- **Objetivo:** contrato de `objective.yaml` (unidad, etiqueta, variables permitidas, particiones,
  métricas, compuertas y regla de campeón). Tiene `version` y un hash SHA-256 de su contenido.
- **Modelo:** artefacto + ficha (`model_cards/<id>.yaml`) que cumple `ScoringModel`.
- **Adaptador:** clase que convierte un tipo de artefacto (joblib, regla, ONNX, endpoint) en un
  `ScoringModel`.
- **Corrida:** evaluación de un modelo bajo un hash de objetivo.
- **Arena:** tabla comparativa de las corridas del hash vigente.
- **Campeón:** modelo elegido por la regla del objetivo.
- **Candidato:** celda-día sin reporte con puntaje del campeón sobre el umbral.
- **Modo sintético:** datos generados con el esquema real y semilla fija, rotulados como tales.

## Requisitos

### R1. Objetivo congelado

**Historia:** Como equipo, quiero que el objetivo quede escrito antes de comparar modelos, para que
la elección no dependa de mirar resultados.

1. El sistema DEBERÁ leer el objetivo de `scripts/vortice/objective.yaml` y validarlo con un esquema
   `pydantic`; SI el archivo no valida, ENTONCES DEBERÁ fallar con un mensaje que nombre el campo.
2. El sistema DEBERÁ calcular el hash SHA-256 del objetivo normalizado y registrarlo en cada corrida.
3. El objetivo DEBERÁ declarar: unidad, etiqueta, `features.allowed`, `features.forbidden`,
   particiones (train 2018–2023, val 2024, test 2025, dev 2019-05-30/31, inference 2026),
   tolerancia del acierto, métricas, compuertas, regla de campeón y `pod_target = 0,70`.
4. CUANDO cambie el hash del objetivo, la arena DEBERÁ mostrar solo corridas del hash nuevo y avisar
   que las anteriores quedaron fuera.
5. El objetivo inicial DEBERÁ reutilizar las constantes de `scripts/dataset/features.py` y la regla
   de `scripts/model/config/model_selection.yaml`, sin redefinirlas con otros valores.

### R2. Contrato e intercambio de modelos

**Historia:** Como integrante de un equipo, quiero sumar mi modelo escribiendo una ficha, para
compararlo sin tocar la app.

1. El sistema DEBERÁ definir el protocolo `ScoringModel` con `score(X) -> ndarray` en [0, 1] y
   `explain(X) -> DataFrame | None`.
2. El sistema DEBERÁ ofrecer los adaptadores `sklearn_joblib`, `rule` y `python_entrypoint`; DONDE
   esté instalado `onnxruntime`, `onnx`; DONDE haya credenciales AWS, `sagemaker_endpoint`.
3. CUANDO se ejecute `register.py --card <ficha>`, el sistema DEBERÁ validar la ficha, cargar el
   artefacto, puntuar 100 filas sintéticas y comprobar rango, ausencia de `NaN` y determinismo antes
   de agregarla a `registry.yaml`.
4. SI la ficha declara una variable fuera de `features.allowed` o dentro de `features.forbidden`,
   ENTONCES el sistema DEBERÁ rechazarla y nombrar la variable.
5. SI `trained_on` incluye `test` o `dev`, ENTONCES el sistema DEBERÁ rechazar la ficha.
6. El arnés DEBERÁ entregar al modelo solo las columnas de su ficha.
7. El sistema DEBERÁ registrar siempre las líneas base `climatology`, `rule_stp`, `rule_sherbs3` y
   `rule_vgp`, definidas como fichas `rule` (sin código propio).
8. El sistema DEBERÁ incluir una ficha para `New_Web/modelo.joblib` (bundle con claves `model`,
   `features`, `metadata`) como ejemplo de modelo entrenado.

### R3. Evaluación con un único protocolo

**Historia:** Como jurado, quiero que todos los modelos se midan igual, para que la comparación sea
justa.

1. CUANDO se ejecute `evaluate.py --model <id>` (o `--all`), el sistema DEBERÁ puntuar `val` y
   `test` de cada `lead_h` que la ficha soporte.
2. El sistema DEBERÁ elegir el umbral en `val` como el más alto que logra POD por evento ≥
   `pod_target`, y aplicarlo sin cambios a `test`.
3. El sistema DEBERÁ calcular en `test`: POD por evento (acierto tolerante), FAR por día de alerta,
   días de alerta por evento detectado, AUC-PR por celda-hora, Brier, tasa base, `n` eventos y `n`
   días.
4. El sistema DEBERÁ estimar intervalos del 90 % con bootstrap remuestreando **días** (`group`).
5. El sistema DEBERÁ excluir las fechas `dev` de toda métrica.
6. El sistema DEBERÁ escribir `data/vortice/runs/<objective_hash>/<model_id>/` con `metrics.json`,
   `scores_test.parquet`, `threshold.json` y una copia de la ficha, y actualizar
   `data/vortice/leaderboard.parquet`.
7. SI una corrida con el mismo hash, modelo y versión ya existe, ENTONCES el sistema DEBERÁ saltarla
   salvo `--force`.

### R4. Regla de campeón

1. CUANDO se ejecute `promote.py`, el sistema DEBERÁ declarar elegible a un modelo si supera a
   `climatology` en AUC-PR y su FAR en test es ≤ al de la mejor regla física con POD ≥ `pod_target`.
2. Entre los elegibles, el sistema DEBERÁ elegir el de menor `complexity` cuyo FAR esté a menos de un
   error estándar bootstrap del mejor.
3. SI ningún modelo es elegible, ENTONCES el campeón DEBERÁ ser la mejor regla física y la app DEBERÁ
   decirlo.
4. El sistema DEBERÁ escribir `data/vortice/champion.json` con el modelo, el hash del objetivo, las
   cifras que justifican la decisión y la fecha.

### R5. App de demostración

**Historia:** Como visitante, quiero entender en cinco minutos qué hace Vórtice, cómo se compara cada
modelo y dónde mirar.

1. La app DEBERÁ tener estas páginas: **Objetivo**, **Repetición 30-may-2019**, **Arena**,
   **Candidatos**, **Ficha del modelo** y **Sumar un modelo**.
2. **Objetivo** DEBERÁ mostrar el contenido de `objective.yaml` en lenguaje claro, su versión y su
   hash corto, y la lista de lo que no se puede concluir.
3. **Repetición** DEBERÁ mostrar el mapa de puntaje por hora (deslizador 00–23 UTC) del modelo
   elegido junto a la mejor regla física, con los eventos del catálogo encima y el rótulo «caso de
   desarrollo, no prueba ciega».
4. **Arena** DEBERÁ mostrar una fila por modelo con POD, FAR, días por detección, AUC-PR, Brier,
   intervalos, `n`, compuertas aprobadas y la insignia del campeón; las líneas base siempre visibles.
5. **Candidatos** DEBERÁ listar las celdas-día de 2026 (o de test si no hay 2026) sin reporte con
   puntaje del campeón sobre el umbral, ordenadas, con aviso de cordillera cuando
   `sfc_height > 1500 m`.
6. **Ficha del modelo** DEBERÁ mostrar la ficha, sus variables y, si `explain` existe, las
   contribuciones medias en los eventos de test.
7. Un selector global DEBERÁ permitir cambiar el modelo mostrado entre los registrados sin
   reiniciar la app.
8. La app DEBERÁ funcionar sin datos descargados en **modo sintético**, con un rótulo visible en
   todas las páginas.
9. La app NO DEBERÁ entrenar, descargar de ERA5/GOES ni modificar el registro.
10. Las columnas DEBERÁN apilarse en pantallas angostas y los colores DEBERÁN venir de un único
    módulo de tema.

### R6. Almacén local o en S3

1. El sistema DEBERÁ leer y escribir artefactos, corridas, arena y campeón en la raíz que indique
   `VORTICE_STORE` (por defecto `data/vortice/`), sea una ruta local o un prefijo `s3://`.
2. SI `VORTICE_STORE` es `s3://` y no hay credenciales, ENTONCES la app DEBERÁ caer a modo sintético
   y avisarlo, sin romperse.

### R7. Despliegue

1. El sistema DEBERÁ incluir un `Dockerfile` para la app (arm64 y amd64) que no copie `data/`.
2. El sistema DEBERÁ integrarse con `deploy/deploy_vortice.ps1` y `deploy/steps/vortice_deploy.sh`
   (EC2 por SSM, puerto 8502), cambiando solo la ruta de entrada de la app y `VORTICE_STORE`.
3. El sistema DEBERÁ documentar en `scripts/vortice/README.md` cómo correr local, cómo sumar un
   modelo y cómo publicar.

### R8. Calidad

1. Cada módulo con lógica propia DEBERÁ tener pruebas `unittest` sin datos descargados.
2. DEBERÁ haber pruebas de: rechazo de variables prohibidas, rechazo de `trained_on: [test]`,
   umbral elegido solo con `val`, bootstrap por día, exclusión de `dev`, regla de campeón con casos
   construidos y hash estable del objetivo.
3. DEBERÁ haber una prueba AppTest que abra cada página en modo sintético sin excepciones.
4. `make check` DEBERÁ pasar.
