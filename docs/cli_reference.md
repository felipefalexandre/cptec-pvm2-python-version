# Command-line reference

`pvm2` is installed as a console script by `pip install -e .`.  This page lists
the commands, the common execution options and the configuration keys.  Use
`pvm2 <command> --help` for the authoritative option list.

## Commands

| Command | Purpose |
| --- | --- |
| `pvm2 doctor` | Check dependencies, data checksums and presets; `--full` also runs the reference experiment and kappa gate. |
| `pvm2 run` | Run the model from a YAML configuration or a consolidated NetCDF file. |
| `pvm2 reproduce` | Run the reference configuration, compare with the observed map and write the validation report. |
| `pvm2 prepare` | Inspect heterogeneous sources, choose a land-mask grid and write prepared inputs. |
| `pvm2 pipeline` | Prepare heterogeneous inputs and run the model in one command. |
| `pvm2 convert-legacy` | Convert the six legacy binaries to a consolidated NetCDF file. |
| `pvm2 validate` | Validate dimensions, ranges, units and land-mask consistency. |
| `pvm2 inspect` | Report metadata, domain, time, units and SHA-256 hashes. |
| `pvm2 compare-legacy` | Compare Python and Fortran fields. |
| `pvm2 info` | Describe a NetCDF file or normalized configuration as JSON. |
| `pvm2 config check` | Parse and validate a YAML configuration. |
| `pvm2 config show` | Print a normalized configuration as YAML or JSON. |

## Common execution options

These options are accepted by `run`, `reproduce` and `pipeline`:

| Option | Meaning |
| --- | --- |
| `--config PATH` | YAML configuration file. |
| `--input PATH` | Consolidated NetCDF climate file; overrides the configuration. |
| `--output PATH` | Output directory; overrides `output.directory`. |
| `--co2 PA` | Atmospheric CO2 partial pressure. |
| `--fire` / `--no-fire` | Enable or disable the fire parameterisation. |
| `--max-years N` | Maximum equilibrium years. |
| `--no-geotiff` | Do not write GeoTIFF outputs. |
| `--set KEY=VALUE` | Override a configuration key; repeatable. |
| `--tile-cells N` | Process at most `N` active cells at a time, with identical results. |
| `--checkpoint PATH` | Write an atomic checkpoint after complete model years. |
| `--checkpoint-every N` | Checkpoint interval in years (default `1`). |
| `--resume` | Continue from `--checkpoint`; validates grid, CO2 and water-balance inputs. |
| `--run-dir` | Write into a timestamped run subdirectory. |
| `--run-id NAME` | Write into a named run subdirectory. |
| `--dry-run` | Load and validate inputs, then print the plan without running the model. |
| `--quiet` | Suppress informational and progress messages. |

`prepare` also accepts `--dry-run` and `--quiet`.  A dry-run still resamples
and validates the inputs but does not write the prepared NetCDF file.

## Command examples

```bash
# Validate the reference configuration without running the model
pvm2 run --config experiments/original/original.yaml --dry-run

# Long run with bounded active-cell tiles and a restart file
pvm2 run --config case.yaml --tile-cells 5000 \
  --checkpoint outputs/case-checkpoint.npz

# Resume an interrupted run
pvm2 run --config case.yaml \
  --checkpoint outputs/case-checkpoint.npz --resume

# Reference validation with an explicit report path
pvm2 reproduce --config experiments/original/original.yaml \
  --report reports/reference.html --min-kappa 0.50

# Prepare heterogeneous inputs without writing the intermediate file
pvm2 prepare --config configs/heterogeneous.yaml --target 1 --yes --dry-run

# Prepare and run in one step
pvm2 pipeline --config configs/heterogeneous.yaml --target 1 --yes

# Inspect and validate inputs
pvm2 inspect --config experiments/original/original.yaml --json
pvm2 validate --config experiments/original/original.yaml \
  --json --report reports/input_validation.json

# Configuration round-trip
pvm2 config check --config case.yaml --json
pvm2 config show --config case.yaml --resolved
```

## Configuration keys

| Key | Meaning |
| --- | --- |
| `input.climate` | Consolidated NetCDF climate file. |
| `input.legacy` | Mapping of the six legacy binary paths. |
| `input.sources` | Mapping of per-variable paths or `{path, variable, units, coordinates}` specifications. |
| `input.shape` | `[ny, nx]` required for legacy binaries. |
| `input.coordinates_file` | Optional latitude text file for legacy runs. |
| `input.variables` / `input.coordinates` / `input.units` | NetCDF variable, coordinate and unit mappings. |
| `input.lon_duplicate` | `drop_last` or `keep` for a duplicated 360-degree column. |
| `model.co2_pa` | CO2 partial pressure in Pa. |
| `model.fire` | Enable the U-wind fire parameterisation. |
| `model.max_equilibrium_years` | Equilibrium iteration limit. |
| `model.tile_cells` | Optional active-cell tile size. |
| `output.directory` / `output.name` | Output directory and file stem. |
| `output.netcdf` / `output.geotiff` / `output.write_legacy_binary` | Output switches. |
| `output.reference` | Observed biome map used by `reproduce`. |
| `output.run_directory` / `output.run_id` | Timestamped or named run subdirectory. |
| `paths_relative_to` | `cwd` (default) or `config`. |
| `metadata` | Free-form user metadata copied to the manifest. |

Configuration is validated strictly: unknown keys, wrong types and invalid
ranges fail before any input is loaded.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | A validation or scientific gate failed, such as invalid inputs or kappa below `--min-kappa`. |
| `2` | Usage, configuration, file or runtime error. |

The HTML/JSON validation reports and `run_manifest.json` record metrics,
input hashes, configuration snapshot, git state, environment and artifact
hashes.
