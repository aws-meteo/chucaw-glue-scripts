# ECMWF Contract Stabilization (Codex)

## 1) Verdict

`READY_FOR_FOURCASTNET_RETRY`

Rationale: contract-focused tests passed after isolating Pangu/FourCastNet contracts from Platinum dynamic ingestion (`31 passed, 1 skipped, 1 deselected` on targeted run).

## 2) Contract map

### Platinum symbols
- `serialize_parquet_chunked` (`src/chucaw_preprocessor/ecmwf.py`): Platinum-only, dynamic/exhaustive over `ds.data_vars` and all present pressure levels.
- `build_parquet_frames` (`src/chucaw_preprocessor/ecmwf.py`): Platinum-only, now aligned to dynamic/exhaustive behavior.
- `_split_platinum_vars` (`src/chucaw_preprocessor/ecmwf.py`): Platinum-only internal splitter.

### Pangu symbols
- `build_pangu_arrays` (`src/chucaw_preprocessor/ecmwf.py`): Pangu-only strict tensor builder.
- `PANGU_SURFACE_VARS` (`src/chucaw_preprocessor/ecmwf.py`): Pangu-only explicit 4-channel surface contract.
- `PANGU_UPPER_VARS` (`src/chucaw_preprocessor/ecmwf.py`): Pangu-only explicit upper contract (plus `z` from `gh`).
- `EXPECTED_PRESSURE_LEVELS` (`src/chucaw_preprocessor/ecmwf.py`): shared constant, but strict usage in Pangu tensor path.

### FourCastNet symbols
- `FOURCASTNET_REQUIRED_CHANNELS` (`src/chucaw_preprocessor/fourcastnet.py`): FourCastNet-only explicit channel order contract.
- `build_fourcastnet_channel_map` (`src/chucaw_preprocessor/fourcastnet.py`): FourCastNet-only accessor over explicit required channels.
- `build_fourcastnet_tensor` (`src/chucaw_preprocessor/fourcastnet.py`): FourCastNet-only strict tensor constructor.

### Removed/shared ambiguous symbols
- `_SURFACE_VARS`: removed from active contract usage in `ecmwf.py`.
- `_UPPER_VARS`: removed from active contract usage in `ecmwf.py`.
- Previous ambiguity (single globals for multiple consumers) removed by explicit contract names and dynamic Platinum splitter.

## 3) r handling

### Present behavior before fix
- `r` existed in expanded upper globals but `build_parquet_frames` emitted only `z,q,t,u,v`, causing schema mismatch risk vs chunked serialization.

### Fixed behavior
- `build_parquet_frames` now serializes dynamically by discovered upper vars and includes `r` when present.
- If `r` is absent in source dataset, output does not include `r`.

### Explicit no-derivation statement
- No `q -> r` derivation was added in `ecmwf.py` Platinum or Pangu paths.

## 4) Pressure-level policy

### Platinum
- Policy: exhaustive. Serialize all available pressure levels for pressure-level variables.

### Pangu
- Policy: strict. Always select `EXPECTED_PRESSURE_LEVELS` and fixed channel contract.
- Extra Platinum levels do not alter Pangu tensor shape.

### FourCastNet
- Policy: strict explicit channel contract and order (`FOURCASTNET_REQUIRED_CHANNELS`).
- FourCastNet tensor path remains independent of Platinum dynamic variable expansion.

## 5) Tests

### Commands run
- `C:\ProgramData\miniconda3\envs\aws_backend\python.exe -m pytest tests/test_ecmwf_contracts.py tests/test_fourcastnet.py tests/test_fourcastnet_compatibility.py`
  - Result: 1 unrelated failure (`test_notebook_static_checker_detects_tensor_stage`) due to invalid notebook JSON.
- `C:\ProgramData\miniconda3\envs\aws_backend\python.exe -m pytest tests/test_ecmwf_contracts.py tests/test_fourcastnet.py tests/test_fourcastnet_compatibility.py -k "not notebook_static_checker_detects_tensor_stage"`
  - Result: `31 passed, 1 skipped, 1 deselected`.

### New/updated coverage relevant to this task
- `tests/test_ecmwf_contracts.py`
  - Pangu strict shape invariance with extra vars/levels.
  - Platinum `r` present/absent consistency.
  - Platinum extra pressure-level inclusion.
  - FourCastNet explicit contract tensor shape check on test grid.

### Files touched
- `src/chucaw_preprocessor/ecmwf.py`
- `src/chucaw_preprocessor/fourcastnet.py`
- `tests/test_ecmwf_contracts.py`
- `docs/fourcastnet/reports/ecmwf_contract_stabilization_codex.md`

## 6) Remaining blockers

- Unrelated test/doc blocker: `notebooks/fourcastnet_colab_smoke_test.ipynb` is invalid JSON for static checker test.
- Runtime data-side blockers still possible outside unit tests:
  - real ECMWF source may miss `r`, `sp`, or `tcwv` in some runs/products;
  - this is not synthesized in strict scientific paths and must be handled by downstream compatibility/guardrails policy.

## 7) Forbidden actions confirmation

- No Colab execution.
- No SageMaker calls.
- No AWS Glue execution.
- No broad real-data multi-date processing.
- No fabricated production outputs/tensors.
- No commit performed.
