"""Plausible input ranges used to catch unit and variable-mapping mistakes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FieldRange:
    minimum: float
    maximum: float
    units: str
    hint: str = ""


RANGES = {
    "precipitation": FieldRange(
        0.0,
        5000.0,
        "mm/month",
        "monthly totals are expected; use units mm day-1 for rates",
    ),
    "temperature": FieldRange(
        -90.0,
        60.0,
        "degC",
        "Kelvin data must be declared with units K and are converted on load",
    ),
    "par": FieldRange(
        0.0,
        500.0,
        "W m-2",
        "Einstein m-2 s-1 must be declared and is converted on load",
    ),
    "pressure": FieldRange(
        250.0,
        1100.0,
        "hPa",
        "Pa or kPa must be declared and are converted on load",
    ),
    "uwind": FieldRange(
        -150.0,
        150.0,
        "m s-1",
        "check that the wind is in m s-1, not km h-1",
    ),
}


def _issue(key, values, context, land=None):
    values = np.asarray(values)
    if land is not None:
        if not np.any(land):
            return None
        values = values[..., land] if values.ndim > land.ndim else values[land]
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return f"{context}.{key}: no finite values"
    if key == "landmask":
        if not np.all(
            np.isclose(finite, 0.0, atol=1.0e-6)
            | np.isclose(finite, 1.0, atol=1.0e-6)
        ):
            return (
                f"{context}.{key}: landmask must contain only 0 (ocean) and "
                f"1 (land); found range [{finite.min():.4g}, {finite.max():.4g}]"
            )
        return None
    spec = RANGES[key]
    low = float(finite.min())
    high = float(finite.max())
    tolerance = 1.0e-6
    if low < spec.minimum - tolerance or high > spec.maximum + tolerance:
        message = (
            f"{context}.{key}: values [{low:.4g}, {high:.4g}] {spec.units} "
            f"are outside the plausible range "
            f"[{spec.minimum:g}, {spec.maximum:g}] {spec.units}; "
            "check the units and variable mapping"
        )
        if spec.hint:
            message += f" ({spec.hint})"
        return message
    return None


def check_field(key, values, context="input"):
    """Raise ValueError when one field falls outside its plausible range."""
    issue = _issue(key, values, context)
    if issue:
        raise ValueError(issue)


def check_inputs(data, context="input"):
    """Validate all model inputs, reporting every problem at once."""
    land = np.asarray(data.get("landmask", []))
    land = land > 0.5 if land.size else None
    issues = []
    for key in RANGES:
        if key not in data:
            continue
        mask = land if (land is not None and key != "landmask") else None
        issue = _issue(key, data[key], context, mask)
        if issue:
            issues.append(issue)
    if issues:
        raise ValueError(
            "input validation failed:\n  " + "\n  ".join(issues)
        )


def check_sources(sources, context="input.sources"):
    """Validate each per-variable source before resampling."""
    issues = []
    for key, source in sources.items():
        issue = _issue(key, source["values"], f"{context}.{key}")
        if issue:
            issues.append(issue)
    if issues:
        raise ValueError(
            "input validation failed:\n  " + "\n  ".join(issues)
        )
