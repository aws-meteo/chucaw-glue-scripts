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
    # Solicitamos el step '0h' porque es el estado inicial (inputs)
    base_name = f"{date_str}{run_str[:2]}0000-0h-oper-fc"
    prefix = f"{date_str}/{run_str}/ifs/0p25/oper/"
    
    grib_key = f"{prefix}{base_name}.grib2"
    index_key = f"{prefix}{base_name}.index"
    
    local_grib = os.path.join(download_dir, f"{base_name}.grib2")
    local_index = os.path.join(download_dir, f"{base_name}.index")
    
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    
    print(f"Descargando {grib_key}...")
    s3.download_file(bucket_name, grib_key, local_grib)
    try:
        s3.download_file(bucket_name, index_key, local_index)
    except Exception:
        pass # Si el índice no está, cfgrib lo creará
        
    return local_grib

# =====================================================================
# 2. FUNCIÓN CORE: PREPARACIÓN EXACTA PARA PANGU (Reemplaza lib/models/pangu)
# =====================================================================
def prepare_pangu_tensors(grib_path: str, output_dir: str = "input_data"):
    """
    Toma el GRIB2 crudo y genera los archivos input_surface.npy e input_upper.npy.
    Efecto: 
    1. Resuelve conflictos de altura de cfgrib.
    2. Convierte Geopotential Height a Geopotential estricto.
    3. Apila las variables en el orden exacto que espera la IA.
    """
    print("Abriendo y fusionando GRIB2 (Resolviendo conflictos)...")
    datasets = cfgrib.open_datasets(grib_path)
    
    # Unificamos todas las variables (superficie y altura) en un solo Dataset
    ds_list = []
    for d in datasets:
        # Eliminamos coords escalares que impiden el merge
        bad_coords = ['heightAboveGround', 'meanSea', 'entireAtmosphere', 'soilLayer']
        cols_to_drop = [c for c in d.coords if c in bad_coords]
        ds_list.append(d.drop_vars(cols_to_drop, errors='ignore'))
        
    ds = xr.merge(ds_list, compat='override')
    
    # ---------------------------------------------------------
    # A. VALIDACIÓN DE MALLA (Pangu espera 721 lat x 1440 lon)
    # ---------------------------------------------------------
    # Aseguramos que las latitudes vayan de 90 a -90 (orden descendente)
    ds = ds.sortby('latitude', ascending=False)
    
    # ---------------------------------------------------------
    # B. EXTRACCIÓN DE SUPERFICIE (4 variables)
    # Orden estricto Pangu: MSL, U10, V10, T2M
    # ---------------------------------------------------------
    print("Extrayendo variables de superficie...")
    msl = ds['msl'].values  # Mean Sea Level Pressure
    u10 = ds['u10'].values  # Viento U a 10m
    v10 = ds['v10'].values  # Viento V a 10m
    t2m = ds['t2m'].values  # Temperatura a 2m
    
    # Apilamos en un tensor de dimensión (4, 721, 1440)
    surface_array = np.stack([msl, u10, v10, t2m], axis=0).astype(np.float32)
    
    # ---------------------------------------------------------
    # C. EXTRACCIÓN DE ALTURA (5 variables x 13 niveles)
    # Niveles estrictos: 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50
    # Orden estricto Pangu: Z, Q, T, U, V
    # ---------------------------------------------------------
    print("Extrayendo variables de niveles de presión...")
    expected_levels = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
    
    # Filtramos solo los 13 niveles que la red neuronal conoce
    ds_pl = ds.sel(isobaricInhPa=expected_levels)
    
    # TRUCO FÍSICO CRÍTICO: ECMWF entrega Altura Geopotencial (gh)
    # Pero Pangu fue entrenado con Geopotencial (Z). Debemos multiplicar por la gravedad.
    z = ds_pl['gh'].values * 9.80665  
    
    q = ds_pl['q'].values  # Humedad Específica
    t = ds_pl['t'].values  # Temperatura
    u = ds_pl['u'].values  # Viento U
    v = ds_pl['v'].values  # Viento V
    
    # Apilamos en un tensor de dimensión (5, 13, 721, 1440)
    upper_array = np.stack([z, q, t, u, v], axis=0).astype(np.float32)
    
    # ---------------------------------------------------------
    # D. GUARDADO PARA INFERENCIA
    # ---------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    out_sfc = os.path.join(output_dir, "input_surface.npy")
    out_up = os.path.join(output_dir, "input_upper.npy")
    
    np.save(out_sfc, surface_array)
    np.save(out_up, upper_array)
    
    print(f"¡Éxito! Tensores listos para Pangu:\n - {out_sfc} {surface_array.shape}\n - {out_up} {upper_array.shape}")
    
    return out_sfc, out_up

# =====================================================================
# 3. EJECUCIÓN PRINCIPAL (MAIN)
# =====================================================================
if __name__ == "__main__":
    # 1. Definimos la fecha de inicialización
    DATE = '20260317'
    RUN = '00z'
    
    # 2. Descargar
    grib_file = download_ecmwf_initial_state(DATE, RUN)
    
    # 3. Preprocesar y guardar tensores Numpy
    # (El script de Pangu que usas busca por defecto la carpeta 'input_data')
    sfc_npy, up_npy = prepare_pangu_tensors(grib_file, output_dir="input_data")
    
    # 4. Limpieza de disco (Borrar el GRIB pesado)
    if os.path.exists(grib_file):
        os.remove(grib_file)
        print("GRIB temporal eliminado.")
        
    print("\n✅ PREPROCESAMIENTO COMPLETADO.")
    print("Ya puedes ejecutar: python /content/Pangu-Weather/inference_gpu.py")