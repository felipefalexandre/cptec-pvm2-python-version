from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from pvm2 import config, prepare


def _write(path, name, value, lat, lon, units, monthly=True):
    if monthly:
        data = np.full((12, lat.size, lon.size), value, dtype=np.float32)
        ds = xr.Dataset(
            {name: (("time", "lat", "lon"), data, {"units": units})},
            coords={"time": np.arange(1, 13), "lat": lat, "lon": lon},
        )
    else:
        data = np.full((lat.size, lon.size), value, dtype=np.float32)
        ds = xr.Dataset(
            {name: (("lat", "lon"), data, {"units": units})},
            coords={"lat": lat, "lon": lon},
        )
    ds.to_netcdf(path)


def _case(root, temperature=20.0, temperature_units="degC", pr_lon_0_360=False, lon_start=0.0):
    lat_half = np.arange(-29.75, 30.0, 0.5)
    lon_half = np.arange(0.25, 60.0, 0.5)
    lat_one = np.arange(-29.5, 30.0, 1.0)
    lon_one = np.arange(0.5, 60.0, 1.0)
    lat_two = np.arange(-29.0, 29.0, 2.0)
    lon_two = np.arange(1.0, 59.5, 2.0)
    lon_half = lon_half + lon_start
    lon_one = lon_one + lon_start
    lon_two = lon_two + lon_start
    if pr_lon_0_360:
        lon_half = lon_half % 360.0
    paths = {
        "precipitation": root / "pr.nc",
        "temperature": root / "tas.nc",
        "par": root / "par.nc",
        "pressure": root / "ps.nc",
        "uwind": root / "ua.nc",
    }
    _write(paths["precipitation"], "pr", 100.0, lat_half, lon_half, "mm/month")
    _write(
        paths["temperature"],
        "tas",
        temperature,
        lat_one,
        lon_one,
        temperature_units,
    )
    _write(paths["par"], "par", 100.0, lat_two, lon_two, "W m-2")
    _write(paths["pressure"], "ps", 1010.0, lat_half, lon_half, "hPa", False)
    _write(paths["uwind"], "ua850", 3.0, lat_one, lon_one, "m s-1")
    sources = {
        key: {"path": str(path)}
        for key, path in paths.items()
    }
    return config.InputConfig(sources=sources), paths


def test_prepare_heterogeneous_sources_uses_coarsest_grid(tmp_path):
    cfg, _ = _case(tmp_path, pr_lon_0_360=True)
    plan = prepare.make_plan(cfg, target=2.0)
    assert plan.coarsest == pytest.approx(2.0)
    assert [item.resolution for item in plan.options] == [10.0, 5.0, 2.5, 2.0]
    assert plan.selected.resolution == 2.0

    data, _ = prepare.execute(plan)
    shape = data["landmask"].shape
    assert data["precipitation"].shape == (12,) + shape
    assert data["temperature"].shape == (12,) + shape
    assert data["pressure"].shape == shape
    assert np.allclose(data["precipitation"], 100.0)
    assert np.allclose(data["temperature"], 20.0)
    assert set(np.unique(data["landmask"])) <= {0.0, 1.0}
    assert data["lon"].min() >= -180.0
    assert data["lon"].max() < 180.0


def test_prepare_selects_recommended_by_default(tmp_path):
    cfg, _ = _case(tmp_path)
    plan = prepare.make_plan(cfg)
    output = []
    selected = prepare.select_target(
        plan, input_fn=lambda prompt: "", output_fn=output.append
    )
    assert selected.resolution == plan.recommended.resolution
    assert selected.resolution == 2.0
    assert any("recommended" in line for line in output)


def test_prepare_selects_coarsest_when_asked(tmp_path):
    cfg, _ = _case(tmp_path)
    plan = prepare.make_plan(cfg)
    selected = prepare.select_target(
        plan, input_fn=lambda prompt: "1", output_fn=lambda line: None
    )
    assert selected.resolution == 10.0


def test_prepare_rejects_target_finer_than_inputs(tmp_path):
    cfg, _ = _case(tmp_path)
    with pytest.raises(ValueError, match="not compatible"):
        prepare.make_plan(cfg, target=0.5)


