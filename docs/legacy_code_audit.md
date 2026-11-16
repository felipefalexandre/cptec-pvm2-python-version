# CPTEC-PVM2 legacy code audit

Date: 2026-11-15
Scope: complete inventory of the Fortran package delivered as
`PVM2-20261115T130744Z-1-001`, its data, numerical content, build behaviour
and reproduction status.  No numerical expression of the original was changed
during the audit.

## 1. Inventory

| File | Role |
| --- | --- |
| `env5.f` | Main program. Reads climate and land-mask binaries, converts incident PAR, calls `wbm`, writes environmental fields. |
| `wbm4.f` | Water balance and carbon driver. Contains `wbm`, `budget`, `penman`, `evpot2`, `runoff` and `tetens`. |
| `carbon2.f` | Contains `carbon1` (photosynthesis, autotrophic respiration, NPP, LAI) and `carbon2` (litter, soil carbon, heterotrophic respiration). |
| `pvm5.f` | Biome classification, transition-month logic (`findm`), U-wind fire parameterisation and the 12-record output bundle. |
| `skill4.f` | Kappa validation against an observed biome map. |
| `roda_tudo.csh` | Original run script. |
| `LEIAME` | Original readme (Portuguese). |
| Input binaries | Monthly climatologies and static fields in GrADS-style direct-access binaries (see section 6). |
| `Lapola_et_al_T062.bin` | **Observed** reference biome map used for kappa, not model output. |

There is no stored binary output of the original model in the delivery.  The
only model-like map in the package is the observed reference map.  Therefore a
bit-for-bit comparison with a published model run is impossible; validation
must use a locally compiled legacy build and the kappa statistic.

## 2. Program architecture and dependencies

```
env5
├── read12                  direct-access reader
├── wbm                     water balance + carbon per grid cell
│   ├── budget              one month, daily loop
│   │   ├── carbon1         photosynthesis / respiration / NPP / LAI
│   │   ├── carbon2         litter / soil carbon / heterotrophic respiration
│   │   ├── evpot2          potential evapotranspiration (Penman)
│   │   ├── penman          actual evapotranspiration
│   │   ├── runoff          soil-moisture runoff
│   │   └── tetens          saturation vapour pressure
│   └── soil temperature    1200-month exponential filter
└── output writers          ambientais4, soilm, evaptr, mon_npp,
                            mon_photo, mon_ar, rc

pvm5
├── read12 / read bundle
├── ratio                   NPP / PAR index
├── findm                   dry-to-wet transition month
└── fire parameterisation   U-wind at 850 hPa

skill4
├── acerto
└── kappa                   class remapping 13 -> 12 and 20 -> 13
```

Call graph is strictly top-down; no modules, no dynamic allocation, no
external numerical libraries.  All arrays are fixed at `nx=192, ny=96`.

## 3. Execution flow

1. `env5` opens `psup.bin`, `lsmk.bin`, `pnew.bin`, `tnew.bin` and `ipar.bin`
   as direct-access records.
2. `read12` reads 12 monthly records for precipitation, temperature and PAR.
3. PAR is converted from W m-2 to Einstein m-2 s-1:
   `par = ipar / 2.18e5` (`env5.f:84`).
4. `wbm` loops over all cells.  For each land cell it spins up soil temperature
   for 1200 months, then iterates the monthly water/carbon budget until the
   annual soil-water storage changes by less than 0.001 of `wmax` for all 12
   months.  The number of iterations has no fixed cap in the original.
5. Annual and monthly diagnostics are written as direct-access records.
6. `pvm5` reads the diagnostics, computes the NPP/PAR ratio, classifies each
   land cell, applies the fire rule and writes 12 records.
7. `skill4` reads the observed and modelled maps, remaps class 13 to 12 and
   class 20 to 13, and computes the kappa statistic over classes 1..12.

## 4. Numerical content

Equation numbers are those annotated in the Fortran source.  The source uses
two independent numbering series (water balance and carbon), so the same
number can refer to different equations.  The delivered PDF covers only the
fire parameterisation; the full model equations are in Oyama & Nobre (2004).

### 4.1 Water balance (`wbm4.f`)

