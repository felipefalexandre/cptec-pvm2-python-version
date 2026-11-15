"""Optional polygon export of categorical vegetation grids."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .raster import CLASS_NAMES


def write_geojson(path, data, lat, lon, dissolve=True, nodata=0):
    """Convert a categorical grid to polygons.

    This is intentionally opt-in: a 192x96 grid can already produce tens of
    thousands of polygons.  No geometry simplification is applied.
    """
    try:
        import geopandas as gpd
        from rasterio.features import shapes
        from rasterio.transform import from_origin
        from shapely.geometry import shape
    except ImportError as exc:  # pragma: no cover
        raise ImportError("geopandas, rasterio and shapely are required") from exc

    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    dx = float(lon[1] - lon[0])
    dy = float(lat[1] - lat[0])
    transform = from_origin(lon[0] - dx / 2.0, lat[-1] + dy / 2.0, dx, dy)
    array = np.flipud(np.asarray(data)).astype(np.int32)

    records = []
    for geom, value in shapes(array, transform=transform):
        value = int(value)
        if value == nodata:
            continue
        records.append({"biome": value, "geometry": shape(geom)})

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    if dissolve and not gdf.empty:
        gdf = gdf.dissolve(by="biome").reset_index()
    gdf["class_name"] = gdf["biome"].map(CLASS_NAMES)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")
    return path
