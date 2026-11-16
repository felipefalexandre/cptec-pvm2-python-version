import numpy as np
import pytest
import xarray as xr

from pvm2.io import legacy_binary
from pvm2.validation import compare


def test_compare_arrays_masks_sentinel_ocean_and_nan():
    expected = np.array([[1.0, 2.0], [-999.0, np.nan]])
    actual = np.array([[1.1, 1.9], [-999.0, 5.0]])
    land = np.array([[True, False], [True, True]])
    result = compare.compare_arrays(expected, actual, land=land, atol=0.2)
    assert result["n"] == 1
    assert result["max_abs"] == pytest.approx(0.1)
    assert result["passed"] is True
    assert compare.compare_arrays(expected, actual, land=land, atol=0.05)["passed"] is False


def test_compare_arrays_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        compare.compare_arrays(np.zeros((2, 2)), np.zeros((2, 3)))


def test_compare_legacy_end_to_end(tmp_path):
    ny, nx = 2, 3
    lat = np.array([-30.0, 30.0])
    lon = np.array([0.0, 120.0, 240.0])
    land = np.array([[True, True, False], [True, True, False]])
    biome = np.where(land, 1, 0).astype(np.int16)
    ocean = -999.99

    annual_values = {
        "tmin": 10.0,
        "meanpp": 1.2,
        "seanpp": 0.4,
        "meanhr": 0.9,
        "meancs": 8.0,
        "mphoto": 2.0,
        "maresp": 0.8,
        "seai": 0.3,
        "weti": 0.5,
    }
    monthly_values = {
        "npp": 0.1,
        "gpp": 0.2,
        "ra": 0.05,
        "soilmoist": 0.6,
        "evapotranspiration": 3.0,
        "canopy_resistance": 200.0,
    }
    annual = {}
    for name, value in annual_values.items():
        annual[name] = np.where(land, value, ocean)
    monthly = {}
    land3 = np.broadcast_to(land, (12, ny, nx))
    for name, value in monthly_values.items():
        monthly[name] = np.where(land3, value, ocean)

    d2wm = np.where(land, 6.0, ocean)
    ud2w = np.where(land, 2.0, ocean)
    ds = xr.Dataset(
        {
            "biome": (("lat", "lon"), biome),
            **{name: (("lat", "lon"), arr) for name, arr in annual.items()},
            "ratioNPP": (("lat", "lon"), np.where(land, 0.5, ocean)),
            "d2wm": (("lat", "lon"), d2wm),
            "ud2w": (("lat", "lon"), ud2w),
            **{
                name: (("time", "lat", "lon"), arr)
                for name, arr in monthly.items()
            },
        },
        coords={"time": np.arange(1, 13), "lat": lat, "lon": lon},
    )
    nc_path = tmp_path / "python.nc"
    ds.to_netcdf(nc_path)

    fortran_dir = tmp_path / "fortran"
    fortran_dir.mkdir()
    legacy_binary.write_records(
        fortran_dir / "ambientais4_100.bin",
        [annual[name] for name in compare.ANNUAL_FIELDS],
    )
    for filename, name in compare.MONTHLY_FILES:
        legacy_binary.write_records(fortran_dir / filename, list(monthly[name]))
    bundle = [
        biome,
        annual["meanpp"],
        annual["seanpp"],
        np.where(land, 0.5, ocean),
        annual["meanhr"],
        annual["meancs"],
        d2wm,
        ud2w,
        annual["mphoto"],
        annual["maresp"],
        annual["seai"],
        annual["weti"],
    ]
    legacy_binary.write_records(fortran_dir / "bpot4on_100.bin", bundle)

    result = compare.compare_legacy(fortran_dir, nc_path)
    assert result["passed"] is True
    assert "bundle.d2wm" in result["checks"]
    assert result["checks"]["monthly.soilmoist"]["n"] == 48
