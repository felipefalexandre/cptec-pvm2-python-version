"""Compare Python PVM2 outputs with the legacy Fortran field files."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..io import legacy_binary

ANNUAL_FIELDS = (
    "tmin",
    "meanpp",
    "seanpp",
    "meanhr",
    "meancs",
    "mphoto",
    "maresp",
    "seai",
    "weti",
)

MONTHLY_FILES = (
    ("mon_npp_100.bin", "npp"),
    ("mon_photo_100.bin", "gpp"),
    ("mon_ar_100.bin", "ra"),
    ("soilm_100.bin", "soilmoist"),
    ("evaptr_100.bin", "evapotranspiration"),
    ("rc_100.bin", "canopy_resistance"),
)

BUNDLE_FIELDS = (
    ("bpot", "biome", 0.0),
    ("npp", "meanpp", 1.0e-4),
    ("snpp", "seanpp", 1.0e-4),
    ("ratioNPP", "ratioNPP", 1.0e-4),
    ("hresp", "meanhr", 1.0e-4),
    ("csoil", "meancs", 1.0e-4),
    ("d2wm", "d2wm", 0.0),
    ("ud2w", "ud2w", 0.0),
    ("photo", "mphoto", 1.0e-4),
    ("aresp", "maresp", 1.0e-4),
    ("seai", "seai", 1.0e-4),
    ("weti", "weti", 1.0e-4),
)

DEFAULT_TOLERANCES = {
    "tmin": 0.0,
    "meanpp": 1.0e-4,
    "seanpp": 1.0e-4,
    "meanhr": 1.0e-4,
    "meancs": 1.0e-4,
    "mphoto": 1.0e-4,
    "maresp": 1.0e-4,
    "seai": 1.0e-4,
    "weti": 1.0e-4,
    "npp": 1.0e-4,
    "gpp": 1.0e-4,
    "ra": 1.0e-4,
    "soilmoist": 1.0e-4,
    "evapotranspiration": 1.0e-4,
    "canopy_resistance": 1.0e-1,
}


def compare_arrays(expected, actual, land=None, sentinel=-900.0, atol=1.0e-4):
    """Compare two arrays, ignoring sentinels, NaNs and optional ocean cells."""
    expected = np.asarray(expected, dtype=np.float64)
    actual = np.asarray(actual, dtype=np.float64)
    if expected.shape != actual.shape:
        raise ValueError(
            f"shape mismatch: expected {expected.shape}, got {actual.shape}"
        )
    mask = (
        np.isfinite(expected)
        & np.isfinite(actual)
        & (expected > sentinel)
        & (actual > sentinel)
    )
    if land is not None:
        mask &= np.asarray(land, dtype=bool)
    n = int(mask.sum())
    if n == 0:
        return {
            "n": 0,
            "max_abs": None,
            "mean_abs": None,
            "atol": float(atol),
            "passed": True,
        }
    diff = np.abs(expected[mask] - actual[mask])
    return {
        "n": n,
        "max_abs": float(diff.max()),
        "mean_abs": float(diff.mean()),
        "atol": float(atol),
        "passed": bool(diff.max() <= atol),
    }


def compare_legacy(fortran_dir, nc_path, tolerances=None):
    """Compare a Python result file against the files written by env5/pvm5."""
    import xarray as xr

    fortran_dir = Path(fortran_dir)
    tolerances = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    with xr.open_dataset(nc_path) as ds:
        ny, nx = ds.sizes["lat"], ds.sizes["lon"]
        land = np.asarray(ds["biome"], dtype=np.int32) != 0
        checks = {}

        annual_path = fortran_dir / "ambientais4_100.bin"
        if annual_path.exists():
            fields = legacy_binary.read_records(annual_path, 9, ny, nx)
            for name, field in zip(ANNUAL_FIELDS, fields):
                checks[f"annual.{name}"] = compare_arrays(
                    field, ds[name].values, land=land, atol=tolerances[name]
                )

        for filename, name in MONTHLY_FILES:
            path = fortran_dir / filename
            if not path.exists():
                continue
            fields = legacy_binary.read_records(path, 12, ny, nx)
            checks[f"monthly.{name}"] = compare_arrays(
                fields, ds[name].values, land=land, atol=tolerances[name]
            )

        bundle_path = fortran_dir / "bpot4on_100.bin"
        if not bundle_path.exists():
            bundle_path = fortran_dir / "bpot4off_100.bin"
        if bundle_path.exists():
            fields = legacy_binary.read_records(bundle_path, 12, ny, nx)
            for (legacy_name, name, atol), field in zip(BUNDLE_FIELDS, fields):
                checks[f"bundle.{legacy_name}"] = compare_arrays(
                    field, ds[name].values, land=land, atol=atol
                )

    if not checks:
        raise FileNotFoundError(
            f"no legacy field files found in {fortran_dir}"
        )
    return {
        "fortran_dir": str(fortran_dir),
        "python": str(nc_path),
        "checks": checks,
        "passed": all(check["passed"] for check in checks.values()),
    }
