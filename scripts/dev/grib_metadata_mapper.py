import cfgrib
from pathlib import Path

def inspect_all_metadata(path):
    print(f"\n--- Exhaustive GRIB Metadata Inspection: {path} ---")
    try:
        datasets = cfgrib.open_datasets(path)
        all_vars = {}
        for i, ds in enumerate(datasets):
            for var_name in ds.data_vars:
                var = ds[var_name]
                attrs = var.attrs
                all_vars[var_name] = {
                    "long_name": attrs.get("long_name", "N/A"),
                    "units": attrs.get("units", "N/A"),
                    "standard_name": attrs.get("standard_name", "N/A"),
                    "dataset_index": i,
                    "dims": list(var.dims)
                }
        
        # Sort and print
        import json
        print(json.dumps(all_vars, indent=2))
        
        # Suggest expressive mapping
        print("\n--- Suggested Expressive Mapping ---")
        for k, v in all_vars.items():
            clean_name = v['long_name'].lower().replace(" ", "_").replace("-", "_")
            print(f"'{k}': '{clean_name}',")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    g0 = "data/test_data/20260509180000-0h-scda-fc.grib2"
    if Path(g0).exists():
        inspect_all_metadata(g0)
    else:
        print(f"File not found: {g0}")
