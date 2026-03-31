# chucaw-pangu-preprocessor

Procesamiento de GRIB ECMWF para Lakehouse con AWS Glue.

## Estrategia de ramas

- `ecmwf_to_bronze`: conserva el enfoque anterior (Lambda + Docker/ECR para ingesta).
- `development`: nueva línea de trabajo para ETL en Glue (Python Shell) desde bronce hacia platinum.

## Nueva arquitectura (development)

1. Los GRIB llegan a capa bronce en S3.
2. Jobs de AWS Glue Python Shell leen GRIB desde bronce.
3. Se aplica la misma base de limpieza/normalización con `xarray` y `cfgrib`.
4. Salidas a capa platinum:
- formato Pangu (`input_surface.npy`, `input_upper.npy`)
- formato analítico Parquet (`surface`, `upper`)

## Estructura principal

- `src/chucaw_preprocessor/ecmwf.py`: lógica común de lectura, limpieza y conversión.
- `scripts/glue_jobs/pangu_to_silver.py`: job Glue para salida Pangu.
- `scripts/glue_jobs/bronze_to_platinum_parquet.py`: job Glue principal para salida Parquet.
- `scripts/glue_jobs/parquet_to_silver.py`: wrapper de compatibilidad (redirige al job principal).
- `pyproject.toml`: configuración para construir wheel del proyecto.
- `requirements-glue.txt`: dependencias a empaquetar para Glue.
- `scripts/build_glue_artifacts.ps1`: construcción de wheel + wheels de dependencias + zip `.gluewheels.zip`.

## Entorno local (`.venv`)

Se debe trabajar con un entorno local en la carpeta `.venv` usando las versiones fijadas en el repo.

### 1) Crear `.venv` local

Con `conda`:

```powershell
conda create --prefix .venv python=3.12 pip -y
```

Si `conda` no está en `PATH`:

```powershell
& "C:\ProgramData\miniconda3\Scripts\conda.exe" create --prefix .venv python=3.12 pip -y
```

### 2) Activar entorno

```powershell
conda activate .\.venv
```

### 3) Instalar dependencias del proyecto

```powershell
python -m pip install -r requirements.txt
```

### 4) Verificar versión de Python y paquetes

```powershell
python --version
python -m pip list
```

## Dependencias relevantes para Glue

Dependencias nuevas para el escenario Glue/Parquet sobre la base existente:

- `pandas`
- `pyarrow`

Se mantienen librerías para GRIB/xarray:

- `xarray`
- `cfgrib`
- `eccodes`
- `numpy`
- `boto3`

## Construcción de artefactos (wheel + gluewheels)

```powershell
./scripts/build_glue_artifacts.ps1
```

Genera en `dist/`:

- wheel del proyecto `chucaw_preprocessor-*.whl`
- wheels de dependencias
- `glue-dependencies.gluewheels.zip`

## Configuración recomendada en AWS Glue

Basado en la guía oficial de AWS Glue para librerías Python:

- subir wheel del proyecto y `glue-dependencies.gluewheels.zip` a S3
- usar `--additional-python-modules` con rutas S3 a wheels/zip
- para enfoque determinista en producción, preferir artefactos congelados (wheel/zip) sobre instalación dinámica desde PyPI

Ejemplo de argumentos de job:

```text
--additional-python-modules s3://<bucket>/artifacts/glue-dependencies.gluewheels.zip,s3://<bucket>/artifacts/chucaw_preprocessor-0.1.0-py3-none-any.whl
--python-modules-installer-option --no-index
```

## Parámetros de ejecución de jobs

Parámetros comunes para jobs de salida Parquet/Pangu:

- `--BRONZE_BUCKET`
- `--BRONZE_KEY`
- `--PLATINUM_BUCKET` o `--SILVER_BUCKET` (según el script)
- `--PLATINUM_PREFIX` o `--SILVER_PREFIX` (según el script)
- `--DATE` (formato `YYYYMMDD`)
- `--RUN` (ej. `00z`)
- `--TMP_DIR` (opcional, default `/tmp`)

### Job: Pangu

Script: `scripts/glue_jobs/pangu_to_silver.py`

Salida en S3 (plata), particionada:

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/input_surface.npy`

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/input_upper.npy`

### Job: Parquet Bronze -> Platinum (recomendado)

Script: `scripts/glue_jobs/bronze_to_platinum_parquet.py`

Buckets por defecto:

- Bronze: `chucaw-data-bronze-raw-725644097028-us-east-1-an`
- Platinum: `chucaw-data-platinum-processed-725644097028-us-east-1-an`

Parámetros soportados:

- `--BRONZE_BUCKET` (opcional, default bucket bronze)
- `--BRONZE_KEY` (opcional, ruta exacta `.grib2` en bronze)
- `--BRONZE_PREFIX` (opcional, prefijo para búsqueda/listado)
- `--PLATINUM_BUCKET` (opcional, default bucket platinum)
- `--PLATINUM_PREFIX` (opcional, default `ecmwf/parquet`)
- `--DATE` (opcional, `YYYYMMDD`; si no viene, infiere desde key o usa último GRIB)
- `--RUN` (opcional, `00z/06z/12z/18z`)
- `--TMP_DIR` (opcional, default `/tmp`)

Salida en S3 (platinum), particionada:

`<PLATINUM_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/dataset=surface/part-000.parquet`

`<PLATINUM_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/dataset=upper/part-000.parquet`

Ejemplo de `DefaultArguments` en Glue Studio:

```text
--BRONZE_BUCKET chucaw-data-bronze-raw-725644097028-us-east-1-an
--PLATINUM_BUCKET chucaw-data-platinum-processed-725644097028-us-east-1-an
--PLATINUM_PREFIX ecmwf/parquet
--BRONZE_KEY <ruta-exacta-a-tu-grib2>
```

Dependencias del job (Glue 5.0 recomendado):

```text
--additional-python-modules s3://<bucket-artifacts>/glue-dependencies.gluewheels.zip,s3://<bucket-artifacts>/chucaw_preprocessor-0.1.0-py3-none-any.whl
--python-modules-installer-option --no-index
```

### Nota sobre DynamicFrames

Este job está pensado para **Glue Python Shell**, por lo que no usa `DynamicFrame` (que aplica al runtime Spark `glueetl`).  
Si luego migramos a Glue Spark para catálogo/crawlers y transformaciones de gran escala, ahí sí conviene incorporar `GlueContext` + `DynamicFrame`.

## Nota de particiones

Para consultas eficientes, la partición se construye por:

- `year`
- `month`
- `day`
- `run`

## Documentación Sphinx (NumPy style)

La documentación técnica del equipo vive en `docs/sphinx` y usa:

- `sphinx`
- `napoleon` (estilo NumPy docstrings)
- `autodoc` para módulos/scripts

Instalación:

```powershell
python -m pip install -r requirements-docs.txt
```

Build HTML:

```powershell
cd docs/sphinx
..\..\.venv\Scripts\python.exe -m sphinx -b html source build/html
```

Abrir:

`docs/sphinx/build/html/index.html`
