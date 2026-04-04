# Glue Job Examples

This directory contains example configurations for using custom dependencies compiled with the Docker build system.

## Files

- **glue-job-example.json**: AWS Glue job definition (for `aws glue create-job`)
- **glue-job-example.py**: Example Glue ETL script with dependency verification

## Usage

### 1. Build Dependencies

```powershell
.\build-glue-deps.ps1
```

### 2. Upload to S3

```bash
aws s3 cp build/glue-dependencies.zip s3://your-bucket/glue-libs/
```

### 3. Create Glue Job

**Option A: Via AWS CLI**

```bash
# Upload script
aws s3 cp examples/glue-job-example.py s3://your-bucket/scripts/

# Create job (edit glue-job-example.json first)
aws glue create-job --cli-input-json file://examples/glue-job-example.json
```

**Option B: Via Console**

1. Go to AWS Glue → ETL jobs → Create job
2. Set:
   - **Glue version**: 5.0
   - **Language**: Python 3
   - **Script path**: s3://your-bucket/scripts/glue-job-example.py
3. In **Advanced properties** → **Python library path**:
   - Add: `s3://your-bucket/glue-libs/glue-dependencies.zip`

### 4. Run Job

```bash
aws glue start-job-run --job-name example-glue-job-with-custom-deps
```

## Customization

The example script shows:

- ✅ Dependency verification (fail fast if imports fail)
- ✅ Processing GRIB files with xarray/cfgrib
- ✅ Converting to Spark DataFrames
- ✅ Writing Parquet to S3
- ✅ Using Glue Data Catalog

Adapt the commented sections to your use case.

## Troubleshooting

### ImportError in Glue

**Symptom**: `ImportError: No module named 'xarray'`

**Solution**:
1. Verify `--extra-py-files` points to correct S3 path
2. Check CloudWatch logs for actual error
3. Re-run build with verification: `.\build-glue-deps.ps1`

### libeccodes.so not found

**Symptom**: `OSError: libeccodes.so.0: cannot open shared object file`

**Solution**: Bundle eccodes shared libraries (see docs/GLUE_DEPENDENCY_BUILD.md)

---

For full documentation, see:
- [GLUE_BUILD_QUICKSTART.md](../GLUE_BUILD_QUICKSTART.md)
- [docs/GLUE_DEPENDENCY_BUILD.md](../docs/GLUE_DEPENDENCY_BUILD.md)
