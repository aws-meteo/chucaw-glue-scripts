#!/bin/bash
set -e

echo "Installing dependencies..."
pip3 install --quiet xarray==2024.2.0 cfgrib==0.9.14.1 eccodes==2.42.0 2>/dev/null

echo "Running verification..."
python3 << 'PYEOF'
import sys

# Quick import test
deps = [("xarray", "2024"), ("cfgrib", "0.9"), ("eccodes", "2."), ("numpy", "1."), ("pandas", "1."), ("pyarrow", "10.")]
failed = []
for name, ver_prefix in deps:
    try:
        m = __import__(name)
        v = getattr(m, "__version__", "?")
        status = "OK" if v.startswith(ver_prefix) else f"WARN({v})"
        print(f"[{status}] {name} {v}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        failed.append(name)

# Functional test
print("\n--- Functional Tests ---")
import xarray as xr
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Test 1: xarray operations
ds = xr.Dataset({"temp": (["x","y"], np.random.rand(100,100).astype(np.float32))})
mean_val = float(ds["temp"].mean())
print(f"[OK] xarray: dataset mean = {mean_val:.4f}")

# Test 2: pandas/pyarrow roundtrip
df = pd.DataFrame({"a": range(1000), "b": np.random.rand(1000)})
import tempfile, os
with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
    path = f.name
df.to_parquet(path)
df2 = pd.read_parquet(path)
os.unlink(path)
print(f"[OK] parquet: roundtrip {len(df2)} rows")

# Test 3: eccodes bindings
import eccodes
api_ver = eccodes.codes_get_api_version()
print(f"[OK] eccodes: API version {api_ver}")

# Test 4: cfgrib module structure
from cfgrib import messages
print(f"[OK] cfgrib: messages module loaded")

if failed:
    print(f"\nFAILED: {failed}")
    sys.exit(1)
else:
    print("\n=== ALL TESTS PASSED ===")
    sys.exit(0)
PYEOF
