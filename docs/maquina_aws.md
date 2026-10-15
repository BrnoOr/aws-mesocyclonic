# La máquina de AWS del hackathon

Características de la instancia EC2 que tenemos disponible, la misma que hospeda el visor y el
code-server. Los datos vienen de la configuración de despliegue (`deploy/`) y del estado de
Terraform (`deploy/terraform.tfstate`); las cifras de CPU, memoria y red son las fijas del tipo de
instancia en AWS.

## Resumen

| Característica | Valor |
|---|---|
| Tipo de instancia | **`c6g.8xlarge`** (familia C6g, optimizada para cómputo) |
| Arquitectura | **arm64 / AWS Graviton2** (no x86) |
| vCPU | **32** |
| Memoria RAM | **64 GiB** |
| Red | hasta **12,5 Gbps** |
| Ancho de banda EBS | hasta **9 Gbps** |
| ID de instancia | `i-0ea9664c5e9ada5a0` |
| Región / zona | **us-east-1** (us-east-1c) |
| Estado | en ejecución (`running`) |

## Procesador y memoria

- **Procesador:** AWS Graviton2 (ARM Neoverse N1), 64 bits, arquitectura **arm64**. No es x86: las
  dependencias y las imágenes de Docker tienen que ser para arm64 (por eso el `docker build` del
  despliegue es arm64, ver `deploy/provision.sh`).
- **vCPU:** 32 núcleos físicos (Graviton no usa hyperthreading, así que cada vCPU es un núcleo real).
- **RAM:** 64 GiB. La familia C6g lleva una proporción de 2 GiB por vCPU (es "compute optimized":
  mucha CPU en relación a la memoria).

## Almacenamiento

- **Disco raíz (EBS):** un único volumen de **40 GiB**, tipo **gp3**.
  - 3000 IOPS, 125 MiB/s de throughput.
  - Cifrado con KMS, se borra al terminar la instancia (`delete_on_termination`).
  - Dispositivo `/dev/xvda`, volumen `vol-01cd087a3f2391c6a`.
- No tiene volúmenes EBS adicionales ni almacenamiento de instancia (`instance store`) efímero.
- La instancia **no** está marcada como `ebs_optimized` en su configuración, aunque las C6g traen
  ancho de banda EBS dedicado de serie.

> El disco de 40 GiB es la restricción más importante para nuestro trabajo. Cada archivo de nivel de
> presión de ERA5 pesa ~1,4 GB y un caso completo son unos 3 GB de recortes; conviene limpiar lo
> descargado entre días o apuntar `MESO_DATA_ROOT` a un bucket de S3 en vez de llenar el disco.

## Red e identidad

- **IP pública:** 54.84.138.230 · **DNS público:** `ec2-54-84-138-230.compute-1.amazonaws.com`
- **IP privada:** 172.31.42.81 · **DNS privado:** `ip-172-31-42-81.ec2.internal`
- **Interfaz de red:** `eni-072a2f3a6ad6836a3`
- **Subnet:** `subnet-03fb585df1619272d` · **VPC** por defecto (CIDR `172.31.32.0/20`)
- **Security groups:** `sg-0f0d310ee81f4fd96` (`vscode-server-SecurityGroup-xPeh9nqcYEc4`), más el SG
  del visor que agrega el despliegue para abrir el puerto 8501 solo a CloudFront.
- **Perfil IAM:** `vscode-server-CodeEditorInstanceProfile-YyvjoajBIWuw` (rol adjunto a la instancia;
  es el que usan los scripts para hablar con AWS).
- **Metadata:** IMDSv2 obligatorio (`http_tokens = required`).
- **Acceso:** sin par de llaves SSH (`key_name` vacío); el acceso es por **SSM Session Manager**
  (así corre el despliegue sus comandos y así se abre el túnel al visor).
- **Monitoring detallado:** activado.

## Sistema e imagen

- **AMI:** `ami-01ef1060bc43e3f91` (imagen base arm64 del entorno de code-server del hackathon).
- La instancia ya trae **Docker** y corre **nginx** en el puerto 80 sirviendo el code-server, detrás
  de una CloudFront preexistente. El visor se publica aparte en el puerto 8501.
- **Tags:** `Name = CodeEditor`, `event = AWS Generative AI Hackathon VS Code`.
- **Cuenta AWS:** 620965032345.

## Qué implica para el proyecto

- **Buena CPU, poco disco.** 32 vCPU y 64 GiB rinden de sobra para recortar ERA5 en memoria y
  procesar GOES en paralelo; el cuello de botella es el volumen de 40 GiB, no el cómputo.
- **Es arm64.** Cualquier dependencia nativa o imagen de contenedor tiene que resolver para arm64.
  `uv sync` y las ruedas de PyPI del `pyproject.toml` lo soportan; tenlo en cuenta si agregas algo
  nuevo con `uv add`.
- **Está en us-east-1.** Es la región de **GOES** (`noaa-goes16`/`noaa-goes19`), así que esos datos
  se leen sin egreso entre regiones. **ERA5** vive en **us-west-2** (`s3://nsf-ncar-era5/`), así que
  bajarlo desde esta máquina cruza regiones: es correcto, pero más lento y con costo de
  transferencia. Para trabajo intensivo de ERA5, lo ideal sería una máquina en us-west-2 (ver
  `docs/sagemaker.md`).
- **El acceso es por SSM, no SSH.** Para entrar o abrir el visor se usa un túnel de Session Manager,
  como explica la página Starter kit del visor.
