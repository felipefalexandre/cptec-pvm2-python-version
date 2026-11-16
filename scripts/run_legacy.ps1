# Run the compiled Fortran PVM2 twice: env5/pvm2.exe computes the environmental
# fields and pvm5.exe computes the monthly and biome outputs.
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$BuildDir = ""
)

$ErrorActionPreference = "Stop"
if ($BuildDir -eq "") { $BuildDir = Join-Path $Root "build\legacy" }
$code = Join-Path $BuildDir "code"
$outputs = Join-Path $BuildDir "outputs"
foreach ($exe in @("pvm2.exe", "pvm5.exe")) {
    if (-not (Test-Path -LiteralPath (Join-Path $code $exe))) {
        throw "missing $exe; run scripts/build_legacy.ps1 first"
    }
}
New-Item -ItemType Directory -Force -Path $outputs | Out-Null

Push-Location $code
try {
    & .\pvm2.exe
    if ($LASTEXITCODE -ne 0) { throw "pvm2.exe failed" }
    & .\pvm5.exe
    if ($LASTEXITCODE -ne 0) { throw "pvm5.exe failed" }
} finally {
    Pop-Location
}
Write-Host "Fortran outputs written to $outputs"
