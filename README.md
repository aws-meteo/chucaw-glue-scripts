# chucaw-glue-scripts

Procesamiento de GRIB ECMWF para Lakehouse con AWS Glue 5.0 (Python 3.11).

Flujo de datos: **Bronze (GRIB2) → Platinum (Parquet) → tensores de modelo**
(Pangu-Weather y FourCastNet). La lógica común de lectura/limpieza/conversión vive en la
librería instalable `chucaw_preprocessor` (`src/chucaw_preprocessor/`), y cada job de Glue
es un guion delgado que la usa.

## Estructura del repositorio

```
scripts/glue_jobs/     # guiones de los jobs de Glue (ver índice abajo)  →  scripts/glue_jobs/README.md
scripts/glue_jobs/local/  # variantes locales para desarrollo (no se despliegan)
scripts/deploy/        # deploy_glue_job.sh: sube el guion a S3 y crea/actualiza el job
glue/jobs/<nombre>/    # config de despliegue por job (job.json + run.*.json)  →  glue/README.md
src/chucaw_preprocessor/  # librería común (ecmwf, fourcastnet, glue_args, job_common)
.github/workflows/     # build-glue-wheels.yml (artefactos) y deploy-glue-jobs.yml (deploy)
docs/                  # guía de campo, docs Sphinx, reportes, archivo histórico
```

## Índice de jobs de Glue (en orden de pipeline)

Todos los jobs son **Python puro** (boto3 + `xarray`/`cfgrib`/`pandas`/`pyarrow`) sobre
Glue 5.0 como `glueetl`. Detalle de argumentos en
[`scripts/glue_jobs/README.md`](scripts/glue_jobs/README.md).

| # | Job de Glue | Guion | Entrada → Salida |
|---|---|---|---|
| 1 | `bronze_to_platinum_as_parquet` | [`scripts/glue_jobs/bronze_to_platinum_parquet.py`](scripts/glue_jobs/bronze_to_platinum_parquet.py) | GRIB2 → Parquet particionado (Platinum) |
| 2 | `bronze_to_pangu` | [`scripts/glue_jobs/bronze_to_pangu.py`](scripts/glue_jobs/bronze_to_pangu.py) | GRIB2 → Pangu `input_surface.npy` + `input_upper.npy` |
| 2b | `cfsv2_monthly_bronze_to_silver` | [`scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py`](scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py) | GRIB2 → Parquet de CFSv2 long-frame (Silver) |
| 3 | `platinum_parquet_to_fourcastnet` | [`scripts/glue_jobs/platinum_parquet_to_fourcastnet.py`](scripts/glue_jobs/platinum_parquet_to_fourcastnet.py) | Parquet → tensor FourCastNet `.npy` + reportes |
| — | (auditoría, bajo demanda) | [`scripts/glue_jobs/audit_platinum_partition.py`](scripts/glue_jobs/audit_platinum_partition.py) | Parquet → reportes JSON/CSV (solo lectura) |

El nombre canónico de cada job (columna «Job de Glue») coincide con su carpeta bajo
`glue/jobs/` y con el campo `Name` de su `job.json`.

## Despliegue con GitHub Actions

El workflow [`.github/workflows/deploy-glue-jobs.yml`](.github/workflows/deploy-glue-jobs.yml)
sube el guion del job a S3 y **crea o actualiza** el job de Glue. Autenticación por
**GitHub OIDC** (sin llaves de larga duración).

**Ejecutar:** pestaña *Actions* → *Deploy Glue Jobs* → *Run workflow* → elegir un job o
`all`. También corre en `push` a `main` que toque `scripts/glue_jobs/**` o `glue/jobs/**`.

**Secrets / variables a configurar (una vez):**

- `secrets.AWS_DEPLOY_ROLE_ARN` — rol IAM que asume el workflow vía OIDC. Su *trust policy*
  debe permitir el proveedor OIDC de GitHub para este repo, y el rol necesita permisos:
  `glue:GetJob/CreateJob/UpdateJob`, `s3:PutObject` sobre el bucket de artefactos de Glue,
  e `iam:PassRole` para `AWSGlueServiceRole-chucaw`.
- `vars.AWS_REGION` — opcional, por defecto `us-east-1`.

> Nota: crear el proveedor OIDC de GitHub y el rol es un paso del lado de AWS (una vez).
> Este workflow **no** compila el bundle de dependencias; eso sigue en `build-glue-wheels.yml`.

**Deploy local equivalente** (requiere credenciales AWS y `jq`):

```bash
scripts/deploy/deploy_glue_job.sh glue/jobs/bronze_to_platinum_as_parquet
scripts/deploy/deploy_glue_job.sh --dry-run glue/jobs/bronze_to_pangu   # imprime, no ejecuta
```

Ver [`glue/README.md`](glue/README.md) para la estructura de config de despliegue.

## Parámetros de ejecución de jobs

