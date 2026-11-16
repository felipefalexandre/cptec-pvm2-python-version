# Legacy input data

The default climate, land-mask and reference files are included in this
repository so that a fresh clone can reproduce the reference experiment
without external downloads.  Their original licence is not stated; they are
provided only for scientific reproducibility.  If you are a rights holder and
believe an asset should not be redistributed, please open an issue and it will
be removed.

```
legacy/data/inputs/
    prec.bin    temp.bin    ipar.bin
    psup.bin    lsmk.bin    uwind.bin
    prec.nc     temp.nc     uwnd.nc
    prec.ctl    temp.ctl    uwind.ctl
    ylat.txt
legacy/data/reference/
    Lapola_et_al_T062.bin
    lapola_et_al_T062.ctl
    vegetacao_referencia.qml
```

`ylat.txt` is a short coordinate list required to describe the Gaussian grid.
`vegetacao_referencia.qml` is the QGIS palette used for the Figure 1b
installation check.

## Expected files

Byte sizes and SHA-256 values for the primary data:

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `inputs/prec.bin` | 884736 | `0d0919a123c783d366668c4915c559153d9e6657b4695f80ee5667bbae2cc93a` |
| `inputs/temp.bin` | 884736 | `87a22756c769d46efbe5a255e9f4630926ff519e816aa0b31a451b06a431d902` |
| `inputs/ipar.bin` | 884736 | `14163b3353fc59e3975c5706b8837adeaae00f5f202d1e935ea95fcbb80ce17a` |
| `inputs/psup.bin` | 73728 | `fa6b81976c4a0ace211c2b8d43cab038f17b84962192b987c460b0fe9ef071f7` |
| `inputs/lsmk.bin` | 73728 | `a233db60a7b0a5386b28e2fa6adf2632b7dbe46941c32c19de3c403463f91684` |
| `inputs/uwind.bin` | 884736 | `e57b7f4b54af26b30fb86f42477d0de93429740373d0422ec1f99a2dda1169e4` |
| `inputs/ylat.txt` | 902 | `14745b347a603483175943aba53c9a4739f33141f9c81f553c473f9e9625f41e` |
| `reference/Lapola_et_al_T062.bin` | 73728 | `a82115efb45a750a3ce211461affee11faf7301d7e444878329fcbd3a57c4e0b` |
| `reference/vegetacao_referencia.qml` | 1447 | `4344a3558df35aa4060ac105a05281695f0d11102b9a5d4da0ba72cca5e6b968` |

`SHA256SUMS` contains checksums for every included data file.

## Format

Each `.bin` file is a sequence of little-endian IEEE-754 float32 records:

- monthly variables: 12 records of `96 * 192` values;
- static variables: 1 record of `96 * 192` values.

The record order is longitude fastest, then latitude.  In NumPy:

```python
raw = np.fromfile("prec.bin", dtype="<f4")
prec = raw.reshape(12, 96, 192)   # [month, lat, lon]
```

## Units

| File | Variable | Units |
| --- | --- | --- |
| `prec.bin` | precipitation | mm month-1 |
| `temp.bin` | surface temperature | degC |
| `ipar.bin` | incident PAR | W m-2 |
| `psup.bin` | surface pressure | hPa |
| `lsmk.bin` | land mask | 0/1 |
| `uwind.bin` | 850 hPa zonal wind | m s-1 |

`ipar.bin` is converted by the model to Einstein m-2 s-1 with
`par = ipar / 2.18e5`.

## Notes

- `prec.nc`, `temp.nc` and `uwnd.nc` delivered with some copies of the data
  have 193 longitudes (a duplicate at 360).  Dropping the last column gives
  values identical to the `.bin` files.
- `uwind.ctl` points to `uwind.bin`; an older copy of the delivery used the
  misspelled name `uwnd.bin`.
- The latitude axis is a T62 Gaussian grid (96 points).  It is not regularly
  spaced, even though the `.ctl` file describes the x-axis as linear.
- The reference map is the **observed** natural-vegetation map used for kappa.
  It is not a model output.
- The article PDF is kept in `legacy/pdf/` locally but is not redistributed;
  use the DOI in `docs/reference_lapola_2009.md`.
