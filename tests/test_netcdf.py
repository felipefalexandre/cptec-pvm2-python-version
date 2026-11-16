import numpy as np
import xarray as xr

from pvm2 import config
from pvm2.io import netcdf


def _dataset():
    time = np.arange(1, 13)
    lat = np.array([-30.0, 30.0])
    lon = np.array([0.0, 120.0, 240.0])
    shape3 = (12, 2, 3)
    return xr.Dataset(
        {
            "pr": (
                ("time", "lat", "lon"),
                np.full(shape3, 1.0),
                {"units": "mm day-1"},
            ),
            "tas": (
                ("time", "lat", "lon"),
                np.full(shape3, 273.15),
                {"units": "K"},
            ),
            "par": (
                ("time", "lat", "lon"),
                np.full(shape3, 1.0),
                {"units": "Einstein m-2 s-1"},
            ),
            "ua850": (
                ("time", "lat", "lon"),
                np.full(shape3, 2.0),
                {"units": "m s-1"},
            ),
            "ps": (
                ("lat", "lon"),
                np.full((2, 3), 101325.0),
                {"units": "Pa"},
            ),
            "lsmk": (
                ("lat", "lon"),
                np.ones((2, 3)),
                {"units": "1"},
            ),
        },
        coords={"time": time, "lat": lat, "lon": lon},
    )


def test_load_climate_converts_units(tmp_path):
    path = tmp_path / "climate.nc"
    _dataset().to_netcdf(path)
    data = netcdf.load_climate(
        path, config.DEFAULT_VARIABLES, config.DEFAULT_COORDS
    )
    days = np.array([31.0, 28.25, 31.0, 30.0, 31.0, 30.0, 31.0, 31.0, 30.0, 31.0, 30.0, 31.0])
    assert np.allclose(data["precipitation"], days[:, None, None])
    assert np.allclose(data["temperature"], 0.0)
    assert np.allclose(data["pressure"], 1013.25)
    assert np.allclose(data["par"], 2.18e5)
    assert data["pressure"].shape == (2, 3)
    assert data["attrs"]["precipitation"]["units"] == "mm/month"
    assert data["attrs"]["pressure"]["units"] == "hPa"
    assert data["attrs"]["par"]["units"] == "W m-2"


def test_load_climate_accepts_constant_time_static_fields(tmp_path):
    ds = _dataset()
    ds["ps"] = (
        ("time", "lat", "lon"),
        np.broadcast_to(ds["ps"].values, (12, 2, 3)).copy(),
        {"units": "Pa"},
    )
    path = tmp_path / "climate.nc"
    ds.to_netcdf(path)
    data = netcdf.load_climate(
        path, config.DEFAULT_VARIABLES, config.DEFAULT_COORDS
    )
    assert data["pressure"].shape == (2, 3)
    assert np.allclose(data["pressure"], 1013.25)
