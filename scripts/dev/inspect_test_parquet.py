import pandas as pd
import numpy as np
import json
from pathlib import Path

def inspect_parquet(path):
    print(f"\n--- Inspecting Parquet: {path} ---")
    df = pd.read_parquet(path)
    print(f"Columns: {df.columns.tolist()}")
    print(f"Row count: {len(df)}")
    
    # Normalize level column name
    lvl_col = "isobaricInhPa" if "isobaricInhPa" in df.columns else "isobaricinhpa"
    
    # Group by variable and list unique levels
    summary = {}
    v_counts = df["variable"].value_counts().to_dict()
    
    for var in df["variable"].unique():
        lvls = df[df["variable"] == var][lvl_col].unique()
        # Sort levels, handle NaNs (surface)
        lvls_sorted = sorted([float(l) for l in lvls if pd.notnull(l)], reverse=True)
        has_surface = df[(df["variable"] == var) & (df[lvl_col].isna())].shape[0] > 0
        summary[var] = {
            "count": int(v_counts[var]),
            "levels": lvls_sorted,
            "has_surface": has_surface
        }
    
    print(json.dumps(summary, indent=2))
    return summary

if __name__ == "__main__":
    p0 = "data/test_data/20260509180000-0h-scda-fc.parquet"
    if Path(p0).exists():
        inspect_parquet(p0)
    else:
        print(f"File not found: {p0}")
