"""Standalone GRIB -> Parquet preprocessing pipeline.

This module keeps the original pipeline shape but replaces Pangu-specific outputs
with a parquet serialization workflow.
"""

import os
import warnings

import boto3
import cfgrib
import pandas as pd
import xarray as xr
from botocore import UNSIGNED
from botocore.config import Config

# Ignorar advertencias futuras de xarray/cfgrib para logs limpios
warnings.filterwarnings("ignore", category=FutureWarning)


# =====================================================================
# 1. FUNCIÓN DE DESCARGA: OBTIENE EL ESTADO INICIAL (ANÁLISIS T+0)
# =====================================================================
def download_ecmwf_initial_state(date_str: str, run_str: str, download_dir: str = "/tmp") -> str:
    """
    Descarga el archivo GRIB2 global operativo desde el Open Data de AWS.

    Parameters
    ----------
    date_str : str
        Fecha en formato ``YYYYMMDD``.
    run_str : str
        Run ECMWF (por ejemplo, ``00z``).
    download_dir : str, default "/tmp"
        Directorio temporal de descarga.

    Returns
    -------
    str
        Ruta local del GRIB descargado.
    """
    bucket_name = "ecmwf-forecasts"
    base_name = f"{date_str}{run_str[:2]}0000-0h-oper-fc"
    prefix = f"{date_str}/{run_str}/ifs/0p25/oper/"

    grib_key = f"{prefix}{base_name}.grib2"
    index_key = f"{prefix}{base_name}.index"

    local_grib = os.path.join(download_dir, f"{base_name}.grib2")
    local_index = os.path.join(download_dir, f"{base_name}.index")

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

    print(f"Descargando {grib_key}...")
    s3.download_file(bucket_name, grib_key, local_grib)
    try:
        s3.download_file(bucket_name, index_key, local_index)
    except Exception:
        pass  # Si el índice no está, cfgrib lo creará

    return local_grib


# =====================================================================
# 2. FUNCIÓN CORE: CONVERSIÓN A PARQUET
# =====================================================================
def prepare_parquet(grib_path: str, output_dir: str = "/tmp/output_data") -> str:
    """
    Toma el GRIB2 crudo y genera un Parquet tabular con todas las variables.

    Parameters
    ----------
    grib_path : str
        Ruta local al archivo GRIB.
    output_dir : str, default "/tmp/output_data"
        Directorio temporal para salida parquet.

    Returns
    -------
    str
        Ruta local al parquet generado.
    """
    print("Abriendo y fusionando GRIB2 (Resolviendo conflictos)...")
    datasets = cfgrib.open_datasets(grib_path)

    ds_list = []
    for dataset in datasets:
        bad_coords = ["heightAboveGround", "meanSea", "entireAtmosphere", "soilLayer"]
        cols_to_drop = [coord for coord in dataset.coords if coord in bad_coords]
        ds_list.append(dataset.drop_vars(cols_to_drop, errors="ignore"))

    ds = xr.merge(ds_list, compat="override")
    if "latitude" in ds.coords:
        ds = ds.sortby("latitude", ascending=False)

    print("Convirtiendo Dataset a DataFrame tabular...")
    df = ds.to_array("variable").rename("value").to_dataframe().reset_index()
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float32")

    os.makedirs(output_dir, exist_ok=True)
    out_parquet = os.path.join(output_dir, "ecmwf_data.parquet")
    df.to_parquet(out_parquet, index=False, compression="snappy")
    print(f"¡Éxito! Parquet listo: {out_parquet} ({len(df)} filas)")

    return out_parquet


# =====================================================================
# 3. LAMBDA HANDLER — punto de entrada para AWS Lambda/Glue Python Shell
# =====================================================================
def lambda_handler(event, context):
    """
    Payload de ejemplo:
        {"date": "20260318", "run": "00z", "output_bucket": "mi-bucket-silver"}

    Parameters
    ----------
    event : dict
        Evento con configuracion de fecha/run y salida.
    context : Any
        Contexto de Lambda/Glue.

    Returns
    -------
    dict
        Resumen de ejecucion y ubicacion de salida en S3.
    """
    date_str = event.get("date", "20260317")
    run_str = event.get("run", "00z")
    download_dir = "/tmp"
    output_dir = "/tmp/output_data"
    bucket_out = event.get("output_bucket", "tu-bucket-silver-outputs")
    output_prefix = event.get("output_prefix", "silver/ecmwf")

    # 1. Descargar GRIB desde ECMWF Open Data (S3 público)
    grib_file = download_ecmwf_initial_state(date_str, run_str, download_dir)

    # 2. Preprocesar y generar Parquet
    parquet_file = prepare_parquet(grib_file, output_dir=output_dir)

    # 3. Subir resultado a S3, particionado por year/month/day
    year = date_str[:4]
    month = date_str[4:6]
    day = date_str[6:8]
    filename = os.path.basename(parquet_file)
    s3_key = (
        f"{output_prefix}/year={year}/month={month}/day={day}/run={run_str}/{filename}"
    )

    s3 = boto3.client("s3")
    s3.upload_file(parquet_file, bucket_out, s3_key)
    print(f"Subido: s3://{bucket_out}/{s3_key}")

    # 4. Limpieza temporal
    if os.path.exists(grib_file):
        os.remove(grib_file)
        print("GRIB temporal eliminado.")
    if os.path.exists(parquet_file):
        os.remove(parquet_file)
        print("Parquet temporal eliminado.")

    return {
        "statusCode": 200,
        "date": date_str,
        "run": run_str,
        "output_bucket": bucket_out,
        "output_key": s3_key,
    }


# =====================================================================
# 4. EJECUCIÓN LOCAL — simula el evento para pruebas
# =====================================================================
if __name__ == "__main__":
    test_event = {
        "date": "20260317",
        "run": "00z",
        "output_bucket": "tu-bucket-silver-outputs",
        "output_prefix": "silver/ecmwf",
    }
    result = lambda_handler(test_event, None)
    print("\n✅ CONVERSIÓN A PARQUET COMPLETADA.")
    print(result)
