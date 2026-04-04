#!/bin/bash
# ==============================================================================
# AWS Glue 5.0 Dependency Builder
# ==============================================================================
# Compiles and packages Python wheels for offline deployment to AWS Glue 5.0.
# Runs INSIDE the glue5-builder Docker container.
#
# Output:
#   /build/wheels/           — individual .whl files (filtered, no Glue baseline)
#   /build/glue-deps.gluewheels.zip — zip-of-wheels for --additional-python-modules
#   /build/chucaw_preprocessor-*.whl — project wheel
#   /build/manifest.txt      — included/excluded package list
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

WORKSPACE="/workspace"
BUILD_DIR="/build"
WHEELS_DIR="${BUILD_DIR}/wheels"
REQUIREMENTS="${WORKSPACE}/requirements-glue.txt"
GLUE_BASELINE="${WORKSPACE}/lista_de_glue50.txt"

# ---------- Clean ----------
log_info "Cleaning previous build..."
rm -rf "${WHEELS_DIR}" "${BUILD_DIR}"/*.zip "${BUILD_DIR}"/*.whl "${BUILD_DIR}/manifest.txt"
mkdir -p "${WHEELS_DIR}"

# ---------- 1. Build project wheel ----------
log_info "Building project wheel..."
cd "${WORKSPACE}"
python3.11 -m pip install --quiet build
python3.11 -m build --wheel --outdir "${BUILD_DIR}" 2>&1 | tail -3
PROJECT_WHL=$(ls "${BUILD_DIR}"/chucaw_preprocessor-*.whl 2>/dev/null | head -1)
if [ -z "${PROJECT_WHL}" ]; then
    log_error "Project wheel not built!"
    exit 1
fi
log_success "Project wheel: $(basename ${PROJECT_WHL})"

# ---------- 2. Download dependency wheels ----------
log_info "Downloading dependency wheels for cp311/linux..."
python3.11 -m pip download \
    --dest "${WHEELS_DIR}" \
    --only-binary=:all: \
    --platform manylinux_2_28_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform linux_x86_64 \
    --python-version 311 \
    --implementation cp \
    --abi cp311 \
    -r "${REQUIREMENTS}" 2>&1 | tail -20

# Also download pure-python wheels that may not match platform filter
python3.11 -m pip download \
    --dest "${WHEELS_DIR}" \
    --only-binary=:all: \
    --python-version 311 \
    -r "${REQUIREMENTS}" 2>&1 | tail -5 || true

log_success "Downloaded $(ls ${WHEELS_DIR}/*.whl 2>/dev/null | wc -l) wheels"

# ---------- 3. Filter out Glue baseline packages ----------
log_info "Filtering out Glue baseline packages..."

normalize_name() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-' | tr -d '[:space:]'
}

# Build a flat file of baseline package names (one per line)
BASELINE_FILE=$(mktemp)
while IFS= read -r line; do
    line=$(echo "$line" | tr -d '[:space:]')
    [ -z "$line" ] && continue
    echo "$line" | grep -q '^#' && continue
    pkg=$(echo "$line" | cut -d'=' -f1)
    normalize_name "$pkg" >> "${BASELINE_FILE}"
done < "${GLUE_BASELINE}"

is_baseline() {
    grep -qx "$1" "${BASELINE_FILE}"
}

INCLUDED=()
EXCLUDED=()
for whl in "${WHEELS_DIR}"/*.whl; do
    [ -f "$whl" ] || continue
    fname=$(basename "$whl")
    dist=$(echo "$fname" | cut -d'-' -f1)
    dist=$(normalize_name "$dist")

    if is_baseline "$dist"; then
        EXCLUDED+=("$fname")
        rm -f "$whl"
    else
        INCLUDED+=("$fname")
    fi
done
rm -f "${BASELINE_FILE}"

log_success "Kept ${#INCLUDED[@]} wheels, filtered ${#EXCLUDED[@]} Glue baseline packages"

# ---------- 4. Add eccodeslib native wheel if available ----------
log_info "Checking for eccodeslib wheel..."
HAS_ECCODESLIB=$(ls "${WHEELS_DIR}"/eccodeslib-*.whl 2>/dev/null | head -1)
if [ -z "${HAS_ECCODESLIB}" ]; then
    log_warn "eccodeslib wheel not found — attempting pip download without platform filter..."
    python3.11 -m pip download \
        --dest "${WHEELS_DIR}" \
        --only-binary=:all: \
        eccodeslib==2.42.0 2>&1 | tail -5 || {
        log_warn "eccodeslib wheel download failed — may need source build"
    }
fi

# ---------- 5. Create .gluewheels.zip ----------
REMAINING=$(ls "${WHEELS_DIR}"/*.whl 2>/dev/null | wc -l)
if [ "$REMAINING" -eq 0 ]; then
    log_error "No wheels remaining after filtering!"
    exit 1
fi

log_info "Creating .gluewheels.zip with ${REMAINING} wheels..."

# gluewheels.zip structure: wheels/ directory containing .whl files + requirements.txt
cp "${REQUIREMENTS}" "${WHEELS_DIR}/requirements.txt"

cd "${WHEELS_DIR}/.."
ZIP_NAME="glue-dependencies.gluewheels.zip"
rm -f "${BUILD_DIR}/${ZIP_NAME}"
cd "${BUILD_DIR}"
zip -r -q -9 "${ZIP_NAME}" wheels/
ZIP_SIZE=$(du -sh "${BUILD_DIR}/${ZIP_NAME}" | cut -f1)
log_success "Created ${ZIP_NAME} (${ZIP_SIZE})"

# ---------- 6. Generate manifest ----------
log_info "Generating manifest..."
{
    echo "=== Glue 5.0 Dependency Bundle Manifest ==="
    echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Python: 3.11"
    echo "Platform: manylinux_2_28_x86_64"
    echo ""
    echo "=== INCLUDED wheels ==="
    for w in "${INCLUDED[@]}"; do echo "  + $w"; done
    echo ""
    echo "=== EXCLUDED (Glue baseline) ==="
    for w in "${EXCLUDED[@]}"; do echo "  - $w"; done
    echo ""
    echo "=== PROJECT wheel ==="
    echo "  * $(basename ${PROJECT_WHL})"
} > "${BUILD_DIR}/manifest.txt"

log_success "Manifest: ${BUILD_DIR}/manifest.txt"

# ---------- 7. Verify imports ----------
log_info "Running import verification..."
export LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib:${LD_LIBRARY_PATH:-}

# Install from the artifacts we just built (simulates Glue --no-index)
python3.11 -m pip install --quiet --no-index \
    --find-links "${WHEELS_DIR}" \
    "${PROJECT_WHL}" 2>&1 | tail -5

python3.11 -c "
import sys
tests = [
    ('xarray', 'xr'),
    ('cfgrib', 'cfgrib'),
    ('eccodes', 'eccodes'),
    ('numpy', 'np'),
    ('pandas', 'pd'),
    ('pyarrow', 'pa'),
    ('chucaw_preprocessor', 'cp'),
]
failed = []
for name, alias in tests:
    try:
        mod = __import__(name)
        ver = getattr(mod, '__version__', '?')
        print(f'  ✓ {name} {ver}')
    except ImportError as e:
        print(f'  ✗ {name}: {e}')
        failed.append(name)

if failed:
    print(f'\nFAILED: {failed}')
    sys.exit(1)
else:
    print('\n✓ All imports OK')
"

if [ $? -ne 0 ]; then
    log_error "Import verification FAILED"
    exit 1
fi

# ---------- Summary ----------
echo ""
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "BUILD COMPLETE — Glue 5.0 artifacts ready"
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "  .gluewheels.zip : ${BUILD_DIR}/${ZIP_NAME} (${ZIP_SIZE})"
log_success "  Project wheel   : $(basename ${PROJECT_WHL})"
log_success "  Manifest        : ${BUILD_DIR}/manifest.txt"
log_success ""
log_success "Deploy to S3:"
log_success "  aws s3 cp ${BUILD_DIR}/${ZIP_NAME} s3://BUCKET/glue/artifacts/"
log_success "  aws s3 cp ${PROJECT_WHL} s3://BUCKET/glue/artifacts/"
log_success ""
log_success "Glue job config:"
log_success "  --additional-python-modules s3://BUCKET/glue/artifacts/${ZIP_NAME},s3://BUCKET/glue/artifacts/$(basename ${PROJECT_WHL})"
log_success "  --python-modules-installer-option --no-index"
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
