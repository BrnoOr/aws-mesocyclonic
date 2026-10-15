# Despliegue del visor Streamlit sobre la instancia EC2 del hackathon.
#
# La instancia (i-0ea9664c5e9ada5a0) ya tiene Docker y ya corre nginx en el
# puerto 80 sirviendo el code-server, expuesto por una CloudFront preexistente.
# Para no romper nada, este despliegue:
#   1. Publica el visor en Docker en el puerto 8501 del host.
#   2. Abre el puerto 8501 en el security group SOLO para el rango de CloudFront.
#   3. Crea una CloudFront NUEVA que apunta al origin EC2:8501 (http-only).
#      Streamlit usa WebSockets, por eso la cache se desactiva y se reenvia todo.
#   4. Construye y arranca el contenedor en la instancia via SSM.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# --- Entradas conocidas de la instancia existente ----------------------------

data "aws_instance" "viewer" {
  instance_id = var.instance_id
}

# El VPC se deriva de la subnet de la instancia (el data source aws_instance no
# expone vpc_id directamente).
data "aws_subnet" "viewer" {
  id = data.aws_instance.viewer.subnet_id
}

# La ENI primaria de la instancia (aws_instance no la expone directamente).
data "aws_network_interfaces" "viewer" {
  filter {
    name   = "attachment.instance-id"
    values = [var.instance_id]
  }
}

# Prefix list gestionado de AWS para los IP de origen de CloudFront.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# --- Abrir el puerto del visor solo para CloudFront ---------------------------
#
# El SG existente de la instancia (gestionado por el stack vscode-server) ya
# alcanzo su limite de reglas, asi que se crea un SG propio para el visor y se
# adjunta a la interfaz de red de la instancia (una ENI admite varios SGs).

resource "aws_security_group" "viewer" {
  name_prefix = "mesocyclonic-viewer-"
  description = "Visor Streamlit: ingress 8501 solo desde CloudFront"
  vpc_id      = data.aws_subnet.viewer.vpc_id

  ingress {
    description     = "Visor Streamlit solo desde CloudFront"
    from_port       = var.viewer_port
    to_port         = var.viewer_port
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  tags = {
    Project = "mesocyclonic-viewer"
  }
}

resource "aws_network_interface_sg_attachment" "viewer" {
  security_group_id    = aws_security_group.viewer.id
  network_interface_id = tolist(data.aws_network_interfaces.viewer.ids)[0]
}

# --- CloudFront delante del visor ---------------------------------------------

resource "aws_cloudfront_distribution" "viewer" {
  enabled         = true
  comment         = "Visor mesociclones (Streamlit) sobre EC2 ${var.instance_id}"
  http_version    = "http2and3"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"

  origin {
    origin_id   = "viewer-ec2"
    domain_name = data.aws_instance.viewer.public_dns

    custom_origin_config {
      http_port              = var.viewer_port
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60
      origin_keepalive_timeout = 60
    }
  }

  default_cache_behavior {
    target_origin_id       = "viewer-ec2"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Managed-CachingDisabled: Streamlit es dinamico y usa WebSockets.
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # Managed-AllViewer: reenvia todos los headers/cookies/query al origin,
    # necesario para el handshake WebSocket de Streamlit.
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Project = "mesocyclonic-viewer"
  }
}

# --- Construir y arrancar el contenedor en la instancia via SSM ---------------
#
# Se dispara cuando cambia el commit solicitado o el puerto. El script clona el
# repo publico, construye la imagen (arm64) y arranca el contenedor publicando
# el puerto del visor. Es idempotente: recrea el contenedor en cada corrida.

resource "null_resource" "provision" {
  triggers = {
    repo_ref    = var.repo_ref
    viewer_port = var.viewer_port
    case_date   = var.case_date
    script_hash = filesha256("${path.module}/provision.sh")
  }

  provisioner "local-exec" {
    interpreter = ["powershell", "-NoProfile", "-Command"]
    command     = <<-EOT
      $ErrorActionPreference = "Stop"
      $script = Get-Content -Raw "${path.module}/provision.sh"
      $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
      $params = @{
        commands = @(
          "echo $b64 | base64 -d | tr -d '\\r' > /tmp/provision_viewer.sh",
          "chmod +x /tmp/provision_viewer.sh",
          "REPO_REF='${var.repo_ref}' REPO_URL='${var.repo_url}' VIEWER_PORT='${var.viewer_port}' CASE_DATE='${var.case_date}' bash /tmp/provision_viewer.sh"
        )
      } | ConvertTo-Json -Compress
      # El AWS CLI rechaza JSON con BOM: se escribe UTF-8 sin BOM y se pasa por file://.
      $pf = Join-Path $env:TEMP "meso_params.json"
      [System.IO.File]::WriteAllText($pf, $params, (New-Object System.Text.UTF8Encoding($false)))
      $cmdId = (aws ssm send-command --region ${var.region} --instance-ids ${var.instance_id} --document-name AWS-RunShellScript --comment "Build y arranque del visor" --timeout-seconds 1800 --parameters "file://$pf" --query "Command.CommandId" --output text) 2>$null
      Write-Host "SSM CommandId: $cmdId"
      if ([string]::IsNullOrWhiteSpace($cmdId)) { throw "No se pudo enviar el comando SSM" }
      do {
        Start-Sleep -Seconds 15
        $status = (aws ssm get-command-invocation --region ${var.region} --command-id $cmdId --instance-id ${var.instance_id} --query "Status" --output text) 2>$null
        Write-Host "Estado: $status"
      } while ($status -eq "Pending" -or $status -eq "InProgress" -or $status -eq "Delayed" -or [string]::IsNullOrEmpty($status))
      aws ssm get-command-invocation --region ${var.region} --command-id $cmdId --instance-id ${var.instance_id} --query "StandardOutputContent" --output text
      if ($status -ne "Success") {
        Write-Host "=== STDERR ==="
        aws ssm get-command-invocation --region ${var.region} --command-id $cmdId --instance-id ${var.instance_id} --query "StandardErrorContent" --output text
        throw "El provisioning fallo con estado: $status"
      }
    EOT
  }

  depends_on = [aws_network_interface_sg_attachment.viewer]
}
