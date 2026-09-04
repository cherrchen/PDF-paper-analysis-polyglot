# Parser adapter contract

[中文](./parser-adapter-contract.md) | [English](./parser-adapter-contract.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §4, §34–§43.

## Core rule

```text
Third-party parser output → Adapter → Evidence → Internal Recovery → Our Document Model
```

Parser output is **never** a LayoutDocument or SemanticDocument.

## Adapter responsibilities

Every adapter must:

1. Map provider-specific output to unified `Evidence` and subtypes (`RegionCandidate`, `TableCandidate`, etc.).
2. Record `ProvenanceRecord` (producer, version, operation, input_refs).
3. Preserve original confidence and geometry for Recovery to consume.
4. Not leak provider schema types to upstream consumers.

## Capability ownership

Parsers register by capability. Do not run the full ensemble by default. Authoritative assignment: Document Architecture §35 Capability Registry.

## Conflict resolution

Simple majority vote is forbidden. Use Capability Authority, Confidence, Geometry Consistency, Cross-source Evidence, and Internal Rules (§43).

## Upgrade policy

Dependency upgrades require upgrade branch → adapter compatibility → benchmark → regression report → decision. See [`docs/development/roadmap.en.md`](../development/roadmap.en.md) §11.
