# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""M6 reader API: HTTP contract for /api/health and /api/retranslate.

Runs a real ThreadingHTTPServer on an ephemeral port with the pipeline seam
monkeypatched on the handler's module (`paper_api.retranslate` resolves the
lazy `rerender_workspace` import from `pdf_pipeline.pipeline`), so no
lualatex run or real workspace is touched.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest
from paper_api.__main__ import make_handler
from paper_api.retranslate import MAX_BODY_BYTES

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ThreadingHTTPServer]:
    def fake_rerender(
        workspace: Path,
        *,
        viewer_data_dir: Path,
        node_ids: set[str],
    ) -> list[str]:
        if not (workspace / "semantic.json").exists():
            raise FileNotFoundError(str(workspace / "semantic.json"))
        if "bad" in node_ids:
            raise ValueError(f"not re-translatable nodes: {sorted(node_ids)}")
        if "boom" in node_ids:
            raise RuntimeError("compile exploded")
        if "noconfig" in node_ids:
            from paper_llm.translation import TranslationProviderNotConfiguredError

            raise TranslationProviderNotConfiguredError
        viewer_data_dir.mkdir(parents=True, exist_ok=True)
        (viewer_data_dir / "manifest.json").write_text(
            json.dumps({"revision": "rev-test"}),
            encoding="utf-8",
        )
        return sorted(node_ids)

    monkeypatch.setattr("pdf_pipeline.pipeline.rerender_workspace", fake_rerender)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "semantic.json").write_text("{}")
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(workspace, tmp_path / "data", tmp_path / "jobs")
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


def test_health_endpoints(server: ThreadingHTTPServer) -> None:
    for path in ("/", "/health", "/api/health"):
        status, payload = call(server, "GET", path)
        assert status == 200, path
        assert payload == {"status": "ok", "service": "api"}


def test_unknown_path_is_404(server: ThreadingHTTPServer) -> None:
    status, _payload = call(server, "GET", "/other")
    assert status == 404


def test_retranslate_success(server: ThreadingHTTPServer) -> None:
    status, payload = call(
        server, "POST", "/api/retranslate", json.dumps({"nodeIds": ["n-2", "n-1"]}).encode()
    )
    assert status == 200
    assert payload == {"ok": True, "changed": ["n-1", "n-2"], "revision": "rev-test"}


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        (b"not json", 400),
        (b'{"nodeIds": []}', 400),
        (b'{"nodeIds": "n-1"}', 400),
        (b'{"nodeIds": [1]}', 400),
        (b"[]", 400),
        (json.dumps({"nodeIds": ["bad"]}).encode(), 400),
    ],
)
def test_retranslate_bad_requests(
    server: ThreadingHTTPServer, body: bytes, expected_status: int
) -> None:
    status, payload = call(server, "POST", "/api/retranslate", body)
    assert status == expected_status
    assert payload is not None
    assert payload["ok"] is False


def test_retranslate_unknown_node_error_message(server: ThreadingHTTPServer) -> None:
    status, payload = call(
        server, "POST", "/api/retranslate", json.dumps({"nodeIds": ["bad"]}).encode()
    )
    assert status == 400
    assert payload is not None
    assert "not re-translatable nodes" in str(payload["error"])


def test_retranslate_uninitialized_workspace_is_409(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(missing, tmp_path / "d", tmp_path / "jobs")
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = call(
            httpd, "POST", "/api/retranslate", json.dumps({"nodeIds": ["n-1"]}).encode()
        )
        assert status == 409
        assert payload is not None
        assert "workspace not initialized" in str(payload["error"])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_retranslate_internal_error_is_500(server: ThreadingHTTPServer) -> None:
    status, payload = call(
        server, "POST", "/api/retranslate", json.dumps({"nodeIds": ["boom"]}).encode()
    )
    assert status == 500
    assert payload is not None
    assert "compile exploded" in str(payload["error"])


def test_retranslate_body_size_limit(server: ThreadingHTTPServer) -> None:
    big = json.dumps({"nodeIds": ["x" * (MAX_BODY_BYTES + 10)]}).encode()
    status, payload = call(server, "POST", "/api/retranslate", big)
    assert status == 413
    assert payload is not None
    assert payload["ok"] is False


def test_retranslate_wrong_method_is_405(server: ThreadingHTTPServer) -> None:
    status, payload = call(server, "PUT", "/api/retranslate", b"{}")
    assert status == 405
    assert payload is not None
    assert payload["ok"] is False


def _call_with_length(
    server: ThreadingHTTPServer, length: str, body: bytes
) -> tuple[int, dict[str, object] | None]:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.putrequest("POST", "/api/retranslate")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", length)
        connection.endheaders()
        if body:
            connection.send(body)
        response = connection.getresponse()
        payload = response.read()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed if isinstance(parsed, dict) else None
    finally:
        connection.close()


def test_retranslate_negative_content_length_is_400(server: ThreadingHTTPServer) -> None:
    status, payload = _call_with_length(server, "-1", b'{"nodeIds":["n-1"]}')
    assert status == 400
    assert payload is not None
    assert payload["ok"] is False


def test_retranslate_huge_content_length_is_413(server: ThreadingHTTPServer) -> None:
    status, payload = _call_with_length(server, "999999999999", b"{}")
    assert status == 413
    assert payload is not None
    assert payload["ok"] is False


def test_retranslate_declared_length_longer_than_body_times_out(
    server: ThreadingHTTPServer,
) -> None:
    status, payload = _call_with_length(server, "64", b'{"nodeIds":["n-1"]}')
    assert status == 408
    assert payload is not None
    assert payload["ok"] is False


def test_retranslate_missing_provider_is_503(server: ThreadingHTTPServer) -> None:
    status, payload = call(
        server, "POST", "/api/retranslate", json.dumps({"nodeIds": ["noconfig"]}).encode()
    )
    assert status == 503
    assert payload is not None
    assert payload["ok"] is False
    assert "provider" in str(payload["error"])


def test_retranslate_uses_published_workspace_and_checks_revision(tmp_path: Path) -> None:
    from paper_api.retranslate import handle_retranslate
    from pdf_pipeline.pipeline import (
        _publish_viewer_revision,  # pyright: ignore[reportPrivateUsage]
    )

    current = tmp_path / "imported"
    viewer = tmp_path / "data"
    revision = _publish_viewer_revision(
        viewer,
        mapping_text="{}",
        meta_text="{}",
        source_pdf=b"source",
        target_pdf=b"target",
        workspace_dir=current,
    )
    calls: list[tuple[Path, str]] = []

    def rerender(
        workspace: Path, *, viewer_data_dir: Path, node_ids: set[str], expected_revision: str
    ) -> list[str]:
        assert viewer_data_dir == viewer
        calls.append((workspace, expected_revision))
        return sorted(node_ids)

    status, _ = handle_retranslate(
        json.dumps({"nodeIds": ["new-node"], "revision": revision}).encode(),
        workspace=tmp_path / "old",
        data_dir=viewer,
        rerender=rerender,
    )
    assert status == 200
    assert calls == [(current.resolve(), revision)]
    status, _ = handle_retranslate(
        b'{"nodeIds":["new-node"],"revision":"stale"}',
        workspace=tmp_path / "old",
        data_dir=viewer,
        rerender=rerender,
    )
    assert status == 409
    assert len(calls) == 1
