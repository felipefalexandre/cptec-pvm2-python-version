import hashlib
import json

import numpy as np

from pvm2 import cli, config, provenance


def test_file_fingerprint_matches_sha256(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"pvm2")
    result = provenance.file_fingerprint(path)
    assert result["bytes"] == 4
    assert result["sha256"] == hashlib.sha256(b"pvm2").hexdigest()


def test_build_manifest_contains_config_and_input_hashes(tmp_path):
    source = tmp_path / "climate.nc"
    source.write_bytes(b"climate")
    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(
        f"input:\n  climate: {source.as_posix()}\n",
        encoding="utf-8",
    )
    cfg = config.load_config(cfg_path)
    data = {
        "landmask": np.ones((2, 3)),
        "attrs": {"temperature": {"units": "degC"}},
    }
    results = {"equilibrium_years": 7}
    manifest = provenance.build_manifest(
        cfg,
        data=data,
        results=results,
        elapsed=1.25,
        directory=tmp_path / "out",
        run_id="case",
        artifacts={"netcdf": provenance.file_fingerprint(source)},
        command=["pvm2", "run"],
        preparation={"resolution_degrees": 2.0},
    )
    assert manifest["schema_version"] == 2
    assert manifest["run_id"] == "case"
    assert manifest["grid"] == {"shape": [2, 3], "land_cells": 6}
    assert manifest["config_file"]["sha256"] == hashlib.sha256(
        cfg_path.read_bytes()
    ).hexdigest()
    assert manifest["inputs"][0]["sha256"] == hashlib.sha256(b"climate").hexdigest()
    assert manifest["artifacts"]["netcdf"]["sha256"]
    assert manifest["preparation"]["resolution_degrees"] == 2.0


def test_write_manifest_is_atomic_json(tmp_path):
    path = tmp_path / "run" / "run_manifest.json"
    provenance.write_manifest(path, {"ok": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert not path.with_name("run_manifest.json.tmp").exists()


def test_output_paths_accepts_named_run_directory(tmp_path):
    cfg = config.RunConfig()
    cfg.output.directory = str(tmp_path)
    cfg.output.run_id = "case"
    directory, nc_path, run_id = cli._output_paths(cfg)
    assert directory == tmp_path / "case"
    assert nc_path.name == "pvm2.nc"
    assert run_id == "case"


def test_output_paths_creates_timestamped_run_directory(tmp_path):
    cfg = config.RunConfig()
    cfg.output.directory = str(tmp_path)
    cfg.output.run_directory = True
    directory, _, run_id = cli._output_paths(cfg)
    assert directory.parent == tmp_path
    assert directory.name == run_id
    assert run_id.startswith("run-")
