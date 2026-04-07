# Guía Definitiva de Despliegue en AWS Glue 5.0 (Python 3.11)

Esta guía documenta el procedimiento **exacto y paso a paso** para empaquetar, subir y configurar tu pipeline ECMWF (GRIB a Parquet Chunked) en AWS Glue 5.0. Ha sido diseñada considerando las lecciones aprendidas sobre cuelgues por OOM, aislamiento de red y manejo de dependencias complejas (`xarray`, `eccodes`).

## 1. Contexto de los Buckets
Según el código base, el pipeline interactúa con los siguientes buckets (asegúrate de usar las mismas credenciales/perfil AWS que tienen acceso a estos):

*   **Origen (Bronze):** `chucaw-data-bronze-raw-725644097028-us-east-1-an`
*   **Destino (Platinum):** `chucaw-data-platinum-processed-725644097028-us-east-1-an`
*   **Artefactos (Sugerido):** `your-glue-artifacts-bucket` (Debes reemplazarlo por tu bucket real para scripts y librerías).

---

## 2. Construcción de Artefactos (Build)
Glue 5.0 ya incluye varias librerías por defecto (numpy, pandas, pyarrow). Instalar versiones cruzadas o descargar código desde red abierta durante el job de Glue puede causar el fallo `ModuleNotFoundError` o romper dependencias compartidas en C (como `eccodeslib`).

Por esto, usamos un contenedor Docker idéntico al de AWS para pre-compilar las librerías binarias exclusivas de Linux y filtrando las que Glue ya trae incorporadas.

### Ejecución en PowerShell
1. Asegúrate de tener Docker abierto.
2. Abre tu terminal en `C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts`.
3. Ejecuta el orquestador:

```powershell
docker run --rm -v "${PWD}:/workspace" -v "${PWD}/build:/build" --entrypoint /bin/bash glue5-builder:latest /workspace/build_glue_libs.sh
```

**Artefactos Generados en la carpeta `build/`**:
*   `glue-dependencies.gluewheels.zip`: Las dependencias aisladas de internet listas para extraerse en el cluster AWS.
*   `chucaw_preprocessor-0.1.0-py3-none-any.whl`: El backend nativo donde creamos el motor Chunked.

---

## 3. Subida a AWS S3 (Sincronización)
Una vez construidos, debes colocar estos ficheros en S3 para que AWS Glue pueda consumirlos antes de encender sus nodos.

En PowerShell, define tu bucket de artefactos y ejecuta (asumiendo que tu perfil AWS se llama `sbnai-725`):

```powershell
$ARTIFACTS_BUCKET = "chucaw-glue-assets-725644097028-us-east-1-an"
$PROFILE = "sbnai-725"

# Subir empaquetados
aws s3 cp .\build\glue-dependencies.gluewheels.zip "s3://$ARTIFACTS_BUCKET/libs/glue-dependencies.gluewheels.zip" --profile $PROFILE
aws s3 cp .\build\chucaw_preprocessor-0.1.0-py3-none-any.whl "s3://$ARTIFACTS_BUCKET/libs/chucaw_preprocessor-0.1.0-py3-none-any.whl" --profile $PROFILE

# Subir el Job Script Principal
aws s3 cp .\scripts\glue_jobs\bronze_to_platinum_parquet.py "s3://$ARTIFACTS_BUCKET/scripts/bronze_to_platinum_parquet.py" --profile $PROFILE
```

---

## 4. Configurar el AWS Glue Job en la Consola

Dirígete a la Consola de AWS Glue (**AWS Glue > Data Integration and ETL > Jobs**) y usa la interfaz visual para crear un Job de tipo "Python Shell" o "Spark". Para evitar desbordamientos de Memoria (OOM Killers) y referenciar correctamente tus Wheels empaquetados, usa **EXACTAMENTE** esta configuración de Job Details:

### Parámetros Core
*   **Job Name:** `chucaw-grib-to-parquet` (A elección).
*   **IAM Role:** Selecciona el rol con permisos S3 (ej. `GlueServiceRole`).
*   **Type:** `Python Shell` (o `Spark` si escalas a terabytes).
*   **Glue version:** `Glue 5.0 - Supports Python 3.11` *(Crítico, no elegir otra versión).*
*   **Worker type:** `G.1X` *(Crucial: G.1X te ofrece ~16GB de RAM. Evita "Standard" si procesas fechas enteras)*.
*   **Number of workers:** `2` (o más si paralelizarás varios días corriendo).

### Advanced Properties / Job Parameters
Al final de la configuración ("Job Parameters"), debes añadir obligatoriamente las banderas necesarias para indicar a Glue que use tus archivos cerrados `.gluewheels.zip` de S3 y no intercepte el internet.

Añade los parámetros usando las Key y Value exactamente así:

| Key (Parameter)                         | Value                                                                                                                                     | Razón Constructiva                                                                                                                                                          |
| :-------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`--additional-python-modules`**       | `s3://${ARTIFACTS_BUCKET}/libs/glue-dependencies.gluewheels.zip,s3://${ARTIFACTS_BUCKET}/libs/chucaw_preprocessor-0.1.0-py3-none-any.whl` | Mapeo exacto hacia tu Zip-of-Wheels y tu módulo de Chunking.                                                                                                                |
| **`--python-modules-installer-option`** | `--no-index`                                                                                                                              | **Crítico:** Instruye internamente a `pip install` a usar ÚNICAMENTE los librerías locales subidas, evadiendo errores de internet y versiones corrompidas de repos remotos. |

*(Nota: Reemplaza `${ARTIFACTS_BUCKET}` textualmente en las rutas de S3 dentro del panel de Glue por el nombre de tu bucket)*.

---

## 5. Pruebas y Monitoreo del Ejecutor

Cuando mandes a correr el Job, AWS inicializará el Cluster e iniciará el script **`bronze_to_platinum_parquet.py`**.

El Job posee autodescubrimiento. Si no le pasas variables extra, el script automáticamente buscará en:
`s3://chucaw-data-bronze-raw-725644097028-us-east-1-an`
La última grib y la depositará particionada y convertida a Parquet en:
`s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/`

Si deseas procesar un archivo temporal específico para testear, añade como parámetros de Job:
*   `--BRONZE_KEY` : `test/archivo_especifico.grib2`

### Diagnóstico de Fallos Comunes Aprendidos:
1.  **Fallo: `ModuleNotFoundError: No module named 'cfgrib'`**
    *   *Solución:* Olvidaste poner `--python-modules-installer-option` `--no-index`. Glue falló al intentar buscar en internet y no desempaquetó tu `.gluewheels.zip` de S3.
2.  **Fallo: Sigue muriendo abruptamente sin Log de Stacktrace.**
    *   *Solución:* Sigue sufriendo de OutOfMemory. Verifica que el Worker Type es **G.1X** o **G.2X** como mínimo. Verifica que el script subido tiene el modificador Chunked Isobaro (es decir, subiste la V2 refactorizada de `ecmwf.py` compilada y no las compilaciones antiguas).
3.  **Fallo de incompatibilidad de Binary/ELF.**
    *   *Solución:* No compilaste en Docker usando `build_glue_libs.sh`. Corriste comandos en Windows directo y tus librerías se empaquetaron para `.pyd` (Windows) en vez de `.so` (Linux). Re-ejecuta el paso 2 de esta guía.
