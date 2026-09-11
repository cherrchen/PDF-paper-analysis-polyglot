# HTTP API

[中文](./api.md) | [English](./api.en.md)

The API application is a runtime entry point under `apps/api` (stdlib `ThreadingHTTPServer`; the repository deliberately has no web framework). Product HTTP contracts are **intentionally unresolved**; the only landed surface is the M6 reader API: `GET /api/health` and `POST /api/retranslate` (local re-render — see [`reader.en.md`](reader.en.md)). Business logic lives in `paper_api/retranslate.py`; `__main__` only wires routes.

When contracts exist they will live in `schemas/api/` as OpenAPI. `just schema` currently reports that no OpenAPI documents are defined.
