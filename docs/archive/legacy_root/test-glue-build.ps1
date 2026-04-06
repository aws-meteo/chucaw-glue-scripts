# ==============================================================================
# Test AWS Glue Build System (Without Full Build)
# ==============================================================================
# Purpose: Verify Docker availability and configuration without full build
# ==============================================================================

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "AWS Glue Build System - Pre-flight Check" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

$allChecks = @()

# Check 1: Docker availability
Write-Host "[1/5] Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Docker running (v$dockerVersion)" -ForegroundColor Green
        $allChecks += $true
    } else {
        throw "Docker not responding"
    }
} catch {
    Write-Host "  ✗ Docker not available" -ForegroundColor Red
    Write-Host "    → Start Docker Desktop" -ForegroundColor Yellow
    $allChecks += $false
}

# Check 2: Required files
Write-Host ""
Write-Host "[2/5] Checking required files..." -ForegroundColor Yellow
$requiredFiles = @(
    "requirements-glue.txt",
    "Dockerfile.glue-builder",
    "build_glue_libs.sh",
    "verify_glue_deps.py",
    "build-glue-deps.ps1"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file (MISSING)" -ForegroundColor Red
        $missingFiles += $file
    }
}

if ($missingFiles.Count -eq 0) {
    $allChecks += $true
} else {
    $allChecks += $false
}

# Check 3: requirements-glue.txt content
Write-Host ""
Write-Host "[3/5] Checking dependencies..." -ForegroundColor Yellow
if (Test-Path "requirements-glue.txt") {
    $deps = Get-Content "requirements-glue.txt" | Where-Object { $_ -match '\S' }
    foreach ($dep in $deps) {
        Write-Host "  → $dep" -ForegroundColor Gray
    }
    $allChecks += $true
} else {
    Write-Host "  ✗ requirements-glue.txt not found" -ForegroundColor Red
    $allChecks += $false
}

# Check 4: Build directory
Write-Host ""
Write-Host "[4/5] Checking build directory..." -ForegroundColor Yellow
if (-not (Test-Path "build")) {
    Write-Host "  → Creating build directory..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path "build" | Out-Null
}
Write-Host "  ✓ build/ ready" -ForegroundColor Green
$allChecks += $true

# Check 5: Docker base image availability
Write-Host ""
Write-Host "[5/5] Checking AWS Glue base image..." -ForegroundColor Yellow
Write-Host "  → Attempting to pull amazon/aws-glue-libs:glue_libs_5.0.0_image_01" -ForegroundColor Gray
Write-Host "    (This may take a few minutes on first run)" -ForegroundColor Gray

try {
    docker pull amazon/aws-glue-libs:glue_libs_5.0.0_image_01 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ AWS Glue base image available" -ForegroundColor Green
        $allChecks += $true
    } else {
        Write-Host "  ⚠ Could not pull base image (will retry during build)" -ForegroundColor Yellow
        $allChecks += $true  # Don't fail on this
    }
} catch {
    Write-Host "  ⚠ Could not verify base image (will retry during build)" -ForegroundColor Yellow
    $allChecks += $true  # Don't fail on this
}

# Summary
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
$passedChecks = ($allChecks | Where-Object { $_ -eq $true }).Count
$totalChecks = $allChecks.Count

if ($passedChecks -eq $totalChecks) {
    Write-Host "✓ All checks passed! Ready to build." -ForegroundColor Green
    Write-Host ""
    Write-Host "Run the full build with:" -ForegroundColor Cyan
    Write-Host "  .\build-glue-deps.ps1" -ForegroundColor White
} else {
    Write-Host "✗ Some checks failed ($passedChecks/$totalChecks passed)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the issues above and try again." -ForegroundColor Yellow
}

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
