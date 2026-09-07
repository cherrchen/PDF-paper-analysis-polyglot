# Agent Note: M5 Translation & Rendering Pipeline development plan

Status: proposed

[中文](./2026-09-07-m5-translation-rendering-pipeline.md) | [English](./2026-09-07-m5-translation-rendering-pipeline.en.md)

## Problem

The M4 semantic recovery baseline has landed (after two rounds of correctness repairs); the next stage is roadmap M5: upgrading from placeholder translation to genuinely reliable academic-paper translation with natural reflow. Current gaps:

- The translation layer is still the M2 dummy (`[TRANSLATED]` prefix): no real provider, no context, no terminology, no cache.
- RenderDocument only has HEADING/PARAGRAPH/FIGURE blocks; RenderProfile/RenderPolicy are hardcoded inside `compose_render_document`.
- TABLE/EQUATION/BIBLIOGRAPHY_ENTRY project to plain-text paragraphs as a fallback; figures render as an empty `\fbox` placeholder; RenderAnchor is a single-fragment hit point.
- The PRD v0.2 startup checklist flags the FR-PDF-002 (born-digital rejection path) gap.

M5 Exit Gate: real translation + complete academic content + natural LaTeX reflow + RenderAnchor for all major nodes.

## Proposal

Follow roadmap Phases 5.1–5.8 with the scope decisions confirmed with the product owner:

1. **Provider**: first real integration is an OpenAI-compatible Chat Completions HTTP adapter (configurable endpoint/API key/model; compatible with GLM/DeepSeek/Ollama/vLLM).
2. **Profile**: only the default `readable-single-column` profile plus the RenderPolicy system; `dense-two-column` and `source-derived` are out of scope (the latter is Post-Initial R2, PRD §23).
3. **M4 deferred items**: include the figure resource chain and LaTeX equation typesetting; 1 Layout→N Semantic (suggested for M7) and MathML are explicitly deferred.

### Phase 5.0 startup checks (done, commit 0ddb3df)

- `pdf_pipeline.physical.probe_input_capability`: any page with an effective text layer marks the document usable; a text-layer-less document raises a `ValueError` with a user-facing reason at the `run_pipeline` entry (FR-PDF-002).
- Regression guards for the never-translate-bibliography rule already exist (`test_translation.py::test_bibliography_entries_are_not_translated` and friends).

### Phase 5.1+5.6 schema 0.2.0 additive upgrade (in progress, uncommitted)

The working tree already holds uncommitted changes:

- `translation-layer` 0.1.0 → 0.2.0: TranslationEntry gains `providerModel`/`cacheKey`; top level gains `providerModel`/`terminologyRevision`/`terminology[]`; new `Term` (term/preferredTranslation/source/confidence/scope, source ∈ MANUAL/DERIVED/PROVIDER, scope ∈ DOCUMENT/SECTION).
- `render-document` 0.1.0 → 0.2.0: RenderProfile gains `columns`/`paperSize`/`fontSizePt`/`lineSpacingFactor`; RenderPolicy gains `floatTables`/`wideFigureHandling`/`tableOverflowHandling`/`longEquationHandling`/`captionPosition` (Wide variants are derived from policy, not separate IR types); new `RenderTableBlock` (table + caption + columnAlignments), `RenderEquationBlock` (equation), `RenderBibliographyBlock` (entries: semanticNodeId + RichText); RenderFigureBlock gains `resourceIds[]`.
- New `schemas/resources/` (ResourceDocument starting at 0.1.0, wrapping the common ResourceStore with a sourceFingerprint); registered in `scripts/generate.py`, `scripts/verify_schemas.py`, and `document_model/serialize.py` `_ROOT_MODELS`.
- Fixtures updated to 0.2.0 (translation-layer/render-document) and a new `schemas/fixtures/resources/embedded-image.valid.json`.
- Bindings regenerated (`scripts/generate.py`); **not yet run**: full `just schema` validation and downstream code adaptation (`paper_llm/translation.py` and `render_composer.py` still write `schemaVersion="0.1.0"` and will fail validation).

### Remaining phases (not started)

