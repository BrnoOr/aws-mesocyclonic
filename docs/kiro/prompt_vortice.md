# Vórtice en Kiro: prompts

Este archivo trae los prompts para construir y mantener **Vórtice** con Kiro. La configuración que
Kiro lee sola ya está en el repo:

| Ruta | Qué es | Cuándo la carga Kiro |
|---|---|---|
| `.kiro/steering/product.md` | Qué es Vórtice y sus reglas de honestidad | Siempre |
| `.kiro/steering/tech.md` | Stack y convenciones (remite a `AGENTS.md`) | Siempre |
| `.kiro/steering/structure.md` | Qué se reutiliza y dónde va lo nuevo | Siempre |
| `.kiro/steering/dominio-meteo.md` | Trampas del hemisferio sur, fuga, métricas | Al tocar `scripts/vortice`, `model`, `dataset` |
| `.kiro/steering/contrato-modelos.md` | Interfaz `ScoringModel` y ficha YAML | Al tocar el núcleo o las fichas |
| `.kiro/specs/vortice-demo/` | `requirements.md`, `design.md`, `tasks.md` | Al abrir el spec |
| `.kiro/hooks/*.kiro.hook` | Ruff al guardar, validar fichas, objetivo congelado, `make check` manual | Por evento |
| `.kiro/settings/mcp.json` | Documentación de AWS (opcional, requiere `uvx`) | Al iniciar |

## Cómo usarlo

1. Abrir la carpeta del repo en Kiro. Comprobar en el panel de Kiro que aparecen los steering, los
   hooks y el spec `vortice-demo`.
2. Correr `uv sync` en la terminal de Kiro.
3. Pegar el **prompt 1** en el chat (modo *Spec*). Kiro revisa el spec, propone ajustes y ejecuta
   las tareas una por una.
4. Para sumar un modelo después, usar el **prompt 2**. Para cambiar el objetivo, el **prompt 3**.

---

## Prompt 1: construir Vórtice

```text
Vas a construir Vórtice, la demo del proyecto de mesociclones de Chile, siguiendo el spec
.kiro/specs/vortice-demo/ (requirements.md, design.md, tasks.md) y los steering de .kiro/steering/.

Contexto en una línea: Vórtice muestra en un mapa del centro-sur de Chile qué celdas ERA5 y horas
tienen un entorno parecido al de los tornados y trombas documentados, y compara modelos
intercambiables bajo UN objetivo fijo. El objetivo es un dato (scripts/vortice/objective.yaml); los
modelos entran con una ficha YAML y un artefacto, sin tocar la app.

Lo que importa más que el modelo:
1. El objetivo congelado: qué se predice, particiones (train 2018–2023, val 2024, test 2025, dev
   2019-05-30/31 fuera de las métricas), umbral elegido en val y aplicado una vez en test, métricas
   por evento con acierto tolerante, bootstrap por día, regla de campeón. Se escribe y se hace commit
   ANTES de evaluar cualquier modelo.
2. El contrato ScoringModel (score en [0,1], explain opcional) y los adaptadores (rule,
   sklearn_joblib, python_entrypoint, onnx, sagemaker_endpoint). El arnés es el único que ve
   etiquetas: a cada modelo le pasa solo las columnas de su ficha.
3. Las líneas base (climatología y reglas físicas australes) siempre en la arena.
4. Una app Streamlit de solo lectura con seis páginas (Objetivo, Repetición 30-may-2019, Arena,
   Candidatos, Ficha del modelo, Sumar un modelo) que funciona sin datos descargados en modo
   sintético, con rótulo visible.

Cómo trabajar:
- Empieza por la Fase 0 de tasks.md: lee scripts/dataset/, scripts/model/ (kpis.py, train.py,
  config/model_selection.yaml) y New_Web/scripts/webapp/model_app.py. Reutiliza lo que ya calcule
  particiones, acierto tolerante, curva de operación o mapas; no lo dupliques. Si algo del diseño
  choca con lo que existe, dime qué y propón el cambio al spec antes de codificar.
- Ejecuta las tareas en orden, una por una. Al cerrar cada tarea corre la verificación del
  Makefile (objetivo check) y no avances con errores.
- Convenciones de AGENTS.md: código en inglés; docstrings, comentarios, textos de la app y commits
  en español; uv add para dependencias (nunca pip); unittest sin datos descargados; nada de data/
  al git.
- Hemisferio sur: SRH y STP negativos en los positivos. No inviertas signos en silencio.
- No ejecutes despliegues ni comandos contra AWS: deja listos el Dockerfile y
  deploy/steps/vortice_deploy.sh para que el equipo corra deploy/deploy_vortice.ps1.
- No cambies objective.yaml para que un modelo salga mejor. Si crees que el objetivo está mal,
  detente y explícalo.

Criterio de término: el de tasks.md. Al final, entrégame un resumen con qué se reutilizó, qué
quedó pendiente y la arena resultante en modo sintético (y real, si existe el dataset).
```

