# FourCastNet One-Partition Operational Runbook

Scope: run exactly one partition (`2026-04-09 18`) for:
- Task A: local Colab package from local tensor
- Task B: AWS-side validation/run path for one real Platinum partition

Do not run broad jobs, do not process multiple dates, and do not call SageMaker.

## 0) Environment and auth

```powershell
Set-Location C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts
$env:PYTHONPATH='src'
$env:AWS_PROFILE='sbnai-725'
```

If your SSO token is expired:

```powershell
aws sso login --profile sbnai-725
```

Confirm identity:

```powershell
aws sts get-caller-identity --profile sbnai-725
```

## 1) Phase 1: inspect current state

```powershell
git status --short
Get-ChildItem docs\fourcastnet
Get-ChildItem scripts\dev
Get-ChildItem scripts\glue_jobs
Get-ChildItem data\\fourcastnet_tensor_real_v1 -ErrorAction SilentlyContinue
Get-ChildItem data\\fourcastnet_compat_real_v2 -ErrorAction SilentlyContinue
```

Validate existing local tensor:

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR data\\fourcastnet_tensor_real_v1\input_tensor.npy --OUTPUT_REPORT data\\fourcastnet_tensor_real_v1\tensor_validation_report_before_colab.json
```

If `data\\fourcastnet_tensor_real_v1\input_tensor.npy` is missing, regenerate:

```powershell
$env:PYTHONPATH='src'
python scripts\dev\export_fourcastnet_tensor.py --INPUT_PARQUET data\\fourcastnet_compat_real_v2\fcn_compat_20260409_18z.parquet --OUTPUT_DIR data\\fourcastnet_tensor_real_v1 --LATITUDE_POLICY drop_south_pole --OUTPUT_FORMAT npy --FORCE true
```

## 2) Phase 2: Task A (local Colab package)

Create upload directory and copy required files:

```powershell
New-Item -ItemType Directory -Path data\\fourcastnet_colab_upload_local -Force | Out-Null
Copy-Item data\\fourcastnet_tensor_real_v1\input_tensor.npy data\\fourcastnet_colab_upload_local -Force
Copy-Item data\\fourcastnet_tensor_real_v1\tensor_manifest.json data\\fourcastnet_colab_upload_local -Force
Copy-Item data\\fourcastnet_compat_real_v2\channel_provenance.json data\\fourcastnet_colab_upload_local -Force
Copy-Item notebooks\fourcastnet_colab_smoke_test.ipynb data\\fourcastnet_colab_upload_local -Force
```

Search local stats/checkpoint files:

```powershell
Get-ChildItem -Recurse .. -Include global_means.npy,global_stds.npy,backbone.ckpt -ErrorAction SilentlyContinue
```

If found, copy them:

```powershell
Copy-Item <PATH_TO_global_means.npy> data\\fourcastnet_colab_upload_local -Force
Copy-Item <PATH_TO_global_stds.npy>  data\\fourcastnet_colab_upload_local -Force
Copy-Item <PATH_TO_backbone.ckpt>    data\\fourcastnet_colab_upload_local -Force
```

If missing, write report:

```powershell
@'
{
  "missing_assets": ["global_means.npy", "global_stds.npy", "backbone.ckpt"]
}
'@ | Set-Content data\\fourcastnet_colab_upload_local\missing_assets_report.json -Encoding UTF8
```

Quick check:

```powershell
Get-ChildItem data\\fourcastnet_colab_upload_local
Get-Content data\\fourcastnet_tensor_real_v1\tensor_validation_report_before_colab.json
```

## 3) Phase 3: AWS CLI preflight

```powershell
$env:AWS_PROFILE='sbnai-725'
aws sts get-caller-identity --profile sbnai-725
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/ --profile sbnai-725
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/hour=18/ --profile sbnai-725
```

Diagnostic only if `hour=18` is missing:

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/hour=18z/ --profile sbnai-725
```

## 4) Phase 4: AWS-side audit (script against S3)

```powershell
$env:AWS_PROFILE='sbnai-725'
$env:PYTHONPATH='src'
python scripts\glue_jobs\audit_platinum_partition.py --PLATINUM_BUCKET chucaw-data-platinum-processed-725644097028-us-east-1-an --PLATINUM_PARQUET_PREFIX ecmwf/parquet --YEAR 2026 --MONTH 04 --DAY 09 --HOUR 18 --OUTPUT_DIR data\\fourcastnet_aws_audit_2026_04_09_18
```

Expected outputs in `data\\fourcastnet_aws_audit_2026_04_09_18`:
- `available_variables.json`
- `available_variable_levels.csv`
- `validation_report.json`

## 5) Phase 5: Glue job decision

Discover candidate jobs:

