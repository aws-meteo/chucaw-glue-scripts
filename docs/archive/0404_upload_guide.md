# 🚀 Guía de Deployment - AWS Glue Dependencies

**Fecha:** 2026-04-04  
**Objetivo:** Compilar, empaquetar y desplegar dependencias Python (xarray, cfgrib, eccodes) para AWS Glue 4.0  
**Tiempo estimado:** 15-20 minutos

---

## 📋 Tabla de Contenidos

1. [Pre-requisitos](#pre-requisitos)
2. [Paso 1: Construir Docker Builder](#paso-1-construir-docker-builder)
3. [Paso 2: Compilar Dependencias](#paso-2-compilar-dependencias)
4. [Paso 3: Verificar ZIP Localmente](#paso-3-verificar-zip-localmente)
5. [Paso 4: Subir a S3](#paso-4-subir-a-s3)
6. [Paso 5: Crear Glue Job](#paso-5-crear-glue-job)
7. [Paso 6: Ejecutar y Monitorear](#paso-6-ejecutar-y-monitorear)
8. [Troubleshooting](#troubleshooting)

---

## Pre-requisitos

### Software necesario:
- ✅ Docker Desktop instalado y corriendo
- ✅ AWS CLI configurado (`aws --version`)
- ✅ Credenciales AWS activas (`aws sts get-caller-identity`)

### Verificar estado:

```powershell
# 1. Docker corriendo
docker ps

# 2. AWS CLI instalado
aws --version

# 3. Credenciales activas (si usa SSO, hacer login primero)
aws sso login --profile sbnai-admin
aws sts get-caller-identity --profile sbnai-admin
```

**✅ Checkpoint:** Debes ver tu Account ID y Arn.

---

## Paso 1: Construir Docker Builder

### 1.1 Verificar si ya existe la imagen

```powershell
docker images | Select-String "glue-builder"
```

**Si la imagen existe:** Puedes saltar al [Paso 2](#paso-2-compilar-dependencias).

### 1.2 Construir imagen Docker (solo primera vez)

```powershell
# Asegúrate de estar en el directorio del proyecto
cd C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts

# Construir imagen (tarda ~10-15 minutos)
docker build -f Dockerfile.glue-builder -t glue-builder:latest .
```

**⏳ Este paso tarda:** 10-15 minutos (compila eccodes desde fuente).

**Salida esperada:**
```
Step 1/10 : FROM amazon/aws-glue-libs:glue_libs_4.0.0_image_01
...
Step 10/10 : WORKDIR /build
Successfully built abc123def456
Successfully tagged glue-builder:latest
```

**✅ Checkpoint:** Verificar que la imagen existe:

```powershell
docker images glue-builder:latest
```

Debes ver algo como:
```
REPOSITORY      TAG       IMAGE ID       CREATED          SIZE
glue-builder    latest    abc123def456   2 minutes ago    9.81GB
```

---

## Paso 2: Compilar Dependencias

### 2.1 Limpiar builds anteriores (opcional)

```powershell
Remove-Item -Recurse -Force .\build -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path .\build -Force
```

### 2.2 Ejecutar compilación

```powershell
# Ejecutar script de build en el contenedor
docker run --rm `
    -v "${PWD}:/workspace" `
    -v "${PWD}/build:/build" `
    --entrypoint /bin/bash `
    glue-builder:latest `
    /workspace/build_glue_final.sh
```

**⏳ Este paso tarda:** 2-3 minutos.

**Salida esperada:**
```
[INFO] Cleaning...
[INFO] Installing Python packages...
Collecting xarray==2024.2.0
  Downloading xarray-2024.2.0-py3-none-any.whl (1.1 MB)
Collecting cfgrib==0.9.12.0
  Downloading cfgrib-0.9.12.0-py3-none-any.whl (47 kB)
Collecting eccodes==1.7.0
  Downloading eccodes-1.7.0.tar.gz (2.3 MB)
...
[SUCCESS] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[SUCCESS] Build completed!
[SUCCESS] Package: /build/glue-dependencies.zip (14M)
[SUCCESS] Contents:
[SUCCESS]   - xarray 2024.2.0 (compat pandas 1.5.1)
[SUCCESS]   - cfgrib 0.9.12.0
[SUCCESS]   - eccodes 1.7.0
[SUCCESS]   - _lib/libeccodes.so (embedded)
[SUCCESS]   - sitecustomize.py (auto-config)
[SUCCESS] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**✅ Checkpoint:** Verificar que el ZIP existe:

```powershell
Get-Item .\build\glue-dependencies.zip | Select-Object Name, Length, LastWriteTime
```

Debes ver:
```
Name                  Length LastWriteTime
----                  ------ -------------
glue-dependencies.zip 14180352 04-04-2026 0:34:14
```

---

## Paso 3: Verificar ZIP Localmente

### 3.1 Inspeccionar contenido del ZIP

```powershell
# Ver primeras 30 entradas
Add-Type -Assembly System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead("$PWD\build\glue-dependencies.zip")
$zip.Entries | Select-Object -First 30 FullName, Length
$zip.Dispose()
```

**✅ Verificar que contiene:**
- ✅ `xarray/` directory
- ✅ `cfgrib/` directory
- ✅ `eccodes/` directory
- ✅ `_lib/libeccodes.so` (archivo ~10MB)
- ✅ `sitecustomize.py`
- ❌ **NO debe contener:** `numpy/`, `pandas/`, `pyarrow/`

### 3.2 Verificar tamaño

```powershell
$size = (Get-Item .\build\glue-dependencies.zip).Length / 1MB
Write-Host "Tamaño del ZIP: $([math]::Round($size, 2)) MB"
```

**✅ Tamaño esperado:** ~13-14 MB

---

## Paso 4: Subir a S3

### 4.1 Crear bucket S3 (si no existe)

```powershell
# Opción A: Crear bucket nuevo
$bucketName = "glue-deps-test-$(Get-Random -Maximum 9999)"
aws s3 mb "s3://$bucketName" --profile sbnai-admin --region us-east-1
Write-Host "Bucket creado: $bucketName" -ForegroundColor Green

# Opción B: Usar bucket existente
$bucketName = "TU-BUCKET-EXISTENTE"
```

### 4.2 Subir ZIP a S3

```powershell
# Subir dependencias
aws s3 cp .\build\glue-dependencies.zip "s3://$bucketName/glue-libs/glue-dependencies.zip" `
    --profile sbnai-admin `
    --region us-east-1

# Subir script de prueba
aws s3 cp .\examples\glue-job-example.py "s3://$bucketName/glue-scripts/test-deps.py" `
    --profile sbnai-admin `
    --region us-east-1
```

**✅ Checkpoint:** Verificar archivos en S3:

```powershell
aws s3 ls "s3://$bucketName/glue-libs/" --profile sbnai-admin
aws s3 ls "s3://$bucketName/glue-scripts/" --profile sbnai-admin
```

Debes ver:
```
2026-04-04 00:35:00   14180352 glue-dependencies.zip
2026-04-04 00:35:05       3745 test-deps.py
```

---

## Paso 5: Crear Glue Job

### 5.1 Verificar/Crear rol IAM

```powershell
# Verificar si existe el rol
$roleExists = aws iam get-role --role-name GlueTestDepsRole --profile sbnai-admin 2>$null

if (-not $roleExists) {
    Write-Host "Creando rol IAM..." -ForegroundColor Yellow
    
    # Crear trust policy
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
    
    # Crear rol
    aws iam create-role `
        --role-name GlueTestDepsRole `
        --assume-role-policy-document $trustPolicy `
        --profile sbnai-admin
    
    # Adjuntar políticas
    aws iam attach-role-policy `
        --role-name GlueTestDepsRole `
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole" `
        --profile sbnai-admin
    
    aws iam attach-role-policy `
        --role-name GlueTestDepsRole `
        --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" `
        --profile sbnai-admin
    
    Write-Host "Esperando 10s para propagación IAM..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
} else {
    Write-Host "Rol IAM ya existe" -ForegroundColor Green
}
```

### 5.2 Obtener Account ID y ARN del rol

```powershell
$accountId = (aws sts get-caller-identity --profile sbnai-admin --query Account --output text)
$roleArn = "arn:aws:iam::${accountId}:role/GlueTestDepsRole"
Write-Host "Role ARN: $roleArn" -ForegroundColor Cyan
```

### 5.3 Crear Glue Job

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jobName = "test-deps-$timestamp"

# Crear JSON de configuración
$jobCommand = @{
    Name = "glueetl"
    ScriptLocation = "s3://$bucketName/glue-scripts/test-deps.py"
    PythonVersion = "3"
} | ConvertTo-Json -Compress

$defaultArgs = @{
    "--extra-py-files" = "s3://$bucketName/glue-libs/glue-dependencies.zip"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics" = "true"
} | ConvertTo-Json -Compress

# Crear job
aws glue create-job `
    --name $jobName `
    --role $roleArn `
    --command $jobCommand `
    --default-arguments $defaultArgs `
    --glue-version "4.0" `
    --max-capacity 2 `
    --timeout 10 `
    --profile sbnai-admin `
    --region us-east-1

Write-Host "✓ Job creado: $jobName" -ForegroundColor Green
```

**✅ Checkpoint:** Verificar job creado:

```powershell
aws glue get-job --job-name $jobName --profile sbnai-admin --region us-east-1 --query Job.Name
```

---

## Paso 6: Ejecutar y Monitorear

### 6.1 Ejecutar job

```powershell
Write-Host "Ejecutando job..." -ForegroundColor Yellow
$runResult = aws glue start-job-run `
    --job-name $jobName `
    --profile sbnai-admin `
    --region us-east-1 `
    --output json | ConvertFrom-Json

$runId = $runResult.JobRunId
Write-Host "✓ Job iniciado" -ForegroundColor Green
Write-Host "  Job Name: $jobName" -ForegroundColor Cyan
Write-Host "  Run ID: $runId" -ForegroundColor Cyan
```

### 6.2 Monitorear en tiempo real (loop de 200 segundos)

```powershell
Write-Host ""
Write-Host "Monitoreando ejecución (verificando cada 20s)..." -ForegroundColor Yellow
Write-Host ""

$elapsed = 0
$maxWait = 200

while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds 20
    $elapsed += 20
    
    $status = aws glue get-job-run `
        --job-name $jobName `
        --run-id $runId `
        --profile sbnai-admin `
        --region us-east-1 `
        --output json | ConvertFrom-Json
    
    $state = $status.JobRun.JobRunState
    $progress = [math]::Round(($elapsed / $maxWait) * 100)
    
    # Color según estado
    $color = switch ($state) {
        "SUCCEEDED" { "Green" }
        "RUNNING" { "Cyan" }
        "STARTING" { "Yellow" }
        "FAILED" { "Red" }
        "STOPPED" { "Red" }
        default { "White" }
    }
    
    Write-Host "  [$elapsed/${maxWait}s] Estado: $state ($progress%)" -ForegroundColor $color
    
    if ($state -in @("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR")) {
        Write-Host "  Job terminó en $elapsed segundos" -ForegroundColor Yellow
        break
    }
}
```

### 6.3 Verificar resultado final

```powershell
Write-Host ""
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  RESULTADO FINAL" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan

$finalStatus = aws glue get-job-run `
    --job-name $jobName `
    --run-id $runId `
    --profile sbnai-admin `
    --region us-east-1 `
    --output json | ConvertFrom-Json

$finalState = $finalStatus.JobRun.JobRunState

if ($finalState -eq "SUCCEEDED") {
    Write-Host ""
    Write-Host "✓✓✓ ¡ÉXITO COMPLETO!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Las dependencias funcionan correctamente en AWS Glue 4.0:" -ForegroundColor Green
    Write-Host "  ✓ xarray 2024.2.0" -ForegroundColor Green
    Write-Host "  ✓ cfgrib 0.9.12.0" -ForegroundColor Green
    Write-Host "  ✓ eccodes 1.7.0" -ForegroundColor Green
    Write-Host "  ✓ libeccodes.so embebido" -ForegroundColor Green
    Write-Host ""
    Write-Host "ZIP listo para producción:" -ForegroundColor Yellow
    Write-Host "  s3://$bucketName/glue-libs/glue-dependencies.zip" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "✗ Job falló: $finalState" -ForegroundColor Red
    
    if ($finalStatus.JobRun.ErrorMessage) {
        Write-Host ""
        Write-Host "Error:" -ForegroundColor Red
        Write-Host "  $($finalStatus.JobRun.ErrorMessage)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "Ver logs en CloudWatch:" -ForegroundColor Yellow
    Write-Host "  https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/`$252Faws-glue`$252Fjobs`$252Foutput" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
```

### 6.4 Obtener logs (si falló)

```powershell
# Solo si el job falló
if ($finalState -ne "SUCCEEDED") {
    Write-Host "Intentando obtener logs de CloudWatch..." -ForegroundColor Yellow
    
    $logGroup = "/aws-glue/jobs/output"
    $logStream = "$jobName/$runId"
    
    aws logs get-log-events `
        --log-group-name $logGroup `
        --log-stream-name $logStream `
        --limit 50 `
        --profile sbnai-admin `
        --region us-east-1 `
        --output text `
        --query 'events[*].message'
}
```

---

## Troubleshooting

### Error 1: "ImportError: No module named numpy"

**Causa:** El ZIP incluye numpy cuando Glue ya lo tiene.

**Solución:** Reconstruir con `build_glue_final.sh` que excluye numpy/pandas/pyarrow.

### Error 2: "AttributeError: module 'pandas.arrays' has no attribute 'NumpyExtensionArray'"

**Causa:** xarray muy nuevo para pandas 1.5.1 de Glue 4.0.

**Solución:** El script `build_glue_final.sh` usa xarray 2024.2.0 (compatible).

### Error 3: "RuntimeError: Cannot find the ecCodes library"

**Causa:** libeccodes.so no está en el ZIP.

**Solución:** El script `build_glue_final.sh` embebe libeccodes.so en `_lib/`.

### Error 4: Docker no puede pullear imagen base

**Causa:** `amazon/aws-glue-libs:glue_libs_4.0.0_image_01` no está cacheada.

**Solución:**
```powershell
docker pull amazon/aws-glue-libs:glue_libs_4.0.0_image_01
```

### Error 5: Permission denied al ejecutar .sh

**Causa:** Line endings CRLF en Windows.

**Solución:**
```powershell
$content = Get-Content "build_glue_final.sh" -Raw
$content = $content -replace "`r`n", "`n"
[System.IO.File]::WriteAllText("$PWD\build_glue_final.sh", $content, [System.Text.UTF8Encoding]::new($false))
```

---

## 📊 Resumen de Archivos Clave

| Archivo | Descripción |
|---------|-------------|
| `Dockerfile.glue-builder` | Define imagen Docker con eccodes compilado |
| `build_glue_final.sh` | Script que compila y empaqueta dependencias |
| `build/glue-dependencies.zip` | ZIP final (13-14 MB) |
| `examples/glue-job-example.py` | Script de prueba para Glue |
| `deploy-and-test-glue.ps1` | Script automatizado completo (opcional) |

---

## 🎯 Versiones Finales

**Compatibles con Glue 4.0 (Python 3.10, pandas 1.5.1):**

- ✅ xarray **2024.2.0** (no usar 2025.x)
- ✅ cfgrib **0.9.12.0**
- ✅ eccodes **1.7.0**
- ✅ libeccodes.so **2.42.0** (compilado desde fuente)

**Pre-instalado en Glue (NO incluir):**
- ❌ numpy 1.23.5
- ❌ pandas 1.5.1
- ❌ pyarrow 10.0.0

---

## 🔗 URLs Útiles

### AWS Console:
- **Glue Jobs:** https://console.aws.amazon.com/glue/home?region=us-east-1#etl:tab=jobs
- **S3 Buckets:** https://s3.console.aws.amazon.com/s3/buckets?region=us-east-1
- **CloudWatch Logs:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws-glue$252Fjobs$252Foutput

### Documentación:
- **AWS Glue 4.0:** https://docs.aws.amazon.com/glue/latest/dg/glue-version-support-policy.html
- **eccodes:** https://confluence.ecmwf.int/display/ECC/ecCodes+Home
- **xarray:** https://docs.xarray.dev/

---

## ✅ Checklist Final

Antes de considerar el proyecto completo:

- [ ] Docker image `glue-builder:latest` construida
- [ ] ZIP `glue-dependencies.zip` creado (~13-14 MB)
- [ ] ZIP contiene `_lib/libeccodes.so`
- [ ] ZIP NO contiene numpy/pandas/pyarrow
- [ ] Archivos subidos a S3
- [ ] Glue job creado
- [ ] Glue job ejecutado exitosamente (SUCCEEDED)
- [ ] CloudWatch logs verificados (sin errores de import)

---

**Autor:** GitHub Copilot (Claude Sonnet 4.5)  
**Fecha:** 2026-04-04  
**Versión:** 1.0
