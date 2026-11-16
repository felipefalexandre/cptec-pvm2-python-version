# Reference article and Figure 1b check

## Citation

Lapola, D. M.; Oyama, M. D.; Nobre, C. A. **Exploring the range of climate
biome projections for tropical South America: the role of CO2 fertilization
and seasonality.** *Global Biogeochemical Cycles*, v. 23, GB3002, 2009.
DOI: [10.1029/2008GB003357](https://doi.org/10.1029/2008GB003357).

The publisher PDF is **not redistributed** in this repository.  Download it
from the DOI above or place a local copy in `legacy/pdf/`, which is ignored by
Git.

## What Figure 1b shows

Figure 1 of the article compares two global biome maps for the present
climate:

- **Figure 1a** is the observed natural-vegetation reference map distributed
  with the model (`Lapola_et_al_T062.bin`).
- **Figure 1b** is the potential vegetation simulated by CPTEC-PVM2 with the
  1961-1990 mean climate.

The repository reproduces Figure 1b from the default inputs with
`experiments/original/original.yaml` (`ca = 35.35 Pa`, natural fire on).
The observed map is used to compute kappa; the expected value is
`kappa = 0.525` with `agreement = 89.72%` over 3988 land cells.

## Installation check

Run the automated check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_installation.ps1
```

It runs `pytest`, validates the inputs, runs `pvm2 reproduce` with
`--min-kappa 0.50`, and checks that the following files exist:

```
outputs/original/pvm2_original_biome.tif
outputs/original/pvm2_original_reference_biome.tif
legacy/data/reference/vegetacao_referencia.qml
```

Manual equivalent:

```bash
pytest -q
pvm2 validate --config experiments/original/original.yaml
pvm2 reproduce --config experiments/original/original.yaml --min-kappa 0.50
```

## QGIS comparison

1. Open both GeoTIFFs in QGIS:
   - `outputs/original/pvm2_original_biome.tif` (simulated, Figure 1b);
   - `outputs/original/pvm2_original_reference_biome.tif` (observed,
     Figure 1a).
2. Load the palette `legacy/data/reference/vegetacao_referencia.qml` on each
   layer (Layer Properties -> Symbology -> Style -> Load Style).
3. Compare the simulated map with Figure 1b on page 5 of the article.  The
   biome classes and colours follow the QML palette: tropical evergreen
   forest, temperate forest, mixed forest, boreal evergreen and seasonal
   forest, savanna, grasslands, shrubland/caatinga, semi-desert, tundra,
   desert, tropical seasonal forest and ice.

The same comparison is rendered in `reports/scientific_validation.html`.
