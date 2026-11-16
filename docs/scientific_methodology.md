# Scientific methodology

This document describes the model as implemented in `src/pvm2`, including
units, integration order, constants and the mapping to the legacy Fortran.

## 1. Purpose

CPTEC-PVM2 diagnoses the potential vegetation that is in equilibrium with a
prescribed monthly climate (temperature, precipitation, incident
photosynthetically active radiation, surface pressure, 850 hPa zonal wind and
a land mask).  It is not a dynamic vegetation model: the water and carbon
cycles are solved to a steady annual cycle for each grid cell independently.

The model is described by Oyama & Nobre (2004).  The natural-fire
parameterisation is from Lapola et al. (2006) and converts savanna to seasonal
forest when the zonal wind after the dry-to-wet transition is weak.

## 2. Inputs and units

| Field | Symbol | Units | Shape |
| --- | --- | --- | --- |
| precipitation | `P` | mm month-1 | 12 x ny x nx |
| temperature | `T` | degC | 12 x ny x nx |
| incident PAR | `I_par` | W m-2 | 12 x ny x nx |
| surface pressure | `p0` | hPa | ny x nx |
| land mask | `lsmk` | 0/1 (fractional values truncated) | ny x nx |
| 850 hPa zonal wind | `U` | m s-1 | 12 x ny x nx |
| atmospheric CO2 | `ca` | Pa | scalar |

The model converts PAR internally:

```
ipar = I_par / 2.18e5        # Einstein m-2 s-1
```

No horizontal interpolation or resampling is performed.  The output grid is
identical to the input grid.  Ocean cells are those with `int(lsmk) == 0`.

## 3. State variables

Per grid cell:

- `w` — plant-available soil water (mm), bounded by `[0, WMAX]`.
- `g` — soil ice (mm), formed when the soil temperature is at or below
  `TICE` and released when it thaws.
- `s` — snow storage (mm).
- `tsoil[k]` — equilibrium soil temperature for month `k` (degC).

`WMAX = 500 mm`.  The daily time step is used inside each month; month lengths
are 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 days (no leap years).

## 4. Soil temperature

Soil temperature is relaxed toward the monthly air temperature with an
exponential filter:

```
tau = H^2 / (2 D),      H = 1 m
D   = 4e-7 * 30 * 86400 m2 month-1
t1  = t0 exp(-1/tau) + (1 - exp(-1/tau)) T_k
tsoil_k = (t0 + t1)/2
t0  = t1
```

The filter is integrated for 1200 months (100 years) for every land cell
before the water balance starts.  The final 12 values are used as the monthly
soil temperatures in the water/carbon loop.

## 5. Daily water balance

For each day of month `k`:

1. Partition precipitation using the daily air temperature:

   ```
   if T < TSNOW:  psnow = P/ndays,  prain = 0
   else:          psnow = 0,        prain = P/ndays
   ```

   with `TSNOW = -1 degC`.

2. Snowmelt:

   ```
   smelt = 2.63 + 2.55 T + 0.0912 T prain
   smelt = clamp(smelt, 0, s + psnow)
   s     = s + psnow - smelt
   ```

3. Frozen-soil branch.  If `tsoil <= TICE` (`-2.5 degC`):

   ```
   g <- g + w
   w <- 0
   runoff <- smelt + prain
   evap <- 0
   carbon fluxes <- 0
   ```

   Otherwise the thawed branch is used:

   ```
   w_thaw = min(w + g, WMAX)
   rimelt = max(w + g - WMAX, 0)
   g      = 0
   roff   = 11.5 (w_thaw/WMAX)^6.6
   evap   = penman(p0, T, w_thaw, WMAX, RH, ae, rc2)
   dw     = prain + smelt - evap - roff
   w_new  = clamp(w_thaw + dw, 0, WMAX)
   roff   = roff + max(w_thaw + dw - WMAX, 0) + rimelt
   ```

4. Carbon fluxes are computed with `carbon1` and `carbon2` using the current
   water storage before the update; the heterotrophic respiration uses the
   actual evaporation of the day.

