# Correr los cuadernos en Amazon SageMaker

Guía para abrir y ejecutar los cuadernos de `notebooks/` (hoy `eda_mesociclones.ipynb`) en una
máquina gestionada de AWS, cerca de los datos. El cuaderno es Python puro con **uv**: lee los
recortes de `data/crops/<región>/` a través de `common`/`store`, y la raíz de datos se controla con
la variable de entorno `MESO_DATA_ROOT` (una carpeta local o un prefijo `s3://bucket/prefijo`). Eso
encaja directo con SageMaker.

## Por qué SageMaker y en qué región

El EDA toca las tres fuentes del proyecto, y cada una tiene sus trampas (detalle en
`docs/mesociclones_chile.md` y `AGENTS.md`):

- **ERA5** vive en `s3://nsf-ncar-era5/` (**us-west-2**). Cada archivo de nivel de presión pesa
  ~1,4 GB (una variable, un día, el globo) y no admite recorte en el servidor: cada hora se
  transfiere entera como un bloque global y se recorta en memoria. Pide RAM y disco holgados.
- **GOES** lo ve GOES-East (`noaa-goes16`/`noaa-goes19`, **us-east-1**).
- El **catálogo** (`data/tornados_chile.xlsx`) es un único archivo pequeño.

Todos los buckets son de Open Data y el proyecto los lee **anónimo** (`common.s3()` usa `anon=True`),
así que para generar datos no hacen falta credenciales. La región conviene elegirla según de dónde
tires más: **us-west-2** si vas a bajar o procesar ERA5 (es lo que domina el tiempo y lo que
recomienda la página Starter kit del visor), **us-east-1** si tu trabajo es sobre todo GOES. Si
trabajas contra el bucket del equipo, pon el bucket y SageMaker en la misma región para no pagar
egreso entre regiones.

Recomendación para arrancar sin fricción: **Studio JupyterLab en us-west-2**, instancia
`ml.m5.2xlarge` (32 GB de RAM), **≥ 50 GB de EBS**, con `MESO_DATA_ROOT` apuntando a un bucket del
equipo también en us-west-2.

## Opción A — SageMaker Studio (JupyterLab)

Un JupyterLab gestionado; es la vía más directa para este cuaderno.

1. En la consola, **Amazon SageMaker AI → Studio**. Crea un dominio (el modo rápido sirve) y abre
   **JupyterLab**. Crea un *space* con una instancia:
   - Catálogo y GOES: `ml.t3.large` o `ml.t3.xlarge` basta.
   - ERA5 con niveles de presión: sube a `ml.m5.2xlarge` (32 GB) por el recorte en memoria.
   - Dale **≥ 50 GB de EBS** al space; cada archivo de ERA5 pesa ~1,4 GB.

2. En una terminal de JupyterLab, instala **uv**, clona el repo y crea el entorno (el proyecto no es
   un paquete instalable, así que basta `uv sync`):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.local/bin:$PATH"

   git clone <url-del-repo> aws-mesocyclonic
   cd aws-mesocyclonic
   uv sync                 # crea .venv con las dependencias y las herramientas de desarrollo
   ```

3. Registra el entorno como kernel de Jupyter y luego elígelo en el cuaderno:

   ```bash
   uv add --dev ipykernel  # si todavía no está en el grupo dev
   uv run python -m ipykernel install --user --name meso --display-name "Python (meso)"
   ```

   En `notebooks/eda_mesociclones.ipynb`, selecciona el kernel **Python (meso)**.

4. Datos. La celda 0 del cuaderno resuelve la raíz con `MESO_DATA_ROOT`. Dos caminos:

   - **Generarlos en la instancia** con el pipeline (lee de los buckets públicos, sin credenciales):

     ```bash
     uv run scripts/pipeline/download_goes.py  --start 2019-05-30
     uv run scripts/pipeline/download_era5.py  --start 2019-05-30
     uv run scripts/pipeline/process_era5.py   --start 2019-05-30
     ```

   - **Apuntar al bucket del equipo** sin bajar nada a disco (requiere permisos de lectura/escritura
     sobre ese prefijo, ver más abajo):

     ```bash
     export MESO_DATA_ROOT=s3://mi-bucket/meso
     ```

     Expórtala **antes** de abrir Jupyter (o reinicia el kernel), para que `common.DATA` la tome.

## Opción B — SageMaker Notebook Instances (clásica)

Más simple si solo quieres «una máquina con Jupyter». Mismo flujo: creas la instancia, abres una
terminal, instalas `uv`, `uv sync` y registras el kernel como en la opción A. Dale un volumen EBS
grande en la configuración de la instancia por lo de ERA5. Para dejar el entorno listo al arrancar,
puedes poner los comandos de `uv` en un **lifecycle configuration script**.

## Qué revisar sí o sí

- **Rol de ejecución (IAM).** Para los buckets públicos (ERA5 `nsf-ncar-era5`, GOES
  `noaa-goes16`/`noaa-goes19`) no hace falta nada: el acceso es anónimo. Para leer o escribir en el
  bucket del equipo (`MESO_DATA_ROOT=s3://...`), el rol de SageMaker necesita `s3:GetObject`,
  `s3:PutObject` y `s3:ListBucket` sobre ese prefijo.
- **Disco y RAM.** Los archivos de nivel de presión de ERA5 (~1,4 GB) se recortan en memoria: no
  arranques con `ml.t3.medium` para eso. Reserva EBS para los recortes (un caso son unos 3 GB).
- **Costo.** Las instancias se cobran mientras están encendidas, y Studio no se apaga solo por
  defecto. Apaga el space o la notebook instance cuando no la uses.

## Relación con el despliegue en EC2

Esto es para **explorar y entrenar** en cuadernos. El visor se despliega aparte en una EC2 de
us-west-2 por un túnel de Session Manager; esa parte la explica la página **Starter kit** del propio
visor. Ambos caminos comparten la misma idea: trabajar en us-west-2, junto a ERA5, y leer los datos
desde el bucket del equipo o desde los recortes generados por el pipeline.
