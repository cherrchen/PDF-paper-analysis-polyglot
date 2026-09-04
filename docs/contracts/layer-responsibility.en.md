# Layer responsibility boundaries

[中文](./layer-responsibility.md) | [English](./layer-responsibility.en.md)

Authoritative definition: [`docs/architecture/document-architecture.en.md`](../architecture/document-architecture.en.md) §1, §3, §5, §13, §25.

## Four-layer model

| Layer | Question it answers | Must not contain |
| --- | --- | --- |
| PhysicalDocument | What objectively exists in the PDF | Reading-order inference, section semantics |
| LayoutDocument | How the page is visually organized | Semantic labels such as `method_section = true` |
| SemanticDocument | What the document logically is | `bbox`, `page`, `column` |
| RenderDocument | How target content is presented | Hard source-PDF layout contract |

## Permanent prohibitions

```text
SemanticParagraph.bbox / .page / .column
LayoutRegion.method_section = true
```

## Cross-layer links

Layers connect only through Binding / Anchor mappings. They do not share implementation types. Page numbers and bboxes are not persistent SemanticNode identity.

## Evidence and derived layers

- Third-party parser output is Evidence only, entering internal Recovery through adapters.
- Translation / Analysis / Annotation are derived layers; they do not mutate the source SemanticDocument.
- Source layout is evidence for understanding, not a rendering contract for the translated PDF.
