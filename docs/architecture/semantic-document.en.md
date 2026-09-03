# SemanticDocument

[中文](./semantic-document.md) | [English](./semantic-document.en.md)

Semantic model definition: [`document-architecture.en.md`](document-architecture.en.md) sections 13–17.

Canonical contract location (to be implemented): `schemas/semantic-document/` and related physical, layout, mapping, and evidence schemas.

Key points:

- Tree + graph: `SemanticNode` parent-child; `SemanticRelation` for caption, citation, footnote, etc.
- Section and Heading are separate
- Block semantics → `SemanticNode`; inline semantics → `RichText` marks
- Forbidden: page, bbox, column, font size, and other layout information

See implemented note [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md).

Language packages may hold convenience types only after schemas land. They are not independent sources of truth.
