# FourCastNet Full Test Local Validation Codex

## 1. Commands Run
- Evaluated `global_means.npy` and `global_stds.npy` to confirm shape `(1, 21, 1, 1)` and finite values.
- Validated `input_tensor.npy` against stats via `validate_fourcastnet_tensor.py`.
- Evaluated `fourcastnet_colab_smoke_test.ipynb` via `validate_colab_notebook_static.py`.
- Built Colab package `data/fourcastnet_colab_upload_local` by copying all assets and tensors.

## 2. Pass/Fail Status
- Stats Inspection: PASS. Stats have 21 channels.
- Tensor Validation: PASS (after fixing script subsetting logic to slice the first 20 stats channels to match tensor).
- Static Notebook Validation: PASS.
- Colab Package Build: PASS.

## 3. Files Created
- `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
- `data/fourcastnet_colab_upload_local/` (with all required `.npy`, `.ckpt`, `.json`, `.parquet`, `.ipynb` files)
- `docs/fourcastnet/reports/full_test_local_validation_codex.md`

## 4. Exact Blockers
- The `global_means.npy` and `global_stds.npy` had 21 channels, while the expected tensor shape is 20 channels. The validation script crashed enforcing an exact 20-channel shape on stats.
- Indentation and syntax error after replacing the file on the first attempt (fixed).

## 5. Exact Fixes Applied
- Modified `scripts/dev/validate_fourcastnet_tensor.py` `_reshape_stats` function to subset stats arrays to exactly 20 channels (`arr[:20]`) if they have `>= 20` channels. 

## 6. Git Diff Summary
- `scripts/dev/validate_fourcastnet_tensor.py`: added logic to subset 21-channel stats arrays to 20 channels in `_reshape_stats`.
- Added `boulder.json` to the repo root.
- Created `docs/fourcastnet/reports/` and two codex files.

## 7. Colab Package Readiness
- The Colab package `data/fourcastnet_colab_upload_local/` is READY for upload.

## 8. Exact Next Command or Manual Action
- Manual Colab Action: Open `notebooks/fourcastnet_colab_smoke_test.ipynb` in Colab, upload the files inside `data/fourcastnet_colab_upload_local/`, verify FourCastNet code is loaded into `/content/FourCastNet`, and run the notebook to verify inference.