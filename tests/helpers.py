import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_INPUTS = ROOT / "legacy" / "data" / "inputs"
_REFERENCE = ROOT / "legacy" / "data" / "reference" / "Lapola_et_al_T062.bin"
_REQUIRED = ("prec.bin", "temp.bin", "ipar.bin", "psup.bin", "lsmk.bin", "uwind.bin")


def has_legacy_data():
    return all((_INPUTS / name).exists() for name in _REQUIRED) and _REFERENCE.exists()


requires_legacy_data = pytest.mark.skipif(
    not has_legacy_data(),
    reason="legacy input binaries are missing; see legacy/data/README.md",
)


def synthetic_inputs(ny, nx, seed=0):
    rng = np.random.default_rng(seed)
    months = np.arange(12, dtype=np.float64)[:, None, None]
    lat = np.linspace(-60.0, 60.0, ny)[None, :, None]
    lon = np.linspace(0.0, 360.0, nx, endpoint=False)[None, None, :]

    seasonal = np.sin(2.0 * np.pi * months / 12.0)
    temperature = (
        24.0
        - 0.22 * np.abs(lat)
        + 4.0 * seasonal
        + 1.5 * np.cos(np.deg2rad(lon))
    )
    precipitation = np.maximum(
        60.0
        + 90.0 * (0.5 + 0.5 * np.cos(np.deg2rad(lon)))
        + 60.0 * (0.5 + 0.5 * seasonal)
        + 10.0 * rng.standard_normal((12, ny, nx)),
        0.0,
    )
    par = (
        150.0
        + 60.0 * np.cos(2.0 * np.pi * months / 12.0)
        + 0.0 * lat
        + 0.0 * lon
    )
    uwind = 2.5 + 1.0 * np.sin(np.deg2rad(lon)) + 0.0 * lat + 0.0 * months
    pressure = np.full((ny, nx), 1010.0)
    landmask = np.ones((ny, nx))
    landmask[:, : max(1, nx // 8)] = 0.0
    return {
        "precipitation": precipitation,
        "temperature": temperature,
        "par": par,
        "pressure": pressure,
        "landmask": landmask,
        "uwind": uwind,
        "lat": np.linspace(-89.0, 89.0, ny),
        "lon": np.arange(nx, dtype=np.float64) * (360.0 / nx),
    }
