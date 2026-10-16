---
inclusion: always
---

# Tecnología y convenciones

Las convenciones completas están en `AGENTS.md` (#[[file:AGENTS.md]]). Lo esencial:

- **Python 3.13 con uv.** Dependencias con `uv add` / `uv add --dev`, nunca `pip`. El repo no es un
  paquete instalable: los scripts agregan `scripts/` a `sys.path` e importan `common`.
- **Idioma.** Código en inglés (módulos, funciones, flags, columnas, claves YAML del contrato).
  Docstrings, comentarios, textos de interfaz, documentación y commits en español.
- **Estilo.** ruff (`E W F I B UP SIM C4 NPY ANN`; se ignoran `E501`, `C408`) y pyright `basic`.
  Todo parámetro y retorno anotado; todo módulo y función con docstring.
- **Pruebas.** `unittest` en `tests/`, sin datos descargados (usar el generador sintético de
  Vórtice). AppTest de Streamlit para la app.
- **Verificación.** `make check` (o los comandos del `Makefile` en Windows) tiene que pasar antes de
  cerrar cualquier tarea.
- **Datos.** `data/` y `*.parquet`, `*.nc`, `*.joblib` de salida nunca se versionan. Lo que Vórtice
  genera va a `data/vortice/`.

## Stack de Vórtice

| Capa | Herramienta |
|---|---|
| App | Streamlit + Plotly (ya usados en el repo) |
| Tablas | pandas + pyarrow (parquet) |
| Modelos | scikit-learn/joblib, ONNX Runtime (opcional), reglas en YAML, endpoint SageMaker (opcional) |
| Config | YAML (`pyyaml`), validado con `pydantic` |
| Almacén | ruta local o `s3://` según `VORTICE_STORE` (vía `fsspec`/`s3fs`) |
| Despliegue | Docker arm64 en la EC2 del proyecto vía SSM (`deploy/deploy_vortice.ps1`), puerto 8502 |

Antes de agregar una dependencia, revisar `pyproject.toml`: casi todo ya está.
