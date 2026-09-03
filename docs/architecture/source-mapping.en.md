# Source mapping

[中文](./source-mapping.md) | [English](./source-mapping.en.md)

Mapping architecture: [`document-architecture.en.md`](document-architecture.en.md) sections 18–21 and 33.

Three-layer mapping chain:

```text
PhysicalLayoutBinding → SourceAnchor → SourceSemanticBinding
```

Supports N Layout ↔ N Semantic (e.g. cross-column paragraphs). Bidirectional navigation uses semantic blocks such as Heading and Paragraph, not Section as the primary geometric unit.

v0.1 excludes character-level mapping. `SourceFragment` is `LayoutRegionRef` only.
