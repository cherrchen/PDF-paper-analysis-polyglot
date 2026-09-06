# Agent Note: References are not translated (FR-CITE-004)

Status: implemented

[中文](./2026-09-06-bibliography-not-translated.md) | [English](./2026-09-06-bibliography-not-translated.en.md)

## Problem

PRD v0.2 FR-CITE-004 requires that **References are not translated** in the Initial Product. M4 widened `paper_llm.TEXT_NODE_KINDS` to include `BIBLIOGRAPHY_ENTRY` so the target PDF would not drop the bibliography, and the Walking Skeleton therefore prefixed reference entries with `[TRANSLATED]`.

[Product Requirements Document v0.2](../process/2026-09-06-product-requirements-v02.en.md) flagged this as “must fix before M5” and also wrote “M5 must exclude `BIBLIOGRAPHY_ENTRY`.” The second wording deferred the fix into M5, which conflicts with the first: the live pipeline already translates references.

## Decision

1. **Now, before M5**, exclude `BIBLIOGRAPHY_ENTRY` from `TEXT_NODE_KINDS`. This is not an M5 task; the real M5 provider must not put bibliography entries back into the translatable set.
2. RenderComposer still projects `BIBLIOGRAPHY_ENTRY` as paragraphs. With no TranslationEntry it falls back to SemanticDocument source text, so the target PDF still keeps the bibliography.
3. Regression tests lock the policy: schema-fixture and recovered `bibliography` entries must not enter the TranslationLayer; RenderDocument entry text equals the source and contains no `[TRANSLATED]`.
4. This note partially supersedes clause 10 of [M4 Semantic Recovery Engine](./2026-09-06-m4-semantic-recovery-engine.en.md) (“BIBLIOGRAPHY_ENTRY is translatable”); the render fallback (do not drop content) still holds.

## Alternatives considered

- Wait for M5: the dummy path already violates FR-CITE-004, so pre-M5 viewer / golden / end-to-end artifacts would carry a false prefix.
- Still write a TranslationLayer entry and swap back at render time: the layer would be a fake translation, and the viewer or analysis layer would treat it as translated.
- Skip only the `BIBLIOGRAPHY` container: the container has no body text; the translatable kind is `BIBLIOGRAPHY_ENTRY`.

## Consequences

- Dummy translation and later real providers skip reference entries; a “References” section heading remains a translatable `HEADING`.
- Conflict-review item A in [Product Requirements Document v0.2](../process/2026-09-06-product-requirements-v02.en.md) is closed; the M5 kickoff checklist no longer treats “exclude reference translation” as outstanding work.