5. Monthly means are accumulated and the final storages become the initial
   storages of the next month.

Constants: `RH = 0.685`, `RA = 100 s m-1`, `RCMIN = 100 s m-1`,
`H5 = 0.0275 hPa-1`.

### 5.1 Available energy and evapotranspiration

Available energy is a linear function of monthly air temperature:

```
ae = 2.895 T + 52.326        # W m-2
```

Potential evapotranspiration uses the Penman equation with fixed stomatal
resistance `rc = RCMIN`:

```
Delta   = (es(T+1) - es(T-1)) / 2
Delta_e = es(T) (1 - RH)
gamma   = p0 * 1004 / (2.45e6 * 0.622)
gamma2  = gamma (RA + rc) / RA
E       = (Delta ae + (1.20*1004/RA) Delta_e) / (Delta + gamma2)
E       = max(E * 86400/2.45e6, 0)       # mm day-1
```

The saturation vapour pressure uses the legacy Tetens formulation:

```
es(T) = 6.1078 * 10^(7.5 T/(237.3+T))     if T >= 0
es(T) = 6.1078 * 10^(9.5 T/(265.5+T))     if T < 0
```

Actual evapotranspiration replaces `rc` by the canopy resistance

```
rc2 = ca / (0.9 * max(npp, 0.05) * 2.64e-6 * 0.685 * p0 * 100)
```

and returns zero when `Delta_e >= 1/H5 - 0.5` or `rc2 >= 4500 s m-1`,
following the legacy dual test.  The `npp` used here is the instantaneous
daily NPP from `carbon1`.

## 6. Carbon cycle

### 6.1 Photosynthesis

```
vm    = 4e-5 * 2^(0.1(T-25)) / (1 + exp(0.3(T-36)))       # mol CO2 m-2 s-1
Gamma = 21200 / (5200 * 0.57^(0.1(T-25)))                  # Pa
f2    = 30 * 2.1^(0.1(T-25))                               # Pa
f3    = 30000 * 1.2^(0.1(T-25))                            # Pa
es    = tetens(T)
rmax  = 0.622 es/(p0 - es)
r     = -0.315 rmax
ci    = 0.9 (1 - r/0.1)(ca - Gamma) + Gamma
f10   = 1.23 / (1 + exp(-(ca - 24.11)/8.93))
jc    = vm (ci - Gamma) / (ci + f2 f10 (1 + 21200/f3))
jl    = 0.08 * 0.85 * ipar * (ci - Gamma)/(ci + 2 Gamma)
je    = 0.5 vm
```

The co-limitation is computed by intersecting the supply functions with a
diminishing-returns factor:

```
0.83 jp^2 - (jc+jl) jp + jc jl = 0      -> jp  = min(root1, root2)
0.93 f1^2 - (jp+je) f1 + jp je = 0      -> f1a = min(root1, root2)
```

Water stress:

```
wa = w/WMAX
f5 = 1                                   if wa > 0.5
f5 = (wa - 0.205)/(0.5 - 0.205)          if 0.205 <= wa <= 0.5
f5 = wa                                  if wa < 0.205
f1 = f1a f5                              if -10 <= T <= 50
f1 = 0                                   otherwise
```

LAI and canopy scaling:

```
laia     = 0.25 exp(2.5 f1 / 8e-6)
sunlai   = (1 - exp(-0.5 laia))/0.5
shadelai = laia - sunlai
f4       = (1 - exp(-0.5 laia))/0.5
f4sun    = (1 - exp(-0.5 sunlai))/0.5
f4shade  = (1 - exp(-1.5 shadelai))/1.5
```

Fluxes:

```
ph  = 0.012 * 31557600 * f1 f4sun f4shade       # kgC m-2 yr-1
rl  = 0.012 * 31557600 * 0.015 vm f4 f5
rp  = 3.85 rl
ar  = rl + rp                                    if -10 <= T <= 50, else 0
npp = max(ph - ar, 0)
```

`0.012` converts mol CO2 to kg C and `31557600` is the number of seconds in a
365.25-day year.

