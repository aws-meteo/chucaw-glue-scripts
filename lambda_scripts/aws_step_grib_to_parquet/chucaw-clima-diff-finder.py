import logging
import os
import re

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

DEFAULT_BRONZE_BUCKET = "chucaw-data-bronze-raw-725644097028-us-east-1-an"
DEFAULT_PLATINUM_BUCKET = "chucaw-data-platinum-processed-725644097028-us-east-1-an"
DEFAULT_BRONZE_PREFIX = "ecmwf-forecasts/"
DEFAULT_PLATINUM_PREFIX = "ecmwf/parquet/"
DEFAULT_BRONZE_SUFFIX = ".grib2"
DEFAULT_PLATINUM_SUFFIX = ".parquet"


def _config_value(event: dict, name: str, default: str) -> str:
    return str(event.get(name.lower()) or event.get(name) or os.environ.get(name) or default)


def get_all_keys(bucket: str, prefix: str, suffix: str) -> set[str]:
    """Obtiene un set con todas las llaves de un bucket filtradas por sufijo."""
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    
    try:
        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(suffix):
                    keys.add(obj["Key"])
    except Exception as e:
        logger.error(f"Error listando {bucket}/{prefix}: {e}")
        raise e
        
    return keys


def bronze_to_expected_platinum(bronze_key: str, platinum_prefix: str = DEFAULT_PLATINUM_PREFIX) -> str | None:
    """Mapea la ruta GRIB de Bronze a la ruta Parquet de Platinum."""
    # Ejemplo: ecmwf-forecasts/2026/04/06/06z/scda/20260406060000-6h-scda-fc.grib2
    pattern = r"(20\d{2})/(\d{2})/(\d{2})/(00z|06z|12z|18z)/.+/([^/]+)\.grib2$"
    match = re.search(pattern, bronze_key)
    
    if not match:
        logger.warning(f"Key no coincide con el patron esperado: {bronze_key}")
        return None
        
    year, month, day, run, filename = match.groups()
    # important, run is like 06z, gets casted to be hour
    # as it collides with existing columns
    prefix = platinum_prefix.strip("/")
    return f"{prefix}/year={year}/month={month}/day={day}/hour={run}/{filename}.parquet"


def lambda_handler(event, context):
    logger.info("Iniciando escaneo de buckets (Bronze y Platinum)...")
    event = event or {}
    bronze_bucket = _config_value(event, "BRONZE_BUCKET", DEFAULT_BRONZE_BUCKET)
    platinum_bucket = _config_value(event, "PLATINUM_BUCKET", DEFAULT_PLATINUM_BUCKET)
    bronze_prefix = _config_value(event, "BRONZE_PREFIX", DEFAULT_BRONZE_PREFIX)
    platinum_prefix = _config_value(event, "PLATINUM_PREFIX", DEFAULT_PLATINUM_PREFIX)
    bronze_suffix = _config_value(event, "BRONZE_SUFFIX", DEFAULT_BRONZE_SUFFIX)
    platinum_suffix = _config_value(event, "PLATINUM_SUFFIX", DEFAULT_PLATINUM_SUFFIX)
    
    bronze_keys = get_all_keys(bronze_bucket, bronze_prefix, bronze_suffix)
    platinum_keys = get_all_keys(platinum_bucket, platinum_prefix, platinum_suffix)
    
    pending_bronze = []
    
    for b_key in bronze_keys:
        expected_p = bronze_to_expected_platinum(b_key, platinum_prefix=platinum_prefix)
        if expected_p and expected_p not in platinum_keys:
            # Lo devolvemos como diccionario para que el Map State de Step Functions 
            # pueda inyectarlo facilmente usando $.bronze_key
            pending_bronze.append({"bronze_key": b_key})
            
    logger.info(f"Escaneo finalizado. {len(pending_bronze)} archivos pendientes encontrados.")
    
    # El formato exacto de retorno es crítico para el frontend y Step Functions
    return {
        "pending_keys": pending_bronze,
        "count": len(pending_bronze)
    }
