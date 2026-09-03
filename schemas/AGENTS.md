# Schemas

## Ownership

`schemas/` is the only canonical owner of cross-language contracts.

JSON Schema is the document-structure format. OpenAPI is the HTTP format. Do not introduce Protobuf until there is a genuine RPC or binary-contract need.

## Versioning

Additive changes should be backward compatible within a major version. Breaking changes require a schema version change, language package updates, and an Agent Note.

## Generated bindings

Canonical schema → generator → Python / TypeScript / Rust models.

Generated output must be marked generated, produced by one deterministic generator, never edited by hand, and checked for freshness in CI.

Follow `.agents/skills/schema-change/SKILL.md`.

## Compatibility

Schema fixtures under `schemas/fixtures/` are the executable examples. `just schema` must stay green.
