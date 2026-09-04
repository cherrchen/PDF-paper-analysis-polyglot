# Agent Note: M1 Core Document Contracts

Status: implemented

[中文](./2026-09-04-m1-core-document-contracts.md) | [English](./2026-09-04-m1-core-document-contracts.en.md)

## Problem

Document Architecture v0.1 was frozen, but the core contracts existed only as prose: `schemas/` held a single `0.0.0-unresolved` SemanticDocument placeholder, the Python/TypeScript packages had no real models, and the generator had no registered generators. M1 (Core Document Contracts) requires freezing the Physical / Evidence / Layout / Semantic / Mapping schemas and establishing cross-language consistency and layer-responsibility checks.

## Decision

All seven M1 phases are complete:

1. **Six canonical JSON Schemas** (`schemas/<name>/schema.json`, version `0.1.0`):
   - `common` — ID types (ULID/UUID pattern), Provenance, Origin, Resource, Issue, Geometry (Rect/Quad/Polygon), Matrix, LayoutLabel
   - `physical-document` — pages, TextSpan, ImageObject, VectorObject, LinkObject, Canonical Page Space
   - `evidence` — RegionCandidate, TableCandidate, FormulaCandidate, MetadataCandidate; extra keys forbidden so provider payloads cannot leak, native labels preserved in `providerLabel`
   - `layout-document` — LayoutRegion, PageBand, Column, ReadingFlowGraph (graph is source of truth, `primaryFlow` derived), ReadingOrderReason
   - `semantic-document` — SemanticNode (tree) + SemanticRelation (graph), RichText/InlineMark, NodeContent (text/figure/table/equation); replaces the placeholder
   - `mapping` — PhysicalLayoutBinding, SourceAnchor (v0.1 LayoutRegionRef fragments only), SourceSemanticBinding, RenderAnchor/RenderBinding
2. **Deterministic generator** `scripts/generate.py` (`just generate` / `just generate-check`): emits TS types (`packages/typescript/document-model/src/generated/schema.ts`) and Pydantic models (`packages/python/document-model/src/document_model/generated/schema_models.py`). All `$defs` names are globally unique across schemas, so both sides use flat namespaces. Generated files must never be hand-edited; CI enforces freshness.
3. **TS runtime validator** `packages/typescript/document-model/src/validate.ts`: validates documents against the canonical JSON Schema files at runtime (covering the JSON Schema subset the canonical schemas use, including cross-file `$ref`), so generated types cannot drift from the contract.
4. **Python helpers**: `document_model.ids` (ULID-style opaque IDs), `document_model.serialize` (`dump_document`/`load_document`), `document_model.validators` (layer-separation checks + bundle reference integrity).
5. **Fixtures** (`schemas/fixtures/`, deterministically produced by `scripts/build_fixtures.py`): Physical/Layout documents with a two-column page, spanning figure and footnote; a Semantic document with every required NodeKind; mock-provider Evidence; a Mapping covering N→1, 1→N, and N→N scenarios.
6. **Cross-language roundtrip integration test** `tests/integration/test_cross_language_roundtrip.py`: Python serialize → JSON → TS validate/re-serialize → Python parse, semantically identical; the TS side rejects geometry entering the semantic layer.

## Alternatives considered

- Hand-written Pydantic models and TS types: guaranteed drift from the canonical schema; violates Schema first.
- Third-party generators (datamodel-code-generator, json-schema-to-typescript): heavy dependencies with uncontrollable output; the schema surface is small, so a self-contained deterministic generator is more maintainable.
- Pydantic discriminated unions for `oneOf`: union variants already carry Literal discriminator fields, so plain union aliases validate identically to the JSON Schema at document level.
- RenderDocument schema: designed in §25–§32 of the architecture doc, but M1 scope covers five layers only; freezing the Render schema is deferred to the M2 RenderAnchor work.

## Consequences

- All five M1 exit-gate conditions hold: core schemas versioned (`0.1.0`), roundtrip stable, third-party parser schemas cannot leak (EvidenceBundle `additionalProperties: false` locked by tests), layer-responsibility tests complete, mapping many-to-many verified (three scenario fixtures + tests).
- `just schema` validates the six schemas and all fixtures; `just generate-check` locks generated-file freshness; `just test-integration` requires `node` on PATH (already mandatory since M0).
- `SemanticNode.attributes` is the only `additionalProperties: true` location (open attribute bag); the layer boundary is enforced at document level by `document_model.validators.validate_layer_separation` (bbox/page/column keys in the semantic layer are flagged).
- M2 Walking Skeleton can now build the minimal PDF backend, layout/semantic recovery, and rendering directly on these five Pydantic/TS models.
