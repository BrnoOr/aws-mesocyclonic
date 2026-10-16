# Página del proyecto Vórtice: cómo montarla en la web

Encargo para Kiro (o quien despliegue). La página ya está escrita y probada como vista previa; falta
subirla a la EC2 del hackatón para que quede en el enlace público de CloudFront.

## Qué queda en la web

| Ruta | Qué sirve | Contenedor |
|---|---|---|
| `https://d1y31u1kylukz6.cloudfront.net/` | La página del proyecto (esta carpeta) | `vortice-web` (nginx, puerto 8502 → 80) |
| `https://d1y31u1kylukz6.cloudfront.net/app/` | La app Streamlit de Vórtice (`scripts/webapp/model_app.py`) | `vortice` (sin puerto publicado, red `vortice-net`) |

El enlace de CloudFront **no cambia**: sigue apuntando al puerto 8502 de la EC2. Lo que cambia es que
en 8502 ahora responde nginx, que sirve la página en `/` y pasa `/app/` a Streamlit (con WebSocket).
No hay que tocar CloudFront, el security group ni crear recursos nuevos.

## Archivos

| Archivo | Qué es |
|---|---|
| `page.html` | La página. Es un fragmento HTML (sin `<html>`/`<head>`): el `Dockerfile` lo envuelve. |
| `assets/` | Datos y figuras que lee la página: `caso2019.json`, `eventos_aiwp.json`, la foto y dos figuras. |
| `nginx.conf` | `/` estático, `/app/` → `http://vortice:8501`, `/health` para comprobar. |
| `Dockerfile` | Imagen `nginx:1.27-alpine` con la página. |
| `../scripts/webapp/landing_data.py` | Regenera `assets/` desde `modelo.joblib`, `reports/` y el recorte ERA5 de 2019. |
| `../../deploy/steps/web_deploy.sh` | Despliegue en la EC2 (se envía por SSM). |

## Pasos

1. **Subir los cambios a GitHub.** El despliegue clona `main` de `BrnoOr/aws-mesocyclonic`, así que
   todo lo de esta carpeta, `scripts/webapp/landing_data.py`, `deploy/steps/web_deploy.sh` y el cambio de
   `deploy/deploy_vortice.ps1` tienen que estar en `origin/main`:

   ```bash
   git add New_Web/landing New_Web/scripts/webapp/landing_data.py deploy/steps/web_deploy.sh deploy/deploy_vortice.ps1
   git commit -m "feat(web): página del proyecto Vórtice en / y la app en /app/"
   git push origin main
   ```

2. **Desplegar** (Windows, con credenciales AWS de la cuenta 620965032345; ver
   `docs/conectar_aws_kiro_cli.md`):

   ```powershell
   powershell -NoProfile -File deploy/deploy_vortice.ps1 `
     -StepScript deploy/steps/web_deploy.sh -HealthPath /app/_stcore/health
   ```

   Construye dos imágenes en la EC2 (arm64), crea la red `vortice-net`, levanta `vortice` con
   `STREAMLIT_SERVER_BASE_URL_PATH=app` y `vortice-web` en 8502. Termina con `WEB_DEPLOY_DONE`.

3. **Verificar** en el navegador:
   - `/` muestra la portada con la foto del tornado y, al bajar, los dos mapas del 30 de mayo de 2019.
     Mover la hora tiene que redibujar los mapas y cambiar las tres cifras de la derecha.
   - La tabla de «Resultados» lista 25 eventos y el mapa de al lado muestra 25 círculos.
   - «Abrir la app» lleva a `/app/` y la app de Streamlit carga (si queda en «Please wait…», el
     WebSocket no pasa: revisar `docker logs vortice-web`).
   - Probar en el teléfono: nada se sale por el costado.

## Si algo falla

- **Volver a como estaba** (solo la app en 8502):
  `powershell -NoProfile -File deploy/deploy_vortice.ps1`. El script viejo libera el puerto 8502 y
  levanta `vortice` ahí, sin la página.
- **La página carga pero sin mapas ni tabla:** faltan los JSON en `assets/`. Correr
  `uv run python scripts/webapp/landing_data.py` desde `New_Web/` y volver a subir.
- **`/app/` da 502:** el contenedor `vortice` no está en `vortice-net` o no arrancó:
  `docker ps`, `docker logs vortice`.

## Pendientes de contenido (antes del pitch)

- **Equipo.** El pie de página no nombra a los integrantes. Agregarlos en la primera columna de
  `<footer class="site">` en `page.html`.
- **Cifras.** Las de «Resultados» y «Metas» vienen de `reports/aiwp_bundle_eval.md` y
  `reports/train_south-central_lead0h.md`. Si se reentrena el modelo, regenerar `assets/` y
  actualizar a mano los números de esas dos secciones (están escritos en el HTML y en `drawChart()`).
- **Líneas base del CR2** (STP 0 de 7, FAR ≈ 70 %, ≈ 4 alertas por acierto): salen del planteamiento
  del desafío (`docs/bb-assets-s1-presentation.pptx`, lámina 6).

## Tarea opcional: boletines con Amazon Bedrock

El desafío es de IA generativa y el producto todavía no usa un modelo de lenguaje. La página ya trae
una sección «Boletines» oculta que aparece sola si existe `assets/boletines.json`:

```json
[
  {"date": "2026-06-12", "place": "Biobío, cerca de Los Ángeles", "score": 87,
   "text": "Párrafo de 2 a 4 frases para el meteorólogo: qué índices pesan, por qué, y qué revisar."}
]
```

Muestra hasta seis. Para generarlo: un script en `New_Web/scripts/webapp/` que lea la lista de
candidatos (fecha, celda, puntaje y las variables que más pesan), llame a un modelo Claude en Amazon
Bedrock (API Converse) con un prompt que explique los índices australes (signos negativos, régimen
HSLC) y escriba el JSON. Reglas para el texto: no afirmar que hubo un tornado, hablar de
«condiciones favorables» y citar los valores de los índices. Después de generarlo, volver a hacer el
paso 1 y el paso 2.