| Code | Expression | Notes |
| --- | --- | --- |
| `budget` Eq. 1 | `dw = prain + smelt - evap - roff` | daily soil-water budget |
| `budget` Eq. 2 | `ds = psnow - smelt` | snow storage |
| `budget` Eq. 3 | `psnow = prec/ndays` if `temp < -1`, else `prain = prec/ndays` | precipitation split |
| `budget` Eq. 4 | `smelt = 2.63 + 2.55 T + 0.0912 T prain`, clipped to `[0, s+psnow]` | snowmelt |
| `wbm` Eq. 8 | `ae = 2.895 Ta + 52.326` | available energy; the commented alternative `2.26457 Ta + 67.5876` is not used |
| `evpot2` | Penman with `rc = 100 s/m` | potential ET |
| `penman` Eq. 32 | Penman with `rc2 = ca / (0.9 npp_b 2.64e-6 * 0.685 * p0 * 100)` | actual ET; `npp_b = max(npp, 0.05)` |
| `runoff` Eq. 10 | `roff = 11.5 (w/wmax)^6.6` | NCEP-NCAR recalibration; the older `38 (w/wmax)^11` is commented out |
| frozen branch | if `tsoil <= -2.5`, `g <- g + w`, `w <- 0`, all melt/rain becomes runoff and carbon fluxes are zeroed | |
| soil temperature | `t1 = t0 exp(-1/tau) + (1-exp(-1/tau)) T_k`, `tsoil_k = (t0+t1)/2`; `tau = H^2/(2 D)`, `H=1 m`, `D=4e-7*30*86400 m2/month` | 1200-month spin-up |

Constants: `wmax=500 mm`, `rh=0.685`, `tsnow=-1 C`, `tice=-2.5 C`,
`ra=100 s/m`, `rcmin=100 s/m`, `h5=0.0275 mb-1`.

### 4.2 Carbon cycle (`carbon2.f`)

| Code | Expression | Notes |
| --- | --- | --- |
| Eq. 12 | `vm = 4e-5 2^(0.1(T-25)) / (1 + exp(0.3(T-36)))` | Rubisco capacity |
| Eq. 8 | `mgama = 21200 / (5200 0.57^(0.1(T-25)))` | compensation point |
| Eq. 9 | `f2 = 30 * 2.1^(0.1(T-25))` | Michaelis-Menten CO2 |
| Eq. 10 | `f3 = 30000 * 1.2^(0.1(T-25))` | Michaelis-Menten O2 |
| Eq. 14 | `rmax = 0.622 es/(p0-es)` | saturated mixing ratio |
| Eq. 13 | `r = -0.315 rmax` | leaf moisture deficit |
| Eq. 11 | `ci = 0.9 (1 - r/0.1)(ca - mgama) + mgama` | internal CO2 |
| Eq. 4 | `jc = vm (ci-mgama)/(ci + f2 f10 (1+21200/f3))` | Rubisco-limited |
| Eq. 5 | `jl = 0.08*0.85*ipar (ci-mgama)/(ci+2 mgama)` | light-limited |
| Eq. 6 | `je = 0.5 vm` | transport-limited |
| Eq. 3 | `jp = min(root1, root2)` of `0.83 jp^2 - (jc+jl) jp + jc jl = 0` | |
| Eq. 2 | `f1a = min(root1, root2)` of `0.93 f1^2 - (jp+je) f1 + jp je = 0` | |
| Eq. 21 | `f5 = 1` if `w/wmax > 0.5`; `(w/wmax-0.205)/0.295` in `[0.205,0.5]`; `w/wmax` below | water stress |
| Eq. 15 | `laia = 0.25 exp(2.5 f1/8e-6)` | LAI |
| Eqs. 16-20 | sunlit/shaded LAI and canopy scaling factors | |
| Eq. 1 | `ph = 0.012 * 31557600 * f1 * f4sun * f4shade` | canopy gross photosynthesis |
| Eq. 23 | `rl = 0.012 * 31557600 * 0.015 vm f4 f5` | leaf respiration |
| Eq. 24 | `rp = 3.85 rl` | non-leaf respiration |
| Eq. 22 | `ar = rl + rp` | autotrophic respiration |
| Eq. 25 | `nppa = max(ph-ar, 0)` | NPP |
| Eq. 29 | `f6 = 1.16 * 10^(-1.4553 + 0.0014175 * evap*365)` | litter decay |
| Eq. 31 | `f7 = 2^(0.1(Tsoil-25))` | soil temperature response |
| | `lf = 0.1 laia`, `cl = lf/f6` | litter carbon |
| | `cs = 0.3 cl/(0.05 f7) * f5` | soil carbon |
| | `hr = 0.25(cl f6^2 + cs f5 evap f7^2)` | heterotrophic respiration |

