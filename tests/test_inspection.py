import hashlib
import json

import numpy as np
import xarray as xr

from pvm2 import cli, inspection


def _dataset():
    shape = (12, 2, 3)
    time = np.arange(1, 13)
    lat = np.array([-30.0, 30.0])
    lon = np.array([0.0, 120.0, 240.0])
    return xr.Dataset(
        {
            "pr": (("time", "lat", "lon"), np.full(shape, 1.0), {"units": "mm day-1"}),
            "tas": (("time", "lat", "lon"), np.full(shape, 273.15), {"units": "K"}),
            "par": (("time", "lat", "lon"), np.full(shape, 1.0), {"units": "W m-2"}),
            "ua850": (("time", "lat", "lon"), np.full(shape, 2.0), {"units": "m s-1"}),
            "ps": (("lat", "lon"), np.full((2, 3), 101325.0), {"units": "Pa"}),
            "lsmk": (("lat", "lon"), np.ones((2, 3)), {"units": "1"}),
        },
        coords={
            "time": (
                "time",
                time,
                {"units": "months since 2000-01-01", "calendar": "standard"},
            ),
            "lat": ("lat", lat, {"units": "degrees_north"}),
            "lon": ("lon", lon, {"units": "degrees_east"}),
        },
    )


def _config(path, climate):
    path.write_text(
        f"""
paths_relative_to: config
input:
  climate: {climate.name}
""",
        encoding="utf-8",
    )
    return path


def test_inspect_netcdf_reports_metadata(tmp_path):
    path = tmp_path / "climate.nc"
    _dataset().to_netcdf(path)
    report = inspection.inspect_netcdf(path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["sha256"] == expected
    assert report["variables"]["pr"]["stats"]["max"] == 1.0
    assert report["time"]["size"] == 12
    assert report["time"]["calendar"] == "standard"
    assert report["domain"]["latitude"]["size"] == 2
    assert report["domain"]["longitude"]["last"] == 240.0


def test_inspect_inputs_reports_missing_over_land(tmp_path):
    dataset = _dataset()
    dataset["lsmk"][0, 2] = 0.0
    dataset["tas"][0, 1, 1] = np.nan
    dataset["tas"][0, 0, 2] = np.nan
    path = tmp_path / "climate.nc"
    dataset.to_netcdf(path)
    cfg = _config(tmp_path / "case.yaml", path)
    from pvm2 import config

    report = inspection.inspect_inputs(config.load_config(cfg))
    assert report["ok"] is False
    assert report["fields"]["temperature"]["missing"]["over_land"] == 1
    assert report["fields"]["temperature"]["missing"]["over_ocean"] == 1
    assert any("missing values over land" in issue for issue in report["issues"])


def test_validate_json_cli(tmp_path, capsys):
    path = tmp_path / "climate.nc"
    _dataset().to_netcdf(path)
    cfg = _config(tmp_path / "case.yaml", path)
    code = cli.main(["validate", "--config", str(cfg), "--json"])
    captured = json.loads(capsys.readouterr().out)
    assert code == 0
    assert captured["ok"] is True
    assert captured["fields"]["precipitation"]["missing"]["over_land"] == 0


def test_validate_json_cli_fails_on_missing_land(tmp_path, capsys):
    dataset = _dataset()
    dataset["tas"][0, 0, 0] = np.nan
    path = tmp_path / "climate.nc"
    dataset.to_netcdf(path)
    cfg = _config(tmp_path / "case.yaml", path)
    code = cli.main(["validate", "--config", str(cfg), "--json"])
    captured = json.loads(capsys.readouterr().out)
    assert code == 1
    assert captured["ok"] is False
