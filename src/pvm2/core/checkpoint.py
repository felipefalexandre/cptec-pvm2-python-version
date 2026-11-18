"""Checkpoint helpers for long water-balance runs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np


FORMAT_VERSION = 1
INPUT_FIELDS = (
    "precipitation",
    "temperature",
    "par",
    "pressure",
    "landmask",
)


def input_digest(fields):
    """Return a stable SHA-256 over all fields that affect the water balance."""
    digest = hashlib.sha256()
    for name in INPUT_FIELDS:
        values = np.ascontiguousarray(fields[name], dtype=np.float64)
        digest.update(name.encode("ascii"))
        digest.update(str(values.shape).encode("ascii"))
        digest.update(values.tobytes())
    return digest.hexdigest()


def save(
    path,
    *,
    year,
    w,
    g,
    s,
    wg0,
    active,
    fields,
    meta,
):
    """Write an atomic compressed checkpoint and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {
        "year": np.int64(year),
        "w": np.asarray(w),
        "g": np.asarray(g),
        "s": np.asarray(s),
        "wg0": np.asarray(wg0),
        "active": np.asarray(active),
        "meta": np.array(json.dumps(meta, sort_keys=True)),
    }
    for name, values in fields.items():
        arrays[f"field_{name}"] = np.asarray(values)
    temporary = path.with_name(f"{path.name}.tmp")
    with open(temporary, "wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(temporary, path)
    return path


def load(path, fields, expected_meta):
    """Load a checkpoint, validate its metadata and return the saved state."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"].item()))
        for key, value in expected_meta.items():
            if meta.get(key) != value:
                raise ValueError(
                    f"checkpoint {path} does not match this run: "
                    f"{key} is {meta.get(key)!r}, expected {value!r}"
                )
        state = {
            "year": int(data["year"]),
            "w": data["w"].copy(),
            "g": data["g"].copy(),
            "s": data["s"].copy(),
            "wg0": data["wg0"].copy(),
            "active": data["active"].copy(),
            "fields": {
                name: data[f"field_{name}"].copy() for name in fields
            },
        }
    for name, values in state["fields"].items():
        if values.shape != fields[name].shape:
            raise ValueError(
                f"checkpoint {path} field {name} has shape {values.shape}, "
                f"expected {fields[name].shape}"
            )
    return state
