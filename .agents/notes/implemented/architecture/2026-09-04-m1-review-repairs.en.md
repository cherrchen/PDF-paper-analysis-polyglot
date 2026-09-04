# Agent Note: M1 contract review repairs

Status: implemented

[中文](./2026-09-04-m1-review-repairs.md) | [English](./2026-09-04-m1-review-repairs.en.md)

## Problem

Review of `6948642..HEAD` found that the M1 exit gate did not hold: generated Pydantic models were looser than the JSON Schema; fixture IDs collided; claimed N→N and cross-page mappings were not actually covered; bundle reference checks missed dangling ids; `just generate-check` and Vale failed in CI; and Roadmap types `StructureCandidate`, `LayoutGroup`, and `RichText` were missing or unnamed.

## Decision

Complete the M1 contracts before M2 rather than deferring the gaps:

1. The Pydantic generator distinguishes omitted properties from JSON null, and emits `pattern`, `maxItems`, and numeric constraints on optional fields. The TypeScript runtime validator covers `maxItems` / `maxLength` / `exclusiveMaximum` as well.
2. Fixture IDs put the changing sequence in the trailing 26-character slice and fail on collision.
3. The mapping fixture covers cross-page N→1 with distinct page-1 and page-2 regions/spans, and connected N→N through a shared multi-fragment anchor.
4. `validate_bundle_references` checks `rootId`, relation endpoints, duplicate ids, and parent/children consistency.
5. `just generate` runs Ruff format on the Pydantic output so `just generate-check` matches `just fmt`.
6. Schemas gain `StructureCandidate` and `LayoutGroup`. `RichText` is the canonical name; `TextNodeContent` remains an alias.
7. Phase 1.2 "parse the same PDF twice" is JSON deserialization stability in M1; PDF-byte re-parse belongs to M2.1.
8. After the second review, Pydantic models use strict JSON primitive validation: JSON integers accept `2.0` but reject string and Boolean coercion. Optional properties expose the honest runtime type `T | None` while still rejecting explicit JSON `null`; generated files are checked by the strict Python type checker again.
9. Layer-responsibility validation normalizes camel-case forms such as `fontSize` and `pageBreak`, and recursively checks `SemanticNode.attributes`.
10. Bundle reference validation covers Physical page membership; Layout pages, bands, columns, groups, and reading flow; Evidence; Semantic inline marks; cross-document IDs; and per-document provenance stores. External M1 ResourceStore and RenderAnchor references are explicitly outside this function's resolvable scope.
11. Canonical-schema `anyOf` rules require `EquationContent` and `FormulaCandidate` to contain at least one representation or source preview, enforced by both Python and TypeScript runtimes.

Cross-link: [M1 Core Document Contracts](./2026-09-04-m1-core-document-contracts.en.md). The original decision stands; this note records the equivalence and completeness constraints added after review.

See [Schema version boundary before the first feature](../process/2026-09-04-pre-functional-schema-versioning.en.md) for the development-stage `0.1.0` compatibility freeze boundary.

## Alternatives considered

- Mark M1 incomplete and freeze the current tree: illegal ids, colliding identity, and fake N→N would leak into M2.
- Only document a scope cut in the Roadmap: that would drift from the frozen Document Architecture v0.1 vocabulary.
- Hand-edit generated Pydantic files: forbidden.

## Consequences

- Python, JSON Schema, and TypeScript reject illegal ids, `title=null`, 5-point quads, and negative `byteLength` the same way.
- Physical fixture object ids are unique; cross-page paragraph spans live on two pages.
- The CI docs job (`just generate-check` and `just docs`, including Vale) is reproducible locally.
- Generated Python models no longer rely on a type-checker exclusion or file-level type suppression; negative tests cover primitive coercion, empty formulas, and nested geometry.
- The bundle validator reports dangling IDs for references resolvable within an M1 bundle and explicitly documents the external resource/render-anchor boundary.
- M2 can depend on these five-layer contracts without first working around generator or fixture defects.
