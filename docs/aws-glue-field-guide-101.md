# AWS Glue Field Guide 101 (Bronze -> Platinum Parquet)

Guia practica para desplegar y operar el job de Glue de este repo.
Fecha de referencia: **2026-03-30**.

## 1. Objetivo

Mover datos GRIB desde Bronze a Platinum como Parquet, usando Glue 5.0 (`glueetl`, Python 3.11):

- Bronze bucket: `chucaw-data-bronze-raw-725644097028-us-east-1-an`
- Platinum bucket: `chucaw-data-platinum-processed-725644097028-us-east-1-an`
- Script Glue: `scripts/glue_jobs/bronze_to_platinum_parquet.py`

El job genera salida particionada:

- `ecmwf/parquet/year=YYYY/month=MM/day=DD/run=RRz/dataset=surface/part-000.parquet`
- `ecmwf/parquet/year=YYYY/month=MM/day=DD/run=RRz/dataset=upper/part-000.parquet`

## 2. Archivos listos en este repo

Definiciones JSON listas para CLI:

- Crear job: `glue/job-definitions/create-job-bronze-to-platinum.json`
- Actualizar job: `glue/job-definitions/update-job-bronze-to-platinum.json`
- Ejecutar por key exacta: `glue/job-runs/start-job-run-by-key.json`
- Ejecutar por fecha/run: `glue/job-runs/start-job-run-by-date-run.json`

## 3. Prerrequisitos AWS

1. AWS CLI configurado con credenciales del account `725644097028`.
2. Region: `us-east-1`.
3. IAM role de Glue con permisos minimos:
- `s3:GetObject`, `s3:ListBucket` sobre Bronze.
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` sobre Platinum (scripts, temp, outputs).
- `logs:*` basicos para CloudWatch Logs.
4. Bucket paths sugeridos:
- Assets Glue:
- `s3://chucaw-glue-assets-725644097028-us-east-1-an/glue/scripts/`
- `s3://chucaw-glue-assets-725644097028-us-east-1-an/glue/artifacts/`
- TempDir del job:
- `s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/glue/temp/`

## 4. Construir artefactos Python (wheel + dependencies)

Desde la raiz del repo:

```powershell
./scripts/build_glue_artifacts.ps1
```

Se generan en `dist/`:

- `chucaw_preprocessor-0.1.0-py3-none-any.whl`
- `glue-dependencies.gluewheels.zip`
- `glue-dependencies.contents.txt` (manifiesto de incluidas/excluidas)
- `glue-wheelhouse/` con wheels Linux CPython 3.11 usadas para construir el zip

Smoke test recomendado (imports + baseline Glue):

```powershell
& "C:\ProgramData\miniconda3\Scripts\conda.exe" run -p .venv python scripts/smoke/glue_runtime_smoke.py --strict --output-json dist/glue-runtime-smoke.json
```

## 5. Subir script y artefactos a S3

```powershell
aws s3 cp scripts/glue_jobs/bronze_to_platinum_parquet.py s3://chucaw-glue-assets-725644097028-us-east-1-an/glue/scripts/bronze_to_platinum_parquet.py --region us-east-1

aws s3 cp dist/chucaw_preprocessor-0.1.0-py3-none-any.whl s3://chucaw-glue-assets-725644097028-us-east-1-an/glue/artifacts/ --region us-east-1

aws s3 cp dist/glue-dependencies.gluewheels.zip s3://chucaw-glue-assets-725644097028-us-east-1-an/glue/artifacts/ --region us-east-1
```

## 6. Crear o actualizar el Glue Job

Crear (primera vez):

```powershell
aws glue create-job --cli-input-json file://glue/job-definitions/create-job-bronze-to-platinum.json --region us-east-1
```

Actualizar (siguientes cambios):

```powershell
aws glue update-job --cli-input-json file://glue/job-definitions/update-job-bronze-to-platinum.json --region us-east-1
```

## 7. Ejecutar Job

### Opcion A: por key exacta (recomendado en produccion)

Editar `glue/job-runs/start-job-run-by-key.json` con tu `--BRONZE_KEY` y ejecutar:

```powershell
aws glue start-job-run --cli-input-json file://glue/job-runs/start-job-run-by-key.json --region us-east-1
```

### Opcion B: por fecha y run

Editar `glue/job-runs/start-job-run-by-date-run.json` y ejecutar:

```powershell
aws glue start-job-run --cli-input-json file://glue/job-runs/start-job-run-by-date-run.json --region us-east-1
```

### Opcion C: sin key ni fecha

Si no mandas `--BRONZE_KEY` ni `--DATE`, el script intenta tomar el ultimo `.grib2` del prefijo Bronze.

## 8. Monitoreo operativo

1. Ver estado de ejecucion:

```powershell
aws glue get-job-runs --job-name chucaw-bronze-to-platinum-parquet --max-results 5 --region us-east-1
```

2. Verificar outputs en Platinum:

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/ --recursive --region us-east-1
```

## 9. DynamicFrames y esta arquitectura

- Este job usa runtime Spark (`Command.Name = glueetl`) para Glue 5.0 / Python 3.11.
- La logica del script sigue siendo Python puro (`xarray/cfgrib/pandas/pyarrow`) y no usa `DynamicFrame`.
- `DynamicFrame` sigue siendo una opcion valida si despues migran a transformaciones Spark mas pesadas.

## 10. Troubleshooting rapido

1. Error de imports:
- Confirmar que el wheel del proyecto y `glue-dependencies.gluewheels.zip` existen en S3.
- Confirmar `--additional-python-modules` y `--python-modules-installer-option --no-index`.
- Confirmar que el zip fue construido para CPython 3.11 Linux (manifiesto en `glue-dependencies.contents.txt`).

2. Error de permisos S3:
- Revisar IAM role usado por Glue en `Role`.
- Verificar permisos en Bronze (read) y Platinum (write).

3. Sin archivos `.grib2`:
- Verificar `--BRONZE_KEY` o `--BRONZE_PREFIX`.
- Validar que el prefijo realmente contenga archivos en Bronze.

## 11. Referencias oficiales AWS

- Glue Python libraries (principal):
  https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-python-libraries.html
- Seccion Python modules provided:
  https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-python-libraries.html?icmpid=docs_console_unmapped#glue-modules-provided
- CreateJob API:
  https://docs.aws.amazon.com/glue/latest/webapi/API_CreateJob.html
- UpdateJob API:
  https://docs.aws.amazon.com/glue/latest/webapi/API_UpdateJob.html
- StartJobRun API:
  https://docs.aws.amazon.com/glue/latest/webapi/API_StartJobRun.html
