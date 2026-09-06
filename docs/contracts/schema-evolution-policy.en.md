# Schema evolution policy

[中文](./schema-evolution-policy.md) | [English](./schema-evolution-policy.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §46; implementation constraints: [`schemas/AGENTS.md`](../../schemas/AGENTS.md).

## Version semantics

| Level | Meaning | Requirements |
| --- | --- | --- |
| PATCH | Add optional fields / bug fix | Backward compatible; `just schema` passes |
| MINOR | Add backward-compatible capability | Same; update fixtures |
| MAJOR | Breaking structural change | migration + fixture + compatibility test + ADR |

## Compatibility freeze boundary

Before the first runnable end-to-end feature exists, `0.1.0` is a development target rather than a published compatibility promise. During that stage, breaking schema corrections may retain `0.1.0`, but the canonical schemas, fixtures, generated bindings, and cross-language tests must change atomically.

**The freeze is in effect.** After the M2 Walking Skeleton passed its exit gate, the version semantics above protect stored data and consumers. Additive capabilities must bump MINOR. Breaking changes must bump MAJOR and provide a migration, fixtures, compatibility tests, and an Agent Note.

Adding `FOOTNOTE_REFERENCE` to `InlineMarkType` in M4 without a version bump is a recorded post-freeze exception (MINOR-class additive enum). Later additive changes must not repeat it. See the [M4 review-repairs note](../../.agents/notes/implemented/bug-fix/2026-09-06-m4-review-repairs.en.md).

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
