# 🔧 PLAN DE ACCIÓN - Sonnet 4.5

## ✅ ESTADO ACTUAL (Verificado por Opus)

**Tests pasados en Docker Glue 4.0:**
- ✅ xarray 2025.6.1 - import + dataset creation
- ✅ cfgrib 0.9.15.1 - import + messages module
- ✅ eccodes 2.42.0 - import + API version call
- ✅ numpy 1.26.4 - import

**Imagen Docker construida:** `glue-builder:latest` (9.81GB, incluye eccodes compilado)

## HALLAZGOS CLAVE

1. **Glue 5.0 image NO existe** en DockerHub/ECR público
2. **Glue 4.0** (`amazon/aws-glue-libs:glue_libs_4.0.0_image_01`) funciona y es Python 3.10
3. **eccodes requiere compilación** desde fuente con:
   - CMake >= 3.18 (instalado manualmente)
   - Flag `-DENABLE_AEC=OFF`
4. **xarray/cfgrib/eccodes** se instalan con pip después de compilar libeccodes

## TAREAS PARA SONNET 4.5

### T1: Build del ZIP de dependencias ⏳
```powershell
# El Dockerfile ya está listo, solo falta el script de empaquetado
docker run --rm -v "${PWD}:/workspace" -v "${PWD}/build:/build" glue-builder:latest "
pip3 install --target /build/python xarray cfgrib eccodes &&
cd /build/python &&
find . -name __pycache__ -exec rm -rf {} + 2>/dev/null;
find . -name '*.dist-info' -exec rm -rf {} + 2>/dev/null;
zip -r /build/glue-dependencies.zip .
"
```

### T2: Verificar ZIP funciona
```powershell
docker run --rm -v "${PWD}/build:/build" glue-builder:latest "
export PYTHONPATH=/build/python
python3 -c 'import xarray; import cfgrib; import eccodes; print(\"ZIP OK\")'
"
```

### T3: Test E2E en AWS (si hay credenciales)
Ver script `test_e2e_glue.ps1` abajo.

## DOCKERFILE FINAL (Verificado)

```dockerfile
FROM amazon/aws-glue-libs:glue_libs_4.0.0_image_01
USER root

# CMake moderno para eccodes
RUN curl -sL https://github.com/Kitware/CMake/releases/download/v3.28.0/cmake-3.28.0-linux-x86_64.tar.gz | tar xz -C /opt && \
    ln -sf /opt/cmake-3.28.0-linux-x86_64/bin/cmake /usr/local/bin/cmake

# eccodes desde fuente
RUN cd /tmp && \
    curl -sL https://confluence.ecmwf.int/download/attachments/45757960/eccodes-2.42.0-Source.tar.gz -o eccodes.tar.gz && \
    tar xzf eccodes.tar.gz && cd eccodes-2.42.0-Source && mkdir build && cd build && \
    /usr/local/bin/cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DENABLE_PYTHON=OFF -DENABLE_FORTRAN=OFF -DENABLE_AEC=OFF && \
    make -j$(nproc) && make install && ldconfig && rm -rf /tmp/eccodes*

ENV ECCODES_DIR=/usr/local LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
WORKDIR /build
ENTRYPOINT ["/bin/bash", "-c"]
```

## SCRIPT E2E AWS

```powershell
# test_e2e_glue.ps1
param([string]$Bucket, [string]$Region = "us-east-1")

# 1. Verificar credenciales
$id = aws sts get-caller-identity --output json | ConvertFrom-Json
if (-not $id) { throw "No AWS credentials" }

# 2. Subir artifacts
aws s3 cp build/glue-dependencies.zip "s3://$Bucket/libs/"
aws s3 cp examples/glue-job-example.py "s3://$Bucket/scripts/"

# 3. Crear job
$jobName = "test-deps-$(Get-Date -Format 'yyyyMMddHHmmss')"
aws glue create-job --name $jobName --role "arn:aws:iam::$($id.Account):role/GlueRole" `
    --command "Name=glueetl,ScriptLocation=s3://$Bucket/scripts/glue-job-example.py,PythonVersion=3" `
    --default-arguments "--extra-py-files=s3://$Bucket/libs/glue-dependencies.zip" `
    --glue-version "4.0" --number-of-workers 2 --worker-type "G.1X"

# 4. Ejecutar
$run = aws glue start-job-run --job-name $jobName --output json | ConvertFrom-Json
Write-Host "Job Run: $($run.JobRunId)"

# 5. Esperar 200s
Start-Sleep -Seconds 200

# 6. Verificar
$status = aws glue get-job-run --job-name $jobName --run-id $run.JobRunId --output json | ConvertFrom-Json
if ($status.JobRun.JobRunState -eq "SUCCEEDED") {
    Write-Host "✓ PASSED" -ForegroundColor Green
} else {
    Write-Host "✗ FAILED: $($status.JobRun.ErrorMessage)" -ForegroundColor Red
    aws logs tail "/aws-glue/jobs/output" --since 10m
}

# 7. Cleanup
aws glue delete-job --job-name $jobName
```

## NOTAS IMPORTANTES

1. **pyarrow/pandas/numpy** ya vienen en Glue baseline - NO incluir en ZIP
2. **Solo empaquetar:** xarray, cfgrib, eccodes + sus deps ligeras
3. **libeccodes.so** está en `/usr/local/lib` del container - el ZIP de Python necesita encontrarlo en runtime

## SI EL JOB FALLA CON "libeccodes.so not found"

Opción A: Incluir .so en ZIP
```bash
cp /usr/local/lib/libeccodes.so* /build/python/
```

Opción B: Usar `--additional-python-modules` en vez de `--extra-py-files`
```
--additional-python-modules xarray,cfgrib,eccodes
```
(Glue instalará desde PyPI, pero puede fallar sin libeccodes)

Opción C: Crear layer/wheel custom con libeccodes embebido

---
*Verificado por Opus | 2026-04-04*
