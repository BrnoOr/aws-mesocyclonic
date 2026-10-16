# Web de demostración del modelo (Streamlit)

`model_app.py` muestra, con imágenes y gráficos, cómo funciona el modelo de mesociclones: un mapa de
probabilidad sobre la grilla ERA5, la curva de operación, la tabla de KPIs frente a las reglas físicas
y la evaluación sobre el pronóstico AIWP (sin fuga, con el baseline nulo). Es **solo de lectura**:
carga `modelo.joblib` y `reports/` ya generados; no entrena ni descarga.

## Qué necesita antes de correr

```bash
uv sync                                                   # entorno
uv run python scripts/pipeline/clean_catalog.py           # catálogo (para los puntos del mapa)
uv run python scripts/model/train.py   --region south-central --lead 0 --model forest --features wind
uv run python scripts/model/eval_aiwp.py --force
# y al menos un recorte ERA5 en data/crops/south-central/era5_indices/ para el mapa de ejemplo
```

Si falta algún artefacto, la página correspondiente muestra un aviso en vez de fallar.

## Correr en local

```bash
uv run streamlit run scripts/webapp/model_app.py
```

Abre `http://localhost:8501`. Para que otro equipo de tu red lo vea, Streamlit imprime también una
«Network URL».

---

## Obtener un enlace para compartir (público)

> No puedo generar el enlace desde aquí (no tengo cómo provisionar hosting externo). Estos son los
> dos caminos reales; ambos requieren una cuenta tuya.

### Opción A — Streamlit Community Cloud (gratis, el más rápido)

1. Sube el repo a GitHub (público o privado).
2. Entra en <https://share.streamlit.io> con tu cuenta de GitHub y pulsa **New app**.
3. Elige el repo y rama; **Main file path** = `scripts/webapp/model_app.py`.
4. En **Advanced settings** fija la versión de Python (3.12) y, si usas `uv`, añade un
   `requirements.txt` o deja que detecte `pyproject.toml`.
5. **Deploy.** Te da una URL `https://<tu-app>.streamlit.app` que es el enlace para compartir.

**Importante:** `data/` y `modelo.joblib` están en `.gitignore` (no se versionan). Para la nube, sube
los artefactos mínimos que la app lee (`modelo.joblib`, `reports/*`, y 1–2 `era5_idx_*.nc` de
ejemplo) a un almacenamiento accesible (p. ej. un bucket S3 público o inclúyelos en el repo de deploy),
o adapta las rutas de `model_app.py` para leerlos desde ahí. Sin esos artefactos la app arranca pero
muestra avisos de «falta …».

### Opción B — EC2 + túnel de Session Manager (lo que documenta el Starter kit)

En una instancia EC2 en `us-west-2` (junto a los buckets), con el repo y los artefactos:

```bash
uv run streamlit run scripts/webapp/model_app.py --server.port 8501 --server.headless true
```

Desde tu máquina, abre un túnel con AWS Session Manager (sin exponer puertos públicos):

```bash
aws ssm start-session --target <INSTANCE_ID> --region us-west-2 \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8501"],"localPortNumber":["8501"]}'
```

Y abre `http://localhost:8501`. El «enlace para compartir» aquí es el túnel: cada persona abre el suyo
con el mismo comando (requiere permiso IAM `ssm:StartSession` sobre esa instancia). Para un enlace
público permanente harían falta un Application Load Balancer + dominio + HTTPS, que es despliegue a
mano (ver la página «Starter kit» del visor).

### Opción C — Docker (para cualquier host)

El repo trae `Dockerfile`/`compose.yaml` para el visor; se puede apuntar el mismo patrón a
`scripts/webapp/model_app.py` cambiando el comando de arranque, montando `data/` y publicando el
puerto 8501 en el host o detrás de un proxy con HTTPS.

---

## Estado honesto

- La app está **construida y probada en local** (arranca headless sin errores, `make check` en verde).
- **No hay un enlace público** generado por mí: eso depende de que publiques por A, B o C con tu
  cuenta. La ruta más rápida para un enlace compartible es la **Opción A** (minutos, gratis), cuidando
  de hacer accesibles `modelo.joblib` + `reports/` + un `era5_idx` de ejemplo.
