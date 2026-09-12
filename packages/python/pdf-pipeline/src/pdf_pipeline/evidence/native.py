# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Shared helpers for native MinerU / Docling / GROBID dump adapters.

Providers never leak native schemas past this package: dumps are mapped
into canonical EvidenceBundle candidates, then fusion consumes only that.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.normalize import normalize_label

DUMP_DIR_ENV = "PAPER_PARSER_DUMP_DIR"
SOURCE_PDF_ENV = "PAPER_SOURCE_PDF"


def page_id_at(physical: generated.PhysicalDocument, index: int) -> str:
    """Map a dump page index onto the PhysicalDocument page id."""
    if index < 0 or index >= len(physical.pages):
        msg = f"dump page index {index} is outside physical page count {len(physical.pages)}"
        raise ValueError(msg)
    return physical.pages[index].id


def parse_rect(raw: object) -> generated.Rect:
    """Accept canonical rects, [x0,y0,x1,y1], or Docling l/t/r/b boxes."""
    if isinstance(raw, generated.Rect):
        return raw
    if isinstance(raw, dict):
        mapping = {str(key): value for key, value in raw.items()}
        if {"x", "y", "width", "height"} <= mapping.keys():
            return generated.Rect(
                kind="rect",
                x=float(mapping["x"]),
                y=float(mapping["y"]),
                width=float(mapping["width"]),
                height=float(mapping["height"]),
            )
        if {"l", "t", "r", "b"} <= mapping.keys():
            left = float(mapping["l"])
            top = float(mapping["t"])
            return generated.Rect(
                kind="rect",
                x=left,
                y=top,
                width=float(mapping["r"]) - left,
                height=float(mapping["b"]) - top,
            )
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        x0, y0, x1, y1 = (float(value) for value in raw)
        return generated.Rect(kind="rect", x=x0, y=y0, width=x1 - x0, height=y1 - y0)
    msg = f"unsupported native bbox: {raw!r}"
    raise ValueError(msg)


def load_json_dump_text(text: str) -> dict[str, Any]:
    """Parse a JSON object from a string dump."""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        msg = "parser dump must be a JSON object"
        raise TypeError(msg)
    return payload


def load_json_dump(path: Path) -> dict[str, Any]:
    """Read a JSON dump object; reject non-objects so adapters stay typed."""
    return load_json_dump_text(path.read_text(encoding="utf-8"))


def resolve_dump_path(provider: str, fingerprint: str, explicit: Path | None) -> Path | None:
    """Prefer an explicit path, then PAPER_PARSER_DUMP_DIR/<provider>/<fingerprint>.*."""
    if explicit is not None:
        return explicit
    root = os.environ.get(DUMP_DIR_ENV)
    if not root:
        return None
    directory = Path(root) / provider
    for suffix in (".json", ".tei.xml", ".xml"):
        candidate = directory / f"{fingerprint}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def source_pdf_path() -> Path | None:
    """Optional PDF bytes location for live adapters (not used in CI)."""
    raw = os.environ.get(SOURCE_PDF_ENV)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def label_for(provider_label: str) -> generated.LayoutLabel:
    """Normalize a native label; unknown values become UNKNOWN, never crash."""
    return normalize_label(provider_label)
