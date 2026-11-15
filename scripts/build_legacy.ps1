# Build the original Fortran PVM2 exactly as delivered, adapting only the
# direct-access RECL unit (word-based in the original Intel/g95 compiler,
# byte-based in gfortran). No numerical expression is modified.
param(
    [string]$Gfortran = "gfortran",
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$BuildDir = ""
)

$ErrorActionPreference = "Stop"
if ($BuildDir -eq "") { $BuildDir = Join-Path $Root "build\legacy" }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::Combine($BuildDir, "code")) | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "inputs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "outputs") | Out-Null

$src = Join-Path $Root "legacy\fortran"
foreach ($f in @("env5.f", "wbm4.f", "carbon2.f", "pvm5.f")) {
    $text = Get-Content -LiteralPath (Join-Path $src $f) -Raw
    # word-based RECL -> byte-based RECL for gfortran
    $text = $text -replace "recl=nx\*ny\)", "recl=nx*ny*4)"
    Set-Content -LiteralPath ([System.IO.Path]::Combine($BuildDir, "code", $f)) -Value $text -NoNewline
}

$in = Join-Path $Root "legacy\data\inputs"
foreach ($name in @("psup.bin", "lsmk.bin", "ipar.bin", "uwnd.bin", "prec.bin", "temp.bin")) {
    Copy-Item -LiteralPath (Join-Path $in $name) -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", $name)) -Force
}
# env5.f expects pnew.bin / tnew.bin (same data as prec.bin / temp.bin)
Copy-Item -LiteralPath (Join-Path $in "prec.bin") -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", "pnew.bin")) -Force
Copy-Item -LiteralPath (Join-Path $in "temp.bin") -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", "tnew.bin")) -Force

Push-Location ([System.IO.Path]::Combine($BuildDir, "code"))
try {
    & $Gfortran -std=legacy -O0 -ffp-contract=off -fno-fast-math `
        env5.f wbm4.f carbon2.f -o pvm2.exe
    if ($LASTEXITCODE -ne 0) { throw "env5 build failed" }
    & $Gfortran -std=legacy -O0 -ffp-contract=off -fno-fast-math `
        pvm5.f -o pvm5.exe
    if ($LASTEXITCODE -ne 0) { throw "pvm5 build failed" }
    & $Gfortran --version | Select-Object -First 1
} finally {
    Pop-Location
}
Write-Host "Built into $BuildDir"

