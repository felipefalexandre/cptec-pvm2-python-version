import json
from pathlib import Path

from pvm2 import diagnostics

ROOT = Path(__file__).resolve().parents[1]


def test_checksums_match_bundled_data():
    result = diagnostics.verify_checksums(ROOT)
    assert result["status"] == "ok"
    assert result["checked"] > 0
    assert not result["missing"]
    assert not result["mismatched"]


def test_quick_doctor_checks_environment_data_and_presets():
    report = diagnostics.doctor(root=ROOT)
    assert report["ok"] is True
    names = {check["name"] for check in report["checks"]}
    assert {"environment", "data", "reference_config", "landmask_presets"} <= names
    json.loads(diagnostics.json_report(report))


def test_doctor_without_repository_data_is_warning():
    report = diagnostics.doctor(root=ROOT.parent / "missing-pvm2-root")
    assert report["ok"] is True
    data = next(check for check in report["checks"] if check["name"] == "data")
    assert data["status"] == "warn"
