"""Top-level PVM2 model driver."""

from __future__ import annotations

import numpy as np

from .. import ranges
from . import water_balance


def _prepare(data):
    required = (
        "precipitation",
        "temperature",
        "par",
        "pressure",
        "landmask",
        "uwind",
    )
    missing = [name for name in required if name not in data]
    if missing:
        raise KeyError(f"missing input fields: {', '.join(missing)}")

    prec = np.asarray(data["precipitation"], dtype=np.float64)
    temp = np.asarray(data["temperature"], dtype=np.float64)
    par = np.asarray(data["par"], dtype=np.float64)
    uwind = np.asarray(data["uwind"], dtype=np.float64)
    lsmk = np.asarray(data["landmask"], dtype=np.float64)
    p0 = np.asarray(data["pressure"], dtype=np.float64)

    if prec.shape != temp.shape or prec.shape != par.shape or prec.shape != uwind.shape:
        raise ValueError("monthly fields must share the same (12, ny, nx) shape")
    if prec.shape[0] != 12:
        raise ValueError("monthly fields must have exactly 12 time steps")
    if lsmk.shape != prec.shape[1:] or p0.shape != prec.shape[1:]:
        raise ValueError("pressure and landmask must match the spatial grid")

    land = lsmk.astype(np.int32) != 0
    for name, field in (
        ("precipitation", prec),
        ("temperature", temp),
        ("par", par),
        ("uwind", uwind),
    ):
        bad = np.isnan(field) & land[None, :, :]
        if np.any(bad):
            raise ValueError(
                f"{name}: {int(bad.sum())} missing values over land; "
                "PVM2 has no missing-data scheme"
            )
        field = np.where(np.isnan(field), 0.0, field)
        if name == "precipitation":
            prec = field
        elif name == "temperature":
            temp = field
        elif name == "par":
            par = field
        else:
            uwind = field

    if np.any(np.isnan(p0[land]) | np.isnan(lsmk[land])):
        raise ValueError("pressure or landmask contains missing values over land")

    fields = {
        "precipitation": np.maximum(prec, 0.0),
        "temperature": temp,
        "par": par,
        "pressure": p0,
        "landmask": lsmk,
        "uwind": uwind,
    }
    ranges.check_inputs(fields, context="input")
    return fields


def run(
    data,
    co2_pa=35.35,
    fire=True,
    max_equilibrium_years=20000,
    progress=None,
):
    """Execute CPTEC-PVM2 and return all environmental and biome fields."""
    fields = _prepare(data)
    results = water_balance.potential_vegetation(
        fields["precipitation"],
        fields["temperature"],
        fields["par"],
        fields["landmask"],
        fields["pressure"],
        float(co2_pa),
        fields["uwind"],
        fire=fire,
        max_years=max_equilibrium_years,
        progress=progress,
    )
    results["co2_pa"] = float(co2_pa)
    results["fire"] = bool(fire)
    results["lat"] = np.asarray(data.get("lat", []), dtype=np.float64)
    results["lon"] = np.asarray(data.get("lon", []), dtype=np.float64)
    return results
