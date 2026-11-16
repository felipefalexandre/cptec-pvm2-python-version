"""Grid detection and land-mask presets for input harmonisation."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import numpy as np

CLIMATE_KEYS = ("precipitation", "temperature", "par", "pressure", "uwind")

PRESET_DESCRIPTIONS = {
    0.10: "MERGE/CODEX high resolution",
    0.25: "ERA5 / CMIP6 high resolution",
    0.50: "CMIP6 common",
    1.00: "CMIP6 / global climate",
    2.00: "CMIP6 coarse",
    2.50: "CMIP6 coarse",
    5.00: "coarse global",
    10.00: "very coarse global",
}


@dataclass
class LandmaskPreset:
    name: str
    resolution: float
    description: str
    lat: np.ndarray
    lon: np.ndarray
    landmask: np.ndarray
    source: str = "package"
    metadata: dict = field(default_factory=dict)


def _landmask_dir():
    return resources.files("pvm2").joinpath("data", "lsmk")


def _resolution_from_name(name: str) -> float:
    stem = Path(name).stem
    if not stem.startswith("lsmk_"):
        raise ValueError(f"not a landmask preset: {name}")
    return float(stem[len("lsmk_") :].replace("p", "."))


def _load_preset(name, resource):
    import xarray as xr

    with resources.as_file(resource) as path:
        with xr.open_dataset(path) as ds:
            lat = np.asarray(ds["lat"].values, dtype=np.float64)
            lon = np.asarray(ds["lon"].values, dtype=np.float64)
            mask = np.asarray(ds["lsmk"].values, dtype=np.int8)
            metadata = dict(ds.attrs)
    resolution = float(metadata.get("resolution_degrees", _resolution_from_name(name)))
    return LandmaskPreset(
        name=Path(name).stem,
        resolution=resolution,
        description=PRESET_DESCRIPTIONS.get(
            round(resolution, 2), f"{resolution:g} degree grid"
        ),
        lat=lat,
        lon=lon,
        landmask=mask,
        metadata=metadata,
    )


def available_presets() -> list[LandmaskPreset]:
    """Load the land-mask files bundled with the package."""
    directory = _landmask_dir()
    presets = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.name.startswith("lsmk_") and entry.name.endswith(".nc"):
            presets.append(_load_preset(entry.name, entry))
    if not presets:
        raise FileNotFoundError(f"no landmask presets found in {directory}")
    return presets


def axis_spacing(values) -> float:
    """Return the largest spacing between consecutive cell centres."""
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size < 2:
        return 0.0
    diffs = np.abs(np.diff(values))
    diffs = diffs[np.isfinite(diffs) & (diffs > 1.0e-9)]
    if diffs.size == 0:
        return 0.0
    return float(np.max(diffs))


def source_resolution(lat, lon) -> float:
    """Nominal resolution of a source grid, in degrees."""
    return max(axis_spacing(lat), axis_spacing(lon))


def coarsest_resolution(sources) -> float:
    """Largest nominal resolution among the climate fields."""
    values = [
        source_resolution(source["lat"], source["lon"])
        for key, source in sources.items()
        if key in CLIMATE_KEYS
    ]
    if not values:
        raise ValueError("no climate fields found while detecting resolution")
    return max(values)


def compatible_presets(
    coarsest: float,
    presets: list[LandmaskPreset] | None = None,
    tolerance: float = 1.0e-6,
) -> list[LandmaskPreset]:
    """Presets that do not require upscaling climate fields.

    The result is ordered from coarsest to finest, as requested by the
    interactive prompt.
    """
    if presets is None:
        presets = available_presets()
    selected = [
        preset for preset in presets if preset.resolution + tolerance >= coarsest
    ]
    if not selected:
        raise ValueError(
            f"no bundled landmask is coarser than the input resolution "
            f"({coarsest:g} degrees); add a coarser preset"
        )
    return sorted(selected, key=lambda preset: preset.resolution, reverse=True)


def coarsest_compatible(
    coarsest: float,
    presets: list[LandmaskPreset] | None = None,
) -> LandmaskPreset:
    """The finest preset that avoids upscaling; the recommended target."""
    return compatible_presets(coarsest, presets)[-1]


def custom_preset(path, key="landmask") -> LandmaskPreset:
    """Load a user-supplied landmask as a target candidate."""
    from .io import netcdf

    field = netcdf.load_field(
        path,
        key,
        "lsmk",
        {"latitude": "lat", "longitude": "lon", "time": "time"},
    )
    mask = field["values"]
    if mask.ndim != 2:
        raise ValueError(f"{path}: landmask must be a 2-D field")
    from . import ranges

    ranges.check_field("landmask", mask, f"landmask {path}")
    return LandmaskPreset(
        name=str(path),
        resolution=source_resolution(field["lat"], field["lon"]),
        description="user-provided landmask",
        lat=field["lat"],
        lon=field["lon"],
        landmask=mask.astype(np.int8, copy=False),
        source="custom",
        metadata=field["attrs"],
    )


def _normalise_lon(lon):
    lon = np.asarray(lon, dtype=np.float64)
    return (lon + 180.0) % 360.0 - 180.0


def _is_global_longitude(lon) -> bool:
    lon = np.asarray(lon, dtype=np.float64).ravel()
    if lon.size < 2:
        return False
    normalised = _normalise_lon(lon)
    spacing = axis_spacing(normalised)
    ordered = np.sort(normalised)
    wrap_gap = ordered[0] + 360.0 - ordered[-1]
    max_gap = max(float(np.max(np.diff(ordered))), float(wrap_gap))
    return max_gap <= spacing * 1.5 + 1.0e-6


def source_bounds(source) -> dict:
    """Bounding box of cell-centre coverage for one source grid."""
    lat = np.asarray(source["lat"], dtype=np.float64).ravel()
    lon = np.asarray(source["lon"], dtype=np.float64).ravel()
    if lat.size < 2 or lon.size < 2:
        raise ValueError("latitude and longitude need at least two points")
    dlat = axis_spacing(lat)
    normalised = _normalise_lon(lon)
    dlon = axis_spacing(normalised)
    global_lon = _is_global_longitude(lon)
    return {
        "lat_min": float(lat.min() - dlat / 2.0),
        "lat_max": float(lat.max() + dlat / 2.0),
        "lon_min": None if global_lon else float(normalised.min() - dlon / 2.0),
        "lon_max": None if global_lon else float(normalised.max() + dlon / 2.0),
        "lon_global": global_lon,
    }


def common_bounds(sources) -> dict:
    """Intersection of source coverage; longitude is global only if all are."""
    bounds = [source_bounds(source) for key, source in sources.items() if key in CLIMATE_KEYS]
    if not bounds:
        raise ValueError("no climate fields found")
    lat_min = max(item["lat_min"] for item in bounds)
    lat_max = min(item["lat_max"] for item in bounds)
    if lat_max <= lat_min:
        raise ValueError("climate fields do not share an overlapping latitude domain")
    if all(item["lon_global"] for item in bounds):
        lon_min = lon_max = None
    else:
        regional = [item for item in bounds if not item["lon_global"]]
        lon_min = max(item["lon_min"] for item in regional)
        lon_max = min(item["lon_max"] for item in regional)
        if lon_max <= lon_min:
            raise ValueError("climate fields do not share an overlapping longitude domain")
    return {
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
    }


def crop_preset(preset: LandmaskPreset, bounds: dict, tolerance=1.0e-9):
    """Crop a preset to the common source domain."""
    lat = np.asarray(preset.lat, dtype=np.float64)
    lon = np.asarray(preset.lon, dtype=np.float64)
    lat_mask = (
        (lat >= bounds["lat_min"] - tolerance)
        & (lat <= bounds["lat_max"] + tolerance)
    )
    if bounds["lon_min"] is None:
        lon_mask = np.ones(lon.size, dtype=bool)
    else:
        lon_mask = (
            (lon >= bounds["lon_min"] - tolerance)
            & (lon <= bounds["lon_max"] + tolerance)
        )
    if lat_mask.sum() < 2 or lon_mask.sum() < 2:
        raise ValueError(
            "the selected landmask does not contain at least two cells "
            "inside the common climate domain"
        )
    return LandmaskPreset(
        name=preset.name,
        resolution=preset.resolution,
        description=preset.description,
        lat=lat[lat_mask],
        lon=lon[lon_mask],
        landmask=np.asarray(preset.landmask)[
            np.ix_(np.flatnonzero(lat_mask), np.flatnonzero(lon_mask))
        ],
        source=preset.source,
        metadata=dict(preset.metadata),
    )


def _sorted_grid(lat, lon, mask):
    lat = np.asarray(lat, dtype=np.float64)
    lon = _normalise_lon(lon)
    lat_order = np.argsort(lat)
    lon_order = np.argsort(lon)
    return (
        lat[lat_order],
        lon[lon_order],
        np.asarray(mask)[np.ix_(lat_order, lon_order)],
    )


def aggregate_mask(source: LandmaskPreset, target_lat, target_lon, threshold=0.5):
    """Approximate area averaging of a fine land mask onto a coarse grid.

    The target cell is sampled on a 3x3 subgrid and the mean land fraction is
    thresholded at 0.5.  This is used when a user supplies a land mask finer
    than the selected climate grid: climate fields stay on the selected grid
    while the land/sea boundary uses the finer mask.
    """
    src_lat, src_lon, src_mask = _sorted_grid(
        source.lat, source.lon, source.landmask
    )
    dst_lat = np.asarray(target_lat, dtype=np.float64)
    dst_lon = np.asarray(target_lon, dtype=np.float64)

    src_bounds = source_bounds({"lat": src_lat, "lon": src_lon})
    if dst_lat.min() < src_bounds["lat_min"] - 1.0e-6:
        raise ValueError("landmask does not cover the target latitude domain")
    if dst_lat.max() > src_bounds["lat_max"] + 1.0e-6:
        raise ValueError("landmask does not cover the target latitude domain")
    if src_bounds["lon_global"]:
        lon_covered = True
    else:
        lon_covered = (
            dst_lon.min() >= src_bounds["lon_min"] - 1.0e-6
            and dst_lon.max() <= src_bounds["lon_max"] + 1.0e-6
        )
    if not lon_covered:
        raise ValueError("landmask does not cover the target longitude domain")

    samples = 3
    offsets = (np.arange(samples) + 0.5) / samples - 0.5
    dlat = axis_spacing(dst_lat)
    dlon = axis_spacing(dst_lon)
    sub_lat = (dst_lat[:, None] + offsets[None, :] * dlat).ravel()
    sub_lon = (dst_lon[:, None] + offsets[None, :] * dlon).ravel()
    fine = resample_field(
        src_mask,
        src_lat,
        src_lon,
        sub_lat,
        sub_lon,
        periodic_lon=_is_global_longitude(src_lon),
    )
    fraction = fine.reshape(dst_lat.size, samples, dst_lon.size, samples).mean(
        axis=(1, 3)
    )
    return (fraction >= threshold).astype(np.int8)


def _axis_weights(source, target, periodic=False):
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if periodic:
        source = source % 360.0
        order = np.argsort(source)
        source = source[order]
        extended = np.concatenate([source - 360.0, source, source + 360.0])
        target = target % 360.0
    else:
        source = _normalise_lon(source)
        target = _normalise_lon(target)
        order = np.argsort(source)
        source = source[order]
        extended = source
        target = np.clip(target, source[0], source[-1])

    index = np.searchsorted(extended, target) - 1
    index = np.clip(index, 0, extended.size - 2)
    left = extended[index]
    right = extended[index + 1]
    weight = np.divide(
        target - left,
        right - left,
        out=np.zeros_like(target),
        where=(right - left) != 0,
    )
    weight = np.clip(weight, 0.0, 1.0)
    return order, index, weight


def resample_field(
    values,
    source_lat,
    source_lon,
    target_lat,
    target_lon,
    periodic_lon=True,
):
    """Bilinearly resample a 2-D or 3-D field onto a regular target grid.

    Source and target longitudes may use either 0..360 or -180..180.  Global
    sources are interpolated cyclically; regional sources are not.  Missing
    source corners are excluded from the weighted average; a target cell is
    NaN only when all four contributing corners are NaN.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.ndim not in (2, 3):
        raise ValueError("resample_field expects a 2-D or 3-D array")
    src_lat = np.asarray(source_lat, dtype=np.float64).ravel()
    src_lon = _normalise_lon(source_lon)
    dst_lat = np.asarray(target_lat, dtype=np.float64).ravel()
    dst_lon = _normalise_lon(target_lon)

    lat_order, lat_index, lat_weight = _axis_weights(src_lat, dst_lat)
    lon_order, lon_index, lon_weight = _axis_weights(
        src_lon, dst_lon, periodic=periodic_lon
    )
    values = np.take(values, lat_order, axis=-2)
    values = np.take(values, lon_order, axis=-1)

    lat0 = lat_index
    lat1 = np.minimum(lat_index + 1, src_lat.size - 1)
    lon0 = lon_index % src_lon.size
    lon1 = (lon_index + 1) % src_lon.size
    w00 = (1.0 - lat_weight)[:, None] * (1.0 - lon_weight)[None, :]
    w01 = (1.0 - lat_weight)[:, None] * lon_weight[None, :]
    w10 = lat_weight[:, None] * (1.0 - lon_weight)[None, :]
    w11 = lat_weight[:, None] * lon_weight[None, :]

    lead = values.shape[:-2]
    v = values.reshape((-1,) + values.shape[-2:])
    out = np.empty((v.shape[0], dst_lat.size, dst_lon.size), dtype=np.float64)
    for slot in range(v.shape[0]):
        field = v[slot]
        v00 = field[np.ix_(lat0, lon0)]
        v01 = field[np.ix_(lat0, lon1)]
        v10 = field[np.ix_(lat1, lon0)]
        v11 = field[np.ix_(lat1, lon1)]
        valid00 = np.isfinite(v00)
        valid01 = np.isfinite(v01)
        valid10 = np.isfinite(v10)
        valid11 = np.isfinite(v11)
        total = (
            w00 * valid00
            + w01 * valid01
            + w10 * valid10
            + w11 * valid11
        )
        weighted = (
            np.where(valid00, v00, 0.0) * w00
            + np.where(valid01, v01, 0.0) * w01
            + np.where(valid10, v10, 0.0) * w10
            + np.where(valid11, v11, 0.0) * w11
        )
        out[slot] = np.divide(
            weighted,
            total,
            out=np.full(weighted.shape, np.nan),
            where=total > 0.0,
        )
    return out.reshape(lead + (dst_lat.size, dst_lon.size))
