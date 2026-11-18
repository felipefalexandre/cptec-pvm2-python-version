"""Run the bundled reference experiment and compare it with golden values."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from pvm2 import config


ROOT = Path(__file__).resolve().parents[1]


def _biome_digest(path):
    import xarray as xr

    with xr.open_dataset(path, decode_times=False) as dataset:
        biome = np.asarray(dataset["biome"].values, dtype=np.int16)
    counts = np.bincount(biome.ravel(), minlength=21)
    return (
        hashlib.sha256(biome.tobytes()).hexdigest(),
        {str(index): int(value) for index, value in enumerate(counts) if value},
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument(
        "--config",
        default="experiments/original/original.yaml",
        help="reference configuration relative to --root",
    )
    parser.add_argument(
        "--golden",
        default="experiments/original/golden.json",
        help="golden values relative to --root",
    )
    parser.add_argument("--min-kappa", type=float, default=0.50)
    parser.add_argument("--kappa-tolerance", type=float, default=2.0e-4)
    parser.add_argument("--agreement-tolerance", type=float, default=1.0e-2)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve()
    golden = json.loads((root / args.golden).read_text(encoding="utf-8"))
    cfg = config.load_config(config_path)
    with tempfile.TemporaryDirectory(prefix="pvm2-regression-") as temporary:
        work = Path(temporary)
        output = work / "outputs"
        report = work / "reports" / "scientific_validation.html"
        command = [
            sys.executable,
            "-m",
            "pvm2.cli",
            "reproduce",
            "--config",
            str(config_path),
            "--output",
            str(output),
            "--report",
            str(report),
            "--min-kappa",
            str(args.min_kappa),
        ]
        completed = subprocess.run(command, cwd=root, check=False)
        if completed.returncode != 0:
            print("reference reproduction failed", file=sys.stderr)
            return completed.returncode or 1

        metrics_path = report.with_suffix(".json")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))["metrics"]
        manifest_path = output / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        biome_path = output / f"{cfg.output.name}.nc"
        digest, counts = _biome_digest(biome_path)

    checks = {
        "kappa": abs(metrics["kappa"] - golden["kappa"])
        <= args.kappa_tolerance,
        "agreement_percent": abs(
            metrics["agreement_percent"] - golden["agreement_percent"]
        )
        <= args.agreement_tolerance,
        "equilibrium_years": manifest["equilibrium_years"]
        == golden["equilibrium_years"],
        "land_cells": manifest["grid"]["land_cells"] == golden["land_cells"],
        "biome_sha256": digest == golden["biome_sha256"],
        "biome_counts": counts == golden["biome_counts"],
    }
    for name, passed in checks.items():
        print(f"{'OK  ' if passed else 'FAIL'} {name}")
    print(
        "kappa={:.6f} agreement={:.4f}% years={} land_cells={}".format(
            metrics["kappa"],
            metrics["agreement_percent"],
            manifest["equilibrium_years"],
            manifest["grid"]["land_cells"],
        )
    )
    print(f"biome_sha256={digest}")
    if not all(checks.values()):
        print("golden regression failed", file=sys.stderr)
        return 1
    print("golden regression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
