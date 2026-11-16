"""GeoTIFF export for latitude/longitude grids.

Regular grids use a north-up affine transform.  Irregular grids, such as the
T62 Gaussian latitudes used by the legacy model, are written with one ground
control point per cell so that the native grid is preserved without
resampling.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

CLASS_NAMES = {
    0: "ocean",
    1: "ombrophyllous_forest",
    2: "temperate_forest",
    3: "mixed_forest",
    4: "boreal_forest",
    5: "larch",
    6: "savanna",
    7: "grasslands",
    8: "caatinga",
    9: "semi_desert",
    10: "tundra",
    11: "desert",
    13: "seasonal_forest",
    20: "ice",
}


def _regular_axis(values):
    values = np.asarray(values, dtype=np.float64)
    if values.size < 2:
        return None
    diffs = np.diff(values)
    if not np.allclose(diffs, diffs[0], rtol=1e-3, atol=1e-4):
        return None
    if diffs[0] == 0:
        return None
    return values, float(diffs[0])


def _open_geotiff(path, array, nodata, **profile):
    import rasterio

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    options = dict(
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="int16",
        nodata=nodata,
        compress="deflate",
        predictor=2,
        tiled=True,
    )
    options.update(profile)
    return rasterio.open(path, "w", **options)


def _write_class_tags(dst, description=None):
    dst.update_tags(
        CLASS_NAMES="; ".join(f"{k}={v}" for k, v in sorted(CLASS_NAMES.items()))
    )
    if description:
        dst.update_tags(description=description)


def write_geotiff(path, data, lat, lon, nodata=-9999, description=None):
    """Write a categorical (lat, lon) array as a compressed GeoTIFF.

    Regular axes are written with a north-up affine transform.  Irregular
    axes fall back to per-cell ground control points, so the T62 Gaussian grid
    is georeferenced without being resampled.
    """
    try:
        import rasterio
        from rasterio.transform import from_origin
    except ImportError as exc:  # pragma: no cover
        raise ImportError("rasterio is required for GeoTIFF export") from exc

    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = np.asarray(lon, dtype=np.float64)
    array = np.flipud(np.asarray(data)).astype(np.int16)
    lat_axis = _regular_axis(lat_values)
    lon_axis = _regular_axis(lon_values)
    if lat_axis is None or lon_axis is None:
        return write_geotiff_gcps(
            path, data, lat_values, lon_values, nodata=nodata, description=description
        )
    _, dy = lat_axis
    _, dx = lon_axis
    if dy <= 0:
        raise ValueError("latitude must be ascending for this exporter")

    x0 = lon_values[0] - dx / 2.0
    y0 = lat_values[-1] + dy / 2.0
    transform = from_origin(x0, y0, dx, dy)

    with _open_geotiff(
        path, array, nodata, crs="EPSG:4326", transform=transform
    ) as dst:
        dst.write(array, 1)
        _write_class_tags(dst, description)
    return Path(path)


def write_geotiff_gcps(path, data, lat, lon, nodata=-9999, description=None):
    """Write an irregular grid using one ground control point per cell."""
    try:
        import rasterio
        from rasterio.control import GroundControlPoint
        from rasterio.crs import CRS
        from rasterio.errors import NotGeoreferencedWarning
        from rasterio.transform import Affine
    except ImportError as exc:  # pragma: no cover
        raise ImportError("rasterio is required for GeoTIFF export") from exc

    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = np.asarray(lon, dtype=np.float64)
    if lat_values.ndim != 1 or lon_values.ndim != 1:
        raise ValueError("latitude and longitude must be one-dimensional")
    if lat_values.size < 2 or lon_values.size < 2:
        raise ValueError("at least two latitudes and longitudes are required")
    if not np.all(np.isfinite(lat_values)) or not np.all(np.isfinite(lon_values)):
        raise ValueError("latitude and longitude must be finite")

    array = np.flipud(np.asarray(data)).astype(np.int16)
    if array.shape != (lat_values.size, lon_values.size):
        raise ValueError(
            f"data shape {array.shape} does not match grid "
            f"({lat_values.size}, {lon_values.size})"
        )
    north_lat = lat_values[::-1]
    gcps = [
        GroundControlPoint(
            row=float(row),
            col=float(col),
            x=float(lon_values[col]),
            y=float(north_lat[row]),
            z=0.0,
        )
        for row in range(north_lat.size)
        for col in range(lon_values.size)
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with _open_geotiff(
            path,
            array,
            nodata,
            crs="EPSG:4326",
            transform=Affine.identity(),
        ) as dst:
            dst.write(array, 1)
            dst.gcps = (gcps, CRS.from_epsg(4326))
            _write_class_tags(dst, description)
    return Path(path)
