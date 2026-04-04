# AWS Glue 5.0 Dependency Build System

## 📋 Overview

This system compiles Python dependencies for AWS Glue 5.0 using Docker, ensuring binary compatibility with the Glue runtime environment (Amazon Linux 2, Python 3.10).

**The Problem**: Building scientific Python packages like `xarray`, `cfgrib`, and `eccodes` on Windows produces incompatible binaries (.pyd/.dll) that fail on AWS Glue's Linux environment.

**The Solution**: Use AWS's official Glue Docker image to compile dependencies in a matching Linux environment, then package them for deployment.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Windows Development Machine                                 │
│                                                              │
│  PowerShell Orchestrator (build-glue-deps.ps1)             │
│        │                                                     │
│        ├──► Build Docker Image (Dockerfile.glue-builder)   │
│        │    ├─ AWS Glue 5.0 base image                     │
│        │    ├─ Install gcc/gfortran/cmake                   │
│        │    └─ Compile eccodes from source                  │
│        │                                                     │
│        ├──► Run Build Script (build_glue_libs.sh)          │
│        │    ├─ pip install with target platform            │
│        │    ├─ Pre-optimization verification                │
│        │    ├─ Clean __pycache__ / .dist-info               │
│        │    └─ Create dependencies.zip                      │
│        │                                                     │
│        └──► Verify Package (verify_glue_deps.py)           │
│             ├─ Import all critical modules                  │
│             ├─ Test xarray dataset creation                 │
│             ├─ Test cfgrib initialization                   │
│             └─ Test eccodes bindings                        │
│                                                              │
│  Output: build/glue-dependencies.zip                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Upload
                            ▼
                  ┌─────────────────────┐
                  │  Amazon S3 Bucket   │
                  └─────────────────────┘
                            │
                            │ Reference
                            ▼
                  ┌─────────────────────┐
                  │   AWS Glue Job      │
                  │ --extra-py-files    │
                  │ s3://.../deps.zip   │
                  └─────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

1. **Docker Desktop** installed and running
2. **PowerShell 5.1+** (included with Windows 10/11)
3. **requirements-glue.txt** with your dependencies

### Build Dependencies

```powershell
# Full build (first time or after major changes)
.\build-glue-deps.ps1

# Rebuild without re-building Docker image (faster)
.\build-glue-deps.ps1 -SkipBuild

# Clean build from scratch
.\build-glue-deps.ps1 -CleanBuild
```

### Expected Output

```
[SUCCESS] All 10 tests passed! ✓
[SUCCESS] Build completed successfully!
[SUCCESS] Output: C:\...\build\glue-dependencies.zip
[SUCCESS] Size: 45.32 MB
```

## 📦 Components

### 1. Dockerfile.glue-builder

**Purpose**: Creates a build environment matching AWS Glue 5.0

**Key Features**:
- Based on `amazon/aws-glue-libs:glue_libs_5.0.0_image_01`
- Installs compilation toolchain (gcc, g++, gfortran)
- Compiles eccodes 2.42.0 from source
- Sets library paths for netCDF, HDF5, eccodes

**Build Time**: 5-10 minutes (cached after first build)

### 2. build_glue_libs.sh

**Purpose**: Compile and package Python dependencies

**Strategy**:
1. Try precompiled `manylinux2014_x86_64` wheels first (fast)
2. Fall back to source compilation for packages that need it
3. Install to isolated directory (`/build/python`)
4. **Verify imports** before optimization (fail fast)
5. Optimize: Remove `__pycache__`, `.dist-info`, tests
6. Create ZIP with modules at root level
7. **Verify imports** from ZIP (ensure package integrity)

**Output**: `/build/glue-dependencies.zip`

### 3. verify_glue_deps.py

**Purpose**: Validate package functionality (the "REPL loop")

**Tests**:
- ✅ Import all critical packages
- ✅ xarray: Create dataset, compute statistics
- ✅ cfgrib: Initialize eccodes bindings
- ✅ eccodes: Check API version
- ✅ pandas + pyarrow: DataFrame conversions

**Why This Matters**: Catches issues locally in seconds instead of waiting 5-10 minutes for Glue job initialization only to see an `ImportError`.

### 4. build-glue-deps.ps1

**Purpose**: Windows-friendly orchestration script

**Features**:
- Docker availability check
- Automatic Unix line ending conversion (CRLF → LF)
- Windows path to Docker volume mount conversion
- Colored output for readability
- Build manifest generation
- Optional standalone verification

**Parameters**:
- `-SkipBuild`: Use existing Docker image
- `-SkipVerify`: Skip final verification
- `-CleanBuild`: Remove previous artifacts

## 🔧 Troubleshooting

### Docker Build Fails

**Symptom**: `ERROR: failed to solve: failed to fetch ...`

**Solution**:
```powershell
# Ensure Docker Desktop is running
docker info

# Retry with no cache
docker build --no-cache -f Dockerfile.glue-builder -t glue-builder:latest .
```

### eccodes Compilation Fails

**Symptom**: `CMake Error: Could not find CMAKE_ROOT`

**Solution**: The Dockerfile installs cmake. If it fails:
```dockerfile
# Add to Dockerfile.glue-builder before eccodes installation
RUN yum install -y cmake3 && ln -s /usr/bin/cmake3 /usr/bin/cmake
```

### Import Verification Fails

