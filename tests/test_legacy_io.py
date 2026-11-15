from pathlib import Path

import numpy as np
import pytest

from pvm2.io import legacy_binary
from helpers import requires_legacy_data

ROOT = Path(__file__).resolve().parents[1]


def test_single_record_roundtrip(tmp_path):
    data = np.arange(12, dtype=np.float32).reshape(3, 4)
    path = tmp_path / "field.bin"
    legacy_binary.write_records(path, data[None, ...])
    assert np.array_equal(legacy_binary.read_single(path, 3, 4), data)


def test_monthly_roundtrip(tmp_path):
    data = np.arange(12 * 3 * 4, dtype=np.float32).reshape(12, 3, 4)
    path = tmp_path / "monthly.bin"
    legacy_binary.write_monthly(path, data)
    assert np.array_equal(legacy_binary.read_monthly(path, 3, 4), data)


def test_biome_bundle_order(tmp_path):
    fields = {
        "bpot": np.full((1, 1), 1.0),
        "npp": np.full((1, 1), 2.0),
        "snpp": np.full((1, 1), 3.0),
        "ratioNPP": np.full((1, 1), 4.0),
        "hresp": np.full((1, 1), 5.0),
        "csoil": np.full((1, 1), 6.0),
        "d2wm": np.full((1, 1), 7.0),
        "ud2w": np.full((1, 1), 8.0),
        "photo": np.full((1, 1), 9.0),
        "aresp": np.full((1, 1), 10.0),
        "seai": np.full((1, 1), 11.0),
        "weti": np.full((1, 1), 12.0),
    }
    path = tmp_path / "bundle.bin"
    legacy_binary.write_biome_bundle(path, fields)
    records = legacy_binary.read_records(path, 12, 1, 1)
    assert records.shape == (12, 1, 1)
    assert np.array_equal(
        records[:, 0, 0], np.arange(1, 13, dtype=np.float32)
    )


@requires_legacy_data
@pytest.mark.parametrize(
    "name,expected",
    [
        ("prec", (0.0, 1101.010009765625, 76.88319396972656)),
        ("temp", (-71.11000061035156, 38.290000915527344, 5.013609886169434)),
        ("ipar", (0.0, 173.86805725097656, 74.73846435546875)),
        ("uwind", (-12.973665237426758, 19.087852478027344, 1.4240312576293945)),
    ],
)
def test_legacy_input_statistics(name, expected):
    path = ROOT / "legacy" / "data" / "inputs" / f"{name}.bin"
    data = legacy_binary.read_monthly(path, 96, 192)
    assert data.shape == (12, 96, 192)
    lo, hi, mean = expected
    assert float(data.min()) == pytest.approx(lo, abs=1e-4)
    assert float(data.max()) == pytest.approx(hi, abs=1e-4)
    assert float(data.mean()) == pytest.approx(mean, abs=1e-4)
