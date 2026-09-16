"""Workspace catalog endpoints: list known workspaces and open one for viewing.

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and every
handler is directly testable (monkeypatch the ``republish_workspace_viewer``
seam). ``pdf_pipeline`` is imported lazily inside each handler so the API
process keeps its sub-second startup without pulling pdfium.

Read/write ownership: a client names only the workspace it wants to *read*
from. The publication target is always the server's own ``--data-dir``;
opening a workspace republishes that workspace's already-committed artifacts
into the viewer directory and never writes into the workspace itself — the
same rule ``viewer_workspace()`` enforces against client-supplied write paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

WORKSPACES_PATH = "/api/workspaces"
OPEN_WORKSPACE_PATH = "/api/workspaces/open"


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    return cast("dict[str, object]", value)


def _published_workspace(data_dir: Path) -> str | None:
    """The workspace path recorded in the published viewer manifest, if any."""
    try:
        raw: object = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    workspace = cast("dict[str, object]", raw).get("workspace")
    return workspace if isinstance(workspace, str) and workspace else None


def handle_list_workspaces(
    *,
    jobs_root: Path,
    api_workspace: Path,
    data_dir: Path,
) -> tuple[int, dict[str, object]]:
    """Every discoverable workspace, each flagged with whether it is published.

    ``publication.current`` compares the resolved workspace directory against
    the ``workspace`` field of the viewer manifest, so it answers "would
    opening this row change what the viewer shows?". A broken workspace
    degrades its own row (``error`` / ``complete`` false) instead of failing
    the listing; a missing or unreadable viewer manifest just marks every row
    stale.
    """
    from pdf_pipeline.workspace import discover_workspaces, summarize_workspace  # noqa: PLC0415

    current = _published_workspace(data_dir)
    workspaces: list[dict[str, object]] = []
    for root in discover_workspaces(jobs_root=jobs_root, extra=(api_workspace,)):
        summary = summarize_workspace(root)
        publication = {"current": current is not None and current == str(root.resolve())}
        workspaces.append({**summary.to_json(), "publication": publication})
    return 200, {"ok": True, "workspaces": workspaces}


def handle_open_workspace(raw: bytes, *, data_dir: Path) -> tuple[int, dict[str, object]]:
    """Republish a committed workspace into the server's viewer data dir.

    ``400`` for a malformed body, a non-absolute workspace, or a workspace
    the pipeline refuses to publish (``WorkspaceError``: missing manifest,
    version mismatch, source mismatch, uncommitted stages); ``404`` when the
    directory holds no workspace manifest; ``500`` for anything else. The
    client cannot name the write target — it is always the server-owned
    ``data_dir``.
    """
    try:
        payload = _json_object(json.loads(raw.decode("utf-8")))
    except (ValueError, TypeError, UnicodeDecodeError):
        return 400, {"ok": False, "error": "invalid request body"}
    workspace = payload.get("workspace")
    if not isinstance(workspace, str) or not workspace or not Path(workspace).is_absolute():
        return 400, {"ok": False, "error": "workspace must be an absolute path"}
    from pdf_pipeline.workspace import MANIFEST_NAME, WorkspaceError  # noqa: PLC0415

    if not (Path(workspace) / MANIFEST_NAME).is_file():
        return 404, {"ok": False, "error": f"unknown workspace: {workspace}"}
    from pdf_pipeline.pipeline import republish_workspace_viewer  # noqa: PLC0415

    try:
        revision = republish_workspace_viewer(Path(workspace), viewer_data_dir=data_dir)
    except WorkspaceError as error:
        return 400, {"ok": False, "error": str(error)}
    except Exception as error:
        return 500, {"ok": False, "error": str(error)}
    return 200, {"ok": True, "revision": revision}
