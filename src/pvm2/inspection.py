"""Metadata and validation reports for NetCDF files and prepared inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import config, ranges


MONTHLY_FIELDS = ("precipitation", "temperature", "par", "uwind")
STATIC_FIELDS = ("pressure", "landmask")
ALL_FIELDS = MONTHLY_FIELDS + STATIC_FIELDS


def sha256(path, chunk_size=1024 * 1024):
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _json_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_scalar(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _attrs(values):
    return {str(key): _json_scalar(value) for key, value in values.items()}


def _stats(values):
    array = np.asarray(values, dtype=np.float64)
    finite = array[np.isfinite(array)]
    result = {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "nan_count": int(np.isnan(array).sum()),
        "min": None,
        "max": None,
        "mean": None,
    }
    if finite.size:
        result["min"] = float(finite.min())
        result["max"] = float(finite.max())
        result["mean"] = float(finite.mean())
    return result


def _axis(values):
    array = np.asarray(values, dtype=np.float64)
    result = {
        "size": int(array.size),
        "first": None,
        "last": None,
        "spacing": None,
        "uniform": False,
        "ascending": False,
        "descending": False,
    }
    if array.size == 0:
        return result
    result["first"] = float(array[0])
    result["last"] = float(array[-1])
    result["min"] = float(np.nanmin(array))
    result["max"] = float(np.nanmax(array))
    if array.size > 1:
        diffs = np.diff(array)
        result["spacing"] = float(np.median(np.abs(diffs)))
        result["uniform"] = bool(
            np.allclose(diffs, diffs[0], rtol=1.0e-9, atol=1.0e-12)
        )
        result["ascending"] = bool(np.all(diffs > 0))
        result["descending"] = bool(np.all(diffs < 0))
    return result


def _time_summary(dataset, name="time"):
    if name not in dataset.coords and name not in dataset.variables:
        return None
    variable = dataset[name]
    values = np.asarray(variable.values)
    result = {
        "name": name,
        "size": int(values.size),
        "units": variable.attrs.get("units"),
        "calendar": variable.attrs.get("calendar"),
        "dtype": str(values.dtype),
        "values": [_json_scalar(value) for value in values.ravel()[:24]],
    }
    if values.size:
        result["first"] = _json_scalar(values.ravel()[0])
        result["last"] = _json_scalar(values.ravel()[-1])
    return result


def _domain(dataset, coordinates):
    result = {}
    for axis, candidates in (
        ("latitude", ("lat", "latitude", "y")),
        ("longitude", ("lon", "longitude", "x")),
    ):
        name = next((item for item in candidates if item in coordinates), None)
        if name is None:
            continue
        values = np.asarray(dataset[name].values, dtype=np.float64)
        summary = _axis(values)
        summary["name"] = name
        if axis == "longitude" and values.size > 1:
            summary["duplicate_endpoint"] = bool(
                np.isclose(values[0] % 360.0, values[-1] % 360.0)
            )
        result[axis] = summary
    return result


def inspect_netcdf(path):
    """Return a serialisable inventory of a NetCDF file."""
    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover
        raise ImportError("xarray is required to inspect NetCDF files") from exc

    path = Path(path)
    with xr.open_dataset(path, decode_times=False) as dataset:
        coordinates = {}
        for name, variable in dataset.coords.items():
            item = {
                "dims": list(variable.dims),
                "shape": list(variable.shape),
                "dtype": str(variable.dtype),
                "attrs": _attrs(variable.attrs),
            }
            item["axis"] = _axis(variable.values)
            coordinates[name] = item
        variables = {}
        for name, variable in dataset.data_vars.items():
            variables[name] = {
                "dims": list(variable.dims),
                "shape": list(variable.shape),
                "dtype": str(variable.dtype),
                "attrs": _attrs(variable.attrs),
                "stats": _stats(variable.values),
            }
        return {
            "path": str(path),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "dimensions": dict(dataset.sizes),
            "variables": variables,
            "coordinates": coordinates,
            "time": _time_summary(dataset),
            "domain": _domain(dataset, coordinates),
            "global_attrs": _attrs(dataset.attrs),
        }


def _shape_issues(data):
    issues = []
    shapes = {}
    for key in MONTHLY_FIELDS:
        if key not in data:
            issues.append(f"input.{key}: missing field")
            continue
        shape = tuple(np.asarray(data[key]).shape)
        shapes[key] = shape
        if len(shape) != 3 or shape[0] != 12:
            issues.append(
                f"input.{key}: expected (12, ny, nx), got {shape}"
            )
    spatial = None
    if shapes:
        spatial = next(iter(shapes.values()))[1:]
        for key, shape in shapes.items():
            if shape[1:] != spatial:
                issues.append(
                    f"input.{key}: spatial shape {shape[1:]} does not match {spatial}"
                )
    for key in STATIC_FIELDS:
        if key not in data:
            issues.append(f"input.{key}: missing field")
            continue
        shape = tuple(np.asarray(data[key]).shape)
        if spatial is not None and shape != spatial:
            issues.append(
                f"input.{key}: expected spatial shape {spatial}, got {shape}"
            )
    return issues


def _missing_over_land(data):
    lsmk = np.asarray(data.get("landmask"), dtype=np.float64)
    land = lsmk > 0.5
    result = {}
    for key in MONTHLY_FIELDS:
        array = np.asarray(data[key], dtype=np.float64)
        if array.ndim == 3 and array.shape[1:] == land.shape:
            missing = (~np.isfinite(array)) & land[None, :, :]
            result[key] = {
                "over_land": int(missing.sum()),
                "over_ocean": int((~np.isfinite(array) & ~land[None, :, :]).sum()),
            }
        else:
            result[key] = {"over_land": 0, "over_ocean": 0}
    for key in STATIC_FIELDS:
        array = np.asarray(data[key], dtype=np.float64)
        if array.shape == land.shape:
            missing = (~np.isfinite(array)) & land
            result[key] = {
                "over_land": int(missing.sum()),
                "over_ocean": int((~np.isfinite(array) & ~land).sum()),
            }
        else:
            result[key] = {"over_land": 0, "over_ocean": 0}
    return result


def _time_from_file(path):
    try:
        import xarray as xr
    except ImportError:  # pragma: no cover
        return None
    with xr.open_dataset(path, decode_times=False) as dataset:
        return _time_summary(dataset)


def _source_entries(input_cfg):
    entries = []
    if input_cfg.climate:
        entries.append(("climate", input_cfg.climate))
    for key, path in input_cfg.legacy.items():
        entries.append((f"legacy.{key}", path))
    for key, spec in input_cfg.sources.items():
        if isinstance(spec, str):
            entries.append((f"source.{key}", spec))
        else:
            path = spec.get("path") or spec.get("file")
            if path:
                entries.append((f"source.{key}", path))

    by_path = {}
    for role, path in entries:
        key = str(Path(path).resolve())
        item = by_path.setdefault(
            key,
            {"path": str(path), "roles": [], "bytes": None, "sha256": None},
        )
        if role not in item["roles"]:
            item["roles"].append(role)
    result = []
    for item in by_path.values():
        path = Path(item["path"])
        try:
            item["bytes"] = path.stat().st_size
            item["sha256"] = sha256(path)
        except OSError as exc:
            item["error"] = str(exc)
        result.append(item)
    return result


def inspect_inputs(cfg):
    """Load a configuration and report grid, units, missing data and hashes."""
    data = config.load_inputs(cfg.input)
    land = np.asarray(data["landmask"], dtype=np.float64) > 0.5
    attrs = data.get("attrs", {})
    missing = _missing_over_land(data)

    fields = {}
    for key in ALL_FIELDS:
        item = _stats(data[key])
        if isinstance(attrs, dict) and isinstance(attrs.get(key), dict):
            item["units"] = attrs[key].get("units")
            item["source_variable"] = attrs[key].get("source_variable")
        else:
            item["units"] = None
            item["source_variable"] = None
        item["missing"] = missing[key]
        fields[key] = item

    issues = _shape_issues(data) + ranges.collect_issues(data, "input")
    for key, counts in missing.items():
        if counts["over_land"]:
            issues.append(
                f"input.{key}: {counts['over_land']} missing values over land; "
                "PVM2 has no missing-data scheme"
            )

    time = None
    if cfg.input.climate:
        try:
            time = _time_from_file(cfg.input.climate)
        except (OSError, ValueError):
            time = None
    elif cfg.input.legacy:
        time = {"kind": "monthly_climatology", "size": 12}

    sources = _source_entries(cfg.input)
    for source in sources:
        if "error" in source:
            issues.append(
                f"{source['path']}: {source['error']}"
            )

    config_hash = None
    if cfg.source:
        try:
            config_hash = sha256(cfg.source)
        except OSError:
            config_hash = None

    return {
        "ok": not issues,
        "config_file": cfg.source,
        "config_sha256": config_hash,
        "path_mode": cfg.relative_to,
        "warnings": list(cfg.warnings),
        "grid": {
            "latitude": _axis(data.get("lat", [])),
            "longitude": _axis(data.get("lon", [])),
            "shape": list(land.shape),
            "land_cells": int(land.sum()),
        },
        "time": time,
        "fields": fields,
        "sources": sources,
        "issues": issues,
    }