### 6.2 Litter and soil carbon

```
f6 = 1.16 * 10^(-1.4553 + 0.0014175 * (evap*365))
f7 = 2^(0.1(Tsoil - 25))
lf = 0.1 laia
cl = lf / f6
cs = (0.3 cl) / (0.05 f7) * f5
hr = 0.25 (cl f6^2 + cs f5 evap f7^2)
```

`hr` is set to zero when `Tsoil` is outside `[-10, 50] degC`.  Monthly values
are converted to annual equivalents by multiplying by 12 after the daily
average.

## 7. Steady-state solution

For each land cell, the model repeats the 12-month cycle.  A cell is
converged when, for every month,

```
|w_k(year) + g_k(year) - (w_k(year-1) + g_k(year-1))| / WMAX <= 0.001
```

Converged cells are removed from subsequent iterations; the final monthly
fields for those cells are kept.  The loop continues until all land cells
converge, with a configurable safety limit (`max_equilibrium_years`,
default 20000).  The reference run converges in 121 years.

This cell-wise early exit is numerically identical to the legacy
implementation, which stops each cell independently, but is much faster in
Python because only active cells are updated.

## 8. Annual diagnostics

From the converged monthly fields:

```
tmin    = min_k T_k
meanpp  = mean_k npp_k
mphoto  = mean_k ph_k
maresp  = mean_k ar_k
meanhr  = mean_k hr_k
meancs  = mean_k cs_k
seanpp  = (max_k npp_k - min_k npp_k) / meanpp, normalised by its land maximum
seai    = 1 - (1/6) sum_k max(0.5 - w_k/WMAX, 0)
weti    = min(1, sum_k evap_k / sum_k evap_pot_k)
          over months with g_k/WMAX < 1e-7
```

`wsoil2` is `w_k/WMAX` for months without soil ice and -999.99 otherwise.

## 9. Biome classification

The NPP/PAR index is

```
ref   = max((avgpar - 35)/45, 0)
ratio = clamp(meanpp / ref, 0, 1)
```

with `avgpar` the annual mean incident PAR in W m-2.  The rules are listed in
`docs/legacy_code_audit.md` (section 4.3).  They are evaluated in order and
the first match wins; ocean cells are class 0.

### 9.1 Transition month and fire

For each land cell with valid `wsoil2`, `findm` chooses the first local
minimum of the seasonal soil-water cycle whose next-month increase is at
least `(max(w)-min(w))/8`.  The transition month is reported as 1-12, as in
the legacy `findm`, and the U-wind of the following month is `ud2w`.

If `fire = true`, savanna cells (`bpot = 6`) with `ud2w > 1.5 m s-1` are
reclassified as tropical seasonal forest (`bpot = 13`).  This is the complete
fire parameterisation; no other class is modified.

## 10. Outputs

The Python implementation writes a NetCDF file with:

- `biome` — potential vegetation class.
- `tmin`, `meanpp`, `seanpp`, `meanhr`, `meancs`, `mphoto`, `maresp`,
  `seai`, `weti`, `ratioNPP`, `d2wm`, `ud2w`.
- Monthly fields: `npp`, `gpp`, `ra`, `soilmoist`, `evapotranspiration`,
  `runoff`, `snowmelt`, `canopy_resistance`, `lai`, `litter`, `soil_carbon`,
  `heterotrophic_respiration`.
- Optional 12-record legacy bundle in the original `pvm5` order.

All gridded outputs preserve the input latitude/longitude coordinates.

## 11. Differences from the paper

- The delivered code hard-codes `ca = 51.5375 Pa` (about 509 ppmv) while the
  paper's 1961-1990 experiment uses 350 ppmv.  The Python default is 35.35 Pa.
- The paper's fire threshold is `U_lim = 1.5 m s-1`, matching the code.
- The paper reports class 13 separately; the legacy `skill4` remaps 13 to 12
  for kappa.  The Python validation follows the code, not the paper's label.
- The paper's kappa values are not reproduced exactly; see
  `docs/numerical_equivalence.md`.