**Symptom**: `ImportError: libeccodes.so.0: cannot open shared object file`

**Solution**: eccodes shared libraries aren't in the ZIP. Check:
```bash
# Inside Docker container
ldd /build/python/eccodes/_bindings.so
# Should show /usr/local/lib/libeccodes.so

# If missing, copy shared libraries to package
cp /usr/local/lib/libeccodes.so* /build/python/
```

### ZIP Too Large (>250MB)

**Symptom**: AWS Glue rejects large extra-py-files

**Solution**:
1. Remove unnecessary packages from `requirements-glue.txt`
2. Add aggressive optimization to `build_glue_libs.sh`:
   ```bash
   # Remove documentation
   find "${SITE_PACKAGES_DIR}" -type d -name "docs" -exec rm -rf {} +
   
   # Remove examples
   find "${SITE_PACKAGES_DIR}" -type d -name "examples" -exec rm -rf {} +
   
   # Strip debug symbols from .so files
   find "${SITE_PACKAGES_DIR}" -name "*.so" -exec strip {} \;
   ```

### Windows Path Issues

**Symptom**: `cannot find the path specified` in Docker

**Solution**: The script handles this, but verify:
```powershell
# Check mount paths
$workspaceMount = (Get-Location).Path.Replace('\', '/') -replace '^([A-Za-z]):', '/$1'
Write-Host $workspaceMount
# Should output: /c/Users/YourName/Documents/...
```

## 📊 Expected Package Sizes

| Package | Size (MB) | Notes |
|---------|-----------|-------|
| xarray | ~2 | Pure Python |
| cfgrib | ~0.5 | Python + eccodes bindings |
| eccodes | ~1 | Native extensions |
| numpy | ~20 | Pre-compiled wheel |
| pandas | ~15 | Pre-compiled wheel |
| pyarrow | ~25 | Pre-compiled wheel |
| **Total (optimized)** | **~45** | After removing tests, docs, cache |

## 🔒 Security Notes

### Shared Libraries

The ZIP includes Python packages but **not** system shared libraries (libeccodes.so, libnetcdf.so). These must be:
1. Compiled into the package (copy .so files to ZIP), OR
2. Available in AWS Glue's runtime (not guaranteed for eccodes)

**Recommended**: Bundle eccodes shared libraries:
```bash
# Add to build_glue_libs.sh after pip install
mkdir -p "${SITE_PACKAGES_DIR}/lib"
cp /usr/local/lib/libeccodes.so* "${SITE_PACKAGES_DIR}/lib/"
```

Then set `LD_LIBRARY_PATH` in Glue job:
```python
import os
os.environ['LD_LIBRARY_PATH'] = '/tmp/lib:' + os.environ.get('LD_LIBRARY_PATH', '')
```

## 🚢 Deployment

### 1. Upload to S3

```powershell
aws s3 cp build/glue-dependencies.zip s3://your-glue-assets-bucket/libs/
```

### 2. Configure Glue Job

**Via Console**:
- Job parameters → Python library path → `s3://your-glue-assets-bucket/libs/glue-dependencies.zip`

**Via CloudFormation**:
```yaml
GlueJob:
  Type: AWS::Glue::Job
  Properties:
    Command:
      Name: glueetl
      PythonVersion: '3'
      ScriptLocation: s3://your-bucket/scripts/job.py
    DefaultArguments:
      '--extra-py-files': s3://your-glue-assets-bucket/libs/glue-dependencies.zip
      '--enable-glue-datacatalog': true
    GlueVersion: '5.0'
```

### 3. Verify in Glue

**Test Script**:
```python
import sys
from awsglue.context import GlueContext
from pyspark.context import SparkContext

# Initialize
sc = SparkContext()
glueContext = GlueContext(sc)
logger = glueContext.get_logger()

# Test imports
try:
    import xarray as xr
    import cfgrib
    logger.info(f"✓ xarray {xr.__version__}")
    logger.info(f"✓ cfgrib {cfgrib.__version__}")
except ImportError as e:
    logger.error(f"Import failed: {e}")
    raise
```

## 🔄 Maintenance

### Update Dependencies

1. Edit `requirements-glue.txt`
2. Rebuild:
   ```powershell
   .\build-glue-deps.ps1 -CleanBuild
   ```
3. Upload new ZIP to S3
4. Update Glue job version or path

### Update Glue Version

When AWS releases Glue 6.0:

1. Update `Dockerfile.glue-builder`:
   ```dockerfile
   FROM amazon/aws-glue-libs:glue_libs_6.0.0_image_01
   ```

2. Rebuild image:
   ```powershell
   docker build --no-cache -f Dockerfile.glue-builder -t glue-builder:latest .
   ```

3. Test thoroughly before production deployment

## 📝 License

This build system is part of the SbnAI Clima project. See main repository LICENSE.

## 🤝 Contributing

Issues and improvements welcome! Common enhancements:

- [ ] Add support for more platforms (Linux host builds)
- [ ] Parallelize package installation
- [ ] Add S3 upload step to build script
- [ ] Create GitHub Action for automated builds
- [ ] Support Glue 4.0 (Python 3.10, Spark 3.3)

---

**Last Updated**: 2026-04-03  
**AWS Glue Version**: 5.0  
**Python Version**: 3.10  
**Base Image**: amazon/aws-glue-libs:glue_libs_5.0.0_image_01
