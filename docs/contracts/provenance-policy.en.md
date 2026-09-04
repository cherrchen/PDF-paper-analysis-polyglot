# Provenance policy

[中文](./provenance-policy.md) | [English](./provenance-policy.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §22–§23.

## First-class requirement

Every extraction, inference, and generation step must be traceable. `ProvenanceRecord` includes at minimum:

```text
id
producer / producer_version
operation
input_refs
parameters_hash (optional)
```

## Origin semantics

Every result must declare an origin kind:

```text
SOURCE
EXTRACTED
INFERRED
GENERATED
USER
```

LLM-generated content ≠ paper source content. AnalysisLayer must not pollute the source SemanticDocument.

## Attachment rules

These objects should carry `provenance_ids` (or equivalent references):

- Evidence and LayoutRegion
- SemanticNode and SemanticRelation
- TranslationEntry
- SourceAnchor

## Recovery observability

Recovery engines emit confidence, provenance, reason, and issues. Opaque inference without a provenance chain is forbidden.
