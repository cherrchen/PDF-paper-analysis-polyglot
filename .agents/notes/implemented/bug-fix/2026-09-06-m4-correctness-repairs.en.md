# Agent Note: M4 second-review correctness repairs

Status: implemented

[中文](./2026-09-06-m4-correctness-repairs.md) | [English](./2026-09-06-m4-correctness-repairs.en.md)

## Problem

The second code review (at `0346fe6`) confirmed that M4 has the modules and that benchmarks pass, but that is not enough to claim the original nine phases are complete. The defects are dropped content, wrong associations, and tests that prove a node exists without proving it binds the right text:

1. RenderComposer skipped every `CAPTION_OF` source, and the TABLE branch never re-emitted the caption, so table titles vanished from the Render IR.
2. Dummy translation replaced `text` and copied `marks` unchanged; the fixed prefix already sent CITATION / FOOTNOTE_REFERENCE / INLINE_EQUATION at the wrong characters.
3. Footnotes accepted the first same-number digit in reading order, so `Table 1` stole the real `footnote1`; the validator reported zero issues.
4. Footnote labels were deduplicated for the whole document, so later pages reusing `1` or `*` could not link.
5. Unnumbered `HEADING_LIKE` lines were skipped before Abstract, so `Introduction` was swallowed into FRONT_MATTER as an author.
6. SemanticValidator walked the section tree without visit guards and raised `RecursionError` on a cycle.
7. The viewer read only `fragments[0]`, so later source regions of a cross-page paragraph had no click or highlight.
8. Semantic nodes always stored empty `provenanceIds`, with no recovery operation, producer version, or evidence chain.

The earlier [M4 review repairs](2026-09-06-m4-review-repairs.en.md) closed first-round exit-gate gaps (cross-page fixture, citation ranges, weak tests). Those repairs still stand. This note adds correctness and traceability. It does not rebuild the engine, and it does not reclassify deferred GROBID / 1 Layout→N Semantic / true multi-column tables as done.

## Decision

1. **Table titles:** only FIGURE consumes a bound caption; TABLE_CAPTION emits as its own paragraph. A cross-layer assertion requires the title text and node identity in the RenderDocument.
2. **Translation marks:** a fixed prefix shifts offsets; any other rewrite protects marked spans with placeholders and rebuilds them in the translated text; lost placeholders drop marks instead of copying stale source offsets.
3. **Footnotes:** identities are `(page, label)`; candidates are scored (letter-glue / PDFium space-before-superscript) and structural numbers such as `Table 1` are excluded; uncertain or unlinked cases report Issues.
4. **Front matter:** author lines need at least two name tokens; body headings such as `Introduction` are split from affiliations; an unnumbered heading with no abstract opens a SECTION.
5. **Validator:** detect cycles, parent/child consistency, and duplicate membership before heading-order checks; traversals use a visited set and return `SECTION_STRUCTURE` ERROR on a bad tree.
6. **Viewer:** walk every SourceAnchor fragment; `cross-page-paragraph` mapping and `buildPairs` regressions cover each source page region.
7. **Provenance:** each node and relation gets a `ProvenanceRecord` (producer / version / operation / inputRefs including layout regions and their fusion records); the document carries a `ProvenanceStore`.
8. **Status language:** README and the roadmap distinguish “baseline landed” from “all nine original phases complete.” Deferred work keeps a target milestone: 1→N and MathML/figure assets wait for M5; GROBID and true multi-column tables wait for M7.

## Alternatives considered

- Fold the table title into the TABLE paragraph block: before M5 real table typesetting that would glue cells to the title; an independent TABLE_CAPTION block keeps identity and anchors.
- Drop all marks on any real translation: a fixed prefix can shift safely, and placeholders keep citations; dropping everything would lose CITATION before M5.
- Require superscript font evidence before linking footnotes: PDFium dilutes font size across merged spans and would break the existing `footnote 1` fixtures.
- Mark M4 “not started” again: the modules and the N→1 cross-page contract still hold; what was missing was correctness repairs and honest deferral labels.

## Consequences

- The second review’s dropped-content, wrong-association, truncated-viewer, and empty-provenance defects are fixed. Tests now assert text spans and cross-layer integrity, not just node counts.
- The M4 baseline is usable. 1 Layout→N Semantic, GROBID author-year citations, true multi-column tables, figure PDF/SVG/raster assets, and MathML remain deferred per the landing note. The product-requirements directory is still a stub and cannot prove full product acceptance.
- This note supplements rather than replaces the [M4 Semantic Recovery Engine](../architecture/2026-09-06-m4-semantic-recovery-engine.en.md) and the [first-round review repairs](2026-09-06-m4-review-repairs.en.md).
