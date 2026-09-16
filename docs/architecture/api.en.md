# HTTP API

[中文](./api.md) | [English](./api.en.md)

The API application is a runtime entry point under `apps/api` (stdlib `ThreadingHTTPServer`; the repository deliberately has no web framework). Product HTTP contracts are **intentionally unresolved**, but these endpoints have landed: the M6 reader API (see [`reader.en.md`](reader.en.md)) and the M8 batch B Job API (record format and state machine in [`storage.en.md`](storage.en.md), "Jobs and job records"). Business logic lives in `paper_api/retranslate.py`, `paper_api/jobs.py`, `paper_api/workspaces.py`, `paper_api/uploads.py`, and `paper_api/status.py`; `__main__` only wires routes.

| Path | GET | POST | PUT / DELETE / PATCH |
| --- | --- | --- | --- |
| `/`, `/health`, `/api/health` | 200 `{"status":"ok","service":"api"}` | 404 | 404 |
| `/api/retranslate` | 405 | 200 / 400 / 408 / 409 / 413 / 503 | 405 |
| `/api/jobs` | 200 list | 202 submit (400 / 413 / 500) | 405 |
| `/api/jobs/<id>` | 200 / 404 | 405 | 405 |
| `/api/jobs/<id>/retry` | 405 | 202 / 404 / 409 | 405 |
| `/api/workspaces` | 200 list | 405 | 405 |
| `/api/workspaces/open` | 405 | 200 / 400 / 404 / 500 | 405 |
| `/api/uploads` | 405 | 200 / 400 / 413 | 405 |
| `/api/status` | 200 | 405 | 405 |
| any other path | 404 | 404 | 404 |

- `/api/jobs` submission body: `source` and `workspace` required, `viewerDataDir` optional (omitted or `null` ⇒ the server's own `--data-dir`, the directory the local viewer reads — M8 batch F); an explicit value and the other two fields must be **absolute paths**, and `source` must already exist (otherwise 400). Success is `202 {"ok": true, "job": <record>}` with `job.status == "queued"`, `job.attempt == 1`, and the record carrying the **effective** `viewerDataDir`.
- `/api/jobs/<id>/retry` reads no body; a non-`failed` job returns `409` and an unknown id returns `404`.
- `GET /api/workspaces`: `200 {"ok": true, "workspaces": [...]}`; each item is a workspace summary (`name` / `path` / `workspaceVersion` / `stages` (all eight stage names present, a missing record reads `pending`) / `complete` / `updatedAt` / `error`) plus `publication.current` (whether that workspace is the one the current manifest is bound to). The listing enumerates `discover_workspaces()`: `<jobs-root>/workspaces/*/workspace.json` plus the API's own workspace, newest manifest mtime first. A broken manifest never raises — it only makes that row's `error` non-null and `complete` false.
- `POST /api/workspaces/open`: body `{"workspace": "<absolute path>"}`; invalid JSON, a missing field, or a non-absolute path is 400; a directory without `workspace.json` returns 404; an unreadable workspace (missing or corrupt manifest, unsupported version, source-PDF mismatch, uncommitted stages) returns 400; any other exception returns 500; success is `200 {"ok": true, "revision": <id>}`. The server republishes that workspace's **already-committed artifacts** as-is into its own `--data-dir` (`republish_workspace_viewer`: no stage runs, nothing written into the workspace), see [storage](storage.en.md#demo-console).
- `POST /api/uploads`: the body is the PDF bytes, capped at `MAX_UPLOAD_BYTES` (64 MiB); `X-Upload-Name` is required and must end in `.pdf` (a missing header or a non-PDF name is 400); a declared `Content-Length` over the cap returns 413 without reading the body; the first 5 received bytes must be `%PDF-` and the total must not be 0 (otherwise 400). Success is `200 {"ok": true, "path": <absolute inbox path>, "workspace": <server-derived absolute workspace path>, "bytes": <n>, "sha256": <hex>}`; both the filename and the workspace name derive from the file-name slug plus the first 8 digits of the content digest, so re-uploading the same name with identical bytes reuses one file and one workspace.
- `GET /api/status`: `200 {"ok": true, "api": <health payload>, "worker": {...}, "jobs": {...}, "viewer": {...}}`. `worker` always carries the keys `present` / `alive` / `pid` / `startedAt` / `updatedAt` / `ageSeconds` / `concurrency` / `running` (a missing or unparsable heartbeat leaves them `null`, except `running`, which is always an integer), and `alive` means the heartbeat age is `<= HEARTBEAT_STALE_S` (15 s). `jobs` holds the `queued` / `running` / `succeeded` / `failed` counts plus `oldestQueuedAt` (`null` when nothing is queued). `viewer` takes `revision` and `workspace` from the current manifest and is `null` when that manifest is missing or broken.
- Read/write boundary: clients name only **read sources**. The workspace path in `POST /api/workspaces/open` and the bytes in `POST /api/uploads` decide only what is read; every write target is server-owned — `--data-dir` (the viewer data directory) and `<jobs-root>/inbox` (the upload inbox). This is the same rule as `/api/retranslate` resolving its document from the current binding instead of accepting a client write path.
- The JSON body limit is shared with `/api/retranslate` (`MAX_BODY_BYTES`, 4096) and over it returns 413; `/api/uploads` does not use that path (it streams and has its own 64 MiB cap).
- On method/path mismatch: a known path gives `405 {"ok": false, ...}`, an unknown path gives `404`.
- Every endpoint imports `pdf_pipeline` lazily, so API startup does not load pdfium.

Command line: `python -m paper_api [--workspace DIR] [--data-dir DIR] [--jobs-root DIR] [--port N]`, where `--jobs-root` defaults to `.jobs`.

When broader contracts exist they will live in `schemas/api/` as OpenAPI. `just schema` currently reports that no OpenAPI documents are defined.

## Retranslation document binding

The browser submits `{nodeIds, revision}` to `/api/retranslate`. The server resolves the workspace binding from the current Viewer manifest, so importing a second document requires no API restart. Clients do not submit a workspace path. An invalid revision type returns 400. A stale revision, including a competing publication during computation, returns 409; the latter commits no workspace updates from this request. Legacy clients may omit revision; manifests without a workspace binding fall back to the startup `--workspace`. Locking and publication contracts: [storage](storage.en.md).
