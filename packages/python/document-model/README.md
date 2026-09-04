# document-model (Python)

Python bindings for the canonical document contracts (M1): generated Pydantic models plus runtime helpers.

- `src/document_model/generated/` — Pydantic models generated from `schemas/*/schema.json` by `scripts/generate.py`. Never edit; freshness is enforced by `just generate-check`.
- `ids.py` — ULID-style opaque ID generation and the canonical `SCHEMA_VERSION`
- `serialize.py` — `dump_document` / `load_document` serialization helpers
- `validators.py` — layer-separation and bundle reference-integrity checks

The canonical shared contracts live in `schemas/`. Do not make this package an independent source of truth.
