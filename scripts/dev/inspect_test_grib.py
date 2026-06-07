import cfgrib
import json
from pathlib import Path

def inspect_grib(path):
    print(f"\n--- Inspecting GRIB: {path} ---")
    try:
        datasets = cfgrib.open_datasets(path)
        for i, ds in enumerate(datasets):
            print(f"\nDataset {i}:")
            print(ds)
            # List data variables and their dimensions/coords
            for var in ds.data_vars:
                print(f"  Variable: {var}")
                if 'isobaricInhPa' in ds[var].coords:
                    print(f"    Levels: {ds[var].coords['isobaricInhPa'].values.tolist()}")
                elif 'level' in ds[var].coords:
                    print(f"    Level: {ds[var].coords['level'].values.tolist()}")
    except Exception as e:
        print(f"Error inspecting GRIB: {e}")

if __name__ == "__main__":
    g0 = "data/test_data/20260509180000-0h-scda-fc.grib2"
    if Path(g0).exists():
        inspect_grib(g0)
    else:
        print(f"File not found: {g0}")
