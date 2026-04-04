# ==============================================================================
# AWS Glue Dependencies Builder - PowerShell Orchestrator for Windows
# ==============================================================================
# Purpose: Orchestrate Docker-based compilation of AWS Glue dependencies
# Platform: Windows 10/11 with Docker Desktop
# Output: build/glue-dependencies.zip
# ==============================================================================

param(
    [switch]$SkipBuild,
    [switch]$SkipVerify,
    [switch]$CleanBuild
)

# Color output functions
function Write-ColorOutput {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        
        [Parameter(Mandatory=$false)]
        [ValidateSet('Info', 'Success', 'Warning', 'Error')]
        [string]$Type = 'Info'
    )
    
    $color = switch ($Type) {
        'Info'    { 'Cyan' }
        'Success' { 'Green' }
        'Warning' { 'Yellow' }
        'Error'   { 'Red' }
    }
    
    $prefix = switch ($Type) {
        'Info'    { '[INFO]' }
        'Success' { '[SUCCESS]' }
        'Warning' { '[WARN]' }
        'Error'   { '[ERROR]' }
    }
    
    Write-Host "$prefix $Message" -ForegroundColor $color
}

# Configuration
$SCRIPT_DIR = $PSScriptRoot
$BUILD_DIR = Join-Path $SCRIPT_DIR "build"
$DOCKER_IMAGE = "glue-builder:latest"
$OUTPUT_ZIP = "glue-dependencies.zip"

Write-Host ""
Write-Host ("=" * 80)
Write-Host "AWS Glue 5.0 Dependency Builder for Windows" -ForegroundColor Cyan
Write-Host ("=" * 80)
Write-Host ""

# Validate Docker is running
Write-ColorOutput "Checking Docker availability..." -Type Info
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not responding"
    }
    Write-ColorOutput "Docker is running (v$dockerVersion)" -Type Success
} catch {
    Write-ColorOutput "Docker is not running or not installed" -Type Error
    Write-ColorOutput "Please start Docker Desktop and try again" -Type Warning
    exit 1
}

# Clean build directory if requested
if ($CleanBuild) {
    Write-ColorOutput "Cleaning build directory..." -Type Info
    if (Test-Path $BUILD_DIR) {
        Remove-Item -Path $BUILD_DIR -Recurse -Force
    }
}

# Create build directory
if (-not (Test-Path $BUILD_DIR)) {
    Write-ColorOutput "Creating build directory..." -Type Info
    New-Item -ItemType Directory -Path $BUILD_DIR | Out-Null
}

# Build Docker image
if (-not $SkipBuild) {
    Write-ColorOutput "Building Docker image: $DOCKER_IMAGE" -Type Info
    Write-ColorOutput "This may take 5-10 minutes on first run (downloading base image + compiling eccodes)..." -Type Warning
    
    docker build `
        -f Dockerfile.glue-builder `
        -t $DOCKER_IMAGE `
        .
    
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "Docker build failed" -Type Error
        exit 1
    }
    
    Write-ColorOutput "Docker image built successfully" -Type Success
} else {
    Write-ColorOutput "Skipping Docker build (using existing image)" -Type Warning
}

# Convert Windows paths to Unix-style for Docker volume mounts
# Docker Desktop on Windows handles this, but we need consistent forward slashes
$workspaceMount = $SCRIPT_DIR.Replace('\', '/')
$buildMount = $BUILD_DIR.Replace('\', '/')

# Fix drive letter format (C: -> /c or /host_mnt/c depending on Docker Desktop version)
if ($workspaceMount -match '^([A-Za-z]):') {
    $driveLetter = $matches[1].ToLower()
    $workspaceMount = $workspaceMount -replace '^[A-Za-z]:', "/$driveLetter"
    $buildMount = $buildMount -replace '^[A-Za-z]:', "/$driveLetter"
}

Write-ColorOutput "Workspace: $workspaceMount" -Type Info
Write-ColorOutput "Build output: $buildMount" -Type Info

# Ensure line endings are Unix-style (LF) for shell scripts
Write-ColorOutput "Ensuring Unix line endings for shell scripts..." -Type Info
$shellScripts = @(
    "build_glue_libs.sh"
)

foreach ($script in $shellScripts) {
    $scriptPath = Join-Path $SCRIPT_DIR $script
    if (Test-Path $scriptPath) {
        $content = Get-Content -Path $scriptPath -Raw
        $content = $content -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($scriptPath, $content)
        Write-ColorOutput "  Fixed: $script" -Type Success
    }
}

# Run the build process
Write-Host ""
Write-ColorOutput "Starting dependency compilation..." -Type Info
Write-ColorOutput "This will:" -Type Info
Write-ColorOutput "  1. Install dependencies in Linux environment" -Type Info
Write-ColorOutput "  2. Verify imports pre-optimization" -Type Info
Write-ColorOutput "  3. Optimize package size" -Type Info
Write-ColorOutput "  4. Create ZIP archive" -Type Info
Write-ColorOutput "  5. Verify imports from ZIP" -Type Info
Write-Host ""

docker run `
    --rm `
    -v "${workspaceMount}:/workspace" `
    -v "${buildMount}:/build" `
    $DOCKER_IMAGE `
    bash /workspace/build_glue_libs.sh

if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput "Build process failed" -Type Error
    Write-ColorOutput "Check the output above for errors" -Type Warning
    exit 1
}

# Verify the output exists
$outputPath = Join-Path $BUILD_DIR $OUTPUT_ZIP
if (-not (Test-Path $outputPath)) {
    Write-ColorOutput "Output ZIP not found: $outputPath" -Type Error
    exit 1
}

$zipSize = (Get-Item $outputPath).Length / 1MB
Write-Host ""
Write-Host ("=" * 80)
Write-ColorOutput "Build completed successfully!" -Type Success
Write-Host ("=" * 80)
Write-ColorOutput "Output: $outputPath" -Type Success
Write-ColorOutput "Size: $([math]::Round($zipSize, 2)) MB" -Type Success

# Display manifest if available
$manifestPath = Join-Path $BUILD_DIR "manifest.txt"
if (Test-Path $manifestPath) {
    Write-Host ""
    Write-ColorOutput "Installed packages:" -Type Info
    Get-Content $manifestPath | Select-Object -First 20 | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
    $totalPackages = (Get-Content $manifestPath).Count
    if ($totalPackages -gt 20) {
        Write-Host "  ... and $($totalPackages - 20) more" -ForegroundColor Gray
    }
}

Write-Host ""
Write-ColorOutput "Next steps:" -Type Info
Write-ColorOutput "  1. Upload to S3: aws s3 cp build/$OUTPUT_ZIP s3://your-bucket/glue-libs/" -Type Info
Write-ColorOutput "  2. Configure Glue job with --extra-py-files s3://your-bucket/glue-libs/$OUTPUT_ZIP" -Type Info
Write-Host ""

# Optional: Run standalone verification
if (-not $SkipVerify) {
    Write-ColorOutput "Running standalone verification test..." -Type Info
    docker run `
        --rm `
        -v "${workspaceMount}:/workspace" `
        -v "${buildMount}:/build" `
        -e PYTHONPATH="/build/$OUTPUT_ZIP" `
        $DOCKER_IMAGE `
        python3 /workspace/verify_glue_deps.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "Standalone verification passed" -Type Success
    } else {
        Write-ColorOutput "Standalone verification failed" -Type Error
        exit 1
    }
}

Write-Host ""
Write-ColorOutput "All done! Your dependencies are ready for AWS Glue 5.0" -Type Success
Write-Host ""
