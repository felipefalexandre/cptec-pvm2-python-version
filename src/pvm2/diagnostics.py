"""Installation diagnostics and reference-data checks."""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

from . import __version__, config, grid
from .core import model
from .io import legacy_binary
from .validation import kappa

REQUIRED_MODULES = (
    "numpy",
    "pandas",
    "xarray",
    "netCDF4",
    "h5netcdf",
    "rasterio",
    "yaml",
)
REQUIRED_INPUTS = (
    "prec.bin",
    "temp.bin",
    "ipar.bin",
    "psup.bin",
    "lsmk.bin",
    "uwind.bin",
    "ylat.txt",
)
REFERENCE_MAP = "reference/Lapola_et_al_T062.bin"
REFERENCE_STYLE = "reference/vegetacao_referencia.qml"
EXPECTED_PRESETS = 8


def project_root(start=None) -> Path | None:
    anchors = [Path(start)] if start else [Path.cwd(), Path(__file__).resolve()]
    for anchor in anchors:
        for candidate in [anchor, *anchor.parents]:
            if (candidate / "legacy" / "data" / "SHA256SUMS").exists():
                return candidate
    return None


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(name, status, detail, **data):
    return {"name": name, "status": status, "detail": detail, "data": data}


def check_environment():
    version = sys.version_info
    modules = {}
    problems = []
    for name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(name)
            modules[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            modules[name] = "not installed"
            problems.append(name)
    status = "ok" if version >= (3, 10) and not problems else "fail"
    detail = f"Python {platform.python_version()}"
    if problems:
        detail += f"; missing modules: {', '.join(problems)}"
    return _check(
        "environment",
        status,
        detail,
        python=platform.python_version(),
        platform=platform.platform(),
        modules=modules,
    )


def verify_checksums(root) -> dict:
    root = Path(root)
    sums_path = root / "legacy" / "data" / "SHA256SUMS"
    if not sums_path.exists():
        return {
            "status": "fail",
            "checked": 0,
            "missing": [],
            "mismatched": [],
            "detail": f"missing {sums_path}",
        }
    missing = []
    mismatched = []
    checked = 0
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, relative = line.split(maxsplit=1)
        relative = relative.strip()
        path = root / "legacy" / "data" / relative
        checked += 1
        if not path.exists():
            missing.append(relative)
        elif sha256_file(path) != digest:
            mismatched.append(relative)
    status = "ok" if not missing and not mismatched else "fail"
    problems = []
    if missing:
        problems.append(f"{len(missing)} missing")
    if mismatched:
        problems.append(f"{len(mismatched)} changed")
    detail = f"{checked} files verified"
    if problems:
        detail += " (" + ", ".join(problems) + ")"
    return {
        "status": status,
        "checked": checked,
        "missing": missing,
        "mismatched": mismatched,
        "detail": detail,
    }


def check_data(root):
    root = Path(root)
    data_dir = root / "legacy" / "data"
    missing = [
        name for name in REQUIRED_INPUTS if not (data_dir / "inputs" / name).exists()
    ]
    reference = data_dir / REFERENCE_MAP
    style = data_dir / REFERENCE_STYLE
    if not reference.exists():
        missing.append(REFERENCE_MAP)
    if not style.exists():
        missing.append(REFERENCE_STYLE)
    checksums = verify_checksums(root)
    status = "ok"
    if missing or checksums["status"] != "ok":
        status = "fail"
    detail_parts = [checksums["detail"]]
    if missing:
        detail_parts.insert(0, f"missing: {', '.join(missing)}")
    return _check(
        "data",
        status,
        "; ".join(detail_parts),
        root=str(root),
        missing=missing,
        checksums=checksums,
    )


def check_presets():
    try:
        presets = grid.available_presets()
    except Exception as exc:  # pragma: no cover - defensive
        return _check("landmask_presets", "fail", f"could not load presets: {exc}")
    invalid = []
    for preset in presets:
        lat = np.asarray(preset.lat)
        lon = np.asarray(preset.lon)
        mask = np.asarray(preset.landmask)
        if mask.shape != (lat.size, lon.size):
            invalid.append(preset.name)
            continue
        if not np.all(np.isin(mask, (0, 1))):
            invalid.append(preset.name)
    status = "ok" if len(presets) >= EXPECTED_PRESETS and not invalid else "fail"
    detail = f"{len(presets)} presets loaded"
    if invalid:
        detail += f"; invalid: {', '.join(invalid)}"
    return _check(
        "landmask_presets",
        status,
        detail,
        count=len(presets),
        invalid=invalid,
    )


def check_reference_config(root):
    root = Path(root)
    path = root / "experiments" / "original" / "original.yaml"
    if not path.exists():
        return _check("reference_config", "fail", f"missing {path}")
    try:
        cfg = config.load_config(path)
    except Exception as exc:
        return _check("reference_config", "fail", f"{path}: {exc}")
    missing = []
    for key, value in cfg.input.legacy.items():
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            missing.append(f"input.legacy.{key}")
    if cfg.output.reference:
        candidate = Path(cfg.output.reference)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            missing.append("output.reference")
    status = "ok" if not missing else "fail"
    detail = str(path)
    if missing:
        detail += f"; missing: {', '.join(missing)}"
    return _check(
        "reference_config",
        status,
        detail,
        path=str(path),
        missing=missing,
    )


def run_reference(root, min_kappa=None):
    root = Path(root)
    path = root / "experiments" / "original" / "original.yaml"
    try:
        cfg = config.load_config(path)
        data = config.load_inputs(cfg.input)
        results = model.run(
            data,
            co2_pa=cfg.model.co2_pa,
            fire=cfg.model.fire,
            max_equilibrium_years=cfg.model.max_equilibrium_years,
        )
        observed = legacy_binary.read_single(
            root / cfg.output.reference,
            *data["landmask"].shape,
        )
        metrics = kappa.kappa(observed, results["bpot"])
    except Exception as exc:
        return _check("reference_run", "fail", f"{type(exc).__name__}: {exc}")
    status = "ok"
    if min_kappa is not None and metrics["kappa"] < min_kappa:
        status = "fail"
    detail = (
        f"kappa={metrics['kappa']:.4f}, "
        f"agreement={metrics['agreement_percent']:.2f}%, "
        f"years={results['equilibrium_years']}"
    )
    if status == "fail":
        detail += f"; required kappa >= {min_kappa:.4f}"
    return _check(
        "reference_run",
        status,
        detail,
        kappa=metrics["kappa"],
        agreement_percent=metrics["agreement_percent"],
        equilibrium_years=results["equilibrium_years"],
        min_kappa=min_kappa,
    )


def doctor(root=None, full=False, min_kappa=0.50) -> dict:
    root_path = project_root(root)
    checks = [check_environment()]
    if root_path is None:
        checks.append(
            _check(
                "data",
                "warn",
                "legacy/data/SHA256SUMS not found; data checks skipped",
            )
        )
    else:
        checks.append(check_data(root_path))
        checks.append(check_reference_config(root_path))
    checks.append(check_presets())
    if full:
        if root_path is None:
            checks.append(
                _check(
                    "reference_run",
                    "fail",
                    "reference experiment requires the repository data",
                )
            )
        else:
            checks.append(run_reference(root_path, min_kappa=min_kappa))
    ok = all(item["status"] != "fail" for item in checks)
    return {
        "ok": ok,
        "version": __version__,
        "root": str(root_path) if root_path else None,
        "full": bool(full),
        "checks": checks,
    }


def format_report(report) -> str:
    lines = []
    for item in report["checks"]:
        lines.append(f"{item['status'].upper():4s} {item['name']}: {item['detail']}")
    return "\n".join(lines)


def json_report(report) -> str:
    return json.dumps(report, indent=2, default=str)
