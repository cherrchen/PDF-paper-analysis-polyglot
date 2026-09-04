# Contract index

[中文](./README.md) | [English](./README.en.md)

This directory indexes cross-language contracts and governance policies. Full model definitions live in [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md); machine-readable schemas live under `schemas/`. Do not duplicate full schema bodies here.

## Document model contracts

| Contract | Authoritative location | Responsibility summary |
| --- | --- | --- |
| Document Architecture v0.1 | [`document-architecture.en.md`](../architecture/document-architecture.en.md) | Compiler-style pipeline, bundle structure, all layers |
| PhysicalDocument | same §3 | Objective PDF content: pages, text spans, images, vectors, links |
| Evidence | same §4 | Third-party parser output; must not leak into Layout/Semantic |
| LayoutDocument | same §5–§8 | Visual regions, columns, reading order; no paper semantics |
| SemanticDocument | same §13–§17 | Logical structure; no page geometry |
| Mapping | same §18–§21 | Physical↔Layout↔Semantic↔Render bindings |
| RenderDocument | same §25–§32 | Rendering intermediate representation and RenderAnchor |

## Governance policies

| Policy | Document |
| --- | --- |
| Layer responsibility boundaries | [`layer-responsibility.en.md`](layer-responsibility.en.md) |
| Parser adapter | [`parser-adapter-contract.en.md`](parser-adapter-contract.en.md) |
| Schema evolution | [`schema-evolution-policy.en.md`](schema-evolution-policy.en.md) |
| Provenance | [`provenance-policy.en.md`](provenance-policy.en.md) |
| ID strategy | [`id-policy.en.md`](id-policy.en.md) |

## Architecture decisions

ADRs and implemented decisions: [`docs/decisions/`](../decisions/README.en.md) and `.agents/notes/`.

## Schema source of truth

JSON Schemas live under `schemas/`. Generated bindings and compatibility checks: [`schemas/AGENTS.md`](../../schemas/AGENTS.md) and `just schema`.
