# 架构总览

[中文](./overview.md) | [English](./overview.en.md)

权威基准：[**Document Architecture v0.1**](./document-architecture.md)（冻结契约）。

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

SemanticDocument 是语义真源。RenderDocument 是渲染中间表示。LaTeX 是渲染后端投影。LuaLaTeX 是引擎。

专题索引：[`pipeline.md`](pipeline.md)、[`pdf-ingestion.md`](pdf-ingestion.md)、[`source-mapping.md`](source-mapping.md)、[`semantic-document.md`](semantic-document.md)、[`rendering.md`](rendering.md)。
