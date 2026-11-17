from pathlib import Path

import pytest

from pvm2 import config

ROOT = Path(__file__).resolve().parents[1]


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_reference_config_is_unchanged():
    cfg = config.load_config(ROOT / "experiments" / "original" / "original.yaml")
    assert cfg.input.shape == (96, 192)
    assert cfg.input.legacy["precipitation"] == "legacy/data/inputs/prec.bin"
    assert cfg.model.co2_pa == 35.35
    assert cfg.model.fire is True
    assert cfg.relative_to == "cwd"


def test_boolean_and_numeric_strings_are_coerced(tmp_path):
    path = _write(
        tmp_path / "case.yaml",
        """
input:
  climate: input.nc
model:
  fire: "false"
  co2_pa: "51.5"
  max_equilibrium_years: "300"
""",
    )
    cfg = config.load_config(path)
    assert cfg.model.fire is False
    assert cfg.model.co2_pa == 51.5
    assert cfg.model.max_equilibrium_years == 300


def test_unknown_key_reports_path(tmp_path):
    path = _write(
        tmp_path / "bad.yaml",
        """
input:
  climate: input.nc
model:
  co2: 40
""",
    )
    with pytest.raises(config.ConfigError, match="model: unknown key"):
        config.load_config(path)


def test_invalid_boolean_is_rejected(tmp_path):
    path = _write(
        tmp_path / "bad.yaml",
        """
input:
  climate: input.nc
model:
  fire: maybe
""",
    )
    with pytest.raises(config.ConfigError, match="model.fire"):
        config.load_config(path)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_non_finite_numbers_are_rejected(tmp_path, value):
    path = _write(
        tmp_path / "bad.yaml",
        f"""
input:
  climate: input.nc
model:
  co2_pa: {value}
""",
    )
    with pytest.raises(config.ConfigError, match="model.co2_pa"):
        config.load_config(path)


def test_top_level_must_be_mapping(tmp_path):
    path = _write(tmp_path / "bad.yaml", "- one\n- two\n")
    with pytest.raises(config.ConfigError, match="top-level"):
        config.load_config(path)


def test_paths_relative_to_config(tmp_path):
    (tmp_path / "data").mkdir()
    path = _write(
        tmp_path / "case.yaml",
        """
paths_relative_to: config
input:
  climate: data/input.nc
output:
  directory: results
""",
    )
    cfg = config.load_config(path)
    assert Path(cfg.input.climate) == (tmp_path / "data" / "input.nc").resolve()
    assert Path(cfg.output.directory) == (tmp_path / "results").resolve()


def test_overrides_are_applied_before_validation(tmp_path):
    path = _write(
        tmp_path / "case.yaml",
        """
input:
  climate: input.nc
model:
  fire: true
""",
    )
    cfg = config.load_config(
        path,
        overrides=["model.fire=false", "model.co2_pa=40.0"],
    )
    assert cfg.model.fire is False
    assert cfg.model.co2_pa == 40.0


def test_rendered_config_can_be_loaded_again(tmp_path):
    source = _write(
        tmp_path / "case.yaml",
        """
input:
  climate: input.nc
model:
  fire: false
metadata:
  experiment: round-trip
""",
    )
    rendered = tmp_path / "rendered.yaml"
    rendered.write_text(config.as_yaml(config.load_config(source)), encoding="utf-8")
    cfg = config.load_config(rendered)
    assert cfg.input.climate == "input.nc"
    assert cfg.model.fire is False
    assert cfg.metadata == {"experiment": "round-trip"}


def test_resolve_paths_handles_sources_and_reference(tmp_path):
    path = _write(
        tmp_path / "case.yaml",
        """
input:
  sources:
    precipitation: data/pr.nc
output:
  reference: ref.bin
""",
    )
    cfg = config.load_config(path)
    config.resolve_paths(cfg, tmp_path)
    assert Path(cfg.input.sources["precipitation"]["path"]).is_absolute()
    assert Path(cfg.output.reference).is_absolute()
    assert cfg.relative_to == "config"
