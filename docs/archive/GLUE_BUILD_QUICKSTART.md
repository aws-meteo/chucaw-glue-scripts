# 🚀 Quick Start - AWS Glue Dependency Builder

## One Command Build

```powershell
.\build-glue-deps.ps1
```

That's it! This will:
1. ✅ Build Docker image with AWS Glue 5.0 environment
2. ✅ Compile xarray, cfgrib, eccodes for Linux
3. ✅ Verify all imports work
4. ✅ Create optimized ZIP: `build/glue-dependencies.zip`

## What You Get

```
build/
├── glue-dependencies.zip    ← Upload to S3
├── manifest.txt             ← Package list
└── temp/                    ← Build logs
```

## Deploy to AWS

```bash
# Upload
aws s3 cp build/glue-dependencies.zip s3://your-bucket/glue-libs/

# Use in Glue Job
--extra-py-files s3://your-bucket/glue-libs/glue-dependencies.zip
```

## Troubleshooting

### "Docker not running"
→ Start Docker Desktop

### Build fails on first run
→ Normal! eccodes compilation takes 5-10 minutes
→ Second build = 30 seconds (cached)

### Import fails in verification
→ Check `build/temp/pip_*.log` for errors
→ Missing system library? Check Dockerfile.glue-builder

## Full Documentation

See [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) for:
- Architecture diagrams
- Troubleshooting guide
- Security notes
- Deployment instructions

## Files

| File | Purpose |
|------|---------|
| `build-glue-deps.ps1` | Main script (run this) |
| `Dockerfile.glue-builder` | Build environment |
| `build_glue_libs.sh` | Compilation logic |
| `verify_glue_deps.py` | Import validator |
| `requirements-glue.txt` | Your dependencies |

---

**Time to first build**: 5-10 min  
**Time to rebuild**: 30 sec  
**Output size**: ~45 MB (optimized)
