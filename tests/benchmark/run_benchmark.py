"""Phase 7.7 regression benchmark runner.

Runs the full ensemble pipeline over the Tier-1 corpus, produces a
quality report per fixture (roadmap Phase 7.6 metrics), aggregates
confidence calibration, and compares against the committed baseline
(``baseline.json``). Exit code 1 on any regression.

Usage (via just recipes):
    uv run python tests/benchmark/run_benchmark.py                  # report + compare
    uv run python tests/benchmark/run_benchmark.py --report-only    # report, no gate
    uv run python tests/benchmark/run_benchmark.py --update-baseline

Baseline updates are governed by docs/testing/golden.md: they require an
explicit reason in the commit message — never just to make the check
pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / "tests/fixtures/source/latex/build"
TRUTH_DIR = ROOT / "tests/fixtures/layout-truth"
BASELINE_PATH = ROOT / "tests/benchmark/baseline.json"

# Numeric metrics are "higher is better"; regression means dropping
# below the baseline by more than this tolerance.
METRIC_EPSILON = 1e-3

# Metrics compared against the baseline (higher is better). A previously
# measurable value becoming null is a regression, not a skip.
_METRICS = (
    "physicalTextCoverage",
    "regionRecall",
    "regionPrecision",
    "pairwiseOrderingAccuracy",
    "paragraphLabelRecall",
    "headingLabelRecall",
    "semanticExpectationCoverage",
    "tableStructureCoverage",
    "citationResolutionRate",
    "sourceMappingCoverage",
    "renderMappingCoverage",
)


def _truths() -> dict[str, dict[str, Any]]:
    truths: dict[str, dict[str, Any]] = {}
    for path in sorted(TRUTH_DIR.glob("*.json")):
        truth = json.loads(path.read_text())
        truths[truth["fixture"]] = truth
    return truths


def run_corpus() -> dict[str, Any]:
    """Run the ensemble over every built fixture and build the report."""
    from document_model.generated import schema_models as generated
    from pdf_pipeline.calibration import calibrate, calibration_samples
    from pdf_pipeline.capabilities import load_registry
    from pdf_pipeline.config import load_parser_config
    from pdf_pipeline.evidence.normalize import merge_evidence_bundles
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.metrics import quality_report
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.pipeline import region_lines_from, region_texts_from
    from pdf_pipeline.probe import probe_document
    from pdf_pipeline.routing import collect_bundles, route_providers
    from pdf_pipeline.sem_validate import validate_semantic_recovery
    from pdf_pipeline.semantic import recover_semantic_document

    # Same entry point the pipeline uses, so `just benchmark` can prove a
    # replacement registry: PAPER_CAPABILITY_REGISTRY=<file> just benchmark.
    registry = load_registry(load_parser_config().registry_path)
    truths = _truths()
    fixtures: dict[str, Any] = {}
    samples: list[tuple[float, bool]] = []
    for pdf_path in sorted(BUILD_DIR.glob("*.pdf")):
        name = pdf_path.stem
        truth = truths.get(name)
        physical = extract_physical_document(pdf_path.read_bytes())
        plan = route_providers(probe_document(physical), registry)
        collection = collect_bundles(plan, physical, registry)
        bundles = list(collection.bundles)
        merged = merge_evidence_bundles(bundles, issues=collection.issues(physical.id))
        layout = recover_layout_document(physical, evidence=bundles, registry=registry)
        texts = region_texts_from(physical, layout)
        semantic = recover_semantic_document(
            layout,
            texts,
            lines=region_lines_from(physical, layout),
            evidence=merged,
        )
        issues = validate_semantic_recovery(semantic, layout, texts)
        if issues:
            store = semantic.issues or generated.IssueStore(issues=[])
            semantic = semantic.model_copy(
                update={"issues": store.model_copy(update={"issues": [*store.issues, *issues]})}
            )
        if truth:
            samples.extend(
                calibration_samples(
                    layout,
                    texts,
                    truth.get("readingOrder") or [],
                    truth.get("regions"),
                )
            )
        fixtures[name] = {
            "routedProviders": list(plan.provider_names()),
            **quality_report(
                physical=physical,
                layout=layout,
                semantic=semantic,
                region_texts=texts,
                truth=truth,
            ),
        }
    return {
        "fixtures": fixtures,
        "calibration": calibrate(samples).to_json(),
    }


def compare(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Human-readable improved/unchanged/regressed lines against the baseline.

    Calibration accuracy stays diagnostic (it audits the fusion formula,
    not the product gate) even after region-level boxes exist. Missing
    baseline fixtures, or a metric that used to be measurable becoming
    null, are regressions. Blocking issues are ERROR/FATAL counts, not a
    single category.
    """
    lines: list[str] = []
    fixtures = report.get("fixtures", {})
    baseline_fixtures = baseline.get("fixtures", {})
    for name in sorted(set(fixtures) | set(baseline_fixtures)):
        lines.extend(
            _compare_fixture(
                name, _report_dict(fixtures.get(name)), _report_dict(baseline_fixtures.get(name))
            )
        )
    lines.extend(
        _compare_calibration(
            _report_dict(report.get("calibration", {})) or {},
            _report_dict(baseline.get("calibration", {})) or {},
        )
    )
    return [line for line in lines if not line.startswith("unchanged ")] or [
        "unchanged (all metrics within tolerance)"
    ]


