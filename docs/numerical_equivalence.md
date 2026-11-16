# Numerical equivalence

## 1. Strategy

The delivery contains the Fortran source and inputs but **no model output
binary**; the only map (`Lapola_et_al_T062.bin`) is the observed reference map
used by the kappa statistic.  Bit-level comparison with a published run is
therefore impossible.  Equivalence was assessed in four steps:

1. Compile the legacy source locally, changing only the direct-access RECL
   unit required by gfortran.
2. Run the legacy build and the Python implementation on exactly the same
   input binaries and CO2 value.
3. Compare the biome map and every intermediate field cell by cell.
4. Compare both maps against the observed reference with the legacy kappa
   implementation.

Reported agreement levels:

| Level | Meaning |
| --- | --- |
| 0 | runs end to end |
| 1 | same input and output dimensions |
| 2 | intermediate fields agree within float32 tolerance |
| 3 | identical biome map against the legacy build |
| 4 | kappa consistent with the published value |
| 5 | bit-identical output against an original published run |

Achieved: **level 4**.  Level 5 cannot be claimed without an original output
file and a known compiler/libm.

## 2. Legacy build

`scripts/build_legacy.ps1` copies `env5.f`, `wbm4.f`, `carbon2.f`, `pvm5.f`,
replaces `recl=nx*ny)` with `recl=nx*ny*4)`, and compiles with

```
gfortran -std=legacy -O0 -ffp-contract=off -fno-fast-math
```

No numerical statement, constant or loop bound was changed.  The experiment
uses `ca=35.35 Pa`, fire on, exactly as the Python configuration
`experiments/original/original.yaml`.

## 3. Field comparison

Python results were written to `outputs/original/pvm2_original.nc`; the legacy
results are the records in `build/ca350/outputs/`.

Annual environmental fields vs `ambientais4_100.bin` (land cells only):

| Field | Max abs. difference | Relative scale |
| --- | --- | --- |
| `tmin` | 0 | exact |
| `meanpp` | 8.4e-7 | <= 1e-6 of values ~1 |
| `seanpp` | 2.0e-5 | dimensionless |
| `meanhr` | 2.3e-6 | |
| `meancs` | 5.8e-5 | |
| `mphoto` | 3.0e-6 | |
| `maresp` | 3.9e-6 | |
| `seai` | 0 differing land cells | ocean is undefined in the legacy binary |
| `weti` | 0 differing land cells | ocean is undefined in the legacy binary |
| `d2wm` | 0 | exact; reported as months 1-12, as in `findm` |
| `ud2w` | 0 | exact |

Monthly fields:

| Field | Max abs. difference |
| --- | --- |
| `npp` | 9.8e-6 |
| `gpp` (`photo`) | 1.6e-5 |
| `ra` (`aresp`) | 1.2e-5 |
| `soilmoist` | 9.8e-6 |
| `evapotranspiration` | 9.8e-6 |
| `canopy_resistance` | 8.7e-2 s m-1 (small relative to values of order 100-4500) |

These are float32 rounding differences: the legacy writes float32 and does
single-precision arithmetic, while Python accumulates in float64 and only
casts at output.  `tmin` is exact because it is a selection, not an arithmetic
result.

### Biome map

```
biome equal True
agreement 1.0
mismatches []
```

All 18 432 cells, including ocean, have the same class.  The class histogram
is identical (12429 ocean, 1907 ice, 381 ombrophilous, 136 seasonal, etc.).

## 4. Scalar equation checks

`tests/fixtures/fortran_scalars.json` contains `carbon1` and `carbon2` results
produced by the same Fortran subroutines compiled in **double precision**
(`-fdefault-real-8 -fdefault-double-8`).  The Python functions match these
values to better than 1e-9 relative.

