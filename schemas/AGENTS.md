# Schemas

## Ownership

`schemas/` is the only canonical owner of cross-language contracts.

JSON Schema is the document-structure format. OpenAPI is the HTTP format. Do not introduce Protobuf until there is a genuine RPC or binary-contract need.

## Versioning

Compatibility freeze took effect at the M2 exit gate. Additive changes must bump MINOR; breaking changes require MAJOR, a migration, fixtures, compatibility tests, and an Agent Note. Adding `FOOTNOTE_REFERENCE` in M4 without a version bump is a recorded exception — later additive capabilities must not repeat it. See `docs/contracts/schema-evolution-policy.md` and the M4 review-repairs Agent Note.

## Generated bindings

Canonical schema → generator → Python / TypeScript / Rust models.

Generated output must be marked generated, produced by one deterministic generator, never edited by hand, and checked for freshness in CI.

Follow `.agents/skills/schema-change/SKILL.md`.

## Compatibility

Schema fixtures under `schemas/fixtures/` are the executable examples. `just schema` must stay green.
