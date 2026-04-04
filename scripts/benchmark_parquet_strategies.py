import os
import gc
import sys
import time
import threading
import argparse
from pathlib import Path
import random

try:
    import psutil
    import numpy as np
    import pandas as pd
    import xarray as xr
    from scipy import stats
except ImportError as e:
    print(f"Faltan requerimientos de benchmark: {e}", file=sys.stderr)
    print("Corre: pip install psutil scipy numpy pandas xarray")
    sys.exit(1)

# Incorporar contexto local
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chucaw_preprocessor.ecmwf import (
    serialize_parquet_chunked, 
    load_merged_dataset, 
    EXPECTED_PRESSURE_LEVELS, 
    _SURFACE_VARS, 
    _UPPER_VARS, 
    _GRAVITY
)

# =========================================================================
# FUNCIONES DE MÉTODOLOGÍA LEGADA (ALTA MEMORIA) PARA COMPARACIÓN DIRECTA
# =========================================================================
def legacy_build_parquet_frames(ds: xr.Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    surface = ds[_SURFACE_VARS].to_array("variable").rename("value").to_dataframe().reset_index()
    surface["value"] = surface["value"].astype("float32")

    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    upper = xr.Dataset({
        "z": ds_pl["gh"] * _GRAVITY,
        "q": ds_pl["q"],
        "t": ds_pl["t"],
        "u": ds_pl["u"],
        "v": ds_pl["v"],
    })
    upper = upper.to_array("variable").rename("value").to_dataframe().reset_index()
    upper["value"] = upper["value"].astype("float32")
    return surface, upper

def legacy_write_parquet_frames(surface_df: pd.DataFrame, upper_df: pd.DataFrame, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    surface_path = str(Path(output_dir) / "surface.parquet")
    upper_path = str(Path(output_dir) / "upper.parquet")
    surface_df.to_parquet(surface_path, index=False, compression="snappy")
    upper_df.to_parquet(upper_path, index=False, compression="snappy")


# =========================================================================
# MONITOR DE PROCESO DE MÁXIMO CONSUMO DE MEMORIA SO (RESIDENT SET SIZE)
# =========================================================================
stop_monitor = False

def memory_monitor(pid, interval=0.02, results_list=None):
    global stop_monitor
    process = psutil.Process(pid)
    max_mem = 0
    while not stop_monitor:
        try:
            mem = process.memory_info().rss
            if mem > max_mem:
                max_mem = mem
        except Exception:
            pass
        time.sleep(interval)
    if results_list is not None:
        results_list.append(max_mem)

def profile_execution(func, *args, **kwargs):
    global stop_monitor
    
    # Forzar recolección de basura para evitar memoria sucia 100% de la vez.
    gc.collect()
    time.sleep(0.5) 
    
    stop_monitor = False
    mem_results = []
    pid = os.getpid()
    
    # Captura la RAM basal después de limpiar
    basal_memory = psutil.Process(pid).memory_info().rss
    
    monitor_thread = threading.Thread(target=memory_monitor, args=(pid, 0.05, mem_results))
    monitor_thread.start()
    
    start_time = time.perf_counter()
    
    try:
         func(*args, **kwargs)
         success = True
    except Exception as e:
         print(f"💥 Fallo crítico (Ej OOM Killer si es dockerizado): {e}")
         success = False
         
    end_time = time.perf_counter()
    
    stop_monitor = True
    monitor_thread.join()
    
    gc.collect()
    
    final_peak = mem_results[0] if mem_results else basal_memory
    
    return {
        "success": success,
        "duration_sec": end_time - start_time,
        "peak_rss_mb": final_peak / (1024 * 1024)
    }

# =========================================================================
# RUNNERS INSTANCIADOS 
# =========================================================================
def run_legacy(grib_path, out_dir):
    ds = load_merged_dataset(grib_path)
    sdf, udf = legacy_build_parquet_frames(ds)
    sdf["date"] = "20261231"
    sdf["run"] = "00z"
    udf["date"] = "20261231"
    udf["run"] = "00z"
    legacy_write_parquet_frames(sdf, udf, out_dir)

def run_chunked(grib_path, out_dir):
    ds = load_merged_dataset(grib_path)
    serialize_parquet_chunked(ds, out_dir, "20261231", "00z")


# =========================================================================
# GESTIÓN ESTADÍSTICA DE MUESTRAS
# =========================================================================
def calculate_stats(data_list):
    if not data_list:
        return {"mean": 0, "std": 0, "ci_lower": 0, "ci_upper": 0, "n": 0}
        
    arr = np.array(data_list)
    mean = np.mean(arr)
    std = np.std(arr, ddof=1) if len(arr) > 1 else 0
    n = len(arr)
    
    if n > 1:
        se = std / np.sqrt(n)
        ci_95 = stats.t.interval(0.95, n-1, loc=mean, scale=se)
    else:
        ci_95 = (mean, mean)
        
    return {
        "mean": mean,
        "std": std,
        "ci_lower": ci_95[0],
        "ci_upper": ci_95[1],
        "n": n
    }

def print_table(results):
    output_text = "\n" + "="*85 + "\n"
    output_text += f"{'Method':<20} | {'Metric':<15} | {'Mean':<10} | {'Std Dev':<10} | {'95% CI':<20}\n"
    output_text += "-" * 85 + "\n"
    
    for method in ["Legacy (InMemory)", "PyArrow (Chunked)"]:
        if method not in results:
            continue
            
        metrics = results[method]
        d_mean = metrics["duration"]["mean"]
        d_std = metrics["duration"]["std"]
        d_ci = f"({metrics['duration']['ci_lower']:.2f}, {metrics['duration']['ci_upper']:.2f})"
        
        m_mean = metrics["memory"]["mean"]
        m_std = metrics["memory"]["std"]
        m_ci = f"({metrics['memory']['ci_lower']:.1f}, {metrics['memory']['ci_upper']:.1f})"
        
        output_text += f"{method:<20} | {'Duration (s)':<15} | {d_mean:<10.2f} | {d_std:<10.2f} | {d_ci:<20}\n"
        output_text += f"{' '*20} | {'Peak RSS (MB)':<15} | {m_mean:<10.1f} | {m_std:<10.1f} | {m_ci:<20}\n"
        output_text += "-" * 85 + "\n"
        
    print(output_text)
    Path("benchmark_results.txt").write_text(output_text)

# =========================================================================
# ORQUESTADOR PRINCIPAL
# =========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grib-dir", default="scripts/glue_jobs/test_grib", help="Carpeta de muestras GRIB")
    parser.add_argument("--samples", type=int, default=10, help="N° de iteraciones")
    parser.add_argument("--out", default="test_output_parquet", help="Destino temporal")
    args = parser.parse_args()
    
    grib_dir = Path(args.grib_dir)
    grib_files = list(grib_dir.glob("*.grib2"))
    
    if not grib_files:
        print(f"No se detectaron archivos .grib2 en {grib_dir}. Abortando.")
        sys.exit(1)
        
    print(f"🚀 Iniciando rigurosa evaluación local sobre {len(grib_files)} archivos base.")
    print(f"🔄 Se correrán {args.samples} muestras garantizando el flush de la RAM vía GC.\n")
    
    out_dir = Path(args.out)
    os.makedirs(out_dir, exist_ok=True)
    
    raw_results = {
        "Legacy (InMemory)": {"durations": [], "memories": []},
        "PyArrow (Chunked)": {"durations": [], "memories": []}
    }
    
    for i in range(args.samples):
        target_grib = str(random.choice(grib_files))
        print(f"Iteración {i+1}/{args.samples} usando: {Path(target_grib).name}")
        
        # Test 1: CHUNKED
        print("  ▶ PyArrow (Chunked) ... ", end="", flush=True)
        res_chunk = profile_execution(run_chunked, target_grib, str(out_dir))
        if res_chunk["success"]:
            print(f"Ok. ({res_chunk['duration_sec']:.2f}s | {res_chunk['peak_rss_mb']:.1f} MB)")
            raw_results["PyArrow (Chunked)"]["durations"].append(res_chunk["duration_sec"])
            raw_results["PyArrow (Chunked)"]["memories"].append(res_chunk["peak_rss_mb"])
        
        # Test 2: LEGACY
        print("  ▶ Legacy (InMemory) ... ", end="", flush=True)
        res_leg = profile_execution(run_legacy, target_grib, str(out_dir))
        if res_leg["success"]:
            print(f"Ok. ({res_leg['duration_sec']:.2f}s | {res_leg['peak_rss_mb']:.1f} MB)")
            raw_results["Legacy (InMemory)"]["durations"].append(res_leg["duration_sec"])
            raw_results["Legacy (InMemory)"]["memories"].append(res_leg["peak_rss_mb"])
            
    print("\n⏳ Calculando promedios y varianzas (95% CI)...")
    
    final_stats = {}
    for method in raw_results:
        final_stats[method] = {
            "duration": calculate_stats(raw_results[method]["durations"]),
            "memory": calculate_stats(raw_results[method]["memories"])
        }
        
    print_table(final_stats)
