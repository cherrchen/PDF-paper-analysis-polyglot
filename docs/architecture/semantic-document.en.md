# SemanticDocument

[中文](./semantic-document.md) | [English](./semantic-document.en.md)

Semantic model definition: [`document-architecture.en.md`](document-architecture.en.md) sections 13–17.

Canonical contract location (implemented in M1): `schemas/semantic-document/schema.json` (version `0.1.0`). Related schemas: `schemas/common/`, `schemas/physical-document/`, `schemas/evidence/`, `schemas/layout-document/`, `schemas/mapping/`.

Key points:

- Tree + graph: `SemanticNode` parent-child; `SemanticRelation` for caption, citation, footnote, etc.
- Section and Heading are separate
- Block semantics → `SemanticNode`; inline semantics → `RichText` marks
- Forbidden: page, bbox, column, font size, and other layout information; `SemanticNode.attributes` is the only open location, and `document_model.validators.validate_layer_separation` recursively checks its nested objects
- `EquationContent` and formula Evidence must preserve at least one representation: LaTeX, MathML, Unicode/raw text, or a source preview; content-free formulas are invalid

The M4 recovery engine (`pdf_pipeline.semantic` + `sem_*` modules) produces:

- The DOCUMENT root's first child is FRONT_MATTER; below it a numbering-driven SECTION tree. HEADING level comes from the heading text pattern
- Paragraph merging consumes CONTINUATION edges; `attributes.layoutRegionIds` drives N Layout → 1 Semantic multi-fragment SourceAnchors. 1 Layout → N Semantic is not implemented
- Inline marks: `CITATION` / `FOOTNOTE_REFERENCE` / `INLINE_EQUATION`
- Failed recognition never loses content: tables fall back to line-major cells by default, equations keep rawText, unresolved citations stay as text and report Issues. `FigureResource.embeddedImageIds` stays empty until a ResourceStore exists
- After recovery, `pdf_pipeline.sem_validate` audits in document-tree order; findings land in `SemanticDocument.issues`
- Landing: [M4 Semantic Recovery Engine](../../.agents/notes/implemented/architecture/2026-09-06-m4-semantic-recovery-engine.en.md); review repairs: [M4 review repairs](../../.agents/notes/implemented/bug-fix/2026-09-06-m4-review-repairs.en.md)

See implemented note [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md).

Language packages may hold convenience types only after schemas land. They are not independent sources of truth: the Python binding lives in `packages/python/document-model` (generated Pydantic), the TypeScript binding in `packages/typescript/document-model` (generated types plus a runtime schema validator).
