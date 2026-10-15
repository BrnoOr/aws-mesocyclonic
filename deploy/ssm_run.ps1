# Envía un script bash a la instancia por SSM, espera a que termine y muestra la salida.
# Uso: powershell -NoProfile -File deploy/ssm_run.ps1 -ScriptPath <archivo.sh> [-TimeoutSeconds 3600]
param(
  [Parameter(Mandatory = $true)][string]$ScriptPath,
  [int]$TimeoutSeconds = 3600,
  [string]$InstanceId = "i-0ea9664c5e9ada5a0",
  [string]$Region = "us-east-1"
)
$ErrorActionPreference = "Stop"

$script = Get-Content -Raw $ScriptPath
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
$params = @{
  commands = @(
    "echo $b64 | base64 -d | tr -d '\r' > /tmp/meso_step.sh",
    "chmod +x /tmp/meso_step.sh",
    "bash /tmp/meso_step.sh"
  )
} | ConvertTo-Json -Compress

$pf = Join-Path $env:TEMP "meso_ssm_params.json"
[System.IO.File]::WriteAllText($pf, $params, (New-Object System.Text.UTF8Encoding($false)))

$cmdId = (aws ssm send-command --region $Region --instance-ids $InstanceId `
  --document-name AWS-RunShellScript --comment "paso meso" `
  --timeout-seconds $TimeoutSeconds --parameters "file://$pf" `
  --query "Command.CommandId" --output text)
Write-Host "CommandId: $cmdId"
if ([string]::IsNullOrWhiteSpace($cmdId)) { throw "No se pudo enviar el comando SSM" }

do {
  Start-Sleep -Seconds 10
  $status = (aws ssm get-command-invocation --region $Region --command-id $cmdId `
    --instance-id $InstanceId --query "Status" --output text) 2>$null
  Write-Host "Estado: $status"
} while ($status -eq "Pending" -or $status -eq "InProgress" -or $status -eq "Delayed" -or [string]::IsNullOrEmpty($status))

Write-Host "=== STDOUT ==="
aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $InstanceId --query "StandardOutputContent" --output text
Write-Host "=== STDERR ==="
aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $InstanceId --query "StandardErrorContent" --output text
Write-Host "=== FIN ($status) ==="
if ($status -ne "Success") { exit 1 }
