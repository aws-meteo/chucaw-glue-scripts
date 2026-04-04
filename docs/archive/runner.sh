#!/bin/bash
cd /workspace
pip install -q psutil scipy
python3 scripts/benchmark_parquet_strategies.py --samples 5 > my_results.log 2>&1
