# FourCastNet Cleanup Commit Plan

This is a proposal only. No commits are created by this cleanup pass.

## Commit group 1: Core FourCastNet preprocessing contract
Files:
- `src/chucaw_preprocessor/fourcastnet.py`
- core validation tests directly tied to channel/grid contract

Purpose:
- Keep scientific/data contract logic isolated and reviewable.

## Commit group 2: Development artifact exporters and validators
Files:
- `scripts/dev/make_fourcastnet_compatibility_fixture.py`
- `scripts/dev/export_fourcastnet_tensor.py`
- `scripts/dev/validate_fourcastnet_tensor.py`
- `scripts/dev/fourcastnet_direct_tensor_smoke.py`
- `scripts/dev/export_fourcastnet_h5.py`
- `scripts/dev/validate_fourcastnet_h5.py`
- `scripts/dev/validate_colab_notebook_static.py`
- `scripts/dev/generate_fourcastnet_synthetic_parquet.py`

Purpose:
- Group local/Colab dev tooling for smoke and compatibility flows.

## Commit group 3: Glue/local operational scripts
Files:
- `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py`
- `scripts/glue_jobs/local_parquet_to_fourcastnet.py`
- `scripts/glue_jobs/audit_platinum_partition.py`
- job-related tests in `tests/test_fourcastnet_jobs.py`

Purpose:
- Keep AWS/Glue-facing entrypoints separate from dev-only tools.

## Commit group 4: Notebook and documentation
Files:
- `notebooks/fourcastnet_colab_smoke_test.ipynb`
- `docs/fourcastnet/README.md`
- `docs/fourcastnet/preprocessing.md`
- `docs/fourcastnet/colab_smoke_test.md`
- `docs/fourcastnet/artifact_inventory.md`
- `docs/fourcastnet/cleanup_commit_plan.md`

Purpose:
- Make user-facing procedures independently reviewable.

## Commit group 5: Test infrastructure and repository hygiene
Files:
- `tests/conftest.py`
- `.gitignore`
- any cleanup-only inventory/hygiene docs not included above

Purpose:
- Stabilize local test execution and prevent generated artifacts from polluting git.
