# Sitio de producto Vórtice: cómo montarlo en la web

Página para vender Vórtice con la aplicación adentro: la **consola** (mapas hora a hora, explicación
de cada celda y puntajes más altos) le pide los datos a la **API de inferencia**. Reemplaza en el
puerto 8502 a la app Streamlit y a la landing (`../landing/`), que quedan en el repo sin desplegar.

## Qué queda en la web

| Ruta | Qué sirve | Contenedor |
|---|---|---|
| `https://d1y31u1kylukz6.cloudfront.net/` | Página de producto con la consola | `vortice-site` (nginx, 8502 → 80) |
| `https://d1y31u1kylukz6.cloudfront.net/api/` | API de inferencia (FastAPI); documentación en `/api/docs` | `vortice-api` (uvicorn, sin puerto publicado, red `vortice-net`) |

El enlace de CloudFront no cambia y no hay que tocar CloudFront ni el security group.

**Motor de la API.** Por omisión, el checkpoint local `modelo.joblib` (como hasta ahora). Cuando
exista un endpoint de SageMaker, se cambia con variables de entorno; ver `../sagemaker/README.md`.

**Modo demostración.** Si la API no responde, la consola usa los puntajes precalculados de
`assets/day_*.json` y lo dice en la barra («Modo demostración»). La página nunca queda vacía.

## Archivos

| Archivo | Qué es |
|---|---|
| `page.html` | La página (fragmento HTML; el `Dockerfile` lo envuelve en un documento). |
| `assets/` | Foto de portada y respaldo de la consola: `days.json`, `model.json`, `day_AAAAMMDD.json`. |
| `nginx.conf` | `/` estático, `/api/` → `http://vortice-api:8000`. |
| `Dockerfile` | Imagen nginx del sitio. |
| `../scripts/api/` | La API: `server.py` (rutas), `service.py` (puntaje de un día), `predictors.py` (motor local o SageMaker), `snapshot.py` (regenera `assets/`). |
| `../../deploy/steps/site_deploy.sh` | Despliegue en la EC2 (se envía por SSM). |

## Pasos

1. **Probar en local** (desde `New_Web/`):

   ```bash
   uv run python -m unittest discover -s tests      # API, contrato SageMaker y respaldo
   uv run uvicorn server:app --app-dir scripts/api --port 8000   # la API sola: /api/docs
   uv run python -m http.server 8080 --directory site           # la página en modo demostración
   # abrir http://localhost:8080/page.html (sin nginx no hay /api/, así que usa assets/)
   ```

2. **Subir los cambios a GitHub** (el despliegue clona `main`):

   ```bash
   git add New_Web deploy/steps/site_deploy.sh .gitignore
   git commit -m "feat(web): sitio de producto Vórtice con consola y API de inferencia"
   git push origin main
   ```

3. **Desplegar** (Windows, credenciales de la cuenta 620965032345):

   ```powershell
   powershell -NoProfile -File deploy/deploy_vortice.ps1 `
     -StepScript deploy/steps/site_deploy.sh -HealthPath /api/health
   ```

   Termina con `SITE_DEPLOY_DONE` y muestra el motor en uso.

4. **Verificar** en el navegador:
   - La barra de la consola dice «Motor: checkpoint local · listo para SageMaker» (no «Modo
     demostración»; si lo dice, la API no responde: `docker logs vortice-api`).
   - Cambiar de día (30-05-2019 y 26-06-2023) y mover la hora redibuja los dos mapas.
   - Tocar una celda llena la tabla «Celda seleccionada»; tocar una alerta de la lista también.
   - `/api/docs` abre la documentación de la API.
   - En el teléfono, nada se sale por el costado.

## Si algo falla

- **Volver a la app Streamlit sola:** `powershell -NoProfile -File deploy/deploy_vortice.ps1`.
- **Volver a la landing anterior:** `deploy_vortice.ps1 -StepScript deploy/steps/web_deploy.sh -HealthPath /app/_stcore/health`.
- **La consola no carga ningún día:** faltan `assets/`; correr `uv run python scripts/api/snapshot.py`.

## Si cambia el modelo

Reentrenar deja un `modelo.joblib` nuevo. Después: `uv run python scripts/api/snapshot.py` (respaldo
de la consola), `uv run python sagemaker/package_model.py` (paquete para SageMaker) y actualizar a mano
las cifras de las secciones «Evidencia» y de la portada de `page.html`, que vienen de
`reports/aiwp_bundle_eval.md` y `reports/train_south-central_lead0h.md`.
