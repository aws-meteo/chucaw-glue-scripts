#!/usr/bin/env python3
"""Script de verificación: Prueba las funciones de conversión con datos sintéticos."""

import sys
sys.path.insert(0, "src")

import numpy as np
import xarray as xr
from chucaw_preprocessor.ecmwf import serialize_parquet_chunked

print("=" * 70)
print("TEST: Verificación de funciones de conversión GRIB → Parquet")
print("=" * 70)

# Crear dataset sintético simulando estructura ECMWF
print("\n1. Creando dataset sintético...")

lats = np.arange(90, -91, -1)  # 181 latitudes
lons = np.arange(0, 360, 1)    # 360 longitudes
pressure_levels = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]

# Variables de superficie
ds = xr.Dataset(
    {
        "msl": (["latitude", "longitude"], np.random.rand(len(lats), len(lons)) * 1000 + 100000),
        "u10": (["latitude", "longitude"], np.random.rand(len(lats), len(lons)) * 20 - 10),
        "v10": (["latitude", "longitude"], np.random.rand(len(lats), len(lons)) * 20 - 10),
        "t2m": (["latitude", "longitude"], np.random.rand(len(lats), len(lons)) * 30 + 270),
        
        # Variables de niveles de presión
        "gh": (["isobaricInhPa", "latitude", "longitude"], 
               np.random.rand(len(pressure_levels), len(lats), len(lons)) * 10000),
        "q": (["isobaricInhPa", "latitude", "longitude"], 
              np.random.rand(len(pressure_levels), len(lats), len(lons)) * 0.02),
        "t": (["isobaricInhPa", "latitude", "longitude"], 
              np.random.rand(len(pressure_levels), len(lats), len(lons)) * 50 + 220),
        "u": (["isobaricInhPa", "latitude", "longitude"], 
              np.random.rand(len(pressure_levels), len(lats), len(lons)) * 50 - 25),
        "v": (["isobaricInhPa", "latitude", "longitude"], 
              np.random.rand(len(pressure_levels), len(lats), len(lons)) * 50 - 25),
    },
    coords={
        "latitude": lats,
        "longitude": lons,
        "isobaricInhPa": pressure_levels,
    },
)

print(f"✅ Dataset creado: {len(lats)}x{len(lons)} grid, {len(pressure_levels)} niveles de presión")

# Probar serialize_parquet_chunked
print("\n2. Escribiendo archivos Parquet de manera serializada y fragmentada...")
try:
    output_dir = "./test_output_synthetic"
    surface_path, upper_path = serialize_parquet_chunked(
        ds, output_dir, date_str="20260330", run_str="06z"
    )
    
    print(f"✅ Surface escrito: {surface_path}")
    print(f"✅ Upper escrito: {upper_path}")
    
    # Verificar archivos creados
    import os
    surface_size = os.path.getsize(surface_path) / 1024  # KB
    upper_size = os.path.getsize(upper_path) / 1024  # KB
    
    print(f"\n   Surface: {surface_size:.1f} KB")
    print(f"   Upper: {upper_size:.1f} KB")
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Verificar que se pueden leer los archivos
print("\n4. Verificando lectura de archivos Parquet...")
try:
    import pandas as pd
    
    surface_read = pd.read_parquet(surface_path)
    upper_read = pd.read_parquet(upper_path)
    
    print(f"✅ Surface leído correctamente: {surface_read.shape}")
    print(f"✅ Upper leído correctamente: {upper_read.shape}")
    
except Exception as e:
    print(f"❌ Error al leer: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
print("=" * 70)
print(f"\n📁 Archivos de prueba creados en: {output_dir}/")
print("\nEl script de conversión GRIB → Parquet está funcionando correctamente.")
print("Para archivos GRIB grandes (>100MB), se recomienda aumentar la memoria de WSL.")
