# Despliega la web "Vórtice" en la EC2 del hackathon de principio a fin y verifica el enlace público.
#
# Hace, en orden:
#   1. Comprueba credenciales AWS (sts get-caller-identity, cuenta 620965032345).
#   2. Comprueba que la instancia está Online en SSM.
#   3. Envía deploy/steps/vortice_deploy.sh por SSM (clona el repo, build arm64, arranca en 8502).
#   4. Verifica salud local en la EC2 y responde del enlace CloudFront público.
#
# Uso:
#   powershell -NoProfile -File deploy/deploy_vortice.ps1
#
# Página del proyecto en / y la app en /app/ (mismo enlace CloudFront):
#   powershell -NoProfile -File deploy/deploy_vortice.ps1 -StepScript deploy/steps/web_deploy.sh -HealthPath /app/_stcore/health
#
# Requiere: AWS CLI v2 con credenciales válidas de la cuenta 620965032345 (ver
# docs/conectar_aws_kiro_cli.md). Si salen ExpiredToken/InvalidClientTokenId, renueva las credenciales
# y vuelve a correr este script.
param(
  [string]$InstanceId   = "i-0ea9664c5e9ada5a0",
  [string]$Region       = "us-east-1",
  [string]$CloudFrontUrl = "https://d1y31u1kylukz6.cloudfront.net",
  [int]$TimeoutSeconds  = 3600,
  [string]$StepScript   = "deploy/steps/vortice_deploy.sh",
  [string]$HealthPath   = "/_stcore/health"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

Write-Host "=== 1/4 Verificando credenciales AWS ===" -ForegroundColor Cyan
$who = (aws sts get-caller-identity --region $Region --output json) 2>&1
if ($LASTEXITCODE -ne 0) {
  Fail "Credenciales no válidas o expiradas. Renueva (aws configure / aws sso login) y reintenta.`n$who"
}
Write-Host $who

Write-Host "=== 2/4 Comprobando que la instancia está Online en SSM ===" -ForegroundColor Cyan
$ping = (aws ssm describe-instance-information --region $Region `
  --filters "Key=InstanceIds,Values=$InstanceId" `
  --query "InstanceInformationList[].PingStatus" --output text) 2>&1
Write-Host "PingStatus: $ping"
if ($ping -notmatch "Online") { Fail "La instancia no está Online en SSM (¿apagada o agente caído?)." }

Write-Host "=== 3/4 Enviando el deploy de Vórtice por SSM ===" -ForegroundColor Cyan
$scriptPath = Join-Path $repoRoot $StepScript
if (-not (Test-Path $scriptPath)) { Fail "No se encuentra $scriptPath" }
& (Join-Path $repoRoot "deploy/ssm_run.ps1") -ScriptPath $scriptPath -InstanceId $InstanceId -Region $Region -TimeoutSeconds $TimeoutSeconds
if ($LASTEXITCODE -ne 0) { Fail "El deploy por SSM no terminó con éxito. Revisa el STDOUT/STDERR de arriba." }

Write-Host "=== 4/4 Verificando el enlace público (CloudFront) ===" -ForegroundColor Cyan
# CloudFront puede tardar unos segundos en reflejar el nuevo origin; reintentar.
$ok = $false
for ($i = 1; $i -le 20; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "$CloudFrontUrl$HealthPath" -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -eq 200) {
      Write-Host "OK: Vórtice responde en $CloudFrontUrl (health 200)" -ForegroundColor Green
      $ok = $true; break
    }
  } catch {
    Write-Host "  intento $i/20: aún no responde ($($_.Exception.Message))"
  }
  Start-Sleep -Seconds 6
}
if (-not $ok) {
  Write-Host "AVISO: el health por CloudFront no respondió 200 a tiempo." -ForegroundColor Yellow
  Write-Host "La app puede seguir levantando o CloudFront propagando. Prueba el enlace en el navegador:"
}
Write-Host ""
Write-Host "================ ENLACE PARA COMPARTIR ================" -ForegroundColor Green
Write-Host "  $CloudFrontUrl" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
