# Schemas

Canonical owner of contracts shared between Python, TypeScript, and Rust.

- `semantic-document/` — JSON Schema for SemanticDocument
- `api/` — OpenAPI HTTP contracts, when they exist
- `fixtures/` — schema validation fixtures

Do not maintain independent authoritative models in language packages.

HTTP OpenAPI documents are not present yet. `just schema` reports that explicitly until `schemas/api/` contains a spec.

Generated language bindings, when introduced, must come from these schemas through one deterministic generator, must not be edited by hand, and must have a freshness check (`just generate-check`).
