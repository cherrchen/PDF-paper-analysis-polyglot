# Architecture overview

[中文](./overview.md) | [English](./overview.en.md)

Authoritative baseline: [**Document Architecture v0.1**](./document-architecture.en.md) (frozen contract).

```text
Source PDF
    │
    ▼
PhysicalDocument
    │
    ▼
Evidence → Layout Recovery
    │
    ▼
LayoutDocument
    │
    ▼
Semantic Recovery
    │
    ▼
SemanticDocument
    │
    ├────────► Translation / Analysis / Annotation
    │
    └────────► RenderComposer
                        │
                        ▼
                 RenderDocument
                        │
                        ▼
                      LaTeX
                        │
                        ▼
                    LuaLaTeX
                        │
                        ▼
                 Translated PDF
```

SemanticDocument is the semantic source of truth. RenderDocument is the rendering intermediate representation. LaTeX is the rendering backend projection. LuaLaTeX is the engine.

Topic index: [`pipeline.en.md`](pipeline.en.md), [`pdf-ingestion.en.md`](pdf-ingestion.en.md), [`source-mapping.en.md`](source-mapping.en.md), [`semantic-document.en.md`](semantic-document.en.md), [`rendering.en.md`](rendering.en.md). Development roadmap: [`../development/roadmap.en.md`](../development/roadmap.en.md).
