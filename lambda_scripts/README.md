Lambda and Step Functions assets for pipeline orchestration.

These files are local infrastructure definitions only. Do not run or deploy them
from this repository without a separate AWS change plan.

## aws_step_grib_to_parquet

Idempotent Bronze GRIB -> Platinum Parquet orchestration.

- `chucaw-clima-diff-finder.py`: Lambda handler that lists Bronze `.grib2`
  objects, maps each one to the expected Platinum Parquet key, and returns the
  missing Bronze keys as `pending_keys`.
- `state_machine.json`: Step Functions state machine that invokes the diff
  finder, exits when nothing is pending, or runs the Glue job
  `bronze_to_platinum_as_parquet` for each pending key.
- `IAM_policy.json`: Lambda list-bucket permissions for Bronze and Platinum.
- `step_function_role.json`: Step Functions permissions to invoke the diff
  finder and run the Bronze -> Platinum Glue job.

The Lambda defaults match the current Chucaw buckets and `ecmwf/parquet`
partition layout, but bucket and prefix values can be overridden through Lambda
environment variables or event fields:

- `BRONZE_BUCKET`
- `PLATINUM_BUCKET`
- `BRONZE_PREFIX`
- `PLATINUM_PREFIX`
- `BRONZE_SUFFIX`
- `PLATINUM_SUFFIX`

Other tracked Lambda handlers live in `src/parquet_prep_pipeline.py` and
`src/pangu_prep_pipeline.py`. They are direct preprocessing handlers and are not
required by this Step Functions backfill flow.
