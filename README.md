# CPTEC-PVM2 in Python

[![tests](https://github.com/felipefalexandre/cptec-pvm2-python-version/actions/workflows/tests.yml/badge.svg)](https://github.com/felipefalexandre/cptec-pvm2-python-version/actions/workflows/tests.yml)

A modern Python implementation of **CPTEC-PVM2**, the potential-vegetation
model described by Oyama & Nobre (2004) and extended with the natural-fire
parameterisation of Lapola et al. (2006).  The original Fortran 77 sources are
kept under `legacy/fortran/` for reference and are used to validate the Python
implementation.

The repository contains both the recovered legacy code and a new, tested,
grid-agnostic Python package.  The Python results reproduce the legacy build at
the classification level (100% identical biome map) and match the intermediate
environmental fields to float32 precision.

## Status

| Item | Result |
| --- | --- |
| Biome map vs legacy Fortran (`ca=35.35 Pa`, fire on) | 100% identical |
| Intermediate fields vs legacy Fortran | max abs. diff <= 5.8e-5 (float32 rounding) |
| Kappa vs observed reference map | 0.525 (paper: 0.54) |
| Legacy runtime (192x96 grid) | 3.4 s |
| Python runtime (192x96 grid) | 18.4 s |
| Tests | 91 collected |

Details and caveats are in `docs/numerical_equivalence.md`.

## Installation

Python 3.10 or newer is required (tested with 3.11.9 on Windows).

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev,report]"
pvm2 --version
```

## Input data

The default climate, land-mask and reference data are included so that a
fresh clone can run the reference experiment without external downloads:

```
legacy/data/inputs/
    prec.bin  temp.bin  ipar.bin  psup.bin  lsmk.bin  uwind.bin
    prec.nc   temp.nc   uwnd.nc   *.ctl     ylat.txt
legacy/data/reference/
    Lapola_et_al_T062.bin
    vegetacao_referencia.qml
```

The binaries and the observed reference map are third-party scientific data;
their original licence is not stated.  They are included only for scientific
reproducibility.  See `legacy/data/README.md` for sizes, checksums and
provenance.  The reference experiment configuration is
`experiments/original/original.yaml`.

## Quick start

Convert the legacy direct-access binaries to a self-describing NetCDF file:

```bash
pvm2 convert-legacy --config configs/legacy.yaml
```

Inspect the file:

```bash
pvm2 info --input outputs/pvm2_inputs.nc
```

Run the model from the consolidated NetCDF inputs:

```bash
pvm2 run --config configs/example.yaml
```

or directly from the reference legacy binaries:

```bash
pvm2 run --config experiments/original/original.yaml
```

Reproduce the reference experiment and compute the kappa validation report:

```bash
pvm2 reproduce --config experiments/original/original.yaml
```

Override model settings from the command line:

```bash
pvm2 run --config experiments/original/original.yaml --co2 51.5375 --no-fire
```

Fine grids take many equilibrium years, so `run` logs progress at most every
two seconds (year, month, converged/land cells, elapsed time) and a final
summary.  `--max-years` changes the equilibrium limit.

## Installation check and reference figure

Run the automated check before starting new experiments:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_installation.ps1
```

The script runs the installation diagnostics, the test suite, validates the
bundled inputs, runs the reference experiment with `ca = 35.35 Pa` and fire on,
and requires `kappa >= 0.50` against the observed natural-vegetation map.  The
expected value is `kappa = 0.525` (`agreement = 89.72%`).  The same steps
manually:

```bash
pvm2 doctor
pytest -q
pvm2 validate --config experiments/original/original.yaml
pvm2 reproduce --config experiments/original/original.yaml --min-kappa 0.50
```

`pvm2 doctor` works on Windows, Linux and macOS.  `pvm2 doctor --full` also
runs the reference experiment and checks kappa; add `--json` for automation.

`reproduce` writes:

```
outputs/original/pvm2_original_biome.tif              simulated potential vegetation
outputs/original/pvm2_original_reference_biome.tif    observed natural vegetation
outputs/original/pvm2_original.nc                     full model output
reports/scientific_validation.html                    kappa and map comparison
```

To compare with Figure 1b of Lapola et al. (2009) on page 5, open both
GeoTIFFs in QGIS and load the style
`legacy/data/reference/vegetacao_referencia.qml`.  The simulated map should
show the same biome classes and colours as the published potential-vegetation
panel.  The article citation, DOI and a description of the check are in
`docs/reference_lapola_2009.md`.

## Command line

```
pvm2 doctor          check installation, data checksums and reference kappa
pvm2 run             run PVM2 from a NetCDF file or a YAML configuration
pvm2 reproduce       run the configured reference experiment and validate
pvm2 prepare         resample heterogeneous inputs onto a common lsmk grid
pvm2 convert-legacy  convert legacy binaries to consolidated NetCDF
pvm2 validate        check dimensions, ranges and land-mask consistency
pvm2 inspect         report metadata, domain, time, units and SHA-256
pvm2 compare-legacy  compare Python fields with legacy Fortran output
pvm2 info            describe a NetCDF or configuration file
pvm2 config check    validate a YAML configuration
pvm2 config show     print a normalized YAML configuration
```

`validate` and `inspect` accept `--json`; `validate --report` also writes the
report to a file.  For example:

```bash
pvm2 validate --config experiments/original/original.yaml \
  --json --report reports/input_validation.json
pvm2 inspect --input outputs/pvm2_inputs.nc --json
```

The report includes per-variable units, ranges, missing values over land,
grid spacing, time/calendar metadata and SHA-256 hashes of the configuration
and source files.

### Compare with the Fortran version

Build and run the legacy model with the same CO2 value as
`experiments/original/original.yaml`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_legacy.ps1 `
  -Co2 35.35 -BuildDir build/ca350
powershell -ExecutionPolicy Bypass -File scripts/run_legacy.ps1 `
  -BuildDir build/ca350
```

The second script runs `pvm2.exe` and `pvm5.exe` from `build/ca350/code` and
writes the Fortran fields to `build/ca350/outputs`.  Then run Python and compare
every annual, monthly and bundled field:

```bash
pvm2 run --config experiments/original/original.yaml
pvm2 compare-legacy \
  --fortran-dir build/ca350/outputs \
  --python outputs/original/pvm2_original.nc \
  --report reports/field_comparison.json
```

Use `pvm2 <command> --help` for all options.

## Configuration

Legacy binary input:

```yaml
input:
  shape: [96, 192]
  coordinates_file: legacy/data/inputs/ylat.txt
  legacy:
    precipitation: legacy/data/inputs/prec.bin
    temperature: legacy/data/inputs/temp.bin
    par: legacy/data/inputs/ipar.bin
    pressure: legacy/data/inputs/psup.bin
    landmask: legacy/data/inputs/lsmk.bin
    uwind: legacy/data/inputs/uwind.bin

model:
  co2_pa: 35.35
  fire: true

output:
  directory: outputs
  name: pvm2
  netcdf: true
  geotiff: true
  write_legacy_binary: false
```

NetCDF input with explicit variable/coordinate names and units.  Monthly
climatologies must be 3-D `(time, lat, lon)` with exactly 12 steps; `pressure`
and `landmask` may be 2-D `(lat, lon)` or a constant 3-D field.

```yaml
input:
  climate: outputs/pvm2_inputs.nc
  variables:
    precipitation: pr
    temperature: tas
    par: par
    pressure: ps
    landmask: lsmk
    uwind: ua850
  coordinates:
    latitude: lat
    longitude: lon
    time: time
  units:
    precipitation: mm/month
    temperature: degC
    par: W m-2
    pressure: hPa
    uwind: m s-1
```

Configuration files are validated strictly: unknown keys, wrong types and
invalid choices are rejected before any data is loaded.  Check and inspect a
file without running the model:

```bash
pvm2 config check --config configs/heterogeneous.yaml
pvm2 config show --config configs/heterogeneous.yaml --resolved
```

Use `--set key=value` to override a field without editing the file, for example
`pvm2 run --config experiments/original/original.yaml --set model.fire=false`.
By default paths are relative to the current directory.  Set
`paths_relative_to: config` to resolve them relative to the YAML file instead.
In non-interactive use, `pvm2 prepare` requires an explicit `--target` or
`--yes`.

Supported input units are converted only when unambiguous:

| Variable | Accepted units |
| --- | --- |
| precipitation | `mm/month`, `m/month`, `mm/day`, `m/day`, `kg m-2 s-1` |
| temperature | `degC`, `K` |
| pressure | `hPa`/`mb`, `Pa`, `kPa` |
| PAR | `W m-2`, `Einstein m-2 s-1` |
| wind | `m s-1` |

`pvm2 run` itself never resamples: the output grid is exactly the prepared
input grid.  When variables come from different grids, run `pvm2 prepare`
first.

### Heterogeneous input grids

Datasets from CMIP6, ERA5, MERGE-CPTEC, CODEX or regional products often use
different resolutions and longitude conventions.  `pvm2 prepare` inspects every
climate field, finds the **coarsest** resolution and offers only land-mask grids
that are at least that coarse.  Climate fields are then bilinearly
resampled to the chosen grid and cropped to their common domain; no climate
field is moved to a finer grid.

Sources may be global or already cropped.  `pvm2 prepare` reports the domain
of every input, intersects them, and keeps the target resolution unchanged, so
a regional box in any one variable is applied consistently to all fields.  To
crop global data explicitly, set `input.bbox` or use `--bbox`:

```yaml
input:
  bbox: [-30, 15, -85, -30]   # lat_min, lat_max, lon_min, lon_max
  sources:
    precipitation:
      path: data/pr.nc
      units: mm/day
    temperature:
      path: data/tas.nc
      units: K
    par:
      path: data/par.nc
    pressure:
      path: data/ps.nc
      units: Pa
    uwind:
      path: data/ua850.nc
    # optional; otherwise a bundled lsmk preset is used
    landmask:
      path: data/lsmk.nc
```

Each source may override `variable`, `units` and `coordinates`.  Use
`--bbox LAT_MIN LAT_MAX LON_MIN LON_MAX` to override the crop at run time
(longitudes may be in `-180..180` or `0..360`).  List the domains and
compatible targets without running anything:

```bash
pvm2 prepare --config configs/heterogeneous.yaml --list
```

Choose interactively (the recommended target is the finest grid that does not
upscale any input), or select explicitly:

```bash
pvm2 prepare --config configs/heterogeneous.yaml
pvm2 prepare --config configs/heterogeneous.yaml --target 0.5
pvm2 run --input outputs/prepared/pvm2_inputs_0p5.nc
```

Bundled `lsmk` presets are at 0.10, 0.25, 0.50, 1.00, 2.00, 2.50, 5.00 and
10.00 degrees (see `src/pvm2/data/lsmk/README.md`).  They use Natural Earth
1:10m land polygons rasterized at cell centres, not provider-specific masks.
A user mask can be supplied with `--landmask`.  If it is not finer than the
coarsest climate field it becomes an additional target grid; if it is finer,
it is area-aggregated to the selected grid, so only the coastline benefits
from the finer data while the climate fields remain on the coarser grid.

Longitudes in `0..360` and `-180..180` are both accepted.  The prepared file
uses the selected preset convention (`-180..180`).

### Plausible input ranges

Every run and preparation checks the converted fields before starting the
model.  Values outside these ranges usually mean a unit or variable-mapping
error, and `pvm2` asks for the input to be corrected:

| Variable | Accepted range | Expected units |
| --- | --- | --- |
| precipitation | 0 to 5000 | `mm/month` |
| temperature | -90 to 60 | `degC` |
| PAR | 0 to 500 | `W m-2` |
| pressure | 250 to 1100 | `hPa` |
| uwind | -150 to 150 | `m s-1` |
| landmask | exactly 0 or 1 | `1` |

For example, temperature in Kelvin declared as `degC`, pressure in `Pa`
declared as `hPa`, or a fractional land mask are rejected with the field name,
observed range and expected units.  All problems are reported together.

## Outputs

`run` writes:

- `pvm2_<name>.nc` — NetCDF with coordinates and all annual/monthly fields.
- `pvm2_<name>_biome.tif` - GeoTIFF biome map.  Regular grids use an affine
  transform; irregular grids such as T62 use per-cell GCPs stored in the
  accompanying `.tif.aux.xml` sidecar (keep both files together).
- `pvm2_<name>_legacy.bin` — optional 12-record bundle in the original
  `pvm5` order.
- `pvm2_<name>_reference_biome.tif` — observed reference map written by
  `reproduce`, using the same grid as the simulated map for QGIS comparison.

Main NetCDF variables include `biome` (potential vegetation class), `tmin`,
`meanpp`, `seanpp`, `meanhr`, `meancs`, `mphoto`, `maresp`, `seai`, `weti`,
`ratioNPP`, `d2wm`, `ud2w`, and the monthly fields `npp`, `gpp`, `ra`,
`soilmoist`, `evapotranspiration`, `runoff`, `snowmelt`, `canopy_resistance`,
`lai`, `litter`, `soil_carbon`, `heterotrophic_respiration`.

Class codes:

| Code | Biome |
| --- | --- |
| 0 | ocean / no vegetation |
| 1 | tropical ombrophilous forest |
| 2 | temperate forest |
| 3 | mixed forest |
| 4 | boreal forest |
| 5 | larch forest |
| 6 | savanna |
| 7 | grasslands / campos |
| 8 | caatinga |
| 9 | semi-desert |
| 10 | tundra |
| 11 | desert |
| 13 | tropical seasonal forest |
| 20 | ice |

The kappa implementation remaps 13 -> 12 and 20 -> 13, following `skill4.f`.

The legacy latitude axis is a **T62 Gaussian grid**, not a regular one.  A
single affine transform cannot represent Gaussian latitudes, so this grid is
written with one ground control point per cell.  GDAL stores those GCPs in a
`.tif.aux.xml` sidecar, so the `.tif` and its sidecar must be kept together.
The NetCDF output remains the authoritative, self-contained product.  Regular
synthetic grids use a conventional north-up affine GeoTIFF.

## Validation

```bash
pytest
```

The suite covers:

- carbon and water-balance equations against double-precision Fortran output;
- biome rules and the fire parameterisation;
- legacy binary and NetCDF round-trips, including the consolidated NetCDF
  input path;
- shape preservation on two synthetic resolutions;
- full reference run against a stored Fortran biome map and the observed map;
- field-by-field comparison with the legacy annual, monthly and 12-record
  bundle outputs.

The full reference test takes about 20 seconds; the rest take about 3 seconds.

## Documentation

- `docs/legacy_code_audit.md` — complete audit of the Fortran code, data,
  equations, compilation and risks.
- `docs/scientific_methodology.md` — equations, parameters and units as
  implemented.
- `docs/numerical_equivalence.md` — validation strategy, results and
  limitations.
- `docs/migration_report.md` — architecture of the Python package and the
  migration decisions.
- `docs/reference_lapola_2009.md` — article citation, DOI and the Figure 1b
  installation check.

## Provenance and licence

The new Python code is released under the MIT licence (`LICENSE`).  The legacy
Fortran sources, input data and reference map retain their original authorship
and are not covered by that licence; see `NOTICE` and
`legacy/data/README.md` before redistributing them.

## Citation

If you use this implementation, cite the model papers:

- Oyama, M. D.; Nobre, C. A. A simple potential vegetation model for coupling
  with the Simple Biosphere Model (SiB). *Revista Brasileira de Meteorologia*,
  v. 19, n. 2, p. 203-216, 2004.
- Lapola, D. M. et al. A importância da parametrização de fogo natural no
  CPTEC PVM. 2006. (See `docs/legacy_code_audit.md` for the full reference.)
- Lapola, D. M.; Oyama, M. D.; Nobre, C. A. Exploring the range of climate
  biome projections for tropical South America: the role of CO2 fertilization
  and seasonality. *Global Biogeochemical Cycles*, v. 23, GB3002, 2009.
  https://doi.org/10.1029/2008GB003357
