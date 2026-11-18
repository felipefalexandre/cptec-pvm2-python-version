# Migration report

## 1. Deliverables

| Path | Contents |
| --- | --- |
| `src/pvm2/` | Python package, including `prepare.py`, `grid.py`, `ranges.py`, `core/checkpoint.py` and eight bundled lsmk presets |
| `legacy/fortran/` | original Fortran sources, unmodified |
| `legacy/data/` | default inputs, observed reference map and QGIS palette |
| `scripts/build_legacy.ps1` | reproducible legacy build (RECL adaptation and `-Co2`) |
| `scripts/run_legacy.ps1` | runs the compiled Fortran model and writes its outputs |
| `scripts/check_installation.ps1` | runs tests, validates inputs and checks the reference kappa/figure |
| `scripts/check_regression.py` | CI golden check of the reference biome map, metrics and counts |
| `configs/` | legacy-binary, NetCDF and heterogeneous-source examples |
| `experiments/original/` | reference experiment |
| `tests/` | 101 tests and Fortran-generated fixtures |
| `docs/` | audit, methodology, equivalence, reference-article check, this report |

The default inputs and the observed reference map are included so a fresh
clone can reproduce the reference experiment.  Their licence is not stated
and they are not covered by the MIT License; the paper PDF is not included.
Checksums and provenance are in `legacy/data/README.md`.

## 2. Package architecture

```
pvm2
├── config.py                 YAML -> dataclasses; legacy and NetCDF loaders
├── cli.py                    run / reproduce / convert-legacy / validate / info
├── core
│   ├── constants.py          single source of truth for physical constants
│   ├── carbon.py             tetens, carbon1, carbon2
│   ├── water_balance.py      budget_month, soil temperature, equilibrium,
│   │                         classification, transition month, fire
│   └── model.py              validation/preparation and top-level run
├── io
│   ├── legacy_binary.py      direct-access float32 reader/writer
│   ├── netcdf.py             climate loader, NetCDF writer, summary
│   ├── raster.py             GeoTIFF writer with regular-grid guard
│   └── vector.py             optional polygon export helper
└── validation
    ├── kappa.py              skill4-compatible kappa and class remapping
    └── report.py             HTML/JSON/PNG validation report
```

The core is grid-agnostic: every function derives `ny` and `nx` from the input
arrays.  There is no global `NX`/`NY` and no hidden resampling.

## 3. Configuration model

`config.py` defines `InputConfig`, `ModelConfig`, `OutputConfig` and
`RunConfig`.  `load_config` accepts either a YAML file or a dictionary, fills
defaults, rejects unknown keys or invalid types, and supports repeatable
`key=value` overrides.  Relative paths are resolved against the current
directory by default, or against the configuration file when
`paths_relative_to: config` is set.  `pvm2 config check` and `pvm2 config show`
validate and inspect a file without loading data.  Outputs can opt into a
timestamped (`output.run_directory: true`) or named (`output.run_id`) run
directory.  Inputs are either:

- `input.legacy` — six direct-access binaries plus `shape` and an optional
  latitude file; or
- `input.climate` — a NetCDF file with explicit variable/coordinate/unit
  mappings.

The NetCDF loader converts units only when a mapping is known.  Unmapped
variables are passed through and the caller is responsible for units.

## 4. Numerical implementation

The equations are transcribed directly from the Fortran, including the
commented-out alternatives being left disabled (for example the older runoff
coefficient and the older available-energy fit).  Constants live in
`core/constants.py` and are used by both the water balance and the tests.

Two implementation changes are deliberate and numerically neutral:

1. **Active-cell equilibrium.**  The legacy model stops iterating a cell when
   its annual storage cycle converges.  The Python version keeps a flat array
   of active cell indices and updates only those cells, which gives the same
   per-cell result with an 18x speed-up.  The convergence test is unchanged.
2. **Explicit failure for `findm`.**  The legacy code would read outside
   `dw(12)` if no dry-to-wet transition existed.  Python raises
   `RuntimeError` with the number of affected cells.

No equation, threshold or parameter value was changed.

## 5. Input handling

- Binary records are read as `<f4` and reshaped to `(count, ny, nx)`; the
  Fortran order means longitude varies fastest.  The old mistake of reshaping
  to `(count, nx, ny)` would transpose the map.
- `pnew.bin`/`tnew.bin` and `unew_100.bin` are accepted as aliases for the
  delivered `prec.bin`/`temp.bin`/`uwind.bin`.
