# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Reader API business logic: node re-translation via the pipeline workspace.

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and the
handler is directly testable (monkeypatch the ``rerender_workspace`` seam).
``pdf_pipeline`` is imported lazily inside the handler so the API process
keeps a sub-second startup without pulling pdfium/paper_llm at boot.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# lualatex writes into a single shared build directory per workspace.
RERENDER_LOCK = threading.Lock()

MAX_BODY_BYTES = 4096


def parse_node_ids(raw: bytes) -> set[str]:
    """Extract nodeIds from a POST body.

    ``ValueError`` marks malformed JSON/shape (→ HTTP 400); ``TypeError``
    marks a well-shaped body with non-string ids, which the handler maps the
    same way.
    """
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("nodeIds must be a JSON object body")
    node_ids = payload.get("nodeIds")
    if not isinstance(node_ids, list) or not node_ids:
        raise ValueError("nodeIds must be a non-empty list")
    ids: list[str] = []
    for node_id in node_ids:
        if not isinstance(node_id, str) or not node_id:
            raise TypeError("nodeIds entries must be non-empty strings")
        ids.append(node_id)
    return set(ids)


def handle_retranslate(
    raw_body: bytes,
    *,
    workspace: Path,
    data_dir: Path,
    rerender: Callable[..., list[str]] | None = None,
) -> tuple[int, dict[str, object]]:
    """Run one retranslate request; returns (http_status, json_payload)."""
    try:
        node_ids = parse_node_ids(raw_body)
    except (ValueError, TypeError, UnicodeDecodeError):
        return 400, {"ok": False, "error": "invalid request body"}
    if rerender is None:
        from pdf_pipeline.pipeline import rerender_workspace  # noqa: PLC0415

        rerender = rerender_workspace
    try:
        with RERENDER_LOCK:
            changed = rerender(workspace, viewer_data_dir=data_dir, node_ids=node_ids)
    except ValueError as error:
        return 400, {"ok": False, "error": str(error)}
    except FileNotFoundError:
        return (
            409,
            {"ok": False, "error": "workspace not initialized; run just viewer-fixture"},
        )
    except Exception as error:
        return 500, {"ok": False, "error": str(error)}
    return 200, {"ok": True, "changed": changed}
