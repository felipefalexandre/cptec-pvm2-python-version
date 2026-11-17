"""Run provenance helpers: file hashes, git state and manifest writing."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config, inspection
from .validation import report

ROOT = Path(__file__).resolve().parents[2]


def file_fingerprint(path):
    """Return size and SHA-256 for a file, or an error entry."""
    path = Path(path)
    try:
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": inspection.sha256(path),
        }
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}


def git_info(root=None):
    """Return the current commit, branch and working-tree state."""
    root = Path(root or ROOT)
    commands = {
        "commit": ("rev-parse", "HEAD"),
        "branch": ("rev-parse", "--abbrev-ref", "HEAD"),
        "status": ("status", "--porcelain"),
    }
    result = {}
    for key, command in commands.items():
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *command],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            result["available"] = False
            result["error"] = str(exc)
            return result
        if completed.returncode != 0:
            result["available"] = False
            result["error"] = completed.stderr.strip() or "git command failed"
            return result
        result[key] = completed.stdout.strip()
    status = result["status"]
    result["status"] = [line for line in status.splitlines() if line]
    result["dirty"] = bool(result["status"])
    result["available"] = True
    return result


def build_manifest(
    cfg,
    *,
    data,
    results,
    elapsed,
    directory,
    run_id=None,
    artifacts=None,
    command=None,
):
    """Build a JSON-serialisable provenance manifest for one run."""
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config_file = file_fingerprint(cfg.source) if cfg.source else None
    return {
        "schema_version": 2,
        "version": __version__,
        "run_id": run_id,
        "generated_utc": generated,
        "command": list(command or []),
        "directory": str(directory),
        "config_file": config_file,
        "config_snapshot": config.as_dict(cfg),
        "git": git_info(),
        "environment": report.environment_info(),
        "grid": {
            "shape": [int(value) for value in data["landmask"].shape],
            "land_cells": int((data["landmask"] != 0).sum()),
        },
        "co2_pa": cfg.model.co2_pa,
        "fire": cfg.model.fire,
        "max_equilibrium_years": cfg.model.max_equilibrium_years,
        "equilibrium_years": results["equilibrium_years"],
        "runtime_seconds": elapsed,
        "inputs": inspection.source_fingerprints(cfg.input),
        "input_attrs": data.get("attrs", {}),
        "artifacts": artifacts or {},
        "outputs": str(Path(directory) / f"{cfg.output.name}.nc"),
    }


def write_manifest(path, manifest):
    """Write the manifest atomically and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path
