# Data provenance

The default climate fields, land mask and observed vegetation map are bundled
so a fresh clone can reproduce the reference experiment without downloads.
They are third-party scientific data, not part of the MIT-licensed Python
implementation.  Their original licence is not stated in the delivery; they
are included for reproducibility and may be removed on request by a rights
holder.  See `NOTICE` and `legacy/data/README.md` for the full notice.

## Bundled files

| Path | Contents |
| --- | --- |
| `legacy/data/inputs/prec.bin` | Monthly precipitation climatology, mm month-1. |
| `legacy/data/inputs/temp.bin` | Monthly surface temperature climatology, degC. |
| `legacy/data/inputs/ipar.bin` | Monthly incident PAR, W m-2. |
| `legacy/data/inputs/psup.bin` | Surface pressure, hPa. |
| `legacy/data/inputs/lsmk.bin` | Land mask, 0/1. |
| `legacy/data/inputs/uwind.bin` | Monthly 850 hPa zonal wind, m s-1. |
| `legacy/data/inputs/ylat.txt` | T62 Gaussian latitude coordinates. |
| `legacy/data/reference/Lapola_et_al_T062.bin` | Observed natural-vegetation map used for kappa. |
| `legacy/data/reference/vegetacao_referencia.qml` | QGIS palette for the Figure 1b check. |

NetCDF copies (`prec.nc`, `temp.nc`, `uwnd.nc`) and GrADS control files are
also included.  The binary files are little-endian float32 records; the
monthly fields have 12 records of `96 x 192` values and the static fields have
one record.  See `legacy/data/README.md` for the record layout and units.

## Integrity

`legacy/data/SHA256SUMS` covers every included data file.  From the repository
root:

```bash
cd legacy/data
sha256sum -c SHA256SUMS
```

On Windows PowerShell, compare a file with:

```powershell
Get-FileHash legacy/data/inputs/prec.bin -Algorithm SHA256
```

`pvm2 doctor` checks the same primary files and reports their SHA-256 values.
`pvm2 inspect` records source hashes in its JSON report, and every model run
stores input fingerprints and artifact hashes in `run_manifest.json`.

## Reference map

`Lapola_et_al_T062.bin` is the **observed** natural-vegetation map used to
compute kappa; it is not a model output.  The reference experiment writes its
own simulation to NetCDF/GeoTIFF, and `pvm2 reproduce` compares the two maps.
The QGIS palette is only a visual aid and does not affect the metric.

## Article and technical report

The Lapola et al. (2009) article is identified by DOI
`10.1029/2008GB003357` in `docs/reference_lapola_2009.md` and
`CITATION.cff`.  The publisher PDF is not redistributed.  The older Lapola et
al. (2006) technical report is referenced but also not included.

## Citing the software

Use `CITATION.cff` for the software entry and cite the model papers listed in
`README.md`.  The software citation points to the project rather than to an
individual author; the model papers retain their original authorship.
