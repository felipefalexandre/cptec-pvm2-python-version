from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from pvm2 import config
from pvm2.core import model
from pvm2.io import legacy_binary, netcdf, raster
from pvm2.validation import kappa

from helpers import requires_legacy_data, synthetic_inputs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tiny_results():
    data = synthetic_inputs(10, 12)
    return data, model.run(data, co2_pa=35.35, fire=True)


@pytest.fixture(scope="module")
def original_results():
    cfg = config.load_config(ROOT / "experiments" / "original" / "original.yaml")
    data = config.load_inputs(cfg.input)
    results = model.run(
        data,
        co2_pa=cfg.model.co2_pa,
        fire=cfg.model.fire,
        max_equilibrium_years=cfg.model.max_equilibrium_years,
    )
    return results


def test_output_shapes_follow_input_grid(tiny_results):
    data, results = tiny_results
    ny, nx = data["landmask"].shape
    assert results["bpot"].shape == (ny, nx)
    for name in ("tmin", "meanpp", "seanpp", "seai", "weti", "bpot", "ratioNPP"):
        assert results[name].shape == (ny, nx)
    for name in ("wsoil", "gsoil", "mnpp", "photo", "aresp", "wsoil2"):
        assert results[name].shape == (12, ny, nx)


def test_grid_resolution_independence():
    for ny, nx in ((8, 10), (16, 24)):
        data = synthetic_inputs(ny, nx)
        results = model.run(data, co2_pa=51.5375, fire=False)
        assert results["bpot"].shape == (ny, nx)
        assert results["wsoil"].shape == (12, ny, nx)
        assert np.all(np.isfinite(results["bpot"]))


def test_netcdf_roundtrip(tiny_results, tmp_path):
    data, results = tiny_results
    path = tmp_path / "out.nc"
    netcdf.write_outputs(
        path, results, np.asarray(data["lat"]), np.asarray(data["lon"])
    )
    ds = xr.open_dataset(path)
    assert int(ds.sizes["lat"]) == data["landmask"].shape[0]
    assert int(ds.sizes["lon"]) == data["landmask"].shape[1]
    assert np.array_equal(ds["biome"].values.astype(int), results["bpot"].astype(int))
    ds.close()


def test_legacy_bundle_roundtrip(tiny_results, tmp_path):
    _, results = tiny_results
    path = tmp_path / "bundle.bin"
    legacy_binary.write_biome_bundle(
        path,
        {
            "bpot": results["bpot"],
            "npp": results["meanpp"],
            "snpp": results["seanpp"],
            "ratioNPP": results["ratioNPP"],
            "hresp": results["meanhr"],
            "csoil": results["meancs"],
            "d2wm": results["d2wm"],
            "ud2w": results["ud2w"],
            "photo": results["mphoto"],
            "aresp": results["maresp"],
            "seai": results["seai"],
            "weti": results["weti"],
        },
    )
    records = legacy_binary.read_records(path, 12, *results["bpot"].shape)
    assert np.allclose(records[0], results["bpot"], atol=1e-6)


def test_geotiff_regular_grid(tiny_results, tmp_path):
    data, results = tiny_results
    path = tmp_path / "biome.tif"
    raster.write_geotiff(
        path, results["bpot"], np.asarray(data["lat"]), np.asarray(data["lon"])
    )
    assert path.exists() and path.stat().st_size > 0


@requires_legacy_data
def test_original_experiment_matches_fortran(original_results, fortran_bpot_ca350):
    assert original_results["bpot"].shape == (96, 192)
    agree = (
        original_results["bpot"].astype(int) == fortran_bpot_ca350.astype(int)
    ).mean()
    assert agree == 1.0


@requires_legacy_data
def test_original_kappa_reference(original_results):
    observed = legacy_binary.read_single(
        ROOT / "legacy" / "data" / "reference" / "Lapola_et_al_T062.bin", 96, 192
    ).astype(int)
    modelled = original_results["bpot"].astype(int)
    report = kappa.kappa(observed, modelled)
    assert report["kappa"] == pytest.approx(0.5254, abs=0.002)
