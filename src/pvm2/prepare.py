"""Harmonise climate inputs onto a common land-mask grid."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config, grid, ranges
from .io import netcdf


@dataclass
class PreparationPlan:
    sources: dict
    resolutions: dict
    coarsest: float
    options: list[grid.LandmaskPreset]
    selected: grid.LandmaskPreset | None = None
    mask_override: grid.LandmaskPreset | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def recommended(self):
        return self.options[-1]


def _load_source_spec(cfg, key):
    spec = cfg.sources[key]
    if isinstance(spec, str):
        spec = {"path": spec}
    path = spec.get("path") or spec.get("file")
    if not path:
        raise ValueError(f"input.sources.{key}: missing path")
    variable = spec.get("variable", cfg.variables[key])
    units = spec.get("units", cfg.units.get(key))
    coords = {**cfg.coordinates, **(spec.get("coordinates", {}) or {})}
    lon_duplicate = spec.get("lon_duplicate", cfg.lon_duplicate)
    return netcdf.load_field(
        path, key, variable, coords, units, lon_duplicate
    )


def _wrap_loaded(data):
    sources = {}
    for key in grid.CLIMATE_KEYS:
        sources[key] = {
            "values": np.asarray(data[key], dtype=np.float64),
            "lat": np.asarray(data["lat"], dtype=np.float64),
            "lon": np.asarray(data["lon"], dtype=np.float64),
            "attrs": (data.get("attrs", {}) or {}).get(key, {}),
        }
    return sources


def load_sources(cfg: config.InputConfig):
    """Load climate sources, preserving the grid of each variable."""
    custom_landmask = None
    if cfg.sources:
        missing = [key for key in grid.CLIMATE_KEYS if key not in cfg.sources]
        if missing:
            raise KeyError(
                f"input.sources missing variables: {', '.join(missing)}"
            )
        sources = {
            key: _load_source_spec(cfg, key) for key in grid.CLIMATE_KEYS
        }
        if "landmask" in cfg.sources:
            spec = cfg.sources["landmask"]
            if isinstance(spec, str):
                spec = {"path": spec}
            path = spec.get("path") or spec.get("file")
            if not path:
                raise ValueError("input.sources.landmask: missing path")
            custom_landmask = grid.custom_preset(path)
        return sources, custom_landmask

    data = config.load_inputs(cfg)
    return _wrap_loaded(data), custom_landmask


def _source_table(resolutions):
    lines = []
    for key in grid.CLIMATE_KEYS:
        lines.append(f"  {key:14s} {resolutions[key]:.2f} deg")
    return "\n".join(lines)


def _format_options(options):
    lines = []
    for index, option in enumerate(options, start=1):
        marker = "  [recommended]" if index == len(options) else ""
        lines.append(
            f"  {index}) {option.resolution:6.2f} deg  "
            f"{option.description}{marker}"
        )
    return "\n".join(lines)


def select_target(plan: PreparationPlan, input_fn=input, output_fn=print):
    """Ask the user to choose among compatible land-mask grids."""
    output_fn("Input resolutions (largest cell spacing):")
    output_fn(_source_table(plan.resolutions))
    output_fn(
        f"Coarsest climate resolution: {plan.coarsest:.2f} deg. "
        "Climate fields will be bilinearly resampled to the chosen grid; "
        "no climate field is moved to a finer grid."
    )
    output_fn("Compatible land-mask grids (coarsest to finest):")
    output_fn(_format_options(plan.options))
    default = len(plan.options)
    while True:
        answer = input_fn(f"Select target grid 1-{len(plan.options)} [{default}]: ")
        answer = (answer or "").strip()
        if not answer:
            return plan.recommended
        try:
            choice = int(answer)
        except ValueError:
            output_fn("Enter a number from the list.")
            continue
        if 1 <= choice <= len(plan.options):
            return plan.options[choice - 1]
        output_fn(f"Enter a number between 1 and {len(plan.options)}.")


def make_plan(
    cfg: config.InputConfig,
    target: float | None = None,
    custom_landmask: str | None = None,
    presets: list[grid.LandmaskPreset] | None = None,
) -> PreparationPlan:
    sources, config_landmask = load_sources(cfg)
    resolutions = {
        key: grid.source_resolution(source["lat"], source["lon"])
        for key, source in sources.items()
    }
    coarsest = max(resolutions.values())
    warnings = []

    candidates = list(presets) if presets is not None else grid.available_presets()
    custom = None
    if custom_landmask:
        custom = grid.custom_preset(custom_landmask)
    elif config_landmask is not None:
        custom = config_landmask
    mask_override = None
    if custom is not None:
        if custom.resolution + 1.0e-6 < coarsest:
            mask_override = custom
            warnings.append(
                f"landmask {custom.name!r} is at {custom.resolution:.2f} deg, "
                f"finer than the coarsest climate field ({coarsest:.2f} deg); "
                "it will be area-aggregated to the selected grid without "
                "upscaling any climate field"
            )
        else:
            candidates = [
                item
                for item in candidates
                if not np.isclose(item.resolution, custom.resolution)
            ]
            candidates.append(custom)

    options = grid.compatible_presets(coarsest, candidates)
    plan = PreparationPlan(
        sources=sources,
        resolutions=resolutions,
        coarsest=coarsest,
        options=options,
        mask_override=mask_override,
        warnings=warnings,
    )
    if target is not None:
        matches = [
            option
            for option in options
            if np.isclose(option.resolution, target, atol=1.0e-6)
        ]
        if not matches:
            available = ", ".join(f"{item.resolution:g}" for item in options)
            raise ValueError(
                f"target {target:g} deg is not compatible; choose one of: "
                f"{available}"
            )
        plan.selected = matches[0]
    return plan


def interactive_available() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def execute(plan: PreparationPlan):
    if plan.selected is None:
        raise ValueError("no target grid selected")
    for warning in plan.warnings:
        print(f"[pvm2] warning: {warning}", flush=True)
    ranges.check_sources(plan.sources)

    bounds = grid.common_bounds(plan.sources)
    target = grid.crop_preset(plan.selected, bounds)
    if plan.mask_override is not None:
        target = grid.LandmaskPreset(
            name=target.name,
            resolution=target.resolution,
            description=target.description,
            lat=target.lat,
            lon=target.lon,
            landmask=grid.aggregate_mask(
                plan.mask_override, target.lat, target.lon
            ),
            source="custom",
            metadata=dict(plan.mask_override.metadata),
        )
    out = {}
    for key, source in plan.sources.items():
        out[key] = grid.resample_field(
            source["values"],
            source["lat"],
            source["lon"],
            target.lat,
            target.lon,
            periodic_lon=grid._is_global_longitude(source["lon"]),
        )
    out["landmask"] = np.where(target.landmask != 0, 1.0, 0.0)
    out["lat"] = target.lat
    out["lon"] = target.lon
    out["attrs"] = {
        "source": "pvm2 prepare",
        "target_grid": target.name,
        "target_resolution_degrees": target.resolution,
        "coarsest_input_resolution_degrees": plan.coarsest,
        "input_resolutions_degrees": {
            key: round(value, 6) for key, value in plan.resolutions.items()
        },
        "landmask_source": target.metadata.get("source", target.source),
    }
    if plan.mask_override is not None:
        out["attrs"]["landmask_refinement"] = (
            f"aggregated from {plan.mask_override.resolution:g} deg"
        )
    info = {
        "target": target,
        "bounds": bounds,
        "resolutions": plan.resolutions,
        "coarsest": plan.coarsest,
    }
    return out, info
