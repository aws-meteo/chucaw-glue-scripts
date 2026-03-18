import os
import numpy as np
import xarray as xr
import cfgrib
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import warnings

# Ignorar advertencias futuras de xarray/cfgrib para logs limpios
warnings.filterwarnings('ignore', category=FutureWarning)

# =====================================================================
# 1. FUNCIÓN DE DESCARGA: OBTIENE EL ESTADO INICIAL (ANÁLISIS T+0)
# =====================================================================
def download_ecmwf_initial_state(date_str: str, run_str: str, download_dir: str = "/tmp") -> str:
    """
    Descarga el archivo GRIB2 global operativo desde el Open Data de AWS.
    Efecto: Trae los datos base (T+0) que Pangu usará como "presente".
    """
    bucket_name = 'ecmwf-forecasts'
    base_name = f"{date_str}{run_str[:2]}0000-0h-oper-fc"
    prefix = f"{date_str}/{run_str}/ifs/0p25/oper/"

    grib_key  = f"{prefix}{base_name}.grib2"
    index_key = f"{prefix}{base_name}.index"

    local_grib  = os.path.join(download_dir, f"{base_name}.grib2")
    local_index = os.path.join(download_dir, f"{base_name}.index")

    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

    print(f"Descargando {grib_key}...")
    s3.download_file(bucket_name, grib_key, local_grib)
    try:
        s3.download_file(bucket_name, index_key, local_index)
    except Exception:
        pass  # Si el índice no está, cfgrib lo creará

    return local_grib

# =====================================================================
# 2. FUNCIÓN CORE: PREPARACIÓN EXACTA PARA PANGU
# =====================================================================
def prepare_pangu_tensors(grib_path: str, output_dir: str = "/tmp/input_data"):
    """
    Toma el GRIB2 crudo y genera input_surface.npy e input_upper.npy.
    """
    print("Abriendo y fusionando GRIB2 (Resolviendo conflictos)...")
    datasets = cfgrib.open_datasets(grib_path)

    ds_list = []
    for d in datasets:
        bad_coords = ['heightAboveGround', 'meanSea', 'entireAtmosphere', 'soilLayer']
        cols_to_drop = [c for c in d.coords if c in bad_coords]
        ds_list.append(d.drop_vars(cols_to_drop, errors='ignore'))

    ds = xr.merge(ds_list, compat='override')

    # A. VALIDACIÓN DE MALLA (Pangu espera 721 lat x 1440 lon)
    ds = ds.sortby('latitude', ascending=False)

    # B. EXTRACCIÓN DE SUPERFICIE — orden estricto Pangu: MSL, U10, V10, T2M
    print("Extrayendo variables de superficie...")
    msl = ds['msl'].values
    u10 = ds['u10'].values
    v10 = ds['v10'].values
    t2m = ds['t2m'].values

    surface_array = np.stack([msl, u10, v10, t2m], axis=0).astype(np.float32)

    # C. EXTRACCIÓN DE ALTURA — 5 variables x 13 niveles, orden: Z, Q, T, U, V
    print("Extrayendo variables de niveles de presión...")
    expected_levels = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
    ds_pl = ds.sel(isobaricInhPa=expected_levels)

    # CRÍTICO: ECMWF entrega gh (Altura Geopotencial), Pangu necesita Z (Geopotencial)
    z = ds_pl['gh'].values * 9.80665
    q = ds_pl['q'].values
    t = ds_pl['t'].values
    u = ds_pl['u'].values
    v = ds_pl['v'].values

    upper_array = np.stack([z, q, t, u, v], axis=0).astype(np.float32)

    # D. GUARDADO
    os.makedirs(output_dir, exist_ok=True)
    out_sfc = os.path.join(output_dir, "input_surface.npy")
    out_up  = os.path.join(output_dir, "input_upper.npy")

    np.save(out_sfc, surface_array)
    np.save(out_up,  upper_array)

    print(f"¡Éxito! Tensores listos:\n - {out_sfc} {surface_array.shape}\n - {out_up} {upper_array.shape}")

    return out_sfc, out_up

# =====================================================================
# 3. LAMBDA HANDLER — punto de entrada para AWS Lambda
# =====================================================================
def lambda_handler(event, context):
    """
    AWS Lambda invoca esta función.
    Payload de ejemplo:
        {"date": "20260318", "run": "00z", "output_bucket": "mi-bucket-pangu"}
    """
    date_str     = event.get("date", "20260317")
    run_str      = event.get("run",  "00z")
    download_dir = "/tmp"
    output_dir   = "/tmp/input_data"
    bucket_out   = event.get("output_bucket", "tu-bucket-pangu-outputs")

    # 1. Descargar GRIB desde ECMWF Open Data (S3 público)
    grib_file = download_ecmwf_initial_state(date_str, run_str, download_dir)

    # 2. Preprocesar y generar tensores .npy
    sfc_npy, up_npy = prepare_pangu_tensors(grib_file, output_dir=output_dir)

    # 3. Subir resultados a S3 (Lambda es efímera: /tmp desaparece al terminar)
    s3 = boto3.client('s3')
    uploaded = []
    for local_path in [sfc_npy, up_npy]:
        filename = os.path.basename(local_path)
        s3_key   = f"pangu-inputs/{date_str}/{run_str}/{filename}"
        s3.upload_file(local_path, bucket_out, s3_key)
        print(f"Subido: s3://{bucket_out}/{s3_key}")
        uploaded.append(s3_key)

    # 4. Limpieza del GRIB pesado
    if os.path.exists(grib_file):
        os.remove(grib_file)
        print("GRIB temporal eliminado.")

    return {
        "statusCode": 200,
        "date":          date_str,
        "run":           run_str,
        "output_bucket": bucket_out,
        "files":         uploaded
    }

# =====================================================================
# 4. EJECUCIÓN LOCAL — simula el evento Lambda para pruebas
# =====================================================================
if __name__ == "__main__":
    test_event = {
        "date":          "20260317",
        "run":           "00z",
        "output_bucket": "tu-bucket-pangu-outputs"
    }
    result = lambda_handler(test_event, None)
    print("\n✅ PREPROCESAMIENTO COMPLETADO.")
    print(result)