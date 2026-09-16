"""Server-owned PDF upload inbox: ``POST /api/uploads`` (console upload surface).

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and
``store_upload`` is directly testable without a socket: the caller passes an
iterable of byte chunks instead of a request stream. Nothing here imports the
heavy pipeline; ``pdf_pipeline.workspace`` (pure stdlib) supplies the
canonical ``workspaces`` directory name only.

Read/write ownership: the browser streams raw bytes plus a display name; the
server alone decides where they land (``<jobs-root>/inbox/``). The stored file
name is the sanitized name slug plus the first eight hex digits of the content
hash, so re-uploading the same name with identical bytes reuses one inbox file
and therefore one workspace path. The inbox is not a workspace: no workspace
directory is created here — ``run_pipeline`` creates it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pdf_pipeline.workspace import WORKSPACES_DIRNAME

if TYPE_CHECKING:
    from collections.abc import Iterable

UPLOADS_PATH = "/api/uploads"

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
UPLOAD_READ_TIMEOUT_S = 30.0

INBOX_DIRNAME = "inbox"

_PDF_MAGIC = b"%PDF-"


def _slug(name: str) -> str:
    """A filesystem-safe stem for ``name``; never empty."""
    stem = Path(Path(name).name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_") or "upload"


def store_upload(
    *,
    jobs_root: Path,
    name: str | None,
    content_length: int | None,
    chunks: Iterable[bytes],
) -> tuple[int, dict[str, object]]:
    """Store one uploaded PDF in the inbox; returns (http_status, json_payload).

    Checks run in order so a rejected upload never costs a whole body read:
    missing name, wrong extension, and an over-large declared
    ``content_length`` are answered before ``chunks`` is consumed. The stream
    is written to ``.{slug}.part`` while hashing, so the size cap is enforced
    mid-stream and only the first five bytes are needed to decide the PDF
    magic. Every failure path removes the scratch file, so the inbox never
    shows a half-written upload.
    """
    if not name:
        return 400, {"ok": False, "error": "missing X-Upload-Name header"}
    basename = Path(name).name
    slug = _slug(name)
    if Path(basename).suffix.lower() != ".pdf":
        return 400, {"ok": False, "error": "upload name must end with .pdf"}
    if content_length is not None and content_length > MAX_UPLOAD_BYTES:
        return 413, {"ok": False, "error": "uploaded file too large"}
    inbox = jobs_root / INBOX_DIRNAME
    inbox.mkdir(parents=True, exist_ok=True)
    part = inbox / f".{slug}.part"
    digest = hashlib.sha256()
    total = 0
    prefix = bytearray()
    try:
        with part.open("wb") as sink:
            for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    return 413, {"ok": False, "error": "uploaded file too large"}
                if len(prefix) < len(_PDF_MAGIC):
                    prefix += chunk[: len(_PDF_MAGIC) - len(prefix)]
                digest.update(chunk)
                sink.write(chunk)
        if bytes(prefix) != _PDF_MAGIC:
            reason = "uploaded file is empty" if total == 0 else "uploaded file is not a PDF"
            return 400, {"ok": False, "error": reason}
        stored_stem = f"{slug}-{digest.hexdigest()[:8]}"
        destination = inbox / f"{stored_stem}.pdf"
        part.replace(destination)
        return 200, {
            "ok": True,
            "path": str(destination.resolve()),
            "workspace": str((jobs_root / WORKSPACES_DIRNAME / stored_stem).resolve()),
            "bytes": total,
            "sha256": digest.hexdigest(),
        }
    finally:
        part.unlink(missing_ok=True)
