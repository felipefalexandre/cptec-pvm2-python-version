"""Command line interface for PVM2."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import __version__, config
from .core import model
from .io import legacy_binary, netcdf, raster, vector
from .validation import compare as compare_module
from .validation import kappa as kappa_module
from .validation import report


def _log(message):
    print(f"[pvm2] {message}", flush=True)


def _config_from_args(args):
    if getattr(args, "config", None):
        cfg = config.load_config(args.config)
    else:
        cfg = config.RunConfig()
    if getattr(args, "input", None):
        cfg.input.climate = args.input
    if getattr(args, "output", None):
        cfg.output.directory = args.output
    if getattr(args, "co2", None) is not None:
        cfg.model.co2_pa = args.co2
    if getattr(args, "fire", None) is not None:
        cfg.model.fire = args.fire
    if getattr(args, "max_years", None) is not None:
        cfg.model.max_equilibrium_years = args.max_years
    if getattr(args, "no_geotiff", False):
        cfg.output.geotiff = False
    return cfg


def _legacy_bundle_fields(results):
    return {
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
    }


def _output_paths(cfg):
    directory = Path(cfg.output.directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory, directory / f"{cfg.output.name}.nc"


def _run_and_write(cfg):
    _log("loading inputs")
    data = config.load_inputs(cfg.input)
    ny, nx = data["landmask"].shape
    _log(f"grid {ny} x {nx}; CO2 = {cfg.model.co2_pa} Pa; fire = {cfg.model.fire}")
    started = time.perf_counter()
    results = model.run(
        data,
        co2_pa=cfg.model.co2_pa,
        fire=cfg.model.fire,
        max_equilibrium_years=cfg.model.max_equilibrium_years,
    )
    elapsed = time.perf_counter() - started
    _log(f"model finished in {elapsed:.2f} s; equilibrium years = {results['equilibrium_years']}")

    directory, nc_path = _output_paths(cfg)
    lat = data["lat"]
    lon = data["lon"]
    run_attrs = {
        "co2_pa": cfg.model.co2_pa,
        "fire_parameterisation": cfg.model.fire,
        "equilibrium_years": results["equilibrium_years"],
        "runtime_seconds": f"{elapsed:.3f}",
    }
    if cfg.output.netcdf:
        netcdf.write_outputs(nc_path, results, lat, lon, run_attrs)
        _log(f"wrote {nc_path}")
    if cfg.output.geotiff:
        tif = directory / f"{cfg.output.name}_biome.tif"
        try:
            raster.write_geotiff(tif, results["bpot"], lat, lon)
            _log(f"wrote {tif}")
        except ValueError as exc:
            _log(f"GeoTIFF skipped: {exc}")
    if cfg.output.write_legacy_binary:
        bundle = directory / f"{cfg.output.name}_legacy.bin"
        legacy_binary.write_biome_bundle(bundle, _legacy_bundle_fields(results))
        _log(f"wrote {bundle}")

    manifest = {
        "version": __version__,
        "grid": [ny, nx],
        "co2_pa": cfg.model.co2_pa,
        "fire": cfg.model.fire,
        "equilibrium_years": results["equilibrium_years"],
        "runtime_seconds": elapsed,
        "outputs": str(nc_path),
        "environment": report.environment_info(),
        "input_attrs": data.get("attrs", {}),
    }
    (directory / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return results, data, manifest


def cmd_run(args):
    cfg = _config_from_args(args)
    _run_and_write(cfg)
    return 0


def cmd_reproduce(args):
    cfg = _config_from_args(args)
    results, data, manifest = _run_and_write(cfg)
    if not cfg.output.reference:
        _log("no output.reference configured; skipping kappa comparison")
        return 0
    ny, nx = data["landmask"].shape
    observed = legacy_binary.read_single(cfg.output.reference, ny, nx)
    metrics = kappa_module.kappa(observed, results["bpot"])
    _log(
        "agreement = {:.2f}% | kappa = {:.4f}".format(
            metrics["agreement_percent"], metrics["kappa"]
        )
    )
    path = report.write_validation_report(
        Path("reports") / "scientific_validation.html",
        metrics,
        observed,
        results["bpot"],
        extra={"manifest": manifest, "reference": cfg.output.reference},
    )
    _log(f"wrote {path}")
    return 0


def cmd_convert_legacy(args):
    cfg = config.load_config(args.config)
    if not cfg.input.shape:
        raise ValueError("input.shape is required")
    data = config.load_legacy_inputs(cfg.input)
    directory = Path(cfg.output.directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{cfg.output.name}_inputs.nc"
    netcdf.write_inputs(path, data, attrs={"source": "legacy direct-access binaries"})
    _log(f"wrote {path}")
    return 0


def cmd_validate(args):
    cfg = _config_from_args(args)
    data = config.load_inputs(cfg.input)
    model._prepare(data)
    _log(f"grid {data['landmask'].shape[0]} x {data['landmask'].shape[1]}")
    for key in ("precipitation", "temperature", "par", "pressure", "landmask", "uwind"):
        arr = np.asarray(data[key])
        _log(f"{key:14s} min={np.nanmin(arr):12.4f} max={np.nanmax(arr):12.4f} shape={arr.shape}")
    _log("inputs are valid")
    return 0


def cmd_compare_legacy(args):
    result = compare_module.compare_legacy(args.fortran_dir, args.python)
    for key, check in result["checks"].items():
        if check["max_abs"] is None:
            detail = "no comparable cells"
        else:
            detail = (
                f"n={check['n']:6d} max={check['max_abs']:.3e} "
                f"mean={check['mean_abs']:.3e} atol={check['atol']:.1e}"
            )
        status = "ok" if check["passed"] else "FAIL"
        _log(f"{key:28s} {detail} {status}")
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        _log(f"wrote {path}")
    if result["passed"]:
        _log("all compared fields are within tolerance")
        return 0
    _log("one or more fields differ beyond tolerance")
    return 1


def cmd_info(args):
    if args.input:
        summary = netcdf.summarize(args.input)
        print(json.dumps(summary, indent=2))
    elif args.config:
        cfg = config.load_config(args.config)
        print(json.dumps({"config": args.config, "input": cfg.input.__dict__}, indent=2, default=str))
    else:
        raise SystemExit("provide --input or --config")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pvm2",
        description="CPTEC-PVM2 potential vegetation model (Python implementation)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run PVM2")
    run.add_argument("--input", help="consolidated NetCDF climate file")
    run.add_argument("--output", help="output directory")
    run.add_argument("--config", help="YAML configuration file")
    run.add_argument("--co2", type=float, help="atmospheric CO2 partial pressure (Pa)")
    run.add_argument("--fire", dest="fire", action="store_true", default=None)
    run.add_argument("--no-fire", dest="fire", action="store_false")
    run.add_argument("--max-years", type=int, dest="max_years")
    run.add_argument("--no-geotiff", action="store_true")
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("reproduce", help="run a reference experiment and validate")
    rep.add_argument("--config", required=True)
    rep.add_argument("--output")
    rep.add_argument("--co2", type=float)
    rep.add_argument("--fire", dest="fire", action="store_true", default=None)
    rep.add_argument("--no-fire", dest="fire", action="store_false")
    rep.add_argument("--max-years", type=int, dest="max_years")
    rep.add_argument("--no-geotiff", action="store_true")
    rep.set_defaults(func=cmd_reproduce)

    conv = sub.add_parser("convert-legacy", help="convert legacy binaries to NetCDF")
    conv.add_argument("--config", required=True)
    conv.set_defaults(func=cmd_convert_legacy)

    val = sub.add_parser("validate", help="validate inputs")
    val.add_argument("--input")
    val.add_argument("--config")
    val.set_defaults(func=cmd_validate)

    info = sub.add_parser("info", help="describe a NetCDF or configuration file")
    info.add_argument("--input")
    info.add_argument("--config")
    info.set_defaults(func=cmd_info)

    cmp = sub.add_parser(
        "compare-legacy", help="compare Python fields with legacy Fortran output"
    )
    cmp.add_argument("--fortran-dir", required=True)
    cmp.add_argument("--python", required=True, help="Python result NetCDF file")
    cmp.add_argument("--report", help="optional JSON report path")
    cmp.set_defaults(func=cmd_compare_legacy)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
