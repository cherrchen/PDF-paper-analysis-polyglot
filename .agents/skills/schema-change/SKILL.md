---
name: schema-change
description: Change canonical schemas and regenerate language bindings with compatibility checks.
---

# Schema change

## When to use

Any change to `schemas/` or to generated language bindings.

## Preconditions

Read `schemas/AGENTS.md`. Search Agent Notes for SemanticDocument and API contract decisions.

## Workflow

1. Modify the canonical schema, not language copies
2. Update schema fixtures
3. Regenerate bindings when a generator exists (`just generate`)
4. Review the generated diff; never hand-edit generated files
5. Run Python, TypeScript, and Rust checks
6. Run `just schema`
7. Update docs and Agent Notes if the contract changed

## Validation

`just schema` and `just generate-check`.

## Failure handling

Do not keep a hand-patched binding. Do not introduce Protobuf without a new architecture note.

## Documentation impact

Contract changes update `docs/architecture/semantic-document.md` or `docs/architecture/api.md`.
