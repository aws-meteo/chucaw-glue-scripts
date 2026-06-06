# Channel Contract Fix Codex: FourCastNet v0 Alignment

## 1. Verdict
**READY_FOR_COLAB**

## 2. What changed
- **Code**:
  - `src/chucaw_preprocessor/fourcastnet.py`: Updated `build_fourcastnet_channel_map` to match the official NVlabs FourCastNet v0 backbone order.
  - `scripts/dev/validate_fourcastnet_tensor.py`: Added support for `--STATS_CHANNEL_POLICY first_20_channels` to explicitly handle 21-channel stats files.
- **Docs**:
  - `docs/fourcastnet/preprocessing.md`: Updated channel order list and added notes on stats policy.
- **Tests**:
  - `tests/test_fourcastnet_compatibility.py`: Updated `test_channel_order_stable` with the new official order.
- **Artifacts regenerated**:
  - `data/fourcastnet_tensor_real_v1/input_tensor.npy` (re-exported with corrected order).
  - `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json` (validated with new policy).
  - `docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.json` (updated).
  - `docs/fourcastnet/reports/stats_tensor_alignment_diagnostic.md` (updated).

## 3. Official Channel Contract (NVlabs v0)
The backbone uses channels 0..19 in the following order:
0. u10 surface
1. v10 surface
2. t2m surface
3. sp surface
4. msl surface
5. t 850 hPa
6. u 1000 hPa
7. v 1000 hPa
8. z 1000 hPa
9. u 850 hPa
10. v 850 hPa
11. z 850 hPa
12. u 500 hPa
13. v 500 hPa
14. z 500 hPa
15. t 500 hPa
16. z 50 hPa
17. r 500 hPa
18. r 850 hPa
19. tcwv surface

*Note: SST (channel 20) in the original 21-channel stats files is NOT used by the backbone.*

## 4. Stats Policy
- **Policy**: `first_20_channels`
- **Reasoning**: NVlabs stats files have 21 channels because of a legacy SST variable. Since our tensor is now ordered exactly as the NVlabs 0..19 backbone contract, taking the first 20 channels of the stats file provides perfect alignment.

## 5. Validation Evidence
- **Command**: `python scripts/dev/validate_fourcastnet_tensor.py --INPUT_TENSOR data/fourcastnet_tensor_real_v1/input_tensor.npy --GLOBAL_MEANS data/fourcastnet_assets_v0/global_means.npy --GLOBAL_STDS data/fourcastnet_assets_v0/global_stds.npy --STATS_CHANNEL_POLICY first_20_channels --OUTPUT_REPORT data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
- **Report Path**: `data/fourcastnet_tensor_real_v1/tensor_validation_report_with_stats.json`
- **Results**:
  - `tensor_ok`: true
  - `stats_ok`: true
  - **Normalization Diagnostic**:
    - `abs(normalized_mean) > 10`: 0
    - `abs(normalized_mean) > 100`: 0
    - `abs(normalized_mean) > 1000`: 0
  - **Verdict**: PLAUSIBLE. Normalization anomalies in Geopotential and Temperature (previously reaching z-scores > 2000) are fully resolved.

## 6. Colab Package
- **Status**: Rebuilt and ready.
- **Location**: `data/fourcastnet_colab_upload_local/`
- **Files**:
  - `input_tensor.npy`
  - `tensor_manifest.json`
  - `global_means.npy`
  - `global_stds.npy`
  - `backbone.ckpt`
  - `fourcastnet_colab_smoke_test.ipynb`
  - `channel_provenance.json`
  - `fcn_compat_20260331_06z.parquet`

## 7. Forbidden Actions Confirmation
- No Colab run executed.
- No SageMaker call executed.
- No broad Glue run executed.
- No multiple-date processing executed.
- No tensor fabrication performed.
- No commit created.
