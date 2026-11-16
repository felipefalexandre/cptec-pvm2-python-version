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
| Intermediate fields vs legacy Fortran | max abs. diff <= 2.0e-5 (float32 rounding) |
| Kappa vs observed reference map | 0.525 (paper: 0.54) |
| Legacy runtime (192x96 grid) | 3.4 s |
| Python runtime (192x96 grid) | 18.8 s |
| Tests | 40 collected; 6 skip without the raw data |

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

The raw climate and land-mask binaries are **not redistributed** in this
repository because their original licences are not stated.  Place the files
delivered with the legacy model in `legacy/data/inputs/`:

```
legacy/data/inputs/
    prec.bin  temp.bin  ipar.bin  psup.bin  lsmk.bin  uwind.bin
    ylat.txt
legacy/data/reference/
    Lapola_et_al_T062.bin
```

See `legacy/data/README.md` for sizes, checksums and provenance.  Tests that
need these files are skipped automatically when they are absent.

The reference experiment configuration is
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

## Command line

```
pvm2 run             run PVM2 from a NetCDF file or a YAML configuration
pvm2 reproduce       run the configured reference experiment and validate
pvm2 convert-legacy  convert legacy binaries to consolidated NetCDF
pvm2 validate        check dimensions, ranges and land-mask consistency
pvm2 info            describe a NetCDF or configuration file
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
and `landmask` may be 2-D `(lat, lon)` or 3-D with a single time slice:

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

Supported input units are converted only when unambiguous.  The model never
resamples or interpolates: the output grid is exactly the input grid, and grid
dimensions are read at runtime rather than hard-coded.

## Outputs

`run` writes:

- `pvm2_<name>.nc` — NetCDF with coordinates and all annual/monthly fields.
- `pvm2_<name>_biome.tif` - GeoTIFF biome map.  Regular grids use an affine
  transform; irregular grids such as T62 use per-cell GCPs stored in the
  accompanying `.tif.aux.xml` sidecar (keep both files together).
- `pvm2_<name>_legacy.bin` — optional 12-record bundle in the original
  `pvm5` order.

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
- full reference run against a stored Fortran biome map and the observed map.

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
