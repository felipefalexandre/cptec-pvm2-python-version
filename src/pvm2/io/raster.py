"""GeoTIFF export for regular latitude/longitude grids."""

from __future__ import annotations

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


def write_geotiff(path, data, lat, lon, nodata=-9999, description=None):
    """Write a categorical (lat, lon) array as a compressed GeoTIFF."""
    try:
        import rasterio
        from rasterio.transform import from_origin
    except ImportError as exc:  # pragma: no cover
        raise ImportError("rasterio is required for GeoTIFF export") from exc

    lat_axis = _regular_axis(lat)
    lon_axis = _regular_axis(lon)
    if lat_axis is None or lon_axis is None:
        raise ValueError(
            "GeoTIFF export requires regular monotonic 1-D latitude and longitude"
        )
    lat_values, dy = lat_axis
    lon_values, dx = lon_axis
    if dy <= 0:
        raise ValueError("latitude must be ascending for this exporter")

    x0 = lon_values[0] - dx / 2.0
    y0 = lat_values[-1] + dy / 2.0
    transform = from_origin(x0, y0, dx, dy)
    array = np.flipud(np.asarray(data)).astype(np.int16)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
        compress="deflate",
        predictor=2,
        tiled=True,
    ) as dst:
        dst.write(array, 1)
        dst.update_tags(
            CLASS_NAMES="; ".join(f"{k}={v}" for k, v in sorted(CLASS_NAMES.items()))
        )
        if description:
            dst.update_tags(description=description)
    return path
