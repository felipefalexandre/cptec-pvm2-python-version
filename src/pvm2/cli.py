"""Command line interface for PVM2."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import __version__, config, diagnostics, inspection, prepare, provenance
from .core import model
from .io import legacy_binary, netcdf, raster, vector
from .validation import compare as compare_module
from .validation import kappa as kappa_module
from .validation import report


def _log(message):
    print(f"[pvm2] {message}", flush=True)


def _progress_reporter(started, interval=2.0):
    last = [started]

    def report(event):
        if event.get("phase") != "equilibrium":
            return
        land = int(event.get("land_cells", 0))
        active = int(event.get("active_cells", 0))
        if event.get("done"):
            _log(
                f"equilibrium reached after {event['year']} year(s); "
                f"converged {land - active}/{land} land cells"
            )
            return
        if event.get("year", 0) == 0:
            return
        now = time.perf_counter()
        if now - last[0] < interval:
            return
        last[0] = now
        converged = land - active
        percent = 100.0 * converged / land if land else 100.0
        _log(
            f"equilibrium year {event['year']}, month {event['month']:02d}: "
            f"{converged}/{land} cells converged ({percent:.1f}%), "
            f"{now - started:.1f} s"
        )

    return report


def _config_from_args(args):
    overrides = getattr(args, "set", None)
    if getattr(args, "config", None):
        cfg = config.load_config(args.config, overrides=overrides)
    elif overrides:
        raise ValueError("--set requires --config")
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
    if getattr(args, "run_dir", False):
        cfg.output.run_directory = True
    if getattr(args, "run_id", None):
        run_id = args.run_id
        candidate = Path(run_id)
        if (
            run_id in (".", "..")
            or candidate.is_absolute()
            or candidate.name != run_id
        ):
            raise ValueError("--run-id must be a single directory name")
        cfg.output.run_id = run_id
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
    base = Path(cfg.output.directory)
    run_id = cfg.output.run_id
    if run_id is None and cfg.output.run_directory:
        run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    directory = base / run_id if run_id else base
    if run_id and cfg.output.run_id is None:
        candidate = directory
        counter = 1
        while candidate.exists():
            candidate = base / f"{run_id}-{counter}"
            counter += 1
        directory = candidate
        run_id = directory.name
    directory.mkdir(parents=True, exist_ok=True)
    return directory, directory / f"{cfg.output.name}.nc", run_id


def _run_and_write(cfg):
    _log("loading inputs")
    data = config.load_inputs(cfg.input)
    ny, nx = data["landmask"].shape
    land_cells = int(np.count_nonzero(data["landmask"]))
    _log(f"grid {ny} x {nx}; CO2 = {cfg.model.co2_pa} Pa; fire = {cfg.model.fire}")
    _log(f"model started with {land_cells} land cells")
    started = time.perf_counter()
    results = model.run(
        data,
        co2_pa=cfg.model.co2_pa,
        fire=cfg.model.fire,
        max_equilibrium_years=cfg.model.max_equilibrium_years,
        progress=_progress_reporter(started),
    )
    elapsed = time.perf_counter() - started
    _log(f"model finished in {elapsed:.2f} s; equilibrium years = {results['equilibrium_years']}")

    directory, nc_path, run_id = _output_paths(cfg)
    lat = data["lat"]
    lon = data["lon"]
    run_attrs = {
        "co2_pa": cfg.model.co2_pa,
        "fire_parameterisation": cfg.model.fire,
        "equilibrium_years": results["equilibrium_years"],
        "runtime_seconds": f"{elapsed:.3f}",
    }
    artifacts = {}
    if cfg.output.netcdf:
        netcdf.write_outputs(nc_path, results, lat, lon, run_attrs)
        artifacts["netcdf"] = provenance.file_fingerprint(nc_path)
        _log(f"wrote {nc_path}")
    if cfg.output.geotiff:
        tif = directory / f"{cfg.output.name}_biome.tif"
        try:
            raster.write_geotiff(tif, results["bpot"], lat, lon)
            artifacts["geotiff"] = provenance.file_fingerprint(tif)
            _log(f"wrote {tif}")
        except ValueError as exc:
            _log(f"GeoTIFF skipped: {exc}")
    if cfg.output.write_legacy_binary:
        bundle = directory / f"{cfg.output.name}_legacy.bin"
        legacy_binary.write_biome_bundle(bundle, _legacy_bundle_fields(results))
        artifacts["legacy_binary"] = provenance.file_fingerprint(bundle)
        _log(f"wrote {bundle}")

    manifest = provenance.build_manifest(
        cfg,
        data=data,
        results=results,
        elapsed=elapsed,
        directory=directory,
        run_id=run_id,
        artifacts=artifacts,
        command=sys.argv,
    )
    manifest_path = provenance.write_manifest(
        directory / "run_manifest.json",
        manifest,
    )
    _log(f"wrote {manifest_path}")
    return results, data, manifest


def cmd_doctor(args):
    report = diagnostics.doctor(
        root=args.root,
        full=args.full,
        min_kappa=args.min_kappa,
    )
    if args.json:
        print(diagnostics.json_report(report))
    else:
        for line in diagnostics.format_report(report).splitlines():
            _log(line)
        _log("installation OK" if report["ok"] else "installation has failures")
    return 0 if report["ok"] else 1


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
    if cfg.output.geotiff:
        reference_tif = (
            Path(manifest["directory"])
            / f"{cfg.output.name}_reference_biome.tif"
        )
        try:
            raster.write_geotiff(
                reference_tif, observed, data["lat"], data["lon"]
            )
            manifest["artifacts"]["reference_geotiff"] = (
                provenance.file_fingerprint(reference_tif)
            )
            _log(f"wrote {reference_tif}")
        except ValueError as exc:
            _log(f"reference GeoTIFF skipped: {exc}")
    path = report.write_validation_report(
        Path("reports") / "scientific_validation.html",
        metrics,
        observed,
        results["bpot"],
        extra={"manifest": manifest, "reference": cfg.output.reference},
    )
    manifest["artifacts"]["validation_report"] = provenance.file_fingerprint(path)
    provenance.write_manifest(
        Path(manifest["directory"]) / "run_manifest.json",
        manifest,
    )
    _log(f"wrote {path}")
    if args.min_kappa is not None and metrics["kappa"] < args.min_kappa:
        _log(
            "kappa {:.4f} is below the required minimum {:.4f}".format(
                metrics["kappa"], args.min_kappa
            )
        )
        return 1
    return 0


def cmd_convert_legacy(args):
    cfg = config.load_config(args.config, overrides=args.set)
    if not cfg.input.shape:
        raise ValueError("input.shape is required")
    data = config.load_legacy_inputs(cfg.input)
    directory = Path(cfg.output.directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{cfg.output.name}_inputs.nc"
    netcdf.write_inputs(path, data, attrs={"source": "legacy direct-access binaries"})
    _log(f"wrote {path}")
    return 0


def cmd_prepare(args):
    cfg = config.load_config(args.config, overrides=args.set)
    plan = prepare.make_plan(
        cfg.input,
        target=args.target,
        custom_landmask=args.landmask,
        bbox=args.bbox,
    )
    if args.list:
        _log("input resolutions:")
        for line in prepare._source_table(plan.resolutions).splitlines():
            _log(line.strip())
        _log("input domains:")
        for line in prepare._source_domains(plan.regions).splitlines():
            _log(line.strip())
        _log(f"common domain: {prepare._format_bounds(plan.bounds)}")
        _log(f"coarsest climate resolution: {plan.coarsest:.2f} deg")
        for warning in plan.warnings:
            _log(f"warning: {warning}")
        _log("compatible land-mask grids (coarsest to finest):")
        for line in prepare._format_options(plan.options).splitlines():
            _log(line.strip())
        return 0

    if plan.selected is None:
        if args.yes:
            plan.selected = plan.recommended
            _log(
                f"using recommended target grid: "
                f"{plan.selected.resolution:g} deg "
                f"({plan.selected.description})"
            )
        elif not prepare.interactive_available():
            raise ValueError(
                "no target selected; pass --target or --yes for non-interactive use"
            )
        else:
            plan.selected = prepare.select_target(plan, output_fn=_log)
    data, info = prepare.execute(plan)
    model._prepare(data)
    tag = str(plan.selected.resolution).replace(".", "p")
    path = Path(args.output or Path("outputs") / "prepared" / f"pvm2_inputs_{tag}.nc")
    netcdf.write_inputs(path, data, attrs=data.get("attrs"))
    _log(
        f"prepared {data['landmask'].shape[0]} x {data['landmask'].shape[1]} "
        f"grid at {plan.selected.resolution:g} deg "
        f"({prepare._format_bounds(info['bounds'])})"
    )
    _log(f"wrote {path}")
    _log(f"run with: pvm2 run --input {path}")
    return 0


def _write_json_report(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _log(f"wrote {path}")


def cmd_validate(args):
    cfg = _config_from_args(args)
    try:
        report = inspection.inspect_inputs(cfg)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        report = {
            "ok": False,
            "config_file": cfg.source,
            "issues": [str(exc)],
            "fields": {},
        }
    if args.report:
        _write_json_report(args.report, report)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for issue in report["issues"]:
            _log(f"error: {issue}")
        for key, item in report.get("fields", {}).items():
            if item.get("min") is None:
                _log(f"{key:14s} no finite values shape={item.get('shape')}")
            else:
                _log(
                    f"{key:14s} min={item['min']:12.4f} "
                    f"max={item['max']:12.4f} shape={item.get('shape')} "
                    f"missing_land={item['missing']['over_land']}"
                )
        _log("inputs are valid" if report["ok"] else "input validation failed")
    return 0 if report["ok"] else 1


def cmd_inspect(args):
    if args.input:
        report = inspection.inspect_netcdf(args.input)
    else:
        cfg = config.load_config(args.config, overrides=args.set)
        report = inspection.inspect_inputs(cfg)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    if args.input:
        _log(f"{report['path']}  sha256={report['sha256']}")
        for name, item in report["variables"].items():
            stats = item["stats"]
            units = item["attrs"].get("units") or ""
            _log(
                f"{name:14s} dims={','.join(item['dims'])} "
                f"shape={item['shape']} units={units} "
                f"range=[{stats['min']}, {stats['max']}]"
            )
        if report["time"]:
            time = report["time"]
            _log(
                f"time: {time['size']} steps, units={time.get('units')}, "
                f"calendar={time.get('calendar')}"
            )
        for axis, item in report["domain"].items():
            _log(
                f"{axis}: {item['size']} points, "
                f"{item['min']}..{item['max']}, spacing={item['spacing']}"
            )
    else:
        _log(f"{report['config_file']}  sha256={report['config_sha256']}")
        for issue in report["issues"]:
            _log(f"error: {issue}")
        for key, item in report["fields"].items():
            _log(
                f"{key:14s} min={item['min']} max={item['max']} "
                f"missing_land={item['missing']['over_land']}"
            )
        _log("inputs are valid" if report["ok"] else "input validation failed")
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


def cmd_config_check(args):
    cfg = config.load_config(args.config, overrides=args.set)
    report = {
        "ok": True,
        "source": cfg.source,
        "relative_to": cfg.relative_to,
        "warnings": cfg.warnings,
        "config": config.as_dict(cfg),
    }
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _log(f"configuration is valid: {args.config}")
        for warning in cfg.warnings:
            _log(f"warning: {warning}")
    return 0


def cmd_config_show(args):
    cfg = config.load_config(args.config, overrides=args.set)
    if args.resolved:
        config.resolve_paths(cfg, Path.cwd())
    if args.json:
        print(json.dumps(config.as_dict(cfg), indent=2, default=str))
    else:
        print(config.as_yaml(cfg), end="")
    return 0


def cmd_info(args):
    if args.input:
        summary = netcdf.summarize(args.input)
        print(json.dumps(summary, indent=2))
    elif args.config:
        cfg = config.load_config(args.config)
        print(json.dumps(config.as_dict(cfg), indent=2, default=str))
    else:
        raise SystemExit("provide --input or --config")
    return 0


def _add_set(parser):
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a configuration key (repeatable)",
    )


def _add_run_options(parser):
    parser.add_argument(
        "--run-dir",
        action="store_true",
        help="write outputs into a timestamped run subdirectory",
    )
    parser.add_argument(
        "--run-id",
        help="write outputs into a named run subdirectory",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pvm2",
        description="CPTEC-PVM2 potential vegetation model (Python implementation)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    doc = sub.add_parser(
        "doctor",
        help="check the installation, data and reference experiment",
    )
    doc.add_argument("--root", help="repository root containing legacy/data")
    doc.add_argument("--full", action="store_true", help="also run the reference experiment")
    doc.add_argument(
        "--min-kappa",
        type=float,
        default=0.50,
        help="minimum kappa required by --full (default: 0.50)",
    )
    doc.add_argument("--json", action="store_true", help="print a JSON report")
    doc.set_defaults(func=cmd_doctor)

    run = sub.add_parser("run", help="run PVM2")
    run.add_argument("--input", help="consolidated NetCDF climate file")
    run.add_argument("--output", help="output directory")
    run.add_argument("--config", help="YAML configuration file")
    run.add_argument("--co2", type=float, help="atmospheric CO2 partial pressure (Pa)")
    run.add_argument("--fire", dest="fire", action="store_true", default=None)
    run.add_argument("--no-fire", dest="fire", action="store_false")
    run.add_argument("--max-years", type=int, dest="max_years")
    run.add_argument("--no-geotiff", action="store_true")
    _add_set(run)
    _add_run_options(run)
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("reproduce", help="run a reference experiment and validate")
    rep.add_argument("--config", required=True)
    rep.add_argument("--output")
    rep.add_argument("--co2", type=float)
    rep.add_argument("--fire", dest="fire", action="store_true", default=None)
    rep.add_argument("--no-fire", dest="fire", action="store_false")
    rep.add_argument("--max-years", type=int, dest="max_years")
    rep.add_argument("--no-geotiff", action="store_true")
    rep.add_argument(
        "--min-kappa",
        type=float,
        help="fail if the kappa against the reference map is below this value",
    )
    _add_set(rep)
    _add_run_options(rep)
    rep.set_defaults(func=cmd_reproduce)

    prep = sub.add_parser(
        "prepare",
        help="resample heterogeneous inputs onto a common land-mask grid",
    )
    prep.add_argument("--config", required=True)
    prep.add_argument("--target", type=float, help="target resolution in degrees")
    prep.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
        help="crop the common domain to this box (degrees)",
    )
    prep.add_argument("--landmask", help="custom landmask NetCDF file")
    prep.add_argument("--output", help="prepared NetCDF output path")
    prep.add_argument("--list", action="store_true", help="list compatible grids")
    prep.add_argument(
        "--yes",
        action="store_true",
        help="use the recommended target without an interactive prompt",
    )
    _add_set(prep)
    prep.set_defaults(func=cmd_prepare)

    conv = sub.add_parser("convert-legacy", help="convert legacy binaries to NetCDF")
    conv.add_argument("--config", required=True)
    _add_set(conv)
    conv.set_defaults(func=cmd_convert_legacy)

    val = sub.add_parser("validate", help="validate inputs")
    val.add_argument("--input")
    val.add_argument("--config")
    val.add_argument("--json", action="store_true", help="print a JSON report")
    val.add_argument("--report", help="write the JSON report to this path")
    _add_set(val)
    val.set_defaults(func=cmd_validate)

    inspect = sub.add_parser(
        "inspect",
        help="inspect a NetCDF file or a prepared input configuration",
    )
    source = inspect.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="NetCDF file")
    source.add_argument("--config", help="YAML configuration file")
    inspect.add_argument("--json", action="store_true", help="print a JSON report")
    _add_set(inspect)
    inspect.set_defaults(func=cmd_inspect)

    cfg_parser = sub.add_parser("config", help="check or show configuration files")
    cfg_sub = cfg_parser.add_subparsers(dest="config_command", required=True)
    cfg_check = cfg_sub.add_parser("check", help="validate a configuration file")
    cfg_check.add_argument("--config", required=True)
    cfg_check.add_argument("--json", action="store_true")
    _add_set(cfg_check)
    cfg_check.set_defaults(func=cmd_config_check)
    cfg_show = cfg_sub.add_parser("show", help="print a normalized configuration")
    cfg_show.add_argument("--config", required=True)
    cfg_show.add_argument("--json", action="store_true")
    cfg_show.add_argument(
        "--resolved",
        action="store_true",
        help="resolve relative paths against the current directory",
    )
    _add_set(cfg_show)
    cfg_show.set_defaults(func=cmd_config_show)

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
