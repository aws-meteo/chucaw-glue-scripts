# Chucaw Glue 5.0 — Guía de Despliegue por Tareas

> **Cómo usar este documento:**  
> Cada sección `## TAREA N` es un prompt autocontenido diseñado para dárselo a un modelo ligero.  
> Cada tarea tiene: **contexto**, **qué verificar antes**, **comando exacto**, y **señal de éxito**.  
> Sigue el orden numérico. No saltes tareas.

---

## TAREA 1 — Verificar prerrequisitos

**Contexto:** Antes de cualquier paso necesitamos confirmar que Docker y AWS CLI están listos.

**Ejecuta esto en PowerShell (dentro de `C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts`):**

```powershell
# 1. Verificar Docker
docker images | Select-String "glue5-builder"

# 2. Verificar AWS CLI autenticado
aws sts get-caller-identity --profile sbnai-admin

# 3. Verificar que los artefactos del build ya existen
Get-Item .\build\glue-dependencies.gluewheels.zip | Select-Object Name, @{N="SizeMB";E={[math]::Round($_.Length/1MB,2)}}
Get-Item .\build\chucaw_preprocessor-0.1.0-py3-none-any.whl | Select-Object Name, Length
```

**✅ Señal de éxito:**
- `docker images` muestra `glue5-builder` con tag `latest`
- `aws sts` devuelve el AccountId sin error
- El ZIP pesa ~72 MB y el `.whl` existe

> **⚠️ Si el ZIP no existe:** El build ya fue ejecutado y está en `build/glue-dependencies.gluewheels.zip` (75 MB).  
> Si fue borrado, ve a **TAREA 0** primero.

---

## TAREA 0 (Solo si el ZIP fue borrado) — Reconstruir artefactos con Docker

**Contexto:** El build compila wheelhouses Linux desde el contenedor oficial de AWS Glue 5.0.  
El ENTRYPOINT del Dockerfile es `/bin/bash -c`, por eso necesitamos `--entrypoint /bin/bash` explícito.  
El script usa `/build` mapeado a `./build/` local.

**Ejecuta en PowerShell:**

```powershell
# Asegúrate de estar en la raíz del proyecto
cd C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts

# Construir la imagen si no existe (solo primera vez, ~10 min)
docker build -f Dockerfile.glue-builder -t glue5-builder:latest .

# Ejecutar el build de las dependencias
docker run --rm `
  -v "${PWD}:/workspace" `
  -v "${PWD}/build:/build" `
  --entrypoint /bin/bash `
  glue5-builder:latest `
  /workspace/build_glue_libs.sh
```

> **❗ El comando original `bash /workspace/build_glue_libs.sh` sin `--entrypoint` no muestra output  
> porque el ENTRYPOINT del Dockerfile envuelve el argumento en `/bin/bash -c "bash script.sh"`, lo que  
> falla silenciosamente. Siempre usar `--entrypoint /bin/bash`.**

**✅ Señal de éxito — el terminal imprime:**
```
[OK] Project wheel: chucaw_preprocessor-0.1.0-py3-none-any.whl
[OK] Downloaded 16 wheels
[OK] BUILD COMPLETE — Glue 5.0 artifacts ready
```

Y en `./build/` aparecen:
- `glue-dependencies.gluewheels.zip` (~72-76 MB)
- `chucaw_preprocessor-0.1.0-py3-none-any.whl` (~8 KB)
- `manifest.txt`

---

## TAREA 2 — Subir artefactos a S3

**Contexto:** Debes subir exactamente 3 archivos a S3 antes de configurar el Glue Job.  
Los buckets del proyecto son:
- **Artefactos/Scripts:** Un bucket de tu elección (ej. el mismo que uses para Glue scripts)
- **Bronze (origen de GRIB):** `chucaw-data-bronze-raw-725644097028-us-east-1-an`
- **Platinum (destino Parquet):** `chucaw-data-platinum-processed-725644097028-us-east-1-an`

**Ejecuta en PowerShell (reemplaza `TU-BUCKET` con tu bucket real):**

```powershell
cd C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts

$BUCKET = "TU-BUCKET-DE-ARTEFACTOS"   # <-- REEMPLAZAR
$PROFILE = "sbnai-admin"
$PREFIX = "glue/artifacts"

