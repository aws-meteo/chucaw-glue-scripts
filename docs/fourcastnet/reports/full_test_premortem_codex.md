# FourCastNet Full Test Pre-Mortem Codex

## 1. Current Repo State
- Git status audited: `data/` and `docs/fourcastnet/` are untracked but not staged. No large data files are staged.
- The `boulder.json` file was created but is untracked.

## 2. Asset Existence & Size Check
- `data/fourcastnet_assets_v0/backbone.ckpt`: ~896 MB (Exists)
- `data/fourcastnet_assets_v0/global_means.npy`: 296 B (Exists)
- `data/fourcastnet_assets_v0/global_stds.npy`: 296 B (Exists)
- `data/fourcastnet_tensor_real_v1/input_tensor.npy`: ~83 MB (Exists)
- `data/fourcastnet_colab_upload_local`: Directory exists and contains artifacts from prior runs (e.g., `.ipynb`, `missing_assets_report.json`).

## 3. Exact Next Commands to Run
1. Verify numpy properties of `global_means.npy` and `global_stds.npy` (shape, finite, min/max).
2. Validate local tensor with stats:
   ```powershell
   $env:PYTHONPATH='src'
   python scripts/dev/validate_fourcastnet_tensor.py --INPUT_TENSOR data/fourcastnet_tensor_real_v1/input_tensor.npy --GLOBAL_MEANS data/fourcastnet_assets_v0/global_means.npy --GLOBAL_STDS data/fourcastnet_assets_v0/global_stds.npy --OUTPUT_REPORT data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json
   ```
3. Run static notebook validation:
   ```powershell
   python scripts/dev/validate_colab_notebook_static.py
   ```

## 4. Blockers Identified
- None yet. Possible stats mismatch (20 vs 24 channels) expected during validation.

## 5. Allowed Fixes
- Fix CLI argument mismatches.
- Fix path handling issues.
- Adjust overly strict stats shape handling if scientifically defensible (e.g. subsetting).
- Fix missing report fields.
- Fix notebook path mismatch.

## 6. Forbidden Changes
- Fabricating data.
- Modifying production GRIB-to-parquet paths.
- Claiming success without evidence files.

## 7. Evidence Files Expected Next
- `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
- `docs/fourcastnet/reports/full_test_local_validation_codex.md`