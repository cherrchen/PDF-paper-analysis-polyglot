# HTTP API

[中文](./api.md) | [English](./api.en.md)

The API application is a runtime entry point under `apps/api` (stdlib `ThreadingHTTPServer`; the repository deliberately has no web framework). Product HTTP contracts are **intentionally unresolved**, but these endpoints have landed: the M6 reader API (see [`reader.en.md`](reader.en.md)) and the M8 batch B Job API (record format and state machine in [`storage.en.md`](storage.en.md), "Jobs and job records"). Business logic lives in `paper_api/retranslate.py` and `paper_api/jobs.py`; `__main__` only wires routes.

| Path | GET | POST | PUT / DELETE / PATCH |
| --- | --- | --- | --- |
| `/`, `/health`, `/api/health` | 200 `{"status":"ok","service":"api"}` | 404 | 404 |
| `/api/retranslate` | 405 | 200 / 400 / 408 / 409 / 413 / 503 | 405 |
| `/api/jobs` | 200 list | 202 submit (400 / 413 / 500) | 405 |
| `/api/jobs/<id>` | 200 / 404 | 405 | 405 |
| `/api/jobs/<id>/retry` | 405 | 202 / 404 / 409 | 405 |
| any other path | 404 | 404 | 404 |

- `/api/jobs` submission body: `source` and `workspace` required, `viewerDataDir` optional (omitted or `null` ⇒ the server's own `--data-dir`, the directory the local viewer reads — M8 batch F); an explicit value and the other two fields must be **absolute paths**, and `source` must already exist (otherwise 400). Success is `202 {"ok": true, "job": <record>}` with `job.status == "queued"`, `job.attempt == 1`, and the record carrying the **effective** `viewerDataDir`.
- `/api/jobs/<id>/retry` reads no body; a non-`failed` job returns `409` and an unknown id returns `404`.
- The body limit is shared with `/api/retranslate` (`MAX_BODY_BYTES`, 4096); over it returns 413.
- On method/path mismatch: a known path gives `405 {"ok": false, ...}`, an unknown path gives `404`.
- Every endpoint imports `pdf_pipeline` lazily, so API startup does not load pdfium.

Command line: `python -m paper_api [--workspace DIR] [--data-dir DIR] [--jobs-root DIR] [--port N]`, where `--jobs-root` defaults to `.jobs`.

When broader contracts exist they will live in `schemas/api/` as OpenAPI. `just schema` currently reports that no OpenAPI documents are defined.