# Subir ZIP de dependencias (~72 MB, puede tardar 1-2 min)
aws s3 cp .\build\glue-dependencies.gluewheels.zip `
  "s3://$BUCKET/$PREFIX/glue-dependencies.gluewheels.zip" `
  --profile $PROFILE

# Subir wheel del proyecto
aws s3 cp .\build\chucaw_preprocessor-0.1.0-py3-none-any.whl `
  "s3://$BUCKET/$PREFIX/chucaw_preprocessor-0.1.0-py3-none-any.whl" `
  --profile $PROFILE

# Subir script del Job
aws s3 cp .\scripts\glue_jobs\bronze_to_platinum_parquet.py `
  "s3://$BUCKET/glue/scripts/bronze_to_platinum_parquet.py" `
  --profile $PROFILE
```

**✅ Señal de éxito:** Cada comando imprime `upload: .\build\... to s3://...` sin errores.

**Verificar que los 3 archivos existen en S3:**

```powershell
aws s3 ls "s3://$BUCKET/$PREFIX/" --profile $PROFILE
aws s3 ls "s3://$BUCKET/glue/scripts/" --profile $PROFILE
```

---

## TAREA 3 — Crear el Glue Job en AWS Console

**Contexto:** El Job usa Python Shell (no Spark ETL) con Glue 5.0.  
La clave más crítica es `--python-modules-installer-option: --no-index` — sin esto Glue intenta  
descargar paquetes desde internet y falla porque los workers no tienen salida a PyPI.

**Pasos en la Console de AWS Glue:**

1. Ir a: **AWS Glue → ETL Jobs → Create job**
2. Seleccionar: **"Script editor"** → tipo **"Python Shell"**
3. **Configuración del Job:**

| Campo | Valor exacto |
|---|---|
| **Job name** | `chucaw-grib-to-parquet` |
| **IAM Role** | Tu rol con permisos S3 + Glue |
| **Type** | `Python Shell` |
| **Glue version** | `Glue 5.0 - Supports Python 3.11` |
| **Script filename** | `bronze_to_platinum_parquet.py` |
| **Script path (S3)** | `s3://TU-BUCKET/glue/scripts/bronze_to_platinum_parquet.py` |
| **Max capacity (DPUs)** | `0.0625` (1/16 DPU — mínimo para Python Shell) |

4. En **"Advanced properties" → "Job parameters"**, añadir estos exactamente:

| Key | Value |
|---|---|
| `--additional-python-modules` | `s3://TU-BUCKET/glue/artifacts/glue-dependencies.gluewheels.zip,s3://TU-BUCKET/glue/artifacts/chucaw_preprocessor-0.1.0-py3-none-any.whl` |
| `--python-modules-installer-option` | `--no-index` |

> **⚠️ CRÍTICO:** Los dos valores en `--additional-python-modules` van **separados por coma, sin espacio**.  
> El orden importa: primero el ZIP de dependencias, después el `.whl` del proyecto.

5. Guardar el Job.

---

## TAREA 4 — Ejecutar el Job con un GRIB específico (Test)

**Contexto:** El script `bronze_to_platinum_parquet.py` acepta parámetros de ejecución opcionales.  
Si no se pasan, hace autodescubrimiento del GRIB más reciente en el bucket Bronze.  
Para un test controlado, se pasa `--BRONZE_KEY` con la ruta exacta al `.grib2` en S3.

**Antes de ejecutar:** Sube un GRIB de prueba al bucket Bronze:

```powershell
aws s3 cp .\scripts\glue_jobs\test_grib\20260403180000-0h-scda-fc.grib2 `
  "s3://chucaw-data-bronze-raw-725644097028-us-east-1-an/test/20260403180000-0h-scda-fc.grib2" `
  --profile sbnai-admin
```

**Ejecutar el Job desde AWS CLI:**

```powershell
aws glue start-job-run `
  --job-name "chucaw-grib-to-parquet" `
  --arguments '{
    "--BRONZE_BUCKET": "chucaw-data-bronze-raw-725644097028-us-east-1-an",
    "--BRONZE_KEY": "test/20260403180000-0h-scda-fc.grib2",
    "--PLATINUM_BUCKET": "chucaw-data-platinum-processed-725644097028-us-east-1-an",
    "--PLATINUM_PREFIX": "ecmwf/parquet",
    "--DATE": "20260403",
    "--RUN": "18z"
  }' `
  --profile sbnai-admin
