<#
.SYNOPSIS
Script completo para subir y verificar glue-dependencies.zip en AWS Glue

.DESCRIPTION
Este script:
1. Verifica credenciales AWS
2. Sube el ZIP a S3
3. Crea un Glue Job de prueba
4. Ejecuta el job
5. Espera 200 segundos
6. Verifica el estado y logs
7. Limpia recursos

.PARAMETER Bucket
Nombre del bucket S3 (sin s3://)

.PARAMETER Profile
Perfil AWS a usar (default: sbnai-admin)

.EXAMPLE
.\deploy-and-test-glue.ps1 -Bucket "mi-bucket-glue"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Bucket,
    
    [Parameter(Mandatory=$false)]
    [string]$Profile = "sbnai-admin",
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  AWS GLUE DEPLOYMENT & TEST E2E" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# PASO 1: VERIFICAR CREDENCIALES
# ============================================================================
Write-Host "[1/7] Verificando credenciales AWS..." -ForegroundColor Yellow

try {
    $identity = aws sts get-caller-identity --profile $Profile --output json | ConvertFrom-Json
    Write-Host "✓ Usuario: $($identity.Arn)" -ForegroundColor Green
    $accountId = $identity.Account
} catch {
    Write-Host "✗ ERROR: No se pudo verificar credenciales" -ForegroundColor Red
    Write-Host "Ejecuta: aws sso login --profile $Profile" -ForegroundColor Yellow
    exit 1
}

# ============================================================================
# PASO 2: VERIFICAR ARCHIVOS LOCALES
# ============================================================================
Write-Host "[2/7] Verificando archivos locales..." -ForegroundColor Yellow

$zipPath = "build\glue-dependencies.gluewheels.zip"
$scriptPath = "examples\glue-job-example.py"
$projectWheelPath = (Get-ChildItem -Path "build\chucaw_preprocessor-*.whl" | Select-Object -First 1).FullName

if (-not (Test-Path $zipPath)) {
    Write-Host "✗ ERROR: No existe $zipPath" -ForegroundColor Red
    Write-Host "Ejecuta primero la compilación" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $projectWheelPath)) {
    Write-Host "✗ ERROR: No existe wheel del proyecto en build\" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "✗ ERROR: No existe $scriptPath" -ForegroundColor Red
    exit 1
}

$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Host "✓ ZIP encontrado: $([math]::Round($zipSize, 2)) MB" -ForegroundColor Green
$wheelSize = (Get-Item $projectWheelPath).Length / 1MB
Write-Host "✓ Wheel del proyecto encontrado: $([math]::Round($wheelSize, 2)) MB ($([System.IO.Path]::GetFileName($projectWheelPath)))" -ForegroundColor Green

# ============================================================================
# PASO 3: SUBIR A S3
# ============================================================================
Write-Host "[3/7] Subiendo archivos a S3..." -ForegroundColor Yellow

$s3ZipPath = "s3://$Bucket/glue-libs/glue-dependencies.gluewheels.zip"
$wheelName = [System.IO.Path]::GetFileName($projectWheelPath)
$s3WheelPath = "s3://$Bucket/glue-libs/$wheelName"
$s3ScriptPath = "s3://$Bucket/glue-scripts/test-deps.py"

Write-Host "  → Subiendo ZIP of wheels..."
aws s3 cp $zipPath $s3ZipPath --profile $Profile --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Fallo al subir ZIP" -ForegroundColor Red
    exit 1
}

Write-Host "  → Subiendo wheel del proyecto..."
aws s3 cp $projectWheelPath $s3WheelPath --profile $Profile --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Fallo al subir wheel del proyecto" -ForegroundColor Red
    exit 1
}

Write-Host "  → Subiendo script..."
aws s3 cp $scriptPath $s3ScriptPath --profile $Profile --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Fallo al subir script" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Archivos en S3" -ForegroundColor Green

# ============================================================================
# PASO 4: VERIFICAR/CREAR ROL IAM
# ============================================================================
Write-Host "[4/7] Verificando rol IAM para Glue..." -ForegroundColor Yellow

$roleName = "GlueTestDepsRole"
$roleArn = "arn:aws:iam::${accountId}:role/$roleName"

$roleExists = aws iam get-role --role-name $roleName --profile $Profile 2>$null
if (-not $roleExists) {
    Write-Host "  → Creando rol $roleName..."
    
    $trustPolicy = @{
        Version = "2012-10-17"
        Statement = @(
            @{
                Effect = "Allow"
                Principal = @{ Service = "glue.amazonaws.com" }
                Action = "sts:AssumeRole"
            }
        )
    } | ConvertTo-Json -Depth 10 -Compress
    
    aws iam create-role --role-name $roleName --assume-role-policy-document $trustPolicy --profile $Profile
    aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole" --profile $Profile
    aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" --profile $Profile
    
    Write-Host "  → Esperando 10s para propagación IAM..."
    Start-Sleep -Seconds 10
}

