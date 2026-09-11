"""Reader API business logic: node re-translation via the pipeline workspace.

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and the
handler is directly testable (monkeypatch the ``rerender_workspace`` seam).
``pdf_pipeline`` is imported lazily inside the handler so the API process
keeps a sub-second startup without pulling pdfium/paper_llm at boot.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# lualatex writes into a single shared build directory per workspace.
RERENDER_LOCK = threading.Lock()

MAX_BODY_BYTES = 4096
BODY_READ_TIMEOUT_S = 2.0


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    typed: dict[str, object] = {}
    for key, item in value.items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        typed[str(key)] = item  # pyright: ignore[reportUnknownArgumentType]
    return typed


def parse_node_ids(raw: bytes) -> set[str]:
    """Extract nodeIds from a POST body.

    ``ValueError`` marks malformed JSON/shape (→ HTTP 400); ``TypeError``
    marks a well-shaped body with non-string ids, which the handler maps the
    same way.
    """
    payload = _json_object(json.loads(raw.decode("utf-8")))
    node_ids_obj: object = payload.get("nodeIds")
    if not isinstance(node_ids_obj, list) or not node_ids_obj:
        raise ValueError("nodeIds must be a non-empty list")
    ids: list[str] = []
    for raw_id in cast("list[object]", node_ids_obj):
        if not isinstance(raw_id, str) or not raw_id:
            raise TypeError("nodeIds entries must be non-empty strings")
        ids.append(raw_id)
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
        from paper_llm.translation import TranslationProviderNotConfiguredError  # noqa: PLC0415

        if isinstance(error, TranslationProviderNotConfiguredError):
            return 503, {"ok": False, "error": str(error)}
        return 500, {"ok": False, "error": str(error)}
    payload: dict[str, object] = {"ok": True, "changed": changed}
    manifest_path = data_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = _json_object(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            manifest = None
        if manifest is not None:
            revision = manifest.get("revision")
            if isinstance(revision, str) and revision:
                payload["revision"] = revision
    return 200, payload
