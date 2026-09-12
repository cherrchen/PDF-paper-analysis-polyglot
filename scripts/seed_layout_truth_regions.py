#!/usr/bin/env python3
"""Draft layout-truth ``regions[]`` from snippet matches plus display objects.

Keep only boxes that already correspond to hand-written readingOrder snippets
or FIGURE/TABLE/FORMULA regions. Do not freeze every recovered fragment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.metrics import export_seed_truth_regions
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from

from repo import ROOT

BUILD = ROOT / "tests/fixtures/source/latex/build"
TRUTH = ROOT / "tests/fixtures/layout-truth"


def main() -> int:
    missing: list[str] = []
    for path in sorted(TRUTH.glob("*.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        name = str(truth["fixture"])
        pdf = BUILD / f"{name}.pdf"
        if not pdf.is_file():
            missing.append(name)
            print(f"skip {name}: PDF not built")
            continue
        physical = extract_physical_document(pdf.read_bytes())
        layout = recover_layout_document(physical)
        texts = region_texts_from(physical, layout)
        regions = export_seed_truth_regions(layout, texts, truth.get("readingOrder") or [])
        truth["regions"] = regions
        path.write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{name}: {len(regions)} regions")
    if missing:
        print("run `just latex-smoke` then re-run this script", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
