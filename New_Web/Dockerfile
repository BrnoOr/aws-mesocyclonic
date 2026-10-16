# Imagen de la app Vórtice (Streamlit): detección de mesociclones en Chile.
# Paquete autocontenido: trae el modelo (modelo.joblib), los reportes y un par de recortes ERA5 de
# ejemplo, así que la imagen funciona sin volúmenes ni descargas. Construye para la arquitectura del
# host (en la EC2 del hackathon es arm64/Graviton2).
FROM ghcr.io/astral-sh/uv:0.9.5-python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 PATH="/app/.venv/bin:$PATH"

# Entorno reproducible: solo las dependencias primero, para cachear la capa de uv sync.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

# Código y artefactos que la app lee (solo lectura: no entrena ni descarga).
COPY .streamlit .streamlit
COPY scripts scripts
COPY data data
COPY reports reports
COPY modelo.joblib modelo.joblib

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "scripts/webapp/model_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
