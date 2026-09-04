# @paper/document-model

TypeScript bindings for the canonical document contracts (M1).

- `src/generated/schema.ts` — types generated from `schemas/*/schema.json` by `scripts/generate.py`. Never edit; freshness is enforced by `just generate-check`.
- `src/validate.ts` — runtime validation of documents against the canonical JSON Schemas (including cross-file `$ref`)
- `roundtrip.mjs` — CLI used by the cross-language roundtrip integration tests

Canonical shared contracts live in `schemas/`. Do not treat this package as an independent source of truth.
