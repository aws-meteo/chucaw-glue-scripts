# Official FourCastNet Full Test Guide

Status: authoritative runbook for this repository.  
Date: 2026-05-06  
Scope: one-partition operational test only.  
Goal: prove preprocessing mechanics and full model forward pass execution (not scientific validity).

## 1) What this guide proves

This guide proves:
- Local preprocessing artifacts can be generated and validated.
- Colab can run full forward pass when required model assets are present.
- AWS one-partition path can be preflighted/audited and optionally executed via existing Glue job.
- AWS-generated artifacts can be downloaded and validated if produced.

This guide does not prove:
- Meteorological/scientific correctness of outputs.
- Generalization across multiple dates/runs.
- Production pipeline changes (do not modify GRIB-to-Parquet production code here).

## 2) Rules for this run

- Use exactly one partition.
- Do not call SageMaker.
- Do not run broad Glue jobs.
- Do not process multiple dates.
- Do not fabricate tensors or claim success without evidence files.

## 3) Canonical paths used by this guide

Workspace root:

`C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts`

Local artifact layout under `data\`:
- `data\fourcastnet_source_real_v1`
- `data\fourcastnet_compat_real_v2`
- `data\fourcastnet_tensor_real_v1`
- `data\fourcastnet_colab_upload_local`
- `data\fourcastnet_aws_audit_2026_04_09_18`
- `data\fourcastnet_aws_download_2026_04_09_18`
- `data\fourcastnet_colab_upload_aws`

Notebook:
- `notebooks\fourcastnet_colab_smoke_test.ipynb`

## 4) Full model pass prerequisites (hard requirements)

You cannot get `fourcastnet_proven=true` in Colab unless all are available:
- `input_tensor.npy` (or `.pt`) with shape `(1,20,720,1440)`
- `global_means.npy`
- `global_stds.npy`
- `backbone.ckpt`
- FourCastNet code checkout at `/content/FourCastNet` in Colab (AFNONet import path)

## 5) Environment setup

```powershell
Set-Location C:\Users\Asus\Documents\code\SbnAI\chucaw-glue-scripts
$env:PYTHONPATH='src'
$env:AWS_PROFILE='sbnai-725'
```

If `python` is not resolvable in your shell, use your known interpreter explicitly, for example:

```powershell
& 'C:\ProgramData\miniconda3\envs\aws_backend\python.exe' -V
```

## 6) Phase A: local preprocessing regeneration into `data\`

This produces a fresh worked parquet and tensor package.

### A1) Build local source parquet from one local GRIB

Use one existing GRIB only:

```powershell
$env:PYTHONPATH='src'
wsl.exe bash -lc "cd /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts && PYTHONPATH=src ./.venv311-linux/bin/python scripts/glue_jobs/local_grib_to_platinum_parquet.py --GRIB_PATH data/gribs/20260331060000-0h-scda-fc.grib2 --OUTPUT_DIR data/fourcastnet_source_real_v1 --DATE 20260331 --RUN 06z"
```

Expected key output:
- `data\fourcastnet_source_real_v1\20260331060000-0h-scda-fc.parquet`

### A2) Build compatibility fixture parquet

```powershell
$env:PYTHONPATH='src'
python scripts\dev\make_fourcastnet_compatibility_fixture.py --INPUT_PARQUET data\fourcastnet_source_real_v1\20260331060000-0h-scda-fc.parquet --OUTPUT_DIR data\fourcastnet_compat_real_v2 --MODE compatibility_fixture --LATITUDE_POLICY drop_south_pole --FORCE
```

Expected key output:
- `data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.parquet`

### A3) Export tensor-first artifact

```powershell
$env:PYTHONPATH='src'
python scripts\dev\export_fourcastnet_tensor.py --INPUT_PARQUET data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.parquet --OUTPUT_DIR data\fourcastnet_tensor_real_v1 --LATITUDE_POLICY drop_south_pole --OUTPUT_FORMAT npy --FORCE
```

Expected key outputs:
- `data\fourcastnet_tensor_real_v1\input_tensor.npy`
- `data\fourcastnet_tensor_real_v1\tensor_manifest.json`

### A4) Optional HDF5 compatibility export

```powershell
$env:PYTHONPATH='src'
python scripts\dev\export_fourcastnet_h5.py --INPUT_PARQUET data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.parquet --OUTPUT_H5 data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.h5 --LATITUDE_POLICY drop_south_pole
```

## 7) Phase B: validate generated local artifacts

### B1) Validate tensor

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR data\fourcastnet_tensor_real_v1\input_tensor.npy --OUTPUT_REPORT data\fourcastnet_tensor_real_v1\tensor_validation_report_before_colab.json
```

