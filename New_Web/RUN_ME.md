# Demo web del modelo de mesociclones — paquete autocontenido

Todo lo necesario para **correr la web en local** y para que alguien la **publique** (enlace para
compartir). Incluye el código de la app, los módulos que importa, los artefactos ya generados
(modelo + reportes + un par de recortes ERA5 de ejemplo) y la configuración del entorno.

## Estructura

```
site/                            sitio de producto: página con la consola (site/DEPLOY.md)
scripts/api/                     API de inferencia (FastAPI) que usa la consola; motor local o SageMaker
sagemaker/                       checkpoint empaquetado para un endpoint de SageMaker (paso futuro)
tests/                           pruebas de la API y del contrato con SageMaker
landing/                         página del proyecto anterior (sin consola; app aparte en /app/)
scripts/webapp/model_app.py      la app Streamlit (5 páginas: resumen, mapa de ejemplo, curva, KPIs, AIWP)
scripts/webapp/README.md         guía de despliegue (Streamlit Cloud / EC2+SSM / Docker)
scripts/model/                   módulos que la app importa (model_features, metrics, kpi, …)
scripts/dataset/                 features.py (importado por model_features vía ruta)
scripts/common.py                utilidades compartidas (regiones, rutas)
modelo.joblib                    el modelo entrenado (forest + wind, lead 0, south-central)
reports/                         salidas que la app muestra (curva de operación, KPIs, eval AIWP)
data/catalog_clean.csv           catálogo limpio (puntos de evento en el mapa)
data/control_days.csv            lista de días de control
data/crops/south-central/era5_indices/era5_idx_2019053 0.nc, 20230626.nc   recortes de ejemplo (mapas)
.streamlit/config.toml           tema (claro/oscuro)
pyproject.toml, uv.lock, .python-version   entorno reproducible con uv
requirements.txt                 dependencias mínimas (para Streamlit Cloud, que no usa uv)
docs/MODELO_COMPLETO.md          cómo funciona todo el sistema
```

## Correr en local

**Con `uv` (recomendado):**

```bash
uv sync
uv run streamlit run scripts/webapp/model_app.py
```

**Con pip puro:**

```bash
python -m venv .venv && . .venv/bin/activate      # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
streamlit run scripts/webapp/model_app.py
```

Abre `http://localhost:8501`. Las cinco páginas funcionan con los artefactos incluidos; el mapa de
ejemplo trae los días **2019-05-30** y **2023-06-26** (ambos con eventos reportados).

## Publicar (enlace para compartir)

La ruta más rápida y gratuita es **Streamlit Community Cloud**:

1. Sube este paquete a un repo de GitHub (los artefactos ya vienen incluidos, no están ignorados aquí).
2. <https://share.streamlit.io> → **New app** → elige el repo.
3. **Main file path:** `scripts/webapp/model_app.py` · **Python:** 3.13 (o 3.12).
4. Deploy → obtienes `https://<tu-app>.streamlit.app` para compartir.

`requirements.txt` ya está listo para ese entorno. Las otras opciones (EC2 + túnel de Session Manager,
Docker) están en `scripts/webapp/README.md`.

## Notas

- La app es **solo de lectura**: no entrena ni descarga; lee `modelo.joblib` y `reports/`.
- Para regenerar los artefactos desde cero (dataset completo, entrenamiento), ver
  `docs/MODELO_COMPLETO.md` §11; eso sí requiere descargar ERA5/GOES y no es necesario para la demo.
- Cifra honesta a mostrar: el modelo supera a las reglas físicas en **exceso sobre un nulo por
  permutación** (~+17 %), no en la POD cruda; con pocos días de control los KPIs 2/3 son indicativos.
