# FourCastNet Colab Smoke Test (Tensor-First)

## HDF5 is optional
HDF5 is retained for compatibility/debug workflows, but it is not a model-level requirement. FourCastNet model code consumes in-memory float32 tensors.

## Tensor-first path
Primary smoke path:

`Parquet compatibility fixture -> input_tensor.npy/.pt -> tensor validation -> normalization -> direct PyTorch forward attempt -> structured report`

## When to use HDF5
- Reproducibility/debug snapshots.
- I/O compatibility checks with older NVlabs-style scripts.
- Bridge workflows that expect dataset `fields`.

## When to use direct tensor
- Mechanical execution smoke testing of model forward paths.
- Fast iteration without HDF5 serialization.
- Clear separation of model contract vs dataloader convention.

## How to generate input_tensor.npy
```powershell
$env:PYTHONPATH='src'
python scripts\dev\export_fourcastnet_tensor.py --INPUT_PARQUET tmp\fourcastnet_compat_real_v2\fcn_compat_20260409_18z.parquet --OUTPUT_DIR tmp\fourcastnet_tensor_real_v1 --LATITUDE_POLICY drop_south_pole --OUTPUT_FORMAT npy
```

## How to validate input_tensor.npy
```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR tmp\fourcastnet_tensor_real_v1\input_tensor.npy --OUTPUT_REPORT tmp\fourcastnet_tensor_real_v1\tensor_validation_report.json
```

Optional stats validation:
```powershell
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR tmp\fourcastnet_tensor_real_v1\input_tensor.npy --GLOBAL_MEANS path\to\global_means.npy --GLOBAL_STDS path\to\global_stds.npy --STATS_CHANNEL_POLICY first_20_channels --OUTPUT_REPORT tmp\fourcastnet_tensor_real_v1\tensor_validation_report_with_stats.json
```

## How to run direct tensor smoke locally
Dry-random mode is plumbing-only (never FourCastNet proof):
```powershell
$env:PYTHONPATH='src'
python scripts\dev\fourcastnet_direct_tensor_smoke.py --INPUT_TENSOR tmp\fourcastnet_tensor_real_v1\input_tensor.npy --GLOBAL_MEANS path\to\global_means.npy --GLOBAL_STDS path\to\global_stds.npy --CHECKPOINT path\to\backbone.ckpt --MODEL_BACKEND dry_random --ALLOW_RANDOM_MODEL true --OUTPUT_REPORT tmp\fourcastnet_tensor_real_v1\direct_tensor_smoke_report.json
```

## How to run Colab direct tensor smoke
Use `notebooks/fourcastnet_colab_smoke_test.ipynb`.

Notebook stages:
- `scientific_validity_warning`
- `tensor_schema_preflight`
- `normalization_preflight`
- `checkpoint_model_load_preflight`
- `direct_tensor_inference_attempt`
- `optional_hdf5_io_preflight`

## What counts as proof that FourCastNet runs
- Real backend (for example NVlabs-compatible AFNO path) loads and executes forward pass on normalized input tensor.
- Output tensor is finite and expected shape/channel contract is satisfied.

## What still does not prove scientific validity
- HDF5-valid means schema/I/O validity only.
- Tensor-valid means input tensor contract validity only.
- `dry_random` success means plumbing only.
- Real backend forward success means mechanical execution only.
- None of these imply meteorological trustworthiness when compatibility fixture proxies/derived channels are used.

## Files to upload to Colab
Preferred:
- `input_tensor.npy` or `input_tensor.pt`
- `global_means.npy`
- `global_stds.npy`
- `backbone.ckpt`

Optional:
- `tensor_manifest.json`
- `channel_provenance.json`
- `fcn_compat_20260409_18z.h5`
- `fcn_compat_20260409_18z.parquet`

## Expected Colab outcomes
- `colab_validation_report.json` is always written.
- If tensor schema/stats/model load fails, report captures exact failure stage/reason.
- If inference succeeds on real backend, report indicates mechanical execution success.
- If only dry/plumbing path succeeds, report keeps `fourcastnet_proven=false`.

## Cleanup large local files
- Keep generated artifacts under `tmp`.
- Do not commit generated Parquet/HDF5/tensor artifacts.

```powershell
Remove-Item -Recurse -Force tmp\fourcastnet_tensor_real_v1,tmp\fourcastnet_compat_real_v2,tmp\fourcastnet_strict_real_v2 -ErrorAction SilentlyContinue
```
