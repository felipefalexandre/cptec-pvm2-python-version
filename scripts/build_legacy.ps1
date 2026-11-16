# Build the Fortran PVM2 with two mechanical adaptations for gfortran:
#
#   1. direct-access RECL is byte-based, not word-based;
#   2. the active `ca=` assignment is set explicitly from -Co2.
#
# The default -Co2 51.5375 is the value hard-coded in the delivered source.
# Use -Co2 35.35 to reproduce the reference experiment and the Python
# configuration in experiments/original/original.yaml.
param(
    [string]$Gfortran = "gfortran",
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$BuildDir = "",
    [double]$Co2 = 51.5375
)

$ErrorActionPreference = "Stop"
if ($BuildDir -eq "") { $BuildDir = Join-Path $Root "build\legacy" }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::Combine($BuildDir, "code")) | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "inputs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "outputs") | Out-Null

$co2Literal = $Co2.ToString("0.0####", [System.Globalization.CultureInfo]::InvariantCulture)
$src = Join-Path $Root "legacy\fortran"
foreach ($f in @("env5.f", "wbm4.f", "carbon2.f", "pvm5.f")) {
    $text = Get-Content -LiteralPath (Join-Path $src $f) -Raw
    # word-based RECL -> byte-based RECL for gfortran
    $text = $text -replace "recl=nx\*ny\)", "recl=nx*ny*4)"
    if ($f -eq "env5.f") {
        $pattern = '(?m)^\s*ca= \(\(100\.10-35\.35\)\*0\.25\)\+35\.35.*$'
        if ($text -notmatch $pattern) {
            throw "could not locate the active ca assignment in env5.f"
        }
        $text = [regex]::Replace(
            $text,
            $pattern,
            "      ca= $co2Literal !Pa (set by build_legacy.ps1 -Co2 $co2Literal)"
        )
    }
    Set-Content -LiteralPath ([System.IO.Path]::Combine($BuildDir, "code", $f)) -Value $text -NoNewline
}

$in = Join-Path $Root "legacy\data\inputs"
if (-not (Test-Path -LiteralPath $in)) {
    throw "missing input directory: $in (see legacy/data/README.md)"
}
$inputs = @("psup.bin", "lsmk.bin", "ipar.bin", "prec.bin", "temp.bin", "uwind.bin")
foreach ($name in $inputs) {
    $source = Join-Path $in $name
    if (-not (Test-Path -LiteralPath $source)) {
        throw "missing required legacy input: $source (see legacy/data/README.md)"
    }
    Copy-Item -LiteralPath $source -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", $name)) -Force
}
# env5.f expects pnew.bin / tnew.bin (same data as prec.bin / temp.bin)
Copy-Item -LiteralPath (Join-Path $in "prec.bin") -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", "pnew.bin")) -Force
Copy-Item -LiteralPath (Join-Path $in "temp.bin") -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", "tnew.bin")) -Force
# pvm5.f expects unew_100.bin (same data as uwind.bin)
Copy-Item -LiteralPath (Join-Path $in "uwind.bin") -Destination ([System.IO.Path]::Combine($BuildDir, "inputs", "unew_100.bin")) -Force

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
Write-Host "Built into $BuildDir with ca=$co2Literal Pa"
