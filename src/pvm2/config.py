"""Configuration handling for PVM2 runs."""

from __future__ import annotations

import dataclasses
import math
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

TOP_KEYS = {"input", "model", "output", "paths_relative_to", "metadata"}
INPUT_KEYS = {
    "climate",
    "file",
    "legacy",
    "sources",
    "bbox",
    "shape",
    "variables",
    "coordinates",
    "units",
    "lon_duplicate",
    "coordinates_file",
}
MODEL_KEYS = {"co2_pa", "fire", "max_equilibrium_years"}
OUTPUT_KEYS = {
    "directory",
    "dir",
    "name",
    "netcdf",
    "geotiff",
    "write_legacy_binary",
    "reference",
    "run_directory",
    "run_id",
}
SOURCE_KEYS = {
    "path",
    "file",
    "variable",
    "units",
    "coordinates",
    "lon_duplicate",
}
PATH_MODES = ("cwd", "config")
LON_DUPLICATE_MODES = ("drop_last", "keep")


class ConfigError(ValueError):
    """Invalid configuration with the offending key path."""


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
    run_directory: bool = False
    run_id: str | None = None


@dataclass
class RunConfig:
    input: InputConfig = field(default_factory=InputConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    source: str | None = None
    relative_to: str = "cwd"
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _fail(path, message):
    raise ConfigError(f"{path}: {message}")


def _mapping(value, path):
    if value is None:
        return {}
    if not isinstance(value, dict):
        _fail(path, "must be a mapping")
    return dict(value)


def _check_keys(value, allowed, path, warnings, strict):
    unknown = sorted(set(value) - set(allowed))
    if not unknown:
        return
    message = f"{path}: unknown key(s): {', '.join(unknown)}"
    if strict:
        raise ConfigError(message)
    warnings.append(message)


def _as_bool(value, path):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in ("true", "yes", "on", "1"):
            return True
        if key in ("false", "no", "off", "0"):
            return False
    _fail(path, f"expected a boolean, got {value!r}")


def _as_float(value, path):
    number = None
    if isinstance(value, bool):
        _fail(path, f"expected a number, got {value!r}")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            pass
    if number is None or not math.isfinite(number):
        _fail(path, f"expected a finite number, got {value!r}")
    return number


def _as_int(value, path):
    if isinstance(value, bool):
        _fail(path, f"expected an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _fail(path, f"expected an integer, got {value!r}")


def _as_str(value, path):
    if not isinstance(value, str) or not value.strip():
        _fail(path, f"expected a non-empty string, got {value!r}")
    return value.strip()


def _as_run_id(value, path):
    text = _as_str(value, path)
    candidate = Path(text)
    if text in (".", "..") or candidate.is_absolute() or candidate.name != text:
        _fail(path, "must be a single directory name")
    return text


def _as_path(value, path, base_dir):
    text = _as_str(value, path)
    if base_dir is None:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        return str(candidate)
    return str((base_dir / candidate).resolve())


def _string_mapping(value, allowed, path, warnings, strict):
    raw = _mapping(value, path)
    _check_keys(raw, allowed, path, warnings, strict)
    result = {}
    for key, item in raw.items():
        if key in allowed:
            result[key] = _as_str(item, f"{path}.{key}")
    return result


def _parse_shape(value, path):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _fail(path, "expected [ny, nx]")
    ny = _as_int(value[0], f"{path}[0]")
    nx = _as_int(value[1], f"{path}[1]")
    if ny <= 0 or nx <= 0:
        _fail(path, "dimensions must be positive")
    return (ny, nx)


def _parse_bbox(value, path):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        _fail(path, "expected [lat_min, lat_max, lon_min, lon_max]")
    values = tuple(_as_float(item, f"{path}[{index}]") for index, item in enumerate(value))
    if values[0] >= values[1]:
        _fail(path, "lat_min must be smaller than lat_max")
    return values


def _parse_source(spec, path, base_dir, warnings, strict):
    if isinstance(spec, str):
        return {"path": _as_path(spec, path, base_dir)}
    raw = _mapping(spec, path)
    _check_keys(raw, SOURCE_KEYS, path, warnings, strict)
    if not any(key in raw for key in ("path", "file")):
        _fail(path, "missing path")
    result = {}
    for key, value in raw.items():
        if key in ("path", "file"):
            result[key] = _as_path(value, f"{path}.{key}", base_dir)
        elif key == "coordinates":
            result[key] = _mapping(value, f"{path}.{key}")
        elif key == "lon_duplicate":
            result[key] = _as_choice(
                value,
                LON_DUPLICATE_MODES,
                f"{path}.{key}",
            )
        else:
            result[key] = _as_str(value, f"{path}.{key}")
    return result


def _as_choice(value, choices, path):
    text = _as_str(value, path)
    if text not in choices:
        _fail(path, f"expected one of {', '.join(choices)}, got {text!r}")
    return text


def from_dict(
    data: dict[str, Any],
    *,
    strict: bool = True,
    source=None,
    base_dir=None,
    relative_to=None,
) -> RunConfig:
    raw = _mapping(data, "config")
    warnings = []
    _check_keys(raw, TOP_KEYS, "config", warnings, strict)

    mode = relative_to or raw.get("paths_relative_to", "cwd")
    mode = _as_choice(mode, PATH_MODES, "paths_relative_to")
    if mode == "config" and base_dir is None:
        _fail(
            "paths_relative_to",
            "config mode requires load_config() or an explicit base directory",
        )
    path_base = Path(base_dir) if mode == "config" else None

    inp = _mapping(raw.get("input", {}), "input")
    _check_keys(inp, INPUT_KEYS, "input", warnings, strict)
    if "file" in inp and "climate" not in inp:
        warnings.append("input.file is an alias for input.climate")
    if "file" in inp and "climate" in inp:
        warnings.append("input.climate takes precedence over input.file")

    shape = (
        _parse_shape(inp["shape"], "input.shape")
        if inp.get("shape") is not None
        else None
    )
    legacy_raw = _mapping(inp.get("legacy", {}), "input.legacy")
    _check_keys(
        legacy_raw,
        DEFAULT_VARIABLES.keys(),
        "input.legacy",
        warnings,
        strict,
    )
    legacy = {
        key: _as_path(value, f"input.legacy.{key}", path_base)
        for key, value in legacy_raw.items()
    }
    if legacy and shape is None:
        _fail("input.shape", "required when input.legacy is used")

    sources_raw = _mapping(inp.get("sources", {}), "input.sources")
    _check_keys(
        sources_raw,
        set(DEFAULT_VARIABLES) | {"landmask"},
        "input.sources",
        warnings,
        strict,
    )
    sources = {
        key: _parse_source(
            value,
            f"input.sources.{key}",
            path_base,
            warnings,
            strict,
        )
        for key, value in sources_raw.items()
    }

    climate = inp.get("climate", inp.get("file"))
    climate = _as_path(climate, "input.climate", path_base) if climate else None
    if not climate and not legacy and not sources:
        _fail(
            "input",
            "provide input.climate, input.legacy or input.sources",
        )
    if climate and legacy:
        warnings.append("both input.climate and input.legacy are set; legacy wins")

    coordinates_file = inp.get("coordinates_file")
    coordinates_file = (
        _as_path(coordinates_file, "input.coordinates_file", path_base)
        if coordinates_file
        else None
    )

    input_cfg = InputConfig(
        climate=climate,
        legacy=legacy,
        sources=sources,
        bbox=(
            _parse_bbox(inp["bbox"], "input.bbox")
            if inp.get("bbox") is not None
            else None
        ),
        shape=shape,
        variables=_string_mapping(
            inp.get("variables", {}),
            DEFAULT_VARIABLES.keys(),
            "input.variables",
            warnings,
            strict,
        ),
        coordinates=_string_mapping(
            inp.get("coordinates", {}),
            DEFAULT_COORDS.keys(),
            "input.coordinates",
            warnings,
            strict,
        ),
        units=_string_mapping(
            inp.get("units", {}),
            DEFAULT_VARIABLES.keys(),
            "input.units",
            warnings,
            strict,
        ),
        lon_duplicate=_as_choice(
            inp.get("lon_duplicate", "drop_last"),
            LON_DUPLICATE_MODES,
            "input.lon_duplicate",
        ),
        coordinates_file=coordinates_file,
    )
    input_cfg.variables = {**DEFAULT_VARIABLES, **input_cfg.variables}
    input_cfg.coordinates = {**DEFAULT_COORDS, **input_cfg.coordinates}

    model = _mapping(raw.get("model", {}), "model")
    _check_keys(model, MODEL_KEYS, "model", warnings, strict)
    co2_pa = _as_float(model.get("co2_pa", 35.35), "model.co2_pa")
    if co2_pa <= 0:
        _fail("model.co2_pa", "must be positive")
    max_years = _as_int(
        model.get("max_equilibrium_years", 20000),
        "model.max_equilibrium_years",
    )
    if max_years <= 0:
        _fail("model.max_equilibrium_years", "must be positive")
    model_cfg = ModelConfig(
        co2_pa=co2_pa,
        fire=_as_bool(model.get("fire", True), "model.fire"),
        max_equilibrium_years=max_years,
    )

    out = _mapping(raw.get("output", {}), "output")
    _check_keys(out, OUTPUT_KEYS, "output", warnings, strict)
    if "dir" in out and "directory" not in out:
        warnings.append("output.dir is an alias for output.directory")
    directory = out.get("directory", out.get("dir", "outputs"))
    reference = out.get("reference")
    run_id = out.get("run_id")
    out_cfg = OutputConfig(
        directory=_as_path(directory, "output.directory", path_base),
        name=_as_str(out.get("name", "pvm2"), "output.name"),
        netcdf=_as_bool(out.get("netcdf", True), "output.netcdf"),
        geotiff=_as_bool(out.get("geotiff", True), "output.geotiff"),
        write_legacy_binary=_as_bool(
            out.get("write_legacy_binary", False),
            "output.write_legacy_binary",
        ),
        reference=(
            _as_path(reference, "output.reference", path_base)
            if reference
            else None
        ),
        run_directory=_as_bool(
            out.get("run_directory", False),
            "output.run_directory",
        ),
        run_id=_as_run_id(run_id, "output.run_id") if run_id is not None else None,
    )

    return RunConfig(
        input=input_cfg,
        model=model_cfg,
        output=out_cfg,
        source=str(source) if source else None,
        relative_to=mode,
        warnings=warnings,
        metadata=_mapping(raw.get("metadata", {}), "metadata"),
    )


def _read_yaml(path):
    if yaml is None:
        raise ImportError("PyYAML is required to read YAML configuration files")
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc


def _deep_merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _overrides(assignments):
    result = {}
    for item in assignments or ():
        if "=" not in item:
            raise ConfigError(f"--set expects key=value, got {item!r}")
        key, text = item.split("=", 1)
        parts = [part for part in key.strip().split(".") if part]
        if not parts:
            raise ConfigError(f"--set expects a non-empty key, got {item!r}")
        try:
            value = yaml.safe_load(text) if yaml is not None else text
        except yaml.YAMLError as exc:
            raise ConfigError(f"--set {key}: invalid value {text!r}") from exc
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result


def load_config(path, relative_to=None, overrides=None, strict=True) -> RunConfig:
    path = Path(path)
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level YAML value must be a mapping")
    if overrides:
        raw = _deep_merge(raw, _overrides(overrides))
    return from_dict(
        raw,
        strict=strict,
        source=path,
        base_dir=path.resolve().parent,
        relative_to=relative_to,
    )


def resolve_paths(cfg: RunConfig, base_dir) -> RunConfig:
    base = Path(base_dir)

    def absolute(value):
        if value is None:
            return None
        candidate = Path(value)
        if candidate.is_absolute():
            return str(candidate)
        return str((base / candidate).resolve())

    cfg.input.climate = absolute(cfg.input.climate)
    cfg.input.coordinates_file = absolute(cfg.input.coordinates_file)
    cfg.input.legacy = {
        key: absolute(value) for key, value in cfg.input.legacy.items()
    }
    for key, spec in cfg.input.sources.items():
        if isinstance(spec, dict):
            for field_name in ("path", "file"):
                if field_name in spec:
                    spec[field_name] = absolute(spec[field_name])
        else:
            cfg.input.sources[key] = absolute(spec)
    cfg.output.directory = absolute(cfg.output.directory)
    cfg.output.reference = absolute(cfg.output.reference)
    cfg.relative_to = "config"
    return cfg


def as_dict(cfg: RunConfig) -> dict:
    data = dataclasses.asdict(cfg)
    for key in ("warnings", "source", "relative_to"):
        data.pop(key, None)
    return data


def as_yaml(cfg: RunConfig) -> str:
    if yaml is None:
        raise ImportError("PyYAML is required to render YAML configuration")
    return yaml.safe_dump(as_dict(cfg), sort_keys=False)


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
