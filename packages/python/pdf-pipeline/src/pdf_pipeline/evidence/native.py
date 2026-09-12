# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Shared helpers for native MinerU / Docling / GROBID dump adapters.

Providers never leak native schemas past this package: dumps are mapped
into canonical EvidenceBundle candidates, then fusion consumes only that.
JSON/process I/O stays here so the per-provider adapters can stay typed.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.normalize import normalize_label

if TYPE_CHECKING:
    from collections.abc import Callable

DUMP_DIR_ENV = "PAPER_PARSER_DUMP_DIR"
SOURCE_PDF_ENV = "PAPER_SOURCE_PDF"

_BOTTOMLEFT = frozenset({"BOTTOMLEFT", "BOTTOM_LEFT"})


def page_id_at(physical: generated.PhysicalDocument, index: int) -> str:
    """Map a dump page index onto the PhysicalDocument page id."""
    if index < 0 or index >= len(physical.pages):
        msg = f"dump page index {index} is outside physical page count {len(physical.pages)}"
        raise ValueError(msg)
    return physical.pages[index].id


def page_height_at(physical: generated.PhysicalDocument, index: int) -> float:
    """Canonical page height in PDF points for dump coordinate conversion."""
    page_id_at(physical, index)
    return physical.pages[index].geometry.heightPt


def parse_rect(raw: object, *, page_height: float | None = None) -> generated.Rect:
    """Accept canonical rects, [x0,y0,x1,y1], or Docling l/t/r/b boxes.

    Docling ``BoundingBox`` may use ``coord_origin`` TOPLEFT (canonical) or
    BOTTOMLEFT (PDF). BOTTOMLEFT boxes are converted with ``page_height``.
    """
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
            return _docling_bbox(mapping, page_height=page_height)
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        x0, y0, x1, y1 = (float(value) for value in raw)
        return generated.Rect(kind="rect", x=x0, y=y0, width=x1 - x0, height=y1 - y0)
    msg = f"unsupported native bbox: {raw!r}"
    raise ValueError(msg)


def _docling_bbox(mapping: dict[str, Any], *, page_height: float | None) -> generated.Rect:
    left = float(mapping["l"])
    top = float(mapping["t"])
    right = float(mapping["r"])
    bottom = float(mapping["b"])
    origin_raw = mapping.get("coord_origin") or mapping.get("coordOrigin") or "TOPLEFT"
    origin = str(origin_raw).replace("-", "_").upper()
    if origin in _BOTTOMLEFT:
        if page_height is None:
            msg = "Docling BOTTOMLEFT bbox requires page_height"
            raise ValueError(msg)
        top = page_height - top
        bottom = page_height - bottom
    x = min(left, right)
    y = min(top, bottom)
    return generated.Rect(
        kind="rect",
        x=x,
        y=y,
        width=abs(right - left),
        height=abs(bottom - top),
    )


def as_list(value: object) -> list[object]:
    """Treat missing/non-list dump fields as an empty list."""
    if not isinstance(value, list):
        return []
    return list(cast("list[object]", value))


def as_mapping(value: object) -> dict[str, object] | None:
    """Return a string-keyed mapping, or None when the dump field is not an object."""
    if not isinstance(value, dict):
        return None
    typed = cast("dict[object, object]", value)
    return {str(key): item for key, item in typed.items()}


def load_json_dump_text(text: str) -> dict[str, Any]:
    """Parse a JSON object from a string dump."""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        msg = "parser dump must be a JSON object"
        raise TypeError(msg)
    return {str(key): value for key, value in payload.items()}


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


def collect_live_json(cmd_env: str) -> dict[str, Any] | None:
    """Run an optional CLI that prints a JSON object for PAPER_SOURCE_PDF."""
    command = os.environ.get(cmd_env)
    pdf = source_pdf_path()
    if not command or pdf is None:
        return None
    completed = subprocess.run(  # noqa: S603 — user-configured live parser command
        [*command.split(), str(pdf)],
        check=True,
        capture_output=True,
        text=True,
    )
    return load_json_dump_text(completed.stdout)


def load_provider_json(
    provider: str,
    fingerprint: str,
    *,
    dump_env: str,
    explicit: Path | None,
    live: Callable[[], dict[str, Any] | None],
    live_hint: str,
) -> dict[str, Any]:
    """Load a recorded dump, else an optional live JSON producer."""
    env_dump = os.environ.get(dump_env)
    path = resolve_dump_path(provider, fingerprint, Path(env_dump) if env_dump else explicit)
    if path is not None:
        return load_json_dump(path)
    payload = live()
    if payload is not None:
        return payload
    msg = f"{provider} adapter has no dump: set {dump_env}, {DUMP_DIR_ENV}, or {live_hint}"
    raise FileNotFoundError(msg)


def label_for(provider_label: str) -> generated.LayoutLabel:
    """Normalize a native label; unknown values become UNKNOWN, never crash."""
    return normalize_label(provider_label)
