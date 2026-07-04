# FourCastNet Artifact Inventory

## Source code files
- `src/chucaw_preprocessor/fourcastnet.py`
- `src/chucaw_preprocessor/__init__.py`

## Dev scripts
- `scripts/dev/make_fourcastnet_compatibility_fixture.py`
- `scripts/dev/export_fourcastnet_tensor.py`
- `scripts/dev/validate_fourcastnet_tensor.py`
- `scripts/dev/fourcastnet_direct_tensor_smoke.py`
- `scripts/dev/export_fourcastnet_h5.py`
- `scripts/dev/validate_fourcastnet_h5.py`
- `scripts/dev/validate_colab_notebook_static.py`
- `scripts/dev/generate_fourcastnet_synthetic_parquet.py`

## Glue scripts
- `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py`
- `scripts/glue_jobs/local/local_parquet_to_fourcastnet.py`
- `scripts/glue_jobs/audit_platinum_partition.py`

## Notebook
- `notebooks/fourcastnet_colab_smoke_test.ipynb`

## Docs
- `docs/fourcastnet/README.md`
- `docs/fourcastnet/preprocessing.md`
- `docs/fourcastnet/colab_smoke_test.md`
- `docs/fourcastnet/artifact_inventory.md`
- `docs/fourcastnet/cleanup_commit_plan.md`

## Tests
- `tests/test_fourcastnet.py`
- `tests/test_fourcastnet_jobs.py`
- `tests/test_fourcastnet_compatibility.py`
- `tests/conftest.py`

## Generated artifacts (local only)
- `tmp/**` manifests/reports/parquet/h5/tensors
- pytest temp/cache directories under `tmp/`
- HDF5/tensor outputs from dev scripts (`*.h5`, `*.pt`, `*.npy` in local output folders)

## Ignored artifacts
- `tmp/`
- `tmp_fcn_pytest/`
- `graphify-out/`
- `*.parquet` (already ignored)
- `*.h5`
- `*.pt`

## Candidate stale files (not auto-deleted)
- `boulder.json` (repo root)
- `scratch/`
- `lambda_scripts/`

## Notes
- Production GRIB-to-Parquet paths remain untouched.
- HDF5 path remains available but optional.
- Tensor-first path remains primary smoke path.
- Compatibility fixture remains `NOT_SCIENTIFICALLY_VALID`.