Outside the temperature windows `[-10, 50] C` photosynthesis and respiration
are set to zero.  Plant respiration uses `iphoto` with a 365-day year
(`31557600 s`), so monthly values are rescaled by 12 in `budget`.

### 4.3 Classification (`pvm5.f`)

`ratio(anpp, apar) = clamp(anpp / max((apar-35)/45, 0), 0, 1)`.

Rules, in order:

1. Ocean (`lsmk = 0`) -> 0.
2. Extratropical desert: `-15 <= tmin <= 10` and `ratio <= 0.05` -> 11.
3. Extratropical semi-desert: same window and `ratio <= 0.28` -> 9.
4. Tropical desert: `tmin > 10` and `ratio <= 0.005` -> 11.
5. Tropical semi-desert: `tmin > 10` and `ratio <= 0.15` -> 9.
6. `tmin <= -27`: `ratio == 0` -> ice 20; `ratio <= 0.3` -> tundra 10; else larch 5.
7. `-27 < tmin <= -9`: `ratio <= 0.08` -> tundra 10; else `avgpar <= 58` -> boreal forest 4; else grasslands 7.
8. `-9 < tmin <= -6`: `ratio <= 0.5` -> grasslands 7; else mixed forest 3.
9. `-6 < tmin <= 10`: `ratio <= 0.7` -> grasslands 7; else temperate forest 2.
10. `tmin > 10`: `seanpp > 0.1` and `ratio <= 0.38` -> caatinga 8; `seanpp > 0.1` and `ratio > 0.38` -> savanna 6; `seanpp <= 0.1` and `ratio <= 0.72` -> seasonal forest 13; else ombrophilous forest 1.
11. Fire (`mfire=1`): for savanna cells, compute `ud2w` = U-wind at 850 hPa in the month after the dry-to-wet transition; if `ud2w > 1.5 m/s`, reclassify savanna to seasonal forest 13.

`findm` (`pvm5.f:308`) selects the first local minimum whose next-month
increase exceeds `(max(w)-min(w))/8`.  If no month qualifies, the Fortran
continues with an invalid index; the Python implementation raises an explicit
`RuntimeError`.

### 4.4 Validation (`skill4.f`)

`kappa` compares classes 1..12 after `13 -> 12` and `20 -> 13`.  Class 0
(ocean) is excluded from `n_compared`; the reported agreement percentage in
the Python report includes all cells, while the kappa itself uses only the
3988 land cells present in classes 1..12.

## 5. Parameters

| Parameter | Value | Where |
| --- | --- | --- |
| `wmax` | 500 mm | `wbm4.f` |
| `rh` | 0.685 | `wbm4.f` |
| `tsnow` | -1 C | `wbm4.f` |
| `tice` | -2.5 C | `wbm4.f` |
| `ra` | 100 s/m | `wbm4.f` |
| `rcmin` | 100 s/m | `wbm4.f` |
| `h5` | 0.0275 mb-1 | `wbm4.f` |
| `ae` slope/intercept | 2.895 / 52.326 | `wbm4.f` |
| PAR conversion | 2.18e5 | `env5.f` |
| seconds per year | 31557600 | `carbon2.f` |
| mol CO2 to kg C | 0.012 | `carbon2.f` |
| fire threshold | 1.5 m/s | `pvm5.f` |
| `mfire` | 1 (on) | `pvm5.f` |
| default `ca` in delivered code | `((100.10-35.35)*0.25)+35.35 = 51.5375 Pa` | `env5.f:102` |

