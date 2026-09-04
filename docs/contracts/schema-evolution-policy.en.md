# Schema evolution policy

[中文](./schema-evolution-policy.md) | [English](./schema-evolution-policy.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §46; implementation constraints: [`schemas/AGENTS.md`](../../schemas/AGENTS.md).

## Version semantics

| Level | Meaning | Requirements |
| --- | --- | --- |
| PATCH | Add optional fields / bug fix | Backward compatible; `just schema` passes |
| MINOR | Add backward-compatible capability | Same; update fixtures |
| MAJOR | Breaking structural change | migration + fixture + compatibility test + ADR |

## Core schema scope

```text
PhysicalDocument
LayoutDocument
SemanticDocument
RenderDocument
Evidence
Mapping
```

Must be versioned, serializable, and language-neutral. Canonical format: JSON Schema.

## Generation and freshness

```text
Canonical schema → deterministic generator → Python / TypeScript / Rust bindings
```

Generated code must not be edited by hand. CI enforces freshness via `just generate-check`.

## Change workflow

1. Schema first, implementation second.
2. Update `schemas/` and `schemas/fixtures/` first.
3. Run `just generate` and `just schema`.
4. MAJOR changes require an ADR and a migration path.

## Roadmap cross-reference

Development order and exit gates: [`docs/development/roadmap.en.md`](../development/roadmap.en.md) Milestone 1 Phase 1.7, §10.
