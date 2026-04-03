#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3.11}"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements-glue.txt}"
GLUE_PROVIDED_LIST="${GLUE_PROVIDED_LIST:-lista_de_glue50.txt}"

echo "=== Glue 5.0 Artifact Builder (Bash) ==="

PYTHON_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "ERROR")
if [ "$PYTHON_VERSION" != "3.11" ]; then
    echo "ERROR: Glue 5.0 requires Python 3.11. Detected: $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python version: $PYTHON_VERSION"

echo "Building project wheel..."
$PYTHON -m pip install --upgrade pip build wheel
$PYTHON -m build --wheel --outdir "$OUTPUT_DIR"
echo "✓ Project wheel built"

DEPS_WHEELHOUSE="$OUTPUT_DIR/wheels"
ZIP_NAME="$OUTPUT_DIR/glue-dependencies.gluewheels.zip"
MANIFEST="$OUTPUT_DIR/glue-dependencies.contents.txt"

rm -rf "$DEPS_WHEELHOUSE" "$ZIP_NAME" "$MANIFEST"
mkdir -p "$DEPS_WHEELHOUSE"

cp "$REQUIREMENTS_FILE" "$DEPS_WHEELHOUSE/requirements.txt"
echo "✓ Copied $REQUIREMENTS_FILE → $DEPS_WHEELHOUSE/requirements.txt"

echo "Downloading wheels for Glue 5.0 (manylinux_2_28_x86_64, cp311)..."
$PYTHON -m pip download \
    --dest "$DEPS_WHEELHOUSE" \
    --only-binary=:all: \
    --platform manylinux_2_28_x86_64 \
    --python-version 311 \
    --implementation cp \
    --abi cp311 \
    -r "$DEPS_WHEELHOUSE/requirements.txt"
echo "✓ Wheels downloaded (with transitives)"

if [ ! -f "$GLUE_PROVIDED_LIST" ]; then
    echo "ERROR: Baseline list not found: $GLUE_PROVIDED_LIST"
    exit 1
fi

declare -A GLUE_PROVIDED
while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*([A-Za-z0-9_.-]+)== ]]; then
        PKG_NAME=$(echo "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
        GLUE_PROVIDED["$PKG_NAME"]=1
    fi
done < "$GLUE_PROVIDED_LIST"
echo "✓ Loaded ${#GLUE_PROVIDED[@]} baseline packages from $GLUE_PROVIDED_LIST"

EXCLUDED=()
for wheel in "$DEPS_WHEELHOUSE"/*.whl; do
    [ -e "$wheel" ] || continue
    filename=$(basename "$wheel")
    distname=$(echo "$filename" | cut -d'-' -f1 | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    
    if [ -n "${GLUE_PROVIDED[$distname]:-}" ]; then
        EXCLUDED+=("$filename")
        rm "$wheel"
    fi
done
echo "✓ Filtered out ${#EXCLUDED[@]} baseline wheels"

REQUIRED_DISTS=("click" "cffi" "findlibs" "pycparser" "eccodeslib" "cfgrib" "eccodes" "xarray")
MISSING=()
for dist in "${REQUIRED_DISTS[@]}"; do
    found=0
    for wheel in "$DEPS_WHEELHOUSE"/*.whl; do
        [ -e "$wheel" ] || continue
        filename=$(basename "$wheel")
        wheel_dist=$(echo "$filename" | cut -d'-' -f1 | tr '[:upper:]' '[:lower:]' | tr '_' '-')
        if [ "$wheel_dist" = "$dist" ]; then
            found=1
            break
        fi
    done
    if [ $found -eq 0 ]; then
        MISSING+=("$dist")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "ERROR: Required wheels missing: ${MISSING[*]}"
    exit 1
fi
echo "✓ All required wheels present"

FORBIDDEN_DISTS=("numpy" "pandas" "pyarrow" "boto3")
PRESENT_FORBIDDEN=()
for dist in "${FORBIDDEN_DISTS[@]}"; do
    for wheel in "$DEPS_WHEELHOUSE"/*.whl; do
        [ -e "$wheel" ] || continue
        filename=$(basename "$wheel")
        wheel_dist=$(echo "$filename" | cut -d'-' -f1 | tr '[:upper:]' '[:lower:]' | tr '_' '-')
        if [ "$wheel_dist" = "$dist" ]; then
            PRESENT_FORBIDDEN+=("$dist")
            break
        fi
    done
done

if [ ${#PRESENT_FORBIDDEN[@]} -gt 0 ]; then
    echo "ERROR: Forbidden baseline wheels present: ${PRESENT_FORBIDDEN[*]}"
    exit 1
fi
echo "✓ No forbidden baseline wheels present"

cd "$OUTPUT_DIR"
$PYTHON -c "
import zipfile
from pathlib import Path

zip_path = Path('glue-dependencies.gluewheels.zip')
wheels_dir = Path('wheels')

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for item in wheels_dir.rglob('*'):
        if item.is_file():
            arcname = str(item.relative_to(wheels_dir.parent))
            zf.write(item, arcname)

print(f'✓ Created {zip_path} with wheels/ at root')
"
cd - > /dev/null
echo "✓ Zip created: $ZIP_NAME"

INCLUDED_WHEELS=$(ls "$DEPS_WHEELHOUSE"/*.whl 2>/dev/null | wc -l || echo 0)
cat > "$MANIFEST" <<EOF
Glue dependency bundle manifest
Python: $PYTHON_VERSION
Requirements file: $REQUIREMENTS_FILE
Glue baseline list: $GLUE_PROVIDED_LIST

Included wheels: $INCLUDED_WHEELS
EOF

ls "$DEPS_WHEELHOUSE"/*.whl 2>/dev/null | while read -r wheel; do
    echo "- $(basename "$wheel")" >> "$MANIFEST"
done || true

echo "" >> "$MANIFEST"
echo "Excluded wheels (baseline): ${#EXCLUDED[@]}" >> "$MANIFEST"
if [ ${#EXCLUDED[@]} -eq 0 ]; then
    echo "- (none)" >> "$MANIFEST"
else
    printf '%s\n' "${EXCLUDED[@]}" | sort | while read -r item; do
        echo "- $item" >> "$MANIFEST"
    done
fi

echo "✓ Manifest created: $MANIFEST"

echo ""
echo "=== Build Complete ==="
echo "Project wheel: $OUTPUT_DIR/*.whl"
echo "Dependencies zip: $ZIP_NAME"
echo "Manifest: $MANIFEST"
echo "Included wheels: $INCLUDED_WHEELS"
echo "Excluded baseline wheels: ${#EXCLUDED[@]}"
ls -lh "$OUTPUT_DIR"
