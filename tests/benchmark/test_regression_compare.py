"""Regression gate: missing fixtures and vanished metrics must fail."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _load_compare() -> Callable[[dict[str, Any], dict[str, Any]], list[str]]:
    spec = importlib.util.spec_from_file_location(
        "benchmark_runner", Path(__file__).with_name("run_benchmark.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load run_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compare


compare = _load_compare()


def _fixture(*, coverage: float | None = 1.0, errors: int = 0) -> dict[str, object]:
    return {
        "physicalTextCoverage": coverage,
        "regionRecall": 1.0,
        "regionPrecision": 1.0,
        "pairwiseOrderingAccuracy": 1.0,
        "semanticExpectationCoverage": 1.0,
        "tableStructureCoverage": 1.0,
        "citationResolutionRate": 1.0,
        "sourceMappingCoverage": 1.0,
        "renderMappingCoverage": 0.0,
        "issues": {"byCategory": {}, "bySeverity": {"ERROR": errors}},
    }


def test_compare_missing_fixture_is_regression() -> None:
    baseline = {"fixtures": {"smoke": _fixture()}, "calibration": {"accuracy": 0.5}}
    report = {"fixtures": {}, "calibration": {"accuracy": 0.5}}
    findings = compare(report, baseline)
    assert any(line.startswith("REGRESSED  smoke: missing fixture") for line in findings)


def test_compare_null_metric_is_regression() -> None:
    baseline = {"fixtures": {"smoke": _fixture()}, "calibration": {}}
    report = {"fixtures": {"smoke": _fixture(coverage=None)}, "calibration": {}}
    findings = compare(report, baseline)
    assert any("smoke.physicalTextCoverage" in line and "null" in line for line in findings)
    assert any(line.startswith("REGRESSED") for line in findings)


def test_compare_calibration_decline_is_diagnostic() -> None:
    fixture = _fixture()
    baseline = {"fixtures": {"smoke": fixture}, "calibration": {"accuracy": 0.5}}
    report = {"fixtures": {"smoke": fixture}, "calibration": {"accuracy": 0.4}}
    findings = compare(report, baseline)
    assert any(line.startswith("diagnostic calibration.accuracy") for line in findings)
    assert not any(line.startswith("REGRESSED") for line in findings)


def test_compare_error_severity_increase_is_regression() -> None:
    baseline = {"fixtures": {"smoke": _fixture(errors=0)}, "calibration": {}}
    report = {
        "fixtures": {
            "smoke": {
                **_fixture(errors=0),
                "issues": {
                    "byCategory": {"CITATION_RESOLUTION": 2},
                    "bySeverity": {"ERROR": 2},
                },
            }
        },
        "calibration": {},
    }
    findings = compare(report, baseline)
    assert any("errorIssues" in line and line.startswith("REGRESSED") for line in findings)
