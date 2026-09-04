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

See implemented note [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.en.md).

Language packages may hold convenience types only after schemas land. They are not independent sources of truth: the Python binding lives in `packages/python/document-model` (generated Pydantic), the TypeScript binding in `packages/typescript/document-model` (generated types plus a runtime schema validator).
