param(
    [string]$Python = "python",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}

& $Python -m pip install --upgrade pip build wheel
& $Python -m build --wheel
& $Python -m pip wheel --wheel-dir $OutputDir -r requirements-glue.txt

$zipName = Join-Path $OutputDir "glue-dependencies.gluewheels.zip"
if (Test-Path $zipName) {
    Remove-Item -Force $zipName
}

Compress-Archive -Path (Join-Path $OutputDir "*.whl") -DestinationPath $zipName

Write-Host "Artifacts:"
Get-ChildItem $OutputDir