- **5.1 structured translation protocol**: upgrade the provider protocol from `translate(str) -> str` to `TranslationRequest` (node text + marks + context + terminology + locale) → `TranslationResult` (translation + placeholder receipt + confidence); placeholder protection covers CITATION/INLINE_EQUATION/FOOTNOTE_REFERENCE and all Figure/Table/Equation reference mark types; table cell translation aligns with FR-TRANS-001 (tree shape/relations unchanged).
- **5.2 translation context**: document metadata, section heading chain, neighbor paragraphs (truncated window), terminology injection; prompt assembly stays in the provider adapter (FR-PROVIDER-004).
- **5.3 terminology system**: candidate extraction → LLM-confirmed preferred translations (Source=DERIVED) → manual override file (Source=MANUAL); terminology updates bump `terminologyRevision`.
- **5.4 translation cache**: cache key = hash(node content, target locale, model, config, terminology revision); local persistence; single-paragraph re-translation without re-parsing the PDF (FR-TRANS-004/005).
- **5.5 OpenAI-compatible adapter**: httpx client + retry/timeout/error classification; missing placeholders degrade by dropping marks and recording an issue; CI uses a mock HTTP server, real-key smoke is marked slow.
- **5.6 RenderProfile/Policy parameterization**: `compose_render_document(semantic, translation, profile, policy)`, removing hardcoded values; the default profile is named `readable-single-column`; the `generic-academic.tex` template is parameterized.
- **5.7 LaTeX backend**: real tables (`TableContent.cells` → tabular, overflow degrades per policy without dropping content), equations (unicode/rawText → LaTeX math with a bounded deterministic conversion, falling back to `\text{}`; equations never enter translation, FR-EQ-004/005), figure resource chain (pypdfium2 embedded-image extraction → ResourceStore → fill `FigureResource.embeddedImageIds` → `\includegraphics`), bibliography (BIBLIOGRAPHY block → thebibliography or entry paragraphs), dual-hypertarget RenderAnchors (`<nodeId>` start + `<nodeId>:end` end) recovered as multi-fragment anchors.
- **5.8 acceptance**: goldens go through human-reviewed bless (never bend goldens to make tests pass); unit tests assert text spans and cross-layer bindings, not node counts; E2E dual-viewer navigation; Agent Notes (schema 0.2.0 upgrade, provider adapter, ResourceStore, RenderProfile/Policy, M5 landing) + current-state docs + roadmap status + CHANGELOG.

## Alternatives considered

- Upgrade the abstract interface only without a real provider: the Exit Gate "real translation" cannot be met; rejected.
- A vendor-specific SDK: violates provider agnosticism (FR-PROVIDER-001~004); the OpenAI-compatible HTTP surface has broader coverage.
- Implementing dense-two-column: adds M5 workload and test surface; the PRD Initial Product only accepts the default single column.
- Adding a resourceStore field to the frozen physical-document (which would also need a 0.2.0 bump): use a standalone ResourceDocument instead, touching zero frozen schemas.
- Including 1 Layout→N Semantic and MathML in M5: drifts from the translation+rendering theme; deferred (1→N suggested for M7).

## Acceptance criteria

- All four Exit Gate items green: real translation (mock-driven full chain + manual real-key smoke), complete academic content (real typesetting for figures/tables/equations/bibliography/footnotes), natural LaTeX reflow (single column, page count may change), RenderAnchor for all major nodes including cross-page multi-fragment.
- `just schema`, `just generate-check`, `just ci` pass; the additive upgrade is recorded in an Agent Note.
- FR-PDF-002: scanned/text-layer-less PDFs are explicitly rejected at the entry.
- BIBLIOGRAPHY_ENTRY is never re-admitted to the translatable set by the real provider (regression tests pass).

## Risks

- Insufficient fallback coverage of the unicode→LaTeX equation conversion → a `\text{}` raw-text fallback is designed in; content is never lost.
- Cross-platform determinism of figure resource extraction → resource byte fingerprints follow the existing PDF fingerprint remapping experience.
- The schema 0.2.0 upgrade is mid-flight (bindings regenerated, code not yet adapted) → the working tree cannot pass `just check` directly; finish the downstream `schemaVersion` adaptation first, then validate.
- Real LLM output is non-deterministic → golden/E2E all run on Dummy/mock; the real provider is a slow manual smoke only.

## Progress and handoff (as of 2026-09-07)

- Committed: `0ddb3df feat(m5): reject scanned PDFs at pipeline entry (FR-PDF-002)` (physical.py probe + pipeline entry + 5 unit tests, all green).
- Uncommitted (working tree): all schema 0.2.0 changes above + regenerated bindings. **First next step**: adapt `paper_llm/translation.py` and `render_composer.py` to `schemaVersion="0.2.0"`, run `just schema` + `just generate-check` + `just test-unit`, then commit as `feat(schema): bump translation-layer and render-document to 0.2.0`.
- Detailed phase plan, acceptance checklist, and test discipline are in the Proposal section above; implementation order is 5.1 → 5.2 → 5.3 → 5.4 → 5.5 → 5.6 → 5.7 → 5.8 (the 5.1 and 5.6 schema changes have been merged into this 0.2.0 upgrade).
