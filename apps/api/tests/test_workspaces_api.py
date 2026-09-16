# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Console `select` surface over HTTP: list workspaces, publish one on demand.

Runs a real ThreadingHTTPServer on an ephemeral port. The republish seam is
monkeypatched on `pdf_pipeline.pipeline` (the handler's lazy import resolves it
at call time), so no stage runs and no lualatex is needed. Workspaces are
hand-written manifests: a committed one needs only a matching
``source.pdf`` fingerprint and a record per stage, which is exactly what the
read-only path checks.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, cast

import pytest
from paper_api.__main__ import make_handler
from pdf_pipeline.workspace import STAGE_ORDER, WorkspaceError, sha256_bytes

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SOURCE_BYTES = b"%PDF-1.4\nconsole fixture\n"


def _committed_stages() -> dict[str, object]:
    """A completed record per stage, with no artifacts to verify."""
    return {
        stage.value: {
            "status": "completed",
            "producerVersion": "test",
            "inputFingerprint": "test",
            "artifacts": {},
        }
        for stage in STAGE_ORDER
    }


def _write_workspace(root: Path, *, stages: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "source.pdf").write_bytes(SOURCE_BYTES)
    (root / "workspace.json").write_text(
        json.dumps(
            {
                "workspaceVersion": "0.1.0",
                "sourceFingerprint": sha256_bytes(SOURCE_BYTES),
                "stages": stages,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def api_workspace(tmp_path: Path) -> Path:
    """The committed workspace the API serves: every stage, plus mapping.json."""
    root = tmp_path / "ws"
    _write_workspace(root, stages=_committed_stages())
    (root / "mapping.json").write_text("{}\n", encoding="utf-8")
    return root


def _fake_republish(workspace_dir: Path, *, viewer_data_dir: Path) -> str:
    if not (workspace_dir / "workspace.json").is_file():
        raise WorkspaceError(f"missing workspace manifest: {workspace_dir / 'workspace.json'}")
    if workspace_dir.name.startswith("uncommitted"):
        raise WorkspaceError("workspace stages are not committed: render")
    if workspace_dir.name.startswith("exploding"):
        raise RuntimeError("unexpected failure")
    viewer_data_dir.mkdir(parents=True, exist_ok=True)
    return "rev-republished"


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ThreadingHTTPServer]:
    monkeypatch.setattr("pdf_pipeline.pipeline.republish_workspace_viewer", _fake_republish)
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(tmp_path / "ws", tmp_path / "data", tmp_path / "jobs"),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def call(
    server: ThreadingHTTPServer,
    method: str,
    path: str,
    body: bytes | None = None,
) -> tuple[int, dict[str, object] | None]:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request(method, path, body=body)
        response = connection.getresponse()
        payload = response.read()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed if isinstance(parsed, dict) else None
    finally:
        connection.close()


def _entries(payload: dict[str, object] | None) -> list[dict[str, object]]:
    assert payload is not None
    return cast("list[dict[str, object]]", payload["workspaces"])


def test_list_reports_the_api_workspace_and_the_jobs_root(
    server: ThreadingHTTPServer, api_workspace: Path, tmp_path: Path
) -> None:
    nested = tmp_path / "jobs" / "workspaces" / "stale"
    nested.mkdir(parents=True)
    (nested / "workspace.json").write_text("{}", encoding="utf-8")
    (tmp_path / "jobs" / "workspaces" / "not-a-workspace").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text(
        json.dumps({"revision": "rev-1", "workspace": str(api_workspace.resolve())}),
        encoding="utf-8",
    )

    status, payload = call(server, "GET", "/api/workspaces")

    assert status == 200
    assert payload is not None
    assert payload["ok"] is True
    by_path = {str(entry["path"]): entry for entry in _entries(payload)}
    assert set(by_path) == {str(api_workspace.resolve()), str(nested.resolve())}

    current = by_path[str(api_workspace.resolve())]
    assert current["name"] == "ws"
    assert current["complete"] is True
    assert current["error"] is None
    assert current["workspaceVersion"] == "0.1.0"
    assert current["updatedAt"]
    assert sorted(cast("dict[str, str]", current["stages"])) == sorted(
        stage.value for stage in STAGE_ORDER
    )
    assert set(cast("dict[str, str]", current["stages"]).values()) == {"completed"}
    assert current["publication"] == {"current": True}

    # A manifest this build cannot read still gets a row, marked unusable.
    stale = by_path[str(nested.resolve())]
    assert stale["complete"] is False
    assert stale["error"] is not None
    assert stale["publication"] == {"current": False}


def test_list_is_ok_without_a_published_revision(
    server: ThreadingHTTPServer, api_workspace: Path
) -> None:
    status, payload = call(server, "GET", "/api/workspaces")

    assert status == 200
    entries = _entries(payload)
    assert [str(entry["path"]) for entry in entries] == [str(api_workspace.resolve())]
    assert entries[0]["publication"] == {"current": False}


def test_open_publishes_into_the_server_data_dir(
    server: ThreadingHTTPServer, api_workspace: Path, tmp_path: Path
) -> None:
    status, payload = call(
        server,
        "POST",
        "/api/workspaces/open",
        json.dumps({"workspace": str(api_workspace)}).encode(),
    )

    assert status == 200
    assert payload == {"ok": True, "revision": "rev-republished"}
    # The client names a read source only; the write target is the server's own
    # --data-dir.
    assert (tmp_path / "data").is_dir()


def test_open_rejects_bad_requests(server: ThreadingHTTPServer, tmp_path: Path) -> None:
    cases = [
        b"not json",
        json.dumps({"workspace": "relative/ws"}).encode(),
        json.dumps({"workspace": ""}).encode(),
        json.dumps({"workspace": 5}).encode(),
        json.dumps({}).encode(),
        json.dumps({"workspace": None}).encode(),
    ]
    for body in cases:
        status, payload = call(server, "POST", "/api/workspaces/open", body)
        assert status == 400, body
        assert payload is not None
        assert payload["ok"] is False

    status, payload = call(
        server,
        "POST",
        "/api/workspaces/open",
        json.dumps({"workspace": str(tmp_path / "nowhere")}).encode(),
    )
    assert status == 404
    assert payload is not None
    assert payload["ok"] is False


def test_open_maps_workspace_errors_to_400(server: ThreadingHTTPServer, tmp_path: Path) -> None:
    uncommitted = tmp_path / "uncommitted"
    uncommitted.mkdir()
    (uncommitted / "workspace.json").write_text("{}", encoding="utf-8")

    status, payload = call(
        server,
        "POST",
        "/api/workspaces/open",
        json.dumps({"workspace": str(uncommitted)}).encode(),
    )

    assert status == 400
    assert payload is not None
    assert "not committed" in str(payload["error"])


def test_open_maps_unexpected_errors_to_500(server: ThreadingHTTPServer, tmp_path: Path) -> None:
    exploding = tmp_path / "exploding"
    exploding.mkdir()
    (exploding / "workspace.json").write_text("{}", encoding="utf-8")

    status, payload = call(
        server,
        "POST",
        "/api/workspaces/open",
        json.dumps({"workspace": str(exploding)}).encode(),
    )

    assert status == 500
    assert payload is not None
    assert payload["ok"] is False


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_wrong_method_on_open_is_405(server: ThreadingHTTPServer, method: str) -> None:
    status, payload = call(server, method, "/api/workspaces/open", b"{}")

    assert status == 405
    assert payload is not None
    assert payload["ok"] is False


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_wrong_method_on_the_listing_is_405(server: ThreadingHTTPServer, method: str) -> None:
    status, payload = call(server, method, "/api/workspaces", b"{}")

    assert status == 405
    assert payload is not None
    assert payload["ok"] is False