Argumentos resueltos por `chucaw_preprocessor.glue_args.resolve_args` (funciona en Glue y
localmente). Salidas particionadas por `year=/month=/day=/hour=RRz/`.

### 1) `bronze_to_platinum_as_parquet` (Parquet, recomendado)

Guion: `scripts/glue_jobs/bronze_to_platinum_parquet.py`. Buckets por defecto:

- Bronze: `chucaw-data-bronze-raw-725644097028-us-east-1-an`
- Platinum: `chucaw-data-platinum-processed-725644097028-us-east-1-an`

Selección del origen: `--BRONZE_KEY` (ruta exacta `.grib2`), o `--DATE`+`--RUN`, o
autodescubrimiento del último GRIB. Otros: `--BRONZE_BUCKET`, `--BRONZE_PREFIX`,
`--PLATINUM_BUCKET`, `--PLATINUM_PREFIX` (`ecmwf/parquet`), `--TMP_DIR`.

Salida: `<PLATINUM_PREFIX>/year=YYYY/month=MM/day=DD/hour=RRz/dataset={surface,upper}/part-000.parquet`.

### 2) `bronze_to_pangu` (Pangu)

Guion: `scripts/glue_jobs/bronze_to_pangu.py`. Requeridos: `--BRONZE_BUCKET --BRONZE_KEY
--SILVER_BUCKET --SILVER_PREFIX --DATE --RUN` (opcional `--TMP_DIR`).

Salida: `<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/hour=RRz/{input_surface.npy,input_upper.npy}`.

### 2b) `cfsv2_monthly_bronze_to_silver` (CFSv2)

Guion: `scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py`. Requeridos: `--BRONZE_KEY --BRONZE_BUCKET --SILVER_BUCKET --SILVER_PREFIX` (opcional `--TMP_DIR`).

Salida: `<SILVER_PREFIX>/run_date=YYYYMMDD/cycle=HH/member=XX/product_kind=KIND/valid_month=YYYYMM/avg_kind=KIND/part-000.parquet`.

### 3) `platinum_parquet_to_fourcastnet` (FourCastNet)

Guion: `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py`. Requeridos: `--YEAR --MONTH
--DAY --HOUR`. Optimizado en memoria para particiones `oper` grandes. Orquestado
mensualmente por Step Functions (`stepfunctions/`).

### Variantes locales

`scripts/glue_jobs/local/` contiene runners para iterar sobre archivos locales sin S3
(`local_grib_to_platinum_parquet.py`, `local_parquet_to_fourcastnet.py`).

## Dependencias en Glue (deploy offline 5.0)

El job usa el bundle offline (baseline de Glue + extras nativos):

```text
--additional-python-modules s3://<bucket>/glue/artifacts/glue-dependencies.gluewheels.zip,s3://<bucket>/glue/artifacts/chucaw_preprocessor-0.1.0-py3-none-any.whl
--python-modules-installer-option --no-index
```

- Baseline provisto por Glue (según `docs/lista_de_glue50.txt`): `boto3`, `numpy`, `pandas`,
  `pyarrow`, etc.
- Extras empaquetadas por este repo: `xarray`, `cfgrib`, `eccodes` (y transitivas).

### 🐳 Compilación de dependencias con Docker (Glue 5.0)

Para compilar librerías nativas (`eccodes`) contra el SO de Glue 5.0 (Amazon Linux 2023,
Python 3.11):

```powershell
docker build -f Dockerfile.glue-builder -t glue5-builder:latest .
docker run --rm -v "${PWD}:/workspace" -v "${PWD}/build:/build" `
  --entrypoint /bin/bash glue5-builder:latest /workspace/build_glue_libs.sh
```

Genera en `build/`: `chucaw_preprocessor-*.whl`, `glue-dependencies.gluewheels.zip` y un
`manifest.txt`. El workflow `build-glue-wheels.yml` reproduce esto en CI.

## Entorno local (`.venv`)

```powershell
conda create --prefix .venv python=3.11 pip -y
conda activate .\.venv
python -m pip install -r requirements.txt
```

Smoke test de runtime antes de deploy:

```powershell
python scripts/smoke/glue_runtime_smoke.py --strict --output-json dist/glue-runtime-smoke.json
```

## Nota sobre DynamicFrames

Los jobs corren en runtime Spark (`glueetl`) para usar Glue 5.0 / Python 3.11, pero la
transformación es Python puro con `xarray/pandas/pyarrow` y no usa `DynamicFrame`. Si más
adelante se requiere integración fuerte con Catalog/Spark SQL, conviene incorporar
`GlueContext` + `DynamicFrame`.

## Documentación Sphinx (estilo NumPy)

La documentación técnica vive en `docs/sphinx` (usa `sphinx`, `napoleon`, `autodoc`).

```powershell
python -m pip install -r requirements-docs.txt
cd docs/sphinx
..\..\.venv\Scripts\python.exe -m sphinx -b html source build/html
```
