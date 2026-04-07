import sys
import argparse
from pathlib import Path

# Append src for local loading of ecmwf
sys.path.insert(0, "src")

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import xarray as xr
    import pandas as pd
    from chucaw_preprocessor.ecmwf import load_merged_dataset, EXPECTED_PRESSURE_LEVELS, _GRAVITY
except ImportError as e:
    print(f"Missing dependency: {e}", file=sys.stderr)
    print("Por favor instala modulos faltantes para validacion visual: pip install matplotlib xarray cfgrib pandas pyarrow")
    sys.exit(1)


def compare_surface(grib_ds, parquet_path, output_img, date_str, run_str):
    print(f"[Surface] Loading parquet: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    
    df_var = df[(df['variable'] == 't2m')]
    if df_var.empty:
        raise ValueError(f"No t2m data found")
        
    df_pivot = df_var.pivot(index='latitude', columns='longitude', values='value')
    # Sort coordinates descending for latitude
    df_pivot = df_pivot.sort_index(axis=0, ascending=False).sort_index(axis=1)

    parq_arr = df_pivot.values
    
    # Load GRIB
    grib_arr = grib_ds['t2m'].sortby('latitude', ascending=False).values
    
    # ---- CHECKSUM MATH ----
    grib_mean = np.nanmean(grib_arr)
    parq_mean = np.nanmean(parq_arr)
    diff_mean = abs(grib_mean - parq_mean)
    
    print(f"[Surface QA] Checksum Global Promedio Grib: {grib_mean:.4f}")
    print(f"[Surface QA] Checksum Global Promedio Parquet: {parq_mean:.4f}")
    print(f"[Surface QA] Tolerancia Discrepancia Absoluta: {diff_mean:.3e}")
    if diff_mean > 1e-4:
        raise ValueError(f"CRITICAL ANOMALY: El modelo divergió matemáticamente más del límite {diff_mean:.3e}. Corrupción en Surface (t2m).")
    
    diff = np.abs(grib_arr - parq_arr)
    max_diff = np.nanmax(diff)
    print(f"[Surface] t2m max diff: {max_diff}")
    
    if output_img:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        
        im0 = axes[0].imshow(grib_arr, cmap='RdBu_r')
        axes[0].set_title('GRIB: t2m')
        plt.colorbar(im0, ax=axes[0])
        
        im1 = axes[1].imshow(parq_arr, cmap='RdBu_r')
        axes[1].set_title('Parquet: t2m')
        plt.colorbar(im1, ax=axes[1])
        
        im2 = axes[2].imshow(diff, cmap='hot')
        axes[2].set_title(f'Abs Diff (Max: {max_diff:.3e})')
        plt.colorbar(im2, ax=axes[2])
        
        plt.tight_layout()
        plt.savefig(output_img)
        plt.close()
        print(f"[Surface] Generated Heatmap: {output_img}")


def compare_upper(grib_ds, parquet_path, output_img, date_str, run_str):
    print(f"[Upper] Loading parquet: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    
    # Tolerancia a float para isobaricInhPa en pandas = float o int. 
    df_var = df[(df['variable'] == 'z') & (df['isobaricInhPa'] == 500)]
    if df_var.empty:
        raise ValueError(f"No z data at 500hPa found")
        
    df_pivot = df_var.pivot(index='latitude', columns='longitude', values='value')
    df_pivot = df_pivot.sort_index(axis=0, ascending=False).sort_index(axis=1)
    parq_arr = df_pivot.values
    
    ds_pl = grib_ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    gh_500 = ds_pl['gh'].sel(isobaricInhPa=500).sortby('latitude', ascending=False).values
    grib_arr = gh_500 * _GRAVITY
    
    # ---- CHECKSUM MATH ----
    grib_mean = np.nanmean(grib_arr)
    parq_mean = np.nanmean(parq_arr)
    diff_mean = abs(grib_mean - parq_mean)
    
    print(f"[Upper QA] Checksum Global Promedio Grib: {grib_mean:.4f}")
    print(f"[Upper QA] Checksum Global Promedio Parquet: {parq_mean:.4f}")
    print(f"[Upper QA] Tolerancia Discrepancia Absoluta: {diff_mean:.3e}")
    if diff_mean > 1e-4:
        raise ValueError(f"CRITICAL ANOMALY: El modelo divergió matemáticamente más del límite {diff_mean:.3e}. Corrupción en Upper (z@500).")

    diff = np.abs(grib_arr - parq_arr)
    max_diff = np.nanmax(diff)
    print(f"[Upper] z@500 Max Diff: {max_diff}")
    
    if output_img:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        
        im0 = axes[0].imshow(grib_arr, cmap='viridis')
        axes[0].set_title('GRIB: z @ 500hPa')
        plt.colorbar(im0, ax=axes[0])
        
        im1 = axes[1].imshow(parq_arr, cmap='viridis')
        axes[1].set_title('Parquet: z @ 500hPa')
        plt.colorbar(im1, ax=axes[1])
        
        im2 = axes[2].imshow(diff, cmap='hot')
        axes[2].set_title(f'Abs Diff (Max: {max_diff:.3e})')
        plt.colorbar(im2, ax=axes[2])
        
        plt.tight_layout()
        plt.savefig(output_img)
        plt.close()
        print(f"[Upper] Generated Heatmap: {output_img}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Compara visualmente archivos GRIB contra Parquet.")
    parser.add_argument("--grib", required=True, help="Ruta al archivo GRIB (ej: local.grib2)")
    parser.add_argument("--parquet", required=True, help="Ruta al archivo parquet consolidado")
    parser.add_argument("--date", required=True, help="El parametro date para extraer la particion (ej: 20260330)")
    parser.add_argument("--run", required=True, help="El parametro run para extraer la particion (ej: 06z)")
    parser.add_argument("--out", default=".", help="Ruta de salida para las imágenes (opcional, omitir no guarda imgs)")
    parser.add_argument("--no-images", action="store_true", help="Desactiva la generación visual, ejecuta solo QA checksums")
    
    args = parser.parse_args()
    
    print("Loading GRIB...")
    grib_ds = load_merged_dataset(args.grib)
    
    parquet_path = Path(args.parquet)
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    sf_img = None if args.no_images else out_dir / f'compare_surface_t2m_{args.run}.png'
    up_img = None if args.no_images else out_dir / f'compare_upper_z500_{args.run}.png'
    
    if parquet_path.exists():
        compare_surface(grib_ds, parquet_path, sf_img, args.date, args.run)
        compare_upper(grib_ds, parquet_path, up_img, args.date, args.run)
    else:
        print(f"Error: {parquet_path} no existe.")
