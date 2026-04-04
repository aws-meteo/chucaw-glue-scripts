#!/bin/bash
pip3 install -q xarray cfgrib eccodes 2>/dev/null

python3 << 'EOF'
import xarray
import cfgrib
import eccodes
import numpy as np

print("=== IMPORTS ===")
print(f"xarray: {xarray.__version__}")
print(f"cfgrib: {cfgrib.__version__}")
print(f"eccodes: {eccodes.__version__}")
print(f"numpy: {np.__version__}")

print("\n=== FUNCTIONAL ===")
import xarray as xr
ds = xr.Dataset({"t": (["x"], np.array([1,2,3]))})
print(f"xarray dataset: OK")

api = eccodes.codes_get_api_version()
print(f"eccodes API: {api}")

from cfgrib import messages
print(f"cfgrib messages: OK")

print("\n=== ALL TESTS PASSED ===")
EOF
