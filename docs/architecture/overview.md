# 架构总览

[中文](./overview.md) | [English](./overview.en.md)

```text
Source PDF
    │
    ▼
Document Extraction
    │
    ▼
Layout Analysis
    │
    ▼
SemanticDocument
    │
    ├────────► Analysis / LLM
    │
    ├────────► Translation
    │
    └────────► Rendering Projection
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

SemanticDocument 是语义真源。LaTeX 是渲染表示。LuaLaTeX 是引擎。

渲染后端之上的产品阶段尚未实现。未决设计记在 proposed Agent Note 中，不写在本页。
