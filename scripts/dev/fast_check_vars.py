import pandas as pd
from pathlib import Path

def check_vars(path):
    print(f"\n--- Checking variables in: {path} ---")
    # Only read the 'variable' column to be efficient
    df = pd.read_parquet(path, columns=["variable"])
    unique_vars = df["variable"].unique().tolist()
    print(f"Unique variables: {unique_vars}")
    
    # Check for target variables
    targets = ["sp", "tcwv", "r"]
    found = [v for v in targets if v in unique_vars]
    missing = [v for v in targets if v not in unique_vars]
    
    print(f"Found targets: {found}")
    if missing:
        print(f"MISSING targets: {missing}")
    else:
        print("All targets found!")

if __name__ == "__main__":
    p = "tmp/exhaustive_test/20260509180000-0h-scda-fc.parquet"
    if Path(p).exists():
        check_vars(p)
    else:
        print(f"File not found: {p}")
