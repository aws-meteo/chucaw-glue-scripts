# FourCastNet Pre-Colab Hygiene Report

## 1. Verdict
- `PARTIAL`
- Reason: repository/package hygiene checks passed, but stats-to-tensor channel alignment remains ambiguous (`21` stats channels vs `20` tensor channels), and validator now correctly blocks silent normalization until manual mapping is confirmed.

## 2. Git hygiene
- `git status --short` shows a pre-existing dirty tree with many unrelated modifications/untracked paths.
- `.gitignore` was minimally updated to protect FourCastNet heavy local artifacts:
  - `data/fourcastnet_assets_v0/`
  - `data/fourcastnet_colab_upload_local/`
  - `data/fourcastnet_aws_download_*/`
  - `data/fourcastnet_tensor_real_v1/*.npy`
  - `*.ckpt`
  - `*.h5`
  - `*.pt`
- `git check-ignore -v` results:
  - `data\fourcastnet_assets_v0\backbone.ckpt` -> ignored by `.gitignore:256`
  - `data\fourcastnet_colab_upload_local\backbone.ckpt` -> ignored by `.gitignore:257`
  - `data\fourcastnet_colab_upload_local\input_tensor.npy` -> ignored by `.gitignore:257`
- No commit was created.
- Note: if any artifact was already tracked in Git history/index, `.gitignore` alone does not untrack it (`git rm --cached` would be required, not run here).

## 3. Package hygiene
- Removed stale contradiction file:
  - `data/fourcastnet_colab_upload_local/missing_assets_report.json` (deleted)
- Colab upload package completeness check:
  - present: `input_tensor.npy` (`82,944,128` bytes)
  - present: `tensor_manifest.json` (`1,536` bytes)
  - present: `global_means.npy` (`296` bytes)
  - present: `global_stds.npy` (`296` bytes)
  - present: `backbone.ckpt` (`896,430,597` bytes)
  - present: `fourcastnet_colab_smoke_test.ipynb` (`13,012` bytes)

## 4. Stats/tensor alignment
- Tensor shape: `[1, 20, 720, 1440]`
- Stats original shapes:
  - `global_means.npy`: `[1, 21, 1, 1]`
  - `global_stds.npy`: `[1, 21, 1, 1]`
- Candidate comparison from `docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.json`:
  - `0:20` summary:
    - `abs(normalized_mean) > 10`: `7`
    - `abs(normalized_mean) > 100`: `4`
    - `abs(normalized_mean) > 1000`: `3`
  - `1:21` summary:
    - `abs(normalized_mean) > 10`: `7`
    - `abs(normalized_mean) > 100`: `2`
    - `abs(normalized_mean) > 1000`: `2`
- Heuristic result: `channels_1_to_20` looked less extreme, but this is not a scientific contract.
- Chosen validator policy: `manual_required` (conservative).
- Explicit warning: alignment is not accepted as a normal success; manual channel contract confirmation is required before normalized stats can be trusted.

## 5. Validation
- Command run:
  - `python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR data\fourcastnet_tensor_real_v1\input_tensor.npy --GLOBAL_MEANS data\fourcastnet_assets_v0\global_means.npy --GLOBAL_STDS data\fourcastnet_assets_v0\global_stds.npy --OUTPUT_REPORT data\fourcastnet_tensor_real_v1\tensor_validation_report_with_stats.json`
- Output report:
  - `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
- Results:
  - `tensor_ok=true`
  - `stats_ok=false`
  - `ok=false`
- Warnings/metadata included in report:
  - `means_metadata.stats_original_shape`
  - `means_metadata.stats_channels_original`
  - `means_metadata.stats_channels_used`
  - `means_metadata.stats_channel_policy=manual_required`
  - `means_metadata.stats_channel_policy_warning`
  - same metadata block for stds.

## 6. Files changed
- `.gitignore`
  - Added minimal ignore rules for FourCastNet heavy/local artifacts.
- `scripts/dev/validate_fourcastnet_tensor.py`
  - Replaced silent channel slicing with explicit policy metadata and conservative `manual_required` failure on ambiguous 21->20 mapping.
- `data/fourcastnet_colab_upload_local/missing_assets_report.json`
  - Removed stale contradiction (assets now present).
- `docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.md`
  - Added human-readable candidate comparison and per-channel table.
- `docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.json`
  - Added machine-readable candidate diagnostics and anomaly counts.
- `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
  - Rewritten by validator rerun; now includes explicit stats-policy metadata.
- `docs/fourcastnet/reports/full_test_hygiene_codex.md`
  - Added this hygiene run report.

## 7. Forbidden actions confirmation
- No Colab run executed.
- No SageMaker call executed.
- No broad Glue run executed.
- No multiple-date processing executed.
- No tensor fabrication performed.
- No commit created.

