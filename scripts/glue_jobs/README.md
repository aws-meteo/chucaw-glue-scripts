# Glue job scripts

Entry-point scripts for the AWS Glue jobs, in pipeline order. All jobs are **pure Python**
(boto3 + `xarray`/`cfgrib`/`pandas`/`pyarrow`) built on the `chucaw_preprocessor` library;
they run on **Glue 5.0 / Python 3.11** as `glueetl`. Data flows
**Bronze (GRIB2) → Platinum (Parquet) → model tensors**.

| # | Script | Stage | In → Out | Deploy config |
|---|---|---|---|---|
| 1 | [`bronze_to_platinum_parquet.py`](bronze_to_platinum_parquet.py) | Bronze → Platinum | GRIB2 → tidy Parquet (partitioned) | [`glue/jobs/bronze_to_platinum_as_parquet/`](../../glue/jobs/bronze_to_platinum_as_parquet/) |
| 2 | [`bronze_to_pangu.py`](bronze_to_pangu.py) | Bronze → Silver | GRIB2 → Pangu `input_surface.npy` + `input_upper.npy` | [`glue/jobs/bronze_to_pangu/`](../../glue/jobs/bronze_to_pangu/) |
| 3 | [`platinum_parquet_to_fourcastnet.py`](platinum_parquet_to_fourcastnet.py) | Platinum → FourCastNet | Parquet partition → FCN tensor `.npy` + reports | [`glue/jobs/platinum_parquet_to_fourcastnet/`](../../glue/jobs/platinum_parquet_to_fourcastnet/) |
| 4 | [`audit_platinum_partition.py`](audit_platinum_partition.py) | audit (read-only) | Parquet partition → readiness JSON/CSV | — (run on demand) |

## Arguments

Passed as Glue job args (`--NAME value`) and resolved by
`chucaw_preprocessor.glue_args.resolve_args`, which also works locally via argparse.

- **1 · bronze_to_platinum_parquet** — buckets/prefixes have defaults; select the source
  with `--BRONZE_KEY`, or `--DATE`+`--RUN`, or let it auto-discover the latest `.grib2`.
- **2 · bronze_to_pangu** — required: `--BRONZE_BUCKET --BRONZE_KEY --SILVER_BUCKET
  --SILVER_PREFIX --DATE --RUN` (optional `--TMP_DIR`).
- **3 · platinum_parquet_to_fourcastnet** — required: `--YEAR --MONTH --DAY --HOUR`
  (buckets/prefixes and contract options are optional). Memory-optimized for large
  `oper` partitions.
- **4 · audit_platinum_partition** — reads one Platinum partition and writes reports
  locally; never writes tensors.

## `local/` — local dev variants

Not deployed to Glue. Run against local files for fast iteration:

- [`local/local_grib_to_platinum_parquet.py`](local/local_grib_to_platinum_parquet.py) —
  local GRIB → local Parquet (`--GRIB_PATH`, optional `--SUBSET` 10×10 fast grid).
- [`local/local_parquet_to_fourcastnet.py`](local/local_parquet_to_fourcastnet.py) —
  single local Parquet → local tensor + reports (`--PARQUET_PATH`, `--ALLOW_TEST_GRID`).

## Deploying

See [`glue/README.md`](../../glue/README.md). In short:
`scripts/deploy/deploy_glue_job.sh glue/jobs/<job-name>` (or the `Deploy Glue Jobs`
GitHub Actions workflow) uploads the script to S3 and creates/updates the job.