def test_prepare_uses_finer_custom_landmask_to_refine_target(tmp_path):
    cfg, _ = _case(tmp_path)
    lat = np.arange(-29.5, 30.0, 1.0)
    lon = np.arange(0.5, 60.0, 1.0)
    lsmk = tmp_path / "lsmk.nc"
    _write(lsmk, "lsmk", 1.0, lat, lon, "1", monthly=False)
    plan = prepare.make_plan(cfg, custom_landmask=str(lsmk), target=2.0)
    assert plan.warnings
    assert any("aggregated" in item for item in plan.warnings)
    assert all(item.source != "custom" for item in plan.options)
    assert all(item.resolution >= plan.coarsest for item in plan.options)
    data, _ = prepare.execute(plan)
    assert data["landmask"].shape == data["pressure"].shape
    assert set(np.unique(data["landmask"])) <= {0.0, 1.0}
    assert "landmask_refinement" in data["attrs"]


def test_prepare_rejects_temperature_in_kelvin_with_degc_units(tmp_path):
    cfg, _ = _case(tmp_path, temperature=273.15, temperature_units="degC")
    plan = prepare.make_plan(cfg, target=2.0)
    with pytest.raises(ValueError, match="temperature"):
        prepare.execute(plan)

def test_prepare_global_source_uses_0_360_and_outputs_180_convention(tmp_path):
    lat = np.arange(-89.0, 90.0, 2.0)
    lon = np.arange(0.0, 360.0, 2.0)
    specs = {}
    for key, name, value, units, monthly in (
        ("precipitation", "pr", 80.0, "mm/month", True),
        ("temperature", "tas", 20.0, "degC", True),
        ("par", "par", 100.0, "W m-2", True),
        ("pressure", "ps", 1010.0, "hPa", False),
        ("uwind", "ua850", 3.0, "m s-1", True),
    ):
        path = tmp_path / f"{key}.nc"
        _write(path, name, value, lat, lon, units, monthly)
        specs[key] = {"path": str(path)}
    data, _ = prepare.execute(
        prepare.make_plan(config.InputConfig(sources=specs), target=2.0)
    )
    assert data["landmask"].shape == (90, 180)
    assert data["lon"].min() == pytest.approx(-179.0)
    assert data["lon"].max() == pytest.approx(179.0)
    assert np.allclose(data["precipitation"], 80.0)

def test_prepare_regional_0_360_inputs_are_cropped_consistently(tmp_path):
    cfg, _ = _case(tmp_path, lon_start=300.0)
    plan = prepare.make_plan(cfg, target=2.0)
    assert plan.bounds["lon_min"] == pytest.approx(-60.0)
    assert plan.bounds["lon_max"] == pytest.approx(0.0)
    assert any("regional input domains" in item for item in plan.warnings)
    data, info = prepare.execute(plan)
    assert data["landmask"].shape == (29, 30)
    assert data["lat"].min() == pytest.approx(-29.0)
    assert data["lat"].max() == pytest.approx(27.0)
    assert data["lon"].min() == pytest.approx(-59.0)
    assert data["lon"].max() == pytest.approx(-1.0)
    assert np.allclose(data["precipitation"], 100.0)
    assert data["attrs"]["cropped"] is True


def test_prepare_bbox_crops_global_inputs_without_changing_resolution(tmp_path):
    lat = np.arange(-89.0, 90.0, 2.0)
    lon = np.arange(0.0, 360.0, 2.0)
    specs = {}
    for key, name, value, units, monthly in (
        ("precipitation", "pr", 80.0, "mm/month", True),
        ("temperature", "tas", 20.0, "degC", True),
        ("par", "par", 100.0, "W m-2", True),
        ("pressure", "ps", 1010.0, "hPa", False),
        ("uwind", "ua850", 3.0, "m s-1", True),
    ):
        path = tmp_path / f"{key}.nc"
        _write(path, name, value, lat, lon, units, monthly)
        specs[key] = {"path": str(path)}
    cfg = config.InputConfig(sources=specs, bbox=(-10, 10, 20, 40))
    plan = prepare.make_plan(cfg, target=2.0)
    assert plan.selected.resolution == 2.0
    data, info = prepare.execute(plan)
    assert data["landmask"].shape == (10, 10)
    assert data["lat"].min() == pytest.approx(-9.0)
    assert data["lat"].max() == pytest.approx(9.0)
    assert data["lon"].min() == pytest.approx(21.0)
    assert data["lon"].max() == pytest.approx(39.0)
    assert info["bounds"]["lon_min"] == pytest.approx(20.0)
    assert data["attrs"]["cropped"] is True