Write-Host "✓ Rol IAM: $roleArn" -ForegroundColor Green

# ============================================================================
# PASO 5: CREAR Y EJECUTAR GLUE JOB
# ============================================================================
Write-Host "[5/7] Creando Glue Job..." -ForegroundColor Yellow

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jobName = "test-deps-$timestamp"

$jobCommand = @{
    Name = "glueetl"
    ScriptLocation = $s3ScriptPath
    PythonVersion = "3"
} | ConvertTo-Json -Compress

$defaultArgs = @{
    "--additional-python-modules" = "$s3ZipPath,$s3WheelPath"
    "--python-modules-installer-option" = "--no-index"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics" = "true"
    "--job-language" = "python"
} | ConvertTo-Json -Compress

aws glue create-job `
    --name $jobName `
    --role $roleArn `
    --command $jobCommand `
    --default-arguments $defaultArgs `
    --glue-version "5.0" `
    --max-capacity 2 `
    --timeout 10 `
    --profile $Profile `
    --region $Region

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Fallo al crear job" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Job creado: $jobName" -ForegroundColor Green

Write-Host "  → Iniciando ejecución..."
$runResult = aws glue start-job-run --job-name $jobName --profile $Profile --region $Region --output json | ConvertFrom-Json
$runId = $runResult.JobRunId

Write-Host "✓ Job iniciado con RunId: $runId" -ForegroundColor Green

# ============================================================================
# PASO 6: ESPERAR Y MONITOREAR
# ============================================================================
Write-Host "[6/7] Esperando 200 segundos (job en ejecución)..." -ForegroundColor Yellow
Write-Host ""

$elapsed = 0
$checkInterval = 20

while ($elapsed -lt 200) {
    Start-Sleep -Seconds $checkInterval
    $elapsed += $checkInterval
    
    $status = aws glue get-job-run --job-name $jobName --run-id $runId --profile $Profile --region $Region --output json | ConvertFrom-Json
    $state = $status.JobRun.JobRunState
    
    $progress = [math]::Round(($elapsed / 200) * 100)
    Write-Host "  [$elapsed/200s] Estado: $state ($progress%)" -ForegroundColor Cyan
    
    if ($state -in @("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR")) {
        Write-Host "  Job terminó anticipadamente" -ForegroundColor Yellow
        break
    }
}

Write-Host ""

# ============================================================================
# PASO 7: VERIFICAR RESULTADO
# ============================================================================
Write-Host "[7/7] Verificando resultado..." -ForegroundColor Yellow

$finalStatus = aws glue get-job-run --job-name $jobName --run-id $runId --profile $Profile --region $Region --output json | ConvertFrom-Json
$finalState = $finalStatus.JobRun.JobRunState

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  RESULTADO FINAL" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($finalState -eq "SUCCEEDED") {
    Write-Host "✓ ¡JOB EXITOSO!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Las dependencias funcionan correctamente en AWS Glue 5.0" -ForegroundColor Green
    $exitCode = 0
} else {
    Write-Host "✗ JOB FALLÓ: $finalState" -ForegroundColor Red
    Write-Host ""
    
    if ($finalStatus.JobRun.ErrorMessage) {
        Write-Host "Error: $($finalStatus.JobRun.ErrorMessage)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "Intentando obtener logs de CloudWatch..." -ForegroundColor Yellow
    
    $logGroup = "/aws-glue/jobs/output"
    $logStream = "$jobName/$runId"
    
    try {
        aws logs get-log-events `
            --log-group-name $logGroup `
            --log-stream-name $logStream `
            --limit 50 `
            --profile $Profile `
            --region $Region `
            --output text `
            --query 'events[*].message'
    } catch {
        Write-Host "No se pudieron obtener logs (normal si el job falló muy temprano)" -ForegroundColor Yellow
    }
    
    $exitCode = 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  LIMPIEZA" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

$cleanup = Read-Host "¿Eliminar job de prueba? (S/n)"
if ($cleanup -ne "n") {
    Write-Host "  → Eliminando job $jobName..."
    aws glue delete-job --job-name $jobName --profile $Profile --region $Region
    Write-Host "✓ Job eliminado" -ForegroundColor Green
} else {
    Write-Host "Job conservado para inspección: $jobName" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  URLs ÚTILES" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Console Glue: https://console.aws.amazon.com/glue/home?region=$Region#/v2/etl-configuration/jobs/$jobName"
Write-Host "CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home?region=$Region#logsV2:log-groups/log-group/`$252Faws-glue`$252Fjobs`$252Foutput"
Write-Host ""

exit $exitCode
