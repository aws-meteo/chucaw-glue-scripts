# chucaw-pangu-preprocessor

Procesamiento de GRIB ECMWF para Lakehouse con AWS Glue.

## Estrategia de ramas

- `ecmwf_to_bronze`: conserva el enfoque anterior (Lambda + Docker/ECR para ingesta).
- `development`: nueva línea de trabajo para ETL en Glue (Python Shell) desde bronce hacia plata.

## Nueva arquitectura (development)

1. Los GRIB llegan a capa bronce en S3.
2. Jobs de AWS Glue Python Shell leen GRIB desde bronce.
3. Se aplica la misma base de limpieza/normalización con `xarray` y `cfgrib`.
4. Salidas a capa plata:
1. formato Pangu (`input_surface.npy`, `input_upper.npy`)
2. formato analítico Parquet (`surface`, `upper`)

## Estructura principal

- `src/chucaw_preprocessor/ecmwf.py`: lógica común de lectura, limpieza y conversión.
- `scripts/glue_jobs/pangu_to_silver.py`: job Glue para salida Pangu.
- `scripts/glue_jobs/parquet_to_silver.py`: job Glue para salida Parquet.
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

Parámetros comunes esperados por ambos scripts:

- `--BRONZE_BUCKET`
- `--BRONZE_KEY`
- `--SILVER_BUCKET`
- `--SILVER_PREFIX`
- `--DATE` (formato `YYYYMMDD`)
- `--RUN` (ej. `00z`)
- `--TMP_DIR` (opcional, default `/tmp`)

### Job: Pangu

Script: `scripts/glue_jobs/pangu_to_silver.py`

Salida en S3 (plata), particionada:

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/input_surface.npy`

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/input_upper.npy`

### Job: Parquet

Script: `scripts/glue_jobs/parquet_to_silver.py`

Salida en S3 (plata), particionada:

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/dataset=surface/part-000.parquet`

`<SILVER_PREFIX>/year=YYYY/month=MM/day=DD/run=RRz/dataset=upper/part-000.parquet`

## Nota de particiones

Para consultas eficientes, la partición se construye por:

- `year`
- `month`
- `day`
- `run`
