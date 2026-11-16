"""Build the bundled land/sea masks from Natural Earth 10m land polygons.

This is a maintainer script, not needed to run PVM2.  It downloads (or reads)
the Natural Earth GeoJSON and rasterizes a binary land mask on regular
latitude/longitude grids.  Cell values are assigned from the polygon covering
the cell centre (all_touched=False).

The generated files are written to src/pvm2/data/lsmk/ and are distributed
with the package.  Natural Earth data are in the public domain.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import rasterio.features
from rasterio.transform import from_origin

import xarray as xr

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_land.geojson"
)
RESOLUTIONS = (0.10, 0.25, 0.50, 1.00, 2.00, 2.50, 5.00, 10.00)


def _load_geometries(path: Path):
    if not path.exists():
        print(f"downloading {SOURCE_URL}")
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SOURCE_URL, path)
    with path.open(encoding="utf-8") as fh:
        collection = json.load(fh)
    return [feature["geometry"] for feature in collection["features"]]


def _axis(resolution: float, span: float = 180.0):
    count = int(round(span / resolution))
    if not np.isclose(count * resolution, span):
        raise ValueError(f"{resolution} does not divide {span} degrees evenly")
    start = -span / 2.0 + resolution / 2.0
    return start + np.arange(count) * resolution


def _rasterize(geometries, resolution: float):
    shape = (
        int(round(180.0 / resolution)),
        int(round(360.0 / resolution)),
    )
    transform = from_origin(-180.0, 90.0, resolution, resolution)
    mask = rasterio.features.rasterize(
        [(geometry, 1) for geometry in geometries],
        out_shape=shape,
        transform=transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    )
    return np.flipud(mask)


def _filename(resolution: float):
    return f"lsmk_{str(resolution).replace('.', 'p')}.nc"


def write_mask(output_dir: Path, geometries, resolution: float):
    lat = _axis(resolution)
    lon = _axis(resolution, 360.0)
    mask = _rasterize(geometries, resolution)
    if mask.shape != (lat.size, lon.size):
        raise RuntimeError(f"unexpected mask shape {mask.shape}")

    ds = xr.Dataset(
        {
            "lsmk": (
                ("lat", "lon"),
                mask.astype(np.int8),
                {
                    "long_name": "land_binary_mask",
                    "units": "1",
                    "flag_values": np.array([0, 1], dtype=np.int8),
                    "flag_meanings": "ocean land",
                },
            )
        },
        coords={
            "lat": (
                "lat",
                lat,
                {
                    "standard_name": "latitude",
                    "units": "degrees_north",
                    "axis": "Y",
                },
            ),
            "lon": (
                "lon",
                lon,
                {
                    "standard_name": "longitude",
                    "units": "degrees_east",
                    "axis": "X",
                },
            ),
        },
        attrs={
            "title": "PVM2 land/sea mask preset",
            "Conventions": "CF-1.10",
            "source": (
                "Natural Earth 1:10m land polygons rasterized at cell centres"
            ),
            "source_url": SOURCE_URL,
            "license": "Natural Earth public domain",
            "resolution_degrees": resolution,
            "grid_type": "regular_lat_lon",
            "history": (
                "Created by scripts/make_landmasks.py; "
                "all_touched=False (cell-centre test)"
            ),
        },
    )
    path = output_dir / _filename(resolution)
    ds.to_netcdf(
        path,
        encoding={"lsmk": {"zlib": True, "complevel": 9, "dtype": "int8"}},
    )
    print(f"wrote {path} shape={mask.shape} land={mask.mean():.4f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--geojson",
        default=str(
            Path.home() / ".cache" / "pvm2" / "ne_10m_land.geojson"
        ),
        help="cached Natural Earth GeoJSON path",
    )
    parser.add_argument(
        "--output-dir",
        default=str(
            Path(__file__).resolve().parents[1]
            / "src"
            / "pvm2"
            / "data"
            / "lsmk"
        ),
    )
    parser.add_argument(
        "--resolutions",
        nargs="+",
        type=float,
        default=list(RESOLUTIONS),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    geometries = _load_geometries(Path(args.geojson))
    for resolution in args.resolutions:
        write_mask(output_dir, geometries, resolution)


if __name__ == "__main__":
    main()
