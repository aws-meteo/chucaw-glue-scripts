#!/bin/bash
set -e
echo "=== REBUILDING (keeping metadata) ==="
rm -rf /build/python /build/glue-dependencies.zip

pip3 install --target /build/python xarray cfgrib eccodes 2>&1 | tail -3

# Only remove caches, NOT dist-info
find /build/python -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /build/python -type d -name tests -exec rm -rf {} + 2>/dev/null || true

cd /build/python
zip -qr /build/glue-dependencies.zip .
ls -lh /build/glue-dependencies.zip
echo "=== DONE ==="
