from types import SimpleNamespace

import numpy as np
import pytest

from pvm2 import cli, config


def test_pipeline_prepares_then_runs(monkeypatch, tmp_path):
    cfg = config.RunConfig()
    cfg.output.directory = str(tmp_path / "outputs")
    monkeypatch.setattr(cli.config, "load_config", lambda *args, **kwargs: cfg)

    data = {
        "landmask": np.ones((2, 3)),
        "lat": np.array([-1.0, 1.0]),
        "lon": np.array([0.0, 1.0, 2.0]),
        "attrs": {},
    }
    prepared = tmp_path / "prepared.nc"
    prepared.write_bytes(b"prepared")
    plan = SimpleNamespace(
        selected=SimpleNamespace(resolution=2.0, description="test grid"),
        warnings=[],
    )
    calls = []

    monkeypatch.setattr(
        cli,
        "_prepare_data",
        lambda cfg, args, output=None, write=True: (
            data,
            {"bounds": {}},
            prepared,
            plan,
        ),
    )

    def fake_run(cfg, data=None, preparation=None, execution=None):
        calls.append((cfg, data, preparation, execution))

    monkeypatch.setattr(cli, "_run_and_write", fake_run)
    args = SimpleNamespace(
        config=str(tmp_path / "case.yaml"),
        target=2.0,
        bbox=None,
        landmask=None,
        list=False,
        yes=True,
        prepared_output=str(prepared),
        output=str(tmp_path / "outputs"),
        co2=None,
        fire=None,
        max_years=None,
        no_geotiff=False,
        set=None,
        run_dir=False,
        run_id=None,
        tile_cells=None,
        checkpoint=None,
        checkpoint_every=1,
        resume=False,
        dry_run=False,
        quiet=False,
    )
    assert cli.cmd_pipeline(args) == 0
    assert len(calls) == 1
    assert calls[0][1] is data
    assert calls[0][2]["resolution_degrees"] == 2.0
    assert calls[0][2]["prepared_input"]["sha256"]
    assert calls[0][3]["checkpoint_every"] == 1


def test_pipeline_dry_run_skips_write_and_model(monkeypatch, tmp_path):
    cfg = config.RunConfig()
    monkeypatch.setattr(cli.config, "load_config", lambda *args, **kwargs: cfg)
    data = {"landmask": np.ones((2, 3)), "lat": np.array([-1.0, 1.0])}
    prepared = tmp_path / "prepared.nc"
    plan = SimpleNamespace(
        selected=SimpleNamespace(resolution=2.0, description="test grid"),
        warnings=[],
    )
    writes = []
    plans = []
    monkeypatch.setattr(
        cli,
        "_prepare_data",
        lambda cfg, args, output=None, write=True: (
            writes.append(write) or (data, {"bounds": {}}, prepared, plan)
        ),
    )
    monkeypatch.setattr(
        cli,
        "_show_run_plan",
        lambda cfg, data=None, execution=None: plans.append(data),
    )
    monkeypatch.setattr(
        cli,
        "_run_and_write",
        lambda *args, **kwargs: pytest.fail("model should not run"),
    )
    args = SimpleNamespace(
        config=str(tmp_path / "case.yaml"),
        target=2.0,
        bbox=None,
        landmask=None,
        list=False,
        yes=True,
        prepared_output=str(prepared),
        output=str(tmp_path / "outputs"),
        co2=None,
        fire=None,
        max_years=None,
        no_geotiff=False,
        set=None,
        run_dir=False,
        run_id=None,
        tile_cells=None,
        checkpoint=None,
        checkpoint_every=1,
        resume=False,
        dry_run=True,
        quiet=True,
    )
    assert cli.cmd_pipeline(args) == 0
    assert writes == [False]
    assert plans == [data]
