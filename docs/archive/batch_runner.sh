#!/bin/bash
cd /workspace
pip install -q matplotlib
bash scripts/batch_process_gribs.sh > batch_QA_results.txt 2>&1