def _report_dict(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return cast("dict[str, Any]", value)
    return None


def _compare_fixture(
    name: str,
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> list[str]:
    if previous is not None and current is None:
        return [f"REGRESSED  {name}: missing fixture"]
    if current is None:
        return []
    if previous is None:
        return [f"improved   {name}: new fixture"]
    lines: list[str] = []
    for metric in _METRICS:
        now, before = current.get(metric), previous.get(metric)
        if before is not None and now is None:
            lines.append(f"REGRESSED  {name}.{metric}: {before} -> null")
        elif now is None or before is None:
            continue
        elif now > before + METRIC_EPSILON:
            lines.append(f"improved   {name}.{metric}: {before} -> {now}")
        elif now < before - METRIC_EPSILON:
            lines.append(f"REGRESSED  {name}.{metric}: {before} -> {now}")
        else:
            lines.append(f"unchanged  {name}.{metric}: {now}")
    now_errors = _error_count(current)
    before_errors = _error_count(previous)
    if now_errors > before_errors:
        lines.append(f"REGRESSED  {name}.errorIssues: {before_errors} -> {now_errors}")
    return lines


def _compare_calibration(
    calibration_now: dict[str, Any],
    calibration_before: dict[str, Any],
) -> list[str]:
    now_accuracy = calibration_now.get("accuracy")
    before_accuracy = calibration_before.get("accuracy")
    if now_accuracy is None or before_accuracy is None:
        return []
    if now_accuracy > before_accuracy + METRIC_EPSILON:
        return [f"diagnostic calibration.accuracy: {before_accuracy} -> {now_accuracy} (improved)"]
    if now_accuracy < before_accuracy - METRIC_EPSILON:
        return [f"diagnostic calibration.accuracy: {before_accuracy} -> {now_accuracy} (declined)"]
    return []


def _error_count(fixture_report: dict[str, Any]) -> int:
    """Blocking issue count: ERROR + FATAL, independent of category."""
    issues = fixture_report.get("issues")
    if not isinstance(issues, dict):
        return 0
    issues_map = cast("dict[str, Any]", issues)
    severity_raw: object = issues_map.get("bySeverity")
    if not isinstance(severity_raw, dict):
        return 0
    counts = cast("dict[str, Any]", severity_raw)
    return _as_int(counts.get("ERROR")) + _as_int(counts.get("FATAL"))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="skip the baseline gate")
    parser.add_argument(
        "--update-baseline", action="store_true", help="write the report as the new baseline"
    )
    args = parser.parse_args(argv)

    report = run_corpus()
    report_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    print(report_text)

    if args.update_baseline:
        BASELINE_PATH.write_text(report_text, encoding="utf-8")
        print(f"baseline written: {BASELINE_PATH}")
        return 0
    if not BASELINE_PATH.exists():
        print(f"no baseline at {BASELINE_PATH}; run with --update-baseline first")
        return (args.report_only and 0) or 1
    if args.report_only:
        return 0

    findings = compare(report, json.loads(BASELINE_PATH.read_text()))
    print("\n".join(findings))
    return 1 if any(line.startswith("REGRESSED") for line in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