```

Guarda el `JobRunId` que retorna el comando.

---

## TAREA 5 — Monitorear el Job y verificar resultado

**Contexto:** El Job puede tardar 3-8 minutos. Primero pasa por estado `STARTING` → `RUNNING` → `SUCCEEDED`.

**Verificar estado (reemplaza `<JOB_RUN_ID>` con el ID del paso anterior):**

```powershell
aws glue get-job-run `
  --job-name "chucaw-grib-to-parquet" `
  --run-id "<JOB_RUN_ID>" `
  --profile sbnai-admin `
  | ConvertFrom-Json `
  | Select-Object -ExpandProperty JobRun `
  | Select-Object JobRunState, StartedOn, CompletedOn, ErrorMessage
```

**Verificar que los Parquet fueron escritos en Platinum:**

```powershell
aws s3 ls "s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/" `
  --recursive `
  --profile sbnai-admin
```

**✅ Señal de éxito:**
- Estado: `SUCCEEDED`
- Aparecen archivos como:
  - `ecmwf/parquet/year=2026/month=04/day=03/run=18z/dataset=surface/part-000.parquet`
  - `ecmwf/parquet/year=2026/month=04/day=03/run=18z/dataset=upper/part-000.parquet`

---

## TAREA 6 — Diagnosticar si el Job falla

**Contexto:** Los fallos más comunes y sus causas:

### Fallo A: `ModuleNotFoundError: No module named 'cfgrib'`
**Causa:** `--python-modules-installer-option --no-index` no fue configurado, o hubo un typo en `--additional-python-modules`.  
**Fix:** Revisar los Job Parameters en la console. Las rutas S3 deben existir y la coma debe ser sin espacios.

### Fallo B: Job termina sin error pero sin output (estado `FAILED`)
**Causa:** El GRIB en S3 no existía o la ruta `--BRONZE_KEY` era incorrecta.  
**Fix:** Verificar con `aws s3 ls s3://chucaw-data-bronze-raw.../test/` que el archivo existe.

### Fallo C: `Could not import eccodes`
**Causa:** El wheel de `eccodeslib` requiere las `.so` nativas compiladas para Linux — si el ZIP fue generado en Windows (sin Docker) no funcionará.  
**Fix:** Regenerar el ZIP ejecutando **TAREA 0** (con Docker, no en PowerShell directo).

### Ver logs completos del Job:
```powershell
aws glue get-job-run `
  --job-name "chucaw-grib-to-parquet" `
  --run-id "<JOB_RUN_ID>" `
  --profile sbnai-admin
```
Los logs de CloudWatch estarán en `/aws-glue/jobs/output` si se habilitó `--enable-continuous-cloudwatch-log`.

---

## Referencia rápida — Archivos clave del proyecto

| Archivo | Propósito |
|---|---|
| `build_glue_libs.sh` | Script que corre DENTRO de Docker para compilar y empaquetar las dependencias |
| `Dockerfile.glue-builder` | Imagen basada en `public.ecr.aws/glue/aws-glue-libs:5`, compila `eccodes` desde fuente |
| `requirements-glue.txt` | Dependencias exclusivas de Glue (xarray, cfgrib, eccodes, eccodeslib) |
| `lista_de_glue50.txt` | Paquetes que Glue 5.0 ya provee — se filtran del ZIP para evitar conflictos |
| `scripts/glue_jobs/bronze_to_platinum_parquet.py` | Entrypoint del Glue Job — descarga GRIB de S3, convierte a Parquet chunked, sube a Platinum |
| `src/chucaw_preprocessor/ecmwf.py` | Lógica de conversión: `serialize_parquet_chunked` (PyArrow Writer, sin OOM) |
| `build/glue-dependencies.gluewheels.zip` | ✅ **Ya generado** — 75 MB, 16 wheels Linux cp311 |
| `build/chucaw_preprocessor-0.1.0-py3-none-any.whl` | ✅ **Ya generado** — el código del proyecto empaquetado |
