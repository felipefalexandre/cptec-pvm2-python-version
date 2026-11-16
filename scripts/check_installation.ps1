# Verify that the Python package, the bundled reference data and the
# reference experiment are working before starting new experiments.
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [double]$MinKappa = 0.50
)

$ErrorActionPreference = "Stop"
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

Push-Location $Root
try {
    Write-Host "== Python tests =="
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

    Write-Host "== Input validation =="
    & $python -m pvm2.cli validate --config experiments/original/original.yaml
    if ($LASTEXITCODE -ne 0) { throw "input validation failed" }

    Write-Host "== Reference experiment =="
    & $python -m pvm2.cli reproduce --config experiments/original/original.yaml --min-kappa $MinKappa
    if ($LASTEXITCODE -ne 0) {
        throw "reference experiment failed or kappa is below $MinKappa"
    }
} finally {
    Pop-Location
}

$tif = Join-Path $Root "outputs\original\pvm2_original_biome.tif"
$reference = Join-Path $Root "outputs\original\pvm2_original_reference_biome.tif"
$style = Join-Path $Root "legacy\data\reference\vegetacao_referencia.qml"
foreach ($path in @($tif, $reference, $style)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "missing $path" }
}

Write-Host ""
Write-Host "Installation OK."
Write-Host "Open these GeoTIFFs in QGIS and load the palette from:"
Write-Host "  $style"
Write-Host "  $tif"
Write-Host "  $reference"
Write-Host "Compare the simulated map with Figure 1b of Lapola et al. (2009)."