- NetCDF climate files with a duplicated 360-degree longitude are reduced to
  192 points by dropping the last column, after verifying that the duplicate
  matches the first column.
- Temperature, precipitation, PAR and wind are checked for missing values over
  land before the run; PVM2 has no missing-data scheme.
- The land mask is truncated to integer as in `int(lsmk)`; pressure and mask
  shapes must match the climate grid.

## 6. Output handling

- NetCDF uses xarray/netCDF4 with `lat`, `lon`, `time` (month) coordinates and
  CF-style units and long names.
- The biome variable is named `biome` in NetCDF and `bpot` in the in-memory
  results dictionary (legacy name).
- A 12-record legacy bundle can be written in the exact `pvm5` order:
  `bpot, npp, snpp, ratioNPP, hresp, csoil, d2wm, ud2w, photo, aresp, seai,
  weti`.
- GeoTIFF uses a north-up affine transform for regular axes.  The T62 Gaussian
  grid is written with per-cell ground control points in a `.tif.aux.xml`
  sidecar; no silent reprojection is performed.
- The validation report contains the kappa metrics, per-class table,
  confusion matrix and a map figure.

## 7. Command line

`pvm2` is installed as a console script.  Commands:

- `doctor` — checks dependencies, data checksums, presets and optionally
  reproduces the reference experiment.
- `run` — from YAML or NetCDF; overrides CO2, fire and maximum years, and
  logs throttled equilibrium progress for long fine-grid runs.
- `reproduce` — runs the configured experiment and writes the validation
  report when a reference map is configured.
- `prepare` — inspects per-variable grids and their domains, offers compatible
  bundled land-mask resolutions from coarsest to finest, intersects regional
  inputs (or an optional `bbox`), bilinearly resamples the climate fields to
  the selected grid at unchanged resolution, and validates plausible ranges.
- `pipeline` — runs the prepare step and then the model on the in-memory
  prepared fields, recording the prepared-file hash and preparation metadata
  in the run manifest.
- `convert-legacy` — writes a consolidated NetCDF of the six inputs.
- `validate` — checks shapes, ranges and land-mask consistency; `--json` and
  `--report` emit machine-readable reports.
- `inspect` — reports metadata, units, domain, time/calendar, missing values
  and SHA-256 hashes for a NetCDF file or configured inputs.
- `compare-legacy` — compares annual, monthly and bundled fields with a local
  Fortran build.
- `info` — prints a summary of a NetCDF or configuration.
- `config check` / `config show` — validate and print normalized configuration.

## 8. Testing

`pytest` runs 101 tests in about 61 seconds, and CI adds
`scripts/check_regression.py`, which compares the reference biome map hash,
per-class counts, kappa and equilibrium years against a golden file:

- cell tiling and checkpoint/resume against uninterrupted reference runs;
- scalar `carbon1`/`carbon2` against double-precision Fortran;
- every biome rule, the fire switch and the transition-month search;
- daily budget bounds and finiteness;
- legacy binary and NetCDF round-trips, plus a full run driven by the
  consolidated NetCDF input file;
- input statistics against known values;
- shape preservation for 8x10 and 16x24 synthetic grids;
- full reference run against the stored Fortran biome map;
- kappa against the observed map.

Data-dependent tests are skipped automatically when the bundled inputs are
missing, so an incomplete checkout still runs the remaining tests.

## 9. Performance

| Version | Runtime (96x192, 121 years) |
| --- | --- |
| Fortran, gfortran -O0 | 3.4 s |
| Python, full-grid vectorisation | 341 s |
| Python, active-cell vectorisation | 18.4 s |

The remaining gap is interpreter overhead in the 44 000 daily iterations.
The Penman routines reuse the saturation vapour pressure already computed in
`carbon1`, avoiding two redundant `tetens` evaluations per day.  Further
optimisation (Numba or a compiled kernel) was deliberately left out until
equivalence was established; it can be added behind the same API.

## 10. Known deviations and open items

- `ca` default is 35.35 Pa in Python; the delivered source hard-codes
  51.5375 Pa.  Both are available through `--co2`.
- GCP-based GeoTIFFs need their `.tif.aux.xml` sidecar; NetCDF is the
  self-contained authoritative product.
- `seai`/`weti` over ocean use -999.99 instead of the legacy uninitialised
  values.
- Kappa differs from the paper for classes 6 and 13; see
  `docs/numerical_equivalence.md`.
- Raw inputs and the paper PDF are not in the public repository.
- A future release could add a self-contained resampled COG for Gaussian
  grids and optional Numba acceleration.