The delivered default is labelled "1000 ppmv" but the arithmetic gives
51.5375 Pa, approximately 509 ppmv (1 ppmv ~ 0.101325 Pa).  The published
1961-1990 run uses 35.35 Pa (350 ppmv).  The Python default is 35.35 Pa; the
original value is available through configuration.

## 6. Data format

All model binaries are sequences of little-endian IEEE-754 float32 records.

- Monthly fields: 12 records, each `ny*nx` values.
- Static fields: 1 record.
- Record order is `i` (longitude) fastest, then `j` (latitude):
  `raw.reshape(12, ny, nx)` gives `[time, lat, lon]`.
- The Fortran declarations are `(nx, ny)`, so a direct `reshape(ny, nx)` of
  the 1-D stream is correct; `reshape(12, nx, ny)` would transpose the map.
- Original `recl=nx*ny` was word-based under Intel/g95.  gfortran interprets
  `recl` in bytes, so the build replaces it with `recl=nx*ny*4` only.  No
  numerical expression is modified.
- `env5.f` reads `pnew.bin`/`tnew.bin`; in the delivered package these are the
  same data as `prec.bin`/`temp.bin`.  The build script creates the aliases.
- `pvm5.f` reads `unew_100.bin`, which is the same as `uwind.bin`.

NetCDF copies of the climate fields (`prec.nc`, `temp.nc`, `uwnd.nc`) have
193 longitudes, with a duplicate at 360.  Dropping the last column gives a
192-point axis identical to the binary values.  The Python loader does this
explicitly (`lon_duplicate: drop_last`) and does not interpolate.

## 7. Spatial grid

- `nx=192`, `ny=96`.
- Longitude: 0 to 358.125, spacing 1.875 degrees, 192 points.
- Latitude: 96 points from -88.57217 to 88.57217.
- The latitude axis is a **T62 Gaussian grid**: the values match the roots of
  the Legendre polynomial of degree 96 to better than 5e-6 degrees.  It is not
  a regular latitude grid.  This matters for GeoTIFF export (see
  `docs/numerical_equivalence.md`).

## 8. Compilation

Original scripts assume a word-based RECL compiler and a Unix shell.  The
audit build uses gfortran 16.2 (WinLibs POSIX UCRT) with:

```
-std=legacy -O0 -ffp-contract=off -fno-fast-math
```

The sources are copied to `build/<experiment>/code`, the RECL token is
patched, and the two executables are built:

```
gfortran ... env5.f wbm4.f carbon2.f -o pvm2.exe
gfortran ... pvm5.f -o pvm5.exe
```

On Windows the gfortran `bin` directory must be on `PATH` at run time so the
runtime DLLs can be found.  The Fortran run takes about 3.4 s for `pvm2` and
under 1 s for `pvm5`.

## 9. Reproduction experiments

A local legacy build was run with `ca=35.35 Pa`, fire on and off, and with the
delivered `ca=51.5375 Pa`.  Kappa against the observed map:

| Experiment | Global kappa | Agreement | Class 6 | Class 13 (12) |
| --- | --- | --- | --- | --- |
| `ca=35.35`, fire off | 0.5189 | 89.60% | 0.417 | 0.036 |
| `ca=35.35`, fire on | 0.5254 | 89.72% | 0.447 | 0.219 |
| `ca=51.5375`, fire on | 0.5263 | 89.74% | 0.530 | 0.305 |
| Paper, fire off | 0.53 | - | 0.44 | 0.14 |
| Paper, fire on (U-wind) | 0.54 | - | 0.49 | 0.36 |

The global kappa is reproduced within 0.015.  The direction of the fire effect
is correct (savanna -> seasonal forest), but class 6 and class 13 agreement is
lower than in the paper.  Candidate causes are listed in section 10.

## 10. Risks and discrepancies

1. **No original model output.**  The delivered `Lapola_et_al_T062.bin` is the
   observed map, not a model result.  Bit-level reproduction against a
   published run is impossible.
