"""Reader and writer for the legacy GrADS-style direct-access binaries.

The original programs used ``access='direct', recl=nx*ny`` compiled with a
word-based RECL compiler (Intel/g95).  On disk this is a plain sequence of
little-endian IEEE-754 float32 records, each record being one field of
``ny * nx`` values in Fortran order (x varies fastest).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULT_DTYPE = np.dtype("<f4")


def read_records(path, count, ny, nx, dtype=DEFAULT_DTYPE):
    """Read ``count`` consecutive records into an array (count, ny, nx)."""
    path = Path(path)
    expected = count * ny * nx * dtype.itemsize
    size = path.stat().st_size
    if size != expected:
        raise ValueError(
            f"{path}: file has {size} bytes but {count} records of "
            f"{ny}x{nx} {dtype} require {expected} bytes"
        )
    raw = np.fromfile(path, dtype=dtype)
    return raw.reshape(count, ny, nx)


def read_monthly(path, ny, nx, dtype=DEFAULT_DTYPE):
    """Read 12 monthly records as (12, ny, nx)."""
    return read_records(path, 12, ny, nx, dtype=dtype)


def read_single(path, ny, nx, dtype=DEFAULT_DTYPE):
    """Read a single 2-D record as (ny, nx)."""
    return read_records(path, 1, ny, nx, dtype=dtype)[0]


def write_records(path, fields, dtype=DEFAULT_DTYPE):
    """Write a sequence of (ny, nx) fields as direct-access float32 records."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        for field in fields:
            np.asarray(field, dtype=dtype).tofile(fh)
    return path


def write_monthly(path, field3d, dtype=DEFAULT_DTYPE):
    """Write a (12, ny, nx) array as 12 records."""
    if field3d.shape[0] != 12:
        raise ValueError("monthly field must have 12 time steps")
    return write_records(path, list(field3d), dtype=dtype)


def write_biome_bundle(path, fields):
    """Write the 12 records produced by pvm5.f, in the original order."""
    order = [
        "bpot",
        "npp",
        "snpp",
        "ratioNPP",
        "hresp",
        "csoil",
        "d2wm",
        "ud2w",
        "photo",
        "aresp",
        "seai",
        "weti",
    ]
    return write_records(path, [fields[name] for name in order])