Pass criteria:
- `ok: true`
- shape `[1,20,720,1440]`
- finite values

### B2) Validate HDF5 if present

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_h5.py --INPUT_H5 data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.h5 --OUTPUT_REPORT data\fourcastnet_compat_real_v2\h5_validation_report.json
```

## 8) Phase C: build local Colab upload package

```powershell
New-Item -ItemType Directory -Path data\fourcastnet_colab_upload_local -Force | Out-Null
Copy-Item data\fourcastnet_tensor_real_v1\input_tensor.npy data\fourcastnet_colab_upload_local -Force
Copy-Item data\fourcastnet_tensor_real_v1\tensor_manifest.json data\fourcastnet_colab_upload_local -Force
Copy-Item data\fourcastnet_compat_real_v2\channel_provenance.json data\fourcastnet_colab_upload_local -Force
Copy-Item data\fourcastnet_compat_real_v2\fcn_compat_20260331_06z.parquet data\fourcastnet_colab_upload_local -Force
Copy-Item notebooks\fourcastnet_colab_smoke_test.ipynb data\fourcastnet_colab_upload_local -Force
```

Search model/stats assets:

```powershell
Get-ChildItem -Recurse .. -Include global_means.npy,global_stds.npy,backbone.ckpt -ErrorAction SilentlyContinue
```

If found, copy into `data\fourcastnet_colab_upload_local`.

If missing, write:

```powershell
@'
{
  "missing_assets": ["global_means.npy", "global_stds.npy", "backbone.ckpt"]
}
'@ | Set-Content data\fourcastnet_colab_upload_local\missing_assets_report.json -Encoding UTF8
```

## 9) Phase D: Colab full-pass execution (companion sequence)

### D1) Upload notebook and files

Upload to Colab:
- `fourcastnet_colab_smoke_test.ipynb`
- `input_tensor.npy`
- `tensor_manifest.json`
- `channel_provenance.json`
- `fcn_compat_20260331_06z.parquet` (optional for debug)
- `global_means.npy` (required for full pass)
- `global_stds.npy` (required for full pass)
- `backbone.ckpt` (required for full pass)

### D2) Ensure FourCastNet repo exists in Colab

Run in a Colab cell:

```bash
cd /content
git clone <YOUR_FOURCASTNET_REPO_URL> FourCastNet
ls -la /content/FourCastNet
```

### D3) Preflight check cell (run before notebook stages)

```python
from pathlib import Path
required = [
    "/content/input_tensor.npy",
    "/content/global_means.npy",
    "/content/global_stds.npy",
    "/content/backbone.ckpt",
    "/content/FourCastNet",
]
for p in required:
    print(p, "OK" if Path(p).exists() else "MISSING")
```

If any item is missing, stop and fix uploads first.

### D4) Execute notebook top-to-bottom

Required success evidence:
- `report['normalization_ok'] == True`
- `report['checkpoint_load_ok'] == True`
- `report['model_load_ok'] == True`
- `report['inference_success'] == True`
- `report['fourcastnet_proven'] == True`

Expected output file:
- `/content/colab_validation_report.json`

Download that report and store it with run evidence.

## 10) Phase E: AWS one-partition validation and optional generation

Target partition:
- `year=2026`
- `month=04`
- `day=09`
- `hour=18`

### E1) AWS auth and identity

```powershell
aws sso login --profile sbnai-725
aws sts get-caller-identity --profile sbnai-725
```

### E2) Source partition preflight

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/ --profile sbnai-725
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/hour=18/ --profile sbnai-725
```

