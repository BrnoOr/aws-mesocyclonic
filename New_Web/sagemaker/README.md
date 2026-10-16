# Vórtice en Amazon SageMaker (siguiente paso)

Hoy la API de Vórtice (`scripts/api/`) carga el checkpoint `modelo.joblib` en su propio proceso. Esta
carpeta deja listo el mismo checkpoint para servirlo desde un **endpoint de SageMaker**, sin cambiar
la web ni el contrato de la API. Nada de esto está desplegado todavía.

| Archivo | Qué es |
|---|---|
| `inference.py` | Manejador para el contenedor de scikit-learn de SageMaker (`model_fn`, `input_fn`, `predict_fn`, `output_fn`). |
| `package_model.py` | Prueba el manejador en local y arma `model.tar.gz` (checkpoint + `code/`). |
| `model.tar.gz` | Se genera; no se versiona. |

## Contrato

- Entrada `text/csv`: filas sin encabezado, columnas en el orden de `features` del checkpoint
  (`GET /api/model` las lista). También acepta `application/json` con `{"rows": [{...}]}`.
- Salida `application/json`: `{"probabilities": [p, ...]}`.

`tests/test_api.py` comprueba que `SageMakerPredictor` y este manejador dan las mismas probabilidades
que el checkpoint local.

## Pasos para activarlo

1. **Empaquetar** (desde `New_Web/`):

   ```bash
   uv run python sagemaker/package_model.py
   ```

2. **Subir el paquete** a un bucket de la cuenta, en la región del endpoint:

   ```bash
   aws s3 cp sagemaker/model.tar.gz s3://<bucket>/vortice/model.tar.gz
   ```

3. **Crear el endpoint** con el contenedor de scikit-learn de SageMaker. La versión de scikit-learn
   del contenedor tiene que poder leer el checkpoint: `package_model.py` imprime la versión con que
   se entrenó y la fija en `code/requirements.txt`. Con el SDK de SageMaker:

   ```python
   from sagemaker.sklearn import SKLearnModel

   model = SKLearnModel(
       model_data="s3://<bucket>/vortice/model.tar.gz",
       role="<rol de ejecución de SageMaker>",
       entry_point="inference.py",
       framework_version="<versión de scikit-learn disponible>",
   )
   model.deploy(initial_instance_count=1, instance_type="ml.t2.medium", endpoint_name="vortice")
   ```

   Para un piloto con poco tráfico, un endpoint *serverless* (`ServerlessInferenceConfig`) evita
   pagar una instancia encendida.

4. **Cambiar el motor de la API** al desplegar el sitio. El rol de la EC2 necesita
   `sagemaker:InvokeEndpoint` sobre ese endpoint:

   ```bash
   # en la EC2, vía SSM, antes de deploy/steps/site_deploy.sh:
   export VORTICE_PREDICTOR=sagemaker VORTICE_SAGEMAKER_ENDPOINT=vortice AWS_REGION=us-east-1
   ```

   La consola muestra «Motor: Amazon SageMaker» en la barra cuando la API usa el endpoint.
