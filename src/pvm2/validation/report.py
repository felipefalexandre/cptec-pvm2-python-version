"""Scientific validation report generation."""

from __future__ import annotations

import html
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def environment_info():
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for module in ("numpy", "xarray", "netCDF4", "rasterio", "pandas"):
        try:
            mod = __import__(module)
            info[module] = getattr(mod, "__version__", "unknown")
        except ImportError:
            info[module] = "not installed"
    return info


def divergence_map(observed, modelled, path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    observed = np.asarray(observed)
    modelled = np.asarray(modelled)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    axes[0].imshow(observed.T, origin="lower", cmap="tab20")
    axes[0].set_title("Reference")
    axes[1].imshow(modelled.T, origin="lower", cmap="tab20")
    axes[1].set_title("PVM2")
    diff = observed.astype(np.int32) != modelled.astype(np.int32)
    axes[2].imshow(diff.T, origin="lower", cmap="gray_r")
    axes[2].set_title(f"Divergence ({int(diff.sum())} cells)")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def write_validation_report(path, metrics, observed, modelled, extra=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    png = divergence_map(observed, modelled, path.with_suffix(".png"))
    env = environment_info()
    rows = []
    for cls, row in metrics["per_class"].items():
        if row["observed"] == 0:
            continue
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{:.2f}</td><td>{:.3f}</td></tr>".format(
                cls,
                row["observed"],
                row["modelled"],
                row["correct"],
                row["accuracy_percent"],
                row["kappa"],
            )
        )
    extra_html = ""
    if extra:
        extra_html = "<h2>Run</h2><pre>{}</pre>".format(
            html.escape(json.dumps(extra, indent=2, default=str))
        )
    image_html = (
        f'<img src="{html.escape(png.name)}" alt="divergence map" style="max-width:100%">'
        if png
        else ""
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>PVM2 scientific validation</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}}
table{{border-collapse:collapse;margin:1rem 0}}
th,td{{border:1px solid #bbb;padding:.35rem .6rem;text-align:right}}
th{{background:#eee}} code,pre{{background:#f5f5f5;padding:.2rem}}
</style></head><body>
<h1>PVM2 scientific validation</h1>
<p>Generated {html.escape(env["generated_utc"])}.</p>
<h2>Agreement</h2>
<ul>
<li>Pixel agreement: <b>{metrics["agreement_percent"]:.2f}%</b></li>
<li>Compared cells (classes 1-12): {metrics["n_compared"]}</li>
<li>Kappa: <b>{metrics["kappa"]:.4f}</b> (p0 = {metrics["p0"]:.4f}, pe = {metrics["p_e"]:.4f})</li>
</ul>
<h2>Per class</h2>
<table><tr><th>Class</th><th>Observed</th><th>Modelled</th>
<th>Correct</th><th>Accuracy %</th><th>Kappa</th></tr>
{"".join(rows)}
</table>
<h2>Confusion matrix</h2>
<pre>{html.escape(json.dumps(metrics["confusion_matrix"]))}</pre>
{image_html}
{extra_html}
<h2>Environment</h2>
<pre>{html.escape(json.dumps(env, indent=2))}</pre>
</body></html>
"""
    path.write_text(document, encoding="utf-8")
    metrics_path = path.with_suffix(".json")
    metrics_path.write_text(
        json.dumps({"metrics": metrics, "environment": env, "run": extra}, indent=2),
        encoding="utf-8",
    )
    return path