---

## Prompt 2: sumar un modelo nuevo

Reemplazar lo que está entre `<>`.

```text
Quiero sumar un modelo a Vórtice sin cambiar el objetivo ni la app.

- Artefacto: <ruta local o s3:// del .joblib / .onnx, nombre del endpoint SageMaker, o "modulo:Clase">
- Tipo de adaptador: <sklearn_joblib | onnx | sagemaker_endpoint | python_entrypoint | rule>
- Variables que usa: <lista, deben estar en objective.features.allowed>
- Anticipaciones (lead_h): <0, 1, 3, 6>
- Particiones con que se entrenó: <train | train, val>
- Tratamiento de NaN en GOES: <impute_median | model_native | drop_rows>
- Complejidad (0 regla … 3 boosting, más para redes): <n>
- Descripción breve en español: <qué es y sus límites>

Pasos:
1. Crea scripts/vortice/model_cards/<id>.yaml siguiendo .kiro/steering/contrato-modelos.md.
2. Si el adaptador necesario no existe, impleméntalo en scripts/vortice/core/adapters/ con su
   prueba y regístralo en registry.py. No toques el arnés ni la app.
3. Corre register.py --card <ficha> --dry-run, luego sin --dry-run.
4. Corre evaluate.py --model <id> y después promote.py.
5. Muéstrame la fila del modelo en la arena junto a las líneas base, con n eventos, n días e
   intervalos, y dime si cambió el campeón y por qué según la regla del objetivo.
No ajustes el umbral ni las métricas a mano.
```

---

## Prompt 3: cambiar el objetivo (decisión del equipo)

```text
El equipo decidió cambiar el objetivo de Vórtice: <describe el cambio, p. ej. "evaluar a 1° × día
en vez de 0,25° × hora" o "agregar lead 12 h">.

1. Explícame qué requisitos de .kiro/specs/vortice-demo/requirements.md y qué partes de design.md
   afecta, y si las fichas actuales siguen siendo válidas.
2. Propón el nuevo objective.yaml con la versión subida (mayor si cambia la pregunta o la unidad,
   menor si cambia una métrica o compuerta) y espera mi confirmación.
3. Tras confirmar: actualiza el spec, el objetivo y las pruebas; corre evaluate.py --all y
   promote.py; muéstrame la arena nueva y qué modelos quedaron fuera por no cumplir el contrato.
Las corridas del objetivo anterior se conservan bajo su hash; no las borres.
```

---

## Guion de la demo (5 minutos)

1. **Objetivo** (40 s): la pregunta, qué cuenta como acierto y lo que no se puede concluir.
2. **Repetición 30-may-2019** (90 s): mover el deslizador de 12 a 21 UTC y comparar dónde y cuándo
   se enciende el campeón frente a la regla STP sobre el Biobío (decir lo que muestre el mapa, sin
   adelantarlo). Rótulo: caso de desarrollo.
3. **Arena** (90 s): modelos contra líneas base en 2025, con intervalos. Mostrar que el campeón sale
   de una regla escrita antes de mirar.
4. **Sumar un modelo** (40 s): una ficha de 12 líneas basta; mostrar el prompt 2.
5. **Candidatos** (20 s): celdas sin reporte para revisar con GOES, con aviso de cordillera.
