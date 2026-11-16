# Land/sea mask presets

These files provide binary land/sea masks on the regular latitude/longitude
grids most commonly encountered in climate and land-surface datasets.  They
are used by `pvm2 prepare` as candidate target grids and as the reference for
bilinear interpolation and domain cropping.

| File | Resolution | Typical use |
| --- | --- | --- |
| `lsmk_0p1.nc` | 0.10 deg | MERGE/CODEX and other high-resolution products |
| `lsmk_0p25.nc` | 0.25 deg | ERA5, high-resolution CMIP6 |
| `lsmk_0p5.nc` | 0.50 deg | common CMIP6 grid |
| `lsmk_1p0.nc` | 1.00 deg | CMIP6 / global climate |
| `lsmk_2p0.nc` | 2.00 deg | coarse CMIP6 |
| `lsmk_2p5.nc` | 2.50 deg | coarse CMIP6 |
| `lsmk_5p0.nc` | 5.00 deg | coarse global |
| `lsmk_10p0.nc` | 10.00 deg | very coarse global |

## Source and method

The masks were generated from the **Natural Earth 1:10m land** polygons
(public domain, <https://www.naturalearthdata.com/>) with
`scripts/make_landmasks.py`.  A cell is land when its centre falls inside a
land polygon (`all_touched=False`).  Values are `0` (ocean) and `1` (land).

These are **not** the native CMIP6, ERA5, CODEX or MERGE-CPTEC masks.  The
table above lists only the nominal resolutions commonly used by those
products.  A single, documented coastline source keeps the presets internally
consistent and avoids redistributing model-specific masks whose licences may
differ.  If a study requires a specific provider mask, pass it with
`pvm2 prepare --landmask path/to/lsmk.nc`.

The generated NetCDF files are compressed and contain CF-style coordinates and
provenance attributes.  Longitudes use `-180..180`; the preparation code
accepts inputs in either `0..360` or `-180..180`.
