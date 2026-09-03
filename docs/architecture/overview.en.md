# Architecture overview

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

SemanticDocument is the canonical semantic model. LaTeX is the rendering representation. LuaLaTeX is the engine.

Product stages above the rendering backend are not implemented yet. Unresolved design is recorded in proposed Agent Notes, not in this page.
