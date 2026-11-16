"""Configuration handling for PVM2 runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from .io import legacy_binary, netcdf


DEFAULT_VARIABLES = {
    "precipitation": "pr",
    "temperature": "tas",
    "par": "par",
    "pressure": "ps",
    "landmask": "lsmk",
    "uwind": "ua850",
}

DEFAULT_COORDS = {"latitude": "lat", "longitude": "lon", "time": "time"}


@dataclass
class InputConfig:
    climate: str | None = None
    legacy: dict[str, str] = field(default_factory=dict)
    sources: dict[str, dict] = field(default_factory=dict)
    bbox: tuple[float, float, float, float] | None = None
    shape: tuple[int, int] | None = None
    variables: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VARIABLES))
    coordinates: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COORDS))
    units: dict[str, str] = field(default_factory=dict)
    lon_duplicate: str = "drop_last"
    coordinates_file: str | None = None

    @property
    def is_legacy(self) -> bool:
        return bool(self.legacy)


@dataclass
class ModelConfig:
    co2_pa: float = 35.35
    fire: bool = True
    max_equilibrium_years: int = 20000


@dataclass
class OutputConfig:
    directory: str = "outputs"
    name: str = "pvm2"
    netcdf: bool = True
    geotiff: bool = True
    write_legacy_binary: bool = False
    reference: str | None = None


@dataclass
class RunConfig:
    input: InputConfig = field(default_factory=InputConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def _read_yaml(path):
    if yaml is None:
        raise ImportError("PyYAML is required to read YAML configuration files")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def from_dict(data: dict[str, Any]) -> RunConfig:
    inp = data.get("input", {}) or {}
    model = data.get("model", {}) or {}
    out = data.get("output", {}) or {}

    input_cfg = InputConfig(
        climate=inp.get("climate") or inp.get("file"),
        legacy=dict(inp.get("legacy", {}) or {}),
        sources=dict(inp.get("sources", {}) or {}),
        bbox=tuple(float(value) for value in inp["bbox"]) if inp.get("bbox") else None,
        shape=tuple(inp["shape"]) if inp.get("shape") else None,
        variables={**DEFAULT_VARIABLES, **(inp.get("variables", {}) or {})},
        coordinates={**DEFAULT_COORDS, **(inp.get("coordinates", {}) or {})},
        units=dict(inp.get("units", {}) or {}),
        lon_duplicate=inp.get("lon_duplicate", "drop_last"),
        coordinates_file=inp.get("coordinates_file"),
    )
    model_cfg = ModelConfig(
        co2_pa=float(model.get("co2_pa", 35.35)),
        fire=bool(model.get("fire", True)),
        max_equilibrium_years=int(model.get("max_equilibrium_years", 20000)),
    )
    out_cfg = OutputConfig(
        directory=out.get("directory", out.get("dir", "outputs")),
        name=out.get("name", "pvm2"),
        netcdf=bool(out.get("netcdf", True)),
        geotiff=bool(out.get("geotiff", True)),
        write_legacy_binary=bool(out.get("write_legacy_binary", False)),
        reference=out.get("reference"),
    )
    return RunConfig(input=input_cfg, model=model_cfg, output=out_cfg)


def load_config(path) -> RunConfig:
    return from_dict(_read_yaml(path))


def load_legacy_inputs(cfg: InputConfig):
    if not cfg.shape:
        raise ValueError("input.shape [ny, nx] is required for legacy binaries")
    ny, nx = cfg.shape
    needed = DEFAULT_VARIABLES.keys()
    missing = [key for key in needed if key not in cfg.legacy]
    if missing:
        raise KeyError(f"legacy inputs missing for: {', '.join(missing)}")
    data = {}
    for key, path in cfg.legacy.items():
        if key in ("precipitation", "temperature", "par", "uwind"):
            data[key] = legacy_binary.read_monthly(path, ny, nx)
        elif key in ("pressure", "landmask"):
            data[key] = legacy_binary.read_single(path, ny, nx)
        else:
            raise KeyError(f"unknown legacy variable: {key}")
    lat, lon = _legacy_coordinates(cfg, ny, nx)
    data["lat"] = lat
    data["lon"] = lon
    data["attrs"] = {"source": "legacy direct-access binary"}
    return data


def _legacy_coordinates(cfg, ny, nx):
    if cfg.coordinates_file:
        path = Path(cfg.coordinates_file)
        if not path.exists():
            raise FileNotFoundError(path)
        vals = [float(v) for v in path.read_text(encoding="utf-8").split()]
        if len(vals) != ny:
            raise ValueError(
                f"{path}: expected {ny} latitude values, got {len(vals)}"
            )
        lat = vals
        lon = [i * (360.0 / nx) for i in range(nx)]
        return lat, lon
    lon = [(i + 0.5) * (360.0 / nx) - 0.5 * (360.0 / nx) for i in range(nx)]
    lat = [(j + 0.5) * (180.0 / ny) - 90.0 for j in range(ny)]
    return lat, lon


def load_inputs(cfg: InputConfig):
    if cfg.is_legacy:
        return load_legacy_inputs(cfg)
    if not cfg.climate:
        raise ValueError("either input.climate or input.legacy must be provided")
    return netcdf.load_climate(
        cfg.climate,
        cfg.variables,
        cfg.coordinates,
        cfg.units,
        cfg.lon_duplicate,
    )
