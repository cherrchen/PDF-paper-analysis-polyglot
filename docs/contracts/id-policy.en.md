# ID strategy

[中文](./id-policy.md) | [English](./id-policy.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §47; identity model: [`docs/architecture/source-mapping.en.md`](../architecture/source-mapping.en.md).

## Core ID types

```text
NodeID          — stable SemanticNode identity across representations
RegionID        — layout region
AnchorID        — source / render anchor
EvidenceID      — evidence entry
ResourceID      — images, fragments, and other assets
DocumentID      — document and bundle
ProvenanceID    — provenance record
```

## Persistent identity rules

- Use opaque persistent IDs (UUIDv7 / ULID recommended).
- Do not use `paragraph_1`, `paragraph_2`, etc. as persistent identity.
- Cross-representation stable identity is `SemanticNodeID`, not page number, bbox, or paragraph index.

## Reconciliation

Keep `source_fingerprint` for ID reconciliation on re-parse. IDs do not perform semantic matching by themselves.

## Mapping identity

SourceAnchor ↔ SemanticNode ↔ RenderAnchor uses bindings with many-to-many relationships, not page correspondence.