2. **Hard-coded `ca`.**  The delivered source has a hard-coded 51.5375 Pa
   labelled 1000 ppmv; the published 1961-1990 experiment uses 35.35 Pa.
   Using the delivered default changes the biome map.
3. **Fixed grid dimensions.**  `nx` and `ny` are compile-time parameters in
   every routine.  Porting requires removing them.
4. **Word-based RECL.**  Compiling the untouched source with gfortran produces
   unreadable or truncated records.  Only the RECL unit is adapted.
5. **Float32 arithmetic.**  `carbon1` computes a small root as the difference
   of large terms.  At unphysically high PAR the cancellation causes percent-
   level differences between single and double precision.  At the physical
   PAR range (`ipar/2.18e5`) the difference is at float32 rounding level.
6. **Uninitialised ocean diagnostics.**  `seai` and `weti` are not initialised
   for ocean cells in `wbm`, so the legacy binary contains arbitrary values
   there.  The Python output uses -999.99 for ocean and is compared only over
   land.
7. **`findm` out-of-bounds.**  If no dry-to-wet transition is found, the
   Fortran reads outside `dw(12)`.  Python raises `RuntimeError`.
8. **Fire rule scope.**  The parameterisation only converts savanna (class 6)
   to seasonal forest (class 13); it does not affect other classes.
9. **Kappa remapping.**  Class 13 and 20 must be remapped before comparison;
   remapping twice corrupts ice (20 -> 13 -> 12).
10. **Data licences.**  The climate binaries and observed map have no stated
    licence in the delivery.  They are not redistributed in this repository.
11. **Gaussian latitudes.**  A single affine GeoTIFF transform cannot represent
    the T62 Gaussian y-axis exactly; the exporter therefore uses per-cell GCPs
    stored in a `.tif.aux.xml` sidecar.
12. **Compiler and libm differences.**  `exp`, `sqrt` and power intrinsics can
    differ in the last bits between compilers; this is unavoidable at float32
    and is why the acceptance criterion is class-level agreement plus
    float32-level field agreement.

## 11. Migration plan and mapping

| Legacy | Python |
| --- | --- |
| `env5.f` / `read12` | `pvm2.config.load_legacy_inputs`, `pvm2.io.legacy_binary` |
| `wbm` | `pvm2.core.water_balance.environmental_variables` |
| `budget` | `pvm2.core.water_balance.budget_month` |
| `carbon1` | `pvm2.core.carbon.carbon1` |
| `carbon2` | `pvm2.core.carbon.carbon2` |
| `tetens` | `pvm2.core.carbon.tetens` |
| `penman` / `evpot2` | `water_balance.penman` / `potential_evapotranspiration` |
| `runoff` | `water_balance.runoff` |
| `findm` | `water_balance._find_transition_month` |
| `pvm5` classification | `water_balance.classify` |
| `skill4` | `pvm2.validation.kappa` |
| binary readers/writers | `pvm2.io.legacy_binary` |
| output files | `pvm2.io.netcdf`, `pvm2.io.raster`, `pvm2.io.vector` |

Design decisions:

- Preserve the legacy equations and constants exactly; do not "improve" the
  science during migration.
- Keep a single source of truth for constants (`core/constants.py`).
- Make all grid dimensions dynamic; output shape always equals input shape.
- Keep the legacy binary reader/writer so the original workflow remains
  reproducible.
- Do not silently resample or reproject.
- Make failures explicit (missing transitions, invalid inputs) instead of
  relying on undefined Fortran behaviour.
- Validate against a locally compiled legacy build, not only against the
  paper.

## 12. Acceptance status

| Level | Criterion | Status |
| --- | --- | --- |
| 0 | Code runs end to end | yes |
| 1 | Same inputs, same dimensions | yes |
| 2 | Same intermediate fields within float32 tolerance | yes |
| 3 | Identical biome map against legacy build | yes (100%) |
| 4 | Kappa consistent with published values | yes (0.525 vs 0.54) |
| 5 | Bit-identical output against original executable | not possible: no original output, compiler-dependent |

The Python package also passes 40 automated tests, including shape preservation
on two synthetic grids and double-precision Fortran scalar checks for
`carbon1`/`carbon2`.
