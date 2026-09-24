# Glue deployment configs (`glue/jobs/`)

One folder per AWS Glue job. Each folder is a self-contained **deployment unit**:

```
glue/jobs/<job-name>/
├── job.json            # aws glue create-job input (also the source of the update payload)
└── run.*.json          # optional aws glue start-job-run payloads (example runs)
```

The **folder name is the canonical Glue job name** and must match `job.json`'s `Name`.

| Folder / Glue job name | Script deployed | Pipeline stage |
|---|---|---|
| `bronze_to_platinum_as_parquet` | `scripts/glue_jobs/bronze_to_platinum_parquet.py` | Bronze GRIB2 → Platinum Parquet |
| `bronze_to_pangu` | `scripts/glue_jobs/bronze_to_pangu.py` | Bronze GRIB2 → Pangu `.npy` |
| `platinum_parquet_to_fourcastnet` | `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py` | Platinum Parquet → FourCastNet tensor |
| `cfsv2_monthly_bronze_to_silver` | `scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py` | CFSv2 Monthly Bronze GRIB2 → Silver Parquet |

## How `job.json` maps to a deploy

`Command.ScriptLocation` is the S3 URI the job script is uploaded to. The deploy tooling
takes the **basename** of that URI (e.g. `bronze_to_platinum_parquet.py`), uploads
`scripts/glue_jobs/<basename>` to that exact location, then creates or updates the job.

There is intentionally **no separate `update-job.json`**: the update payload is derived
from `job.json` at deploy time (`{JobName, JobUpdate: <job.json minus Name>}`), so there is
a single source of truth per job. See `scripts/deploy/deploy_glue_job.sh`.

## Deploying

- **CI:** the `Deploy Glue Jobs` GitHub Actions workflow (`.github/workflows/deploy-glue-jobs.yml`).
- **Local:** `scripts/deploy/deploy_glue_job.sh glue/jobs/<job-name>` (needs AWS creds;
  add `--dry-run` to print the commands without calling AWS).

## Notes / TODO before first real deploy

- **`bronze_to_pangu` and `platinum_parquet_to_fourcastnet`** were scaffolded from the
  Bronze→Platinum job as a template. Confirm before the first deploy:
  - `Role`, `WorkerType`/`NumberOfWorkers`, and `Timeout` suit each job
    (`platinum_parquet_to_fourcastnet` is memory-heavy — it may need larger workers).
  - `DefaultArguments`: the pangu job also needs per-run `--BRONZE_KEY`, `--DATE`, `--RUN`;
    the fourcastnet job needs per-run `--YEAR/--MONTH/--DAY/--HOUR`. These are passed at
    `start-job-run` time (the Step Functions orchestrator supplies them), not baked here.
  - The pangu job writes to a **silver** layer; `--SILVER_BUCKET`/`--SILVER_PREFIX`
    default to the platinum bucket under `ecmwf/pangu` — point these at the real silver
    bucket if one exists.
- The Step Functions orchestrator (`stepfunctions/`) starts
  `platinum_parquet_to_fourcastnet` by name — keep the folder/`Name` in sync with it.
