#!/bin/bash
export PYTHONPATH=/build/python
python3 -c "import xarray; import cfgrib; import eccodes; print('xarray:', xarray.__version__); print('cfgrib:', cfgrib.__version__); print('eccodes:', eccodes.__version__); print('API:', eccodes.codes_get_api_version()); print('=== PASSED ===')"