An earlier fixture generated in single precision with an unphysically high
PAR (`150 Einstein m-2 s-1`) differed by up to 0.7% in NPP and 2.6% in LAI.
The cause is catastrophic cancellation in the quadratic root used for `f1a`:
the root is the difference of two large, nearly equal terms.  In the model,
PAR is divided by `2.18e5` before entering `carbon1`, so `jl` is small and the
cancellation is at the float32 rounding level.  The single- and double-
precision scalar checks agree to about 1e-6 relative at the physical PAR
range.  This is documented because it explains why isolated scalar tests can
look worse than the full-model comparison.

## 5. Kappa

`skill4.f` remaps class 13 to 12 and 20 to 13 before comparing classes 1..12.
The Python report uses the same mapping.  The observed map has 3988 cells in
classes 1..12.

| Experiment | Global kappa | Agreement | Class 6 | Class 13/12 |
| --- | --- | --- | --- | --- |
| Legacy, `ca=35.35`, fire off | 0.5189 | 89.60% | 0.417 | 0.036 |
| Legacy, `ca=35.35`, fire on | 0.5254 | 89.72% | 0.447 | 0.219 |
| Legacy, `ca=51.5375`, fire on | 0.5263 | 89.74% | 0.530 | 0.305 |
| Python, `ca=35.35`, fire on | 0.5254 | 89.72% | 0.447 | 0.219 |
| Paper, fire off | 0.53 | - | 0.44 | 0.14 |
| Paper, fire on (U-wind) | 0.54 | - | 0.49 | 0.36 |

Python and the local legacy build produce the same kappa to all printed
digits, as expected from the identical biome map.

The global kappa is within 0.015 of the published value, and the sign of the
fire effect is correct.  The residual differences in classes 6 and 13 are
attributed to the unknown state of the published run (CO2 value, data version,
compiler precision, and the fact that the delivered map is observed rather
than modelled).  They are not evidence of a coding error in the migration,
because the Python map is identical to the locally compiled legacy map.

## 6. Performance

The first vectorised Python version took 341 s for the 192x96 grid, about 100
times slower than the 3.4 s Fortran run.  The implementation was then changed
to solve only the cells that have not yet converged (the legacy algorithm is
cell-independent).  The numerical results are unchanged and the runtime fell
to 18.8 s, about 5.5 times the Fortran time.  Remaining cost is Python
interpreter overhead over the 44 000 daily steps, not the grid size.

## 7. Reproduce the comparison

```bash
# 1. compile and run the legacy model
powershell -ExecutionPolicy Bypass -File scripts/build_legacy.ps1
# the script prints the build directory; run pvm2.exe from its code directory
# with ../inputs and ../outputs in place (see docs/legacy_code_audit.md)

# 2. run Python
pvm2 run --config experiments/original/original.yaml

# 3. compare
pytest tests/test_model.py -q
pvm2 compare-legacy --fortran-dir build/ca350/outputs \
  --python outputs/original/pvm2_original.nc
pvm2 reproduce --config experiments/original/original.yaml
```

The stored Fortran biome map used by the regression test is
`tests/fixtures/fortran_bpot_ca350.npy` (int8, 96x192), generated by the local
legacy build with `ca=35.35 Pa` and fire on.

## 8. Limitations

- No original model output exists, so level 5 is not attainable.
- The reference latitude axis is a T62 Gaussian grid; a single affine
  transform cannot represent it.  The GeoTIFF writer uses per-cell GCPs in a
  `.tif.aux.xml` sidecar instead.  NetCDF preserves the exact coordinates and
  is the authoritative product.
- The legacy binary leaves `seai` and `weti` undefined over ocean.  Python
  writes -999.99 there and comparisons are restricted to land.
- The `ca` in the delivered source is hard-coded to 51.5375 Pa and labelled
  1000 ppmv; this is inconsistent with the published 350 ppmv run.
- The kappa class labels in the paper (13) differ from the legacy remapping
  (13 -> 12); the implementation follows the code.
- Floating-point results are compiler- and libm-dependent at the last bits;
  only class-level agreement and float32-level field agreement are claimed.
