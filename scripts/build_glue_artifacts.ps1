param(
    [string]$Python = "python",
    [string]$OutputDir = "dist",
    [string]$RequirementsFile = "requirements-glue.txt",
    [string]$GlueProvidedList = "lista_de_glue50.txt"
)

$ErrorActionPreference = "Stop"

function Normalize-PackageName {
    param([string]$Name)
    return $Name.ToLowerInvariant().Replace("_", "-").Trim()
}

function Get-GlueProvidedPackages {
    param([string]$Path)

    $set = [System.Collections.Generic.HashSet[string]]::new()
    if (-not (Test-Path $Path)) {
        return $set
    }

    foreach ($line in Get-Content $Path) {
        if ($line -match "^\s*([A-Za-z0-9_.-]+)==") {
            [void]$set.Add((Normalize-PackageName -Name $matches[1]))
        }
    }
    return $set
}

function Get-WheelDistribution {
    param([string]$FileName)
    $base = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    if (-not $base.Contains("-")) {
        return $base
    }
    return ($base -split "-", 2)[0]
}

$pythonVersion = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($pythonVersion -ne "3.11") {
    throw "El build de Glue 5.0 requiere Python 3.11. Version detectada: $pythonVersion"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$depsWheelhouse = Join-Path $OutputDir "wheels"
$zipName = Join-Path $OutputDir "glue-dependencies.gluewheels.zip"
$manifest = Join-Path $OutputDir "glue-dependencies.contents.txt"

if (Test-Path $depsWheelhouse) {
    Remove-Item -LiteralPath $depsWheelhouse -Recurse -Force
}
New-Item -ItemType Directory -Path $depsWheelhouse -Force | Out-Null
$wheelhouseRequirements = Join-Path $depsWheelhouse "requirements.txt"
Copy-Item -Path $RequirementsFile -Destination $wheelhouseRequirements -Force

if (Test-Path $zipName) {
    Remove-Item -LiteralPath $zipName -Force
}
if (Test-Path $manifest) {
    Remove-Item -LiteralPath $manifest -Force
}
Get-ChildItem -Path $OutputDir -Filter *.whl -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force
}

& $Python -m pip install --upgrade pip build wheel
& $Python -m build --wheel --outdir $OutputDir

& $Python -m pip download `
    --dest $depsWheelhouse `
    --only-binary=:all: `
    --platform manylinux_2_28_x86_64 `
    --python-version 311 `
    --implementation cp `
    --abi cp311 `
    -r $wheelhouseRequirements

$glueProvided = Get-GlueProvidedPackages -Path $GlueProvidedList
$excluded = New-Object System.Collections.Generic.List[string]
$included = New-Object System.Collections.Generic.List[string]

foreach ($wheel in (Get-ChildItem -Path $depsWheelhouse -Filter *.whl)) {
    $dist = Normalize-PackageName -Name (Get-WheelDistribution -FileName $wheel.Name)
    if ($glueProvided.Contains($dist)) {
        $excluded.Add($wheel.Name) | Out-Null
        Remove-Item -LiteralPath $wheel.FullName -Force
    }
}

$remaining = Get-ChildItem -Path $depsWheelhouse -Filter *.whl | Sort-Object Name
if ($remaining.Count -eq 0) {
    throw "No quedaron wheels de dependencias para empaquetar luego de filtrar por Glue."
}

foreach ($wheel in $remaining) {
    $included.Add($wheel.Name) | Out-Null
}

& $Python -c @"
import zipfile
from pathlib import Path

zip_path = Path(r'''$zipName''')
wheels_dir = Path(r'''$depsWheelhouse''')

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for item in wheels_dir.rglob('*'):
        if item.is_file():
            arcname = str(item.relative_to(wheels_dir.parent))
            zf.write(item, arcname)

print(f'Created {zip_path} with wheels/ at root')
"@

Set-Content -Path $manifest -Value @(
    "Glue dependency bundle manifest"
    "Python: $pythonVersion"
    "Requirements file: $RequirementsFile"
    "Glue baseline list: $GlueProvidedList"
    ""
    "Included wheels:"
)
Add-Content -Path $manifest -Value ($included | ForEach-Object { "- $_" })
Add-Content -Path $manifest -Value ""
Add-Content -Path $manifest -Value "Excluded wheels (already provided by Glue baseline):"
if ($excluded.Count -eq 0) {
    Add-Content -Path $manifest -Value "- (none)"
}
else {
    Add-Content -Path $manifest -Value ($excluded | Sort-Object | ForEach-Object { "- $_" })
}

Write-Host "Artifacts:"
Get-ChildItem $OutputDir