```powershell
aws glue get-jobs --profile sbnai-725 --query "Jobs[?contains(Name, 'fourcast') || contains(Name, 'FourCast') || contains(Name, 'platinum')].[Name,Role,GlueVersion]" --output table
```

If no clearly suitable job exists for `platinum_parquet_to_fourcastnet`, stop here for Task B and report that only audit/local path is currently possible.

If suitable job exists, run exactly one partition:

```powershell
aws glue start-job-run --profile sbnai-725 --job-name <GLUE_JOB_NAME> --arguments '{"--PLATINUM_BUCKET":"chucaw-data-platinum-processed-725644097028-us-east-1-an","--PLATINUM_PARQUET_PREFIX":"ecmwf/parquet","--FOURCASTNET_PREFIX":"ecmwf/fourcastnet","--YEAR":"2026","--MONTH":"04","--DAY":"09","--HOUR":"18","--TMP_DIR":"/tmp","--ALLOW_INCOMPLETE":"true","--LATITUDE_POLICY":"drop_south_pole"}'
```

Poll status using returned `JobRunId`:

```powershell
aws glue get-job-run --profile sbnai-725 --job-name <GLUE_JOB_NAME> --run-id <JOB_RUN_ID>
```

Stop polling when status is one of: `SUCCEEDED`, `FAILED`, `STOPPED`, `TIMEOUT`.

## 6) Phase 6: Download AWS-generated artifact if present

List output prefix:

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/ --profile sbnai-725 --recursive
```

Download:

```powershell
aws s3 cp s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/ data\\fourcastnet_aws_download_2026_04_09_18 --recursive --profile sbnai-725
```

## 7) Phase 6 validation of downloaded artifacts

If `input_tensor.npy` exists:

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR data\\fourcastnet_aws_download_2026_04_09_18\input_tensor.npy --OUTPUT_REPORT data\\fourcastnet_aws_download_2026_04_09_18\tensor_validation_report.json
```

If `input_fourcastnet.npy` exists:

```powershell
python -c "import numpy as np; a=np.load(r'data\\fourcastnet_aws_download_2026_04_09_18\input_fourcastnet.npy'); print(a.shape, a.dtype)"
```

If `.h5` exists:

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_h5.py --INPUT_H5 <PATH_TO_H5> --OUTPUT_REPORT data\\fourcastnet_aws_download_2026_04_09_18\h5_validation_report.json
```

Inspect manifest/report/provenance files if present:

```powershell
Get-ChildItem data\\fourcastnet_aws_download_2026_04_09_18
```

## 8) Phase 7: AWS Colab package (only if AWS tensor exists)

```powershell
New-Item -ItemType Directory -Path data\\fourcastnet_colab_upload_aws -Force | Out-Null
Copy-Item data\\fourcastnet_aws_download_2026_04_09_18\input_tensor.npy data\\fourcastnet_colab_upload_aws -Force
Copy-Item notebooks\fourcastnet_colab_smoke_test.ipynb data\\fourcastnet_colab_upload_aws -Force
```

Also copy any available manifest/report/provenance and optional local `global_means.npy`, `global_stds.npy`, `backbone.ckpt`.

If AWS tensor is not generated because channels are missing, report as expected and do not fabricate tensor files.

## 9) AWS Console checks (manual)

## 9.1 S3 Console
- Open S3 bucket: `chucaw-data-platinum-processed-725644097028-us-east-1-an`
- Navigate source: `ecmwf/parquet/year=2026/month=04/day=09/hour=18/`
- Confirm parquet objects exist.
- If Glue job ran, navigate output: `ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/`
- Confirm output objects and timestamps match your run window.

## 9.2 Glue Console
- Open AWS Glue > ETL jobs.
- Search for the selected job name.
- Open the **Runs** tab.
- Confirm the run status (`SUCCEEDED`/`FAILED`/etc.) for your `JobRunId`.
- Capture:
  - Job name
  - JobRunId
  - Start time / End time
  - Final status

## 9.3 CloudWatch Logs (if Glue ran)
- From the Glue run detail page, open linked CloudWatch log groups/streams.
- Check for:
  - Argument echo (`YEAR=2026`, `MONTH=04`, `DAY=09`, `HOUR=18`)
  - Variable/channel missing warnings
  - Final success/failure line

## 10) Final evidence checklist

- Local Task A:
  - `data\\fourcastnet_colab_upload_local` exists
  - `input_tensor.npy` present and validated
  - notebook present
  - missing assets explicitly reported if absent
- AWS Task B:
  - `aws sts get-caller-identity` succeeded
  - source partition listing succeeded
  - audit outputs generated, or blocker recorded
  - Glue job only run if suitable existing job found
  - AWS output downloaded and validated if present