Diagnostic only:

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/parquet/year=2026/month=04/day=09/hour=18z/ --profile sbnai-725
```

### E3) Audit S3 partition through script

```powershell
$env:PYTHONPATH='src'
python scripts\glue_jobs\audit_platinum_partition.py --PLATINUM_BUCKET chucaw-data-platinum-processed-725644097028-us-east-1-an --PLATINUM_PARQUET_PREFIX ecmwf/parquet --YEAR 2026 --MONTH 04 --DAY 09 --HOUR 18 --OUTPUT_DIR data\fourcastnet_aws_audit_2026_04_09_18
```

Expected outputs:
- `available_variables.json`
- `available_variable_levels.csv`
- `validation_report.json`

### E4) Glue job discovery and decision

```powershell
aws glue get-jobs --profile sbnai-725 --query "Jobs[?contains(Name, 'fourcast') || contains(Name, 'FourCast') || contains(Name, 'platinum')].[Name,Role,GlueVersion]" --output table
```

If no clearly correct existing job for `platinum_parquet_to_fourcastnet`, stop and report that AWS-side generation is unavailable in this run.

If job exists and is clearly correct, run one partition only:

```powershell
aws glue start-job-run --profile sbnai-725 --job-name <GLUE_JOB_NAME> --arguments '{"--PLATINUM_BUCKET":"chucaw-data-platinum-processed-725644097028-us-east-1-an","--PLATINUM_PARQUET_PREFIX":"ecmwf/parquet","--FOURCASTNET_PREFIX":"ecmwf/fourcastnet","--YEAR":"2026","--MONTH":"04","--DAY":"09","--HOUR":"18","--TMP_DIR":"/tmp","--ALLOW_INCOMPLETE":"true","--LATITUDE_POLICY":"drop_south_pole"}'
```

Poll:

```powershell
aws glue get-job-run --profile sbnai-725 --job-name <GLUE_JOB_NAME> --run-id <JOB_RUN_ID>
```

Stop when status is `SUCCEEDED|FAILED|STOPPED|TIMEOUT`.

### E5) Download AWS generated artifact if present

```powershell
aws s3 ls s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/ --profile sbnai-725 --recursive
aws s3 cp s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/ data\fourcastnet_aws_download_2026_04_09_18 --recursive --profile sbnai-725
```

Validate whichever file type exists:

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_tensor.py --INPUT_TENSOR data\fourcastnet_aws_download_2026_04_09_18\input_tensor.npy --OUTPUT_REPORT data\fourcastnet_aws_download_2026_04_09_18\tensor_validation_report.json
```

```powershell
$env:PYTHONPATH='src'
python scripts\dev\validate_fourcastnet_h5.py --INPUT_H5 data\fourcastnet_aws_download_2026_04_09_18\<FILE>.h5 --OUTPUT_REPORT data\fourcastnet_aws_download_2026_04_09_18\h5_validation_report.json
```

## 11) AWS Console verification checklist

### S3 Console
- Open bucket `chucaw-data-platinum-processed-725644097028-us-east-1-an`.
- Verify source partition objects at `ecmwf/parquet/year=2026/month=04/day=09/hour=18/`.
- If Glue ran, verify output objects at `ecmwf/fourcastnet/year=2026/month=04/day=09/hour=18/`.

### Glue Console
- Open Glue job used in run.
- Check job run entry for your `JobRunId`.
- Capture `Status`, `StartTime`, `EndTime`, and arguments.

### CloudWatch logs
- Open linked logs from Glue run detail.
- Confirm run used exact partition args and collect terminal success/failure lines.

## 12) Final acceptance checklist

Local package acceptance:
- `data\fourcastnet_colab_upload_local` exists.
- `input_tensor.npy` validation report says `ok=true`.
- Notebook exists in upload package.
- Missing model assets explicitly reported if absent.

Full model pass acceptance:
- Colab report contains `fourcastnet_proven=true`.
- Report includes finite output and output shape evidence.
- FourCastNet repo was present at `/content/FourCastNet`.

AWS acceptance:
- `aws sts get-caller-identity` succeeded.
- Partition listings succeeded.
- Audit outputs generated, or blocker clearly recorded.
- Glue run executed only if existing suitable job found.
- AWS artifact downloaded and validated if produced.

## 13) Common failure triage

`Token has expired and refresh failed`:
- Run `aws sso login --profile sbnai-725`, then retry.

`normalization preflight failed or stats missing` in Colab:
- Upload `global_means.npy` and `global_stds.npy` to `/content`.

`checkpoint preflight failed` in Colab:
- Upload `backbone.ckpt` to `/content`.

`Local FourCastNet repo not found at /content/FourCastNet`:
- Clone repo into `/content/FourCastNet`.

`Could not import AFNONet`:
- Verify repo checkout is correct and includes expected modules.

`Invalid tensor shape`:
- Regenerate with `export_fourcastnet_tensor.py`, then revalidate.

## 14) Minimal “go” command sequence for next run

Use this sequence when you want a clean end-to-end execution:

1. Run sections 5, 6, 7, 8.
2. Run section 9 in Colab and confirm `fourcastnet_proven=true`.
3. Run section 10 for AWS one-partition path.
4. Run section 11 manual console checks.
5. Validate acceptance with section 12.
