# Agent Note: Product Requirements Document v0.2

Status: implemented

[中文](./2026-09-06-product-requirements-v02.md) | [English](./2026-09-06-product-requirements-v02.en.md)

## Problem

`docs/product/requirements.md` v0.1 left eight open product questions in §36 (scanned PDF, target two-column layout, bilingual PDF, figure internal text, references translation, SemanticDocument editing, translation provider positioning, runtime shape). Before M5 starts, Initial Product boundaries must be closed or architecture and milestones will keep drifting against unresolved requirements.

## Decision

1. PRD **v0.2** fully supersedes v0.1 as the sole source of truth for user requirements (`docs/product/requirements.md` + `requirements.en.md`).
2. All eight former §36 open questions are closed; summary decisions live in PRD §43 and §50.
3. Downstream architecture, schema, roadmap, and milestones treat v0.2 as the upstream constraint; on conflict, revise technical plans rather than silently changing product requirements.
4. This change is recorded as an explicit Requirements Change, continuing the process from [PRD v0.1 establishment](./2026-09-06-product-requirements.en.md).

### v0.2 confirmed Initial Product boundaries (summary)

| Topic | Initial Product |
| --- | --- |
| Input | Born-digital PDF only |
| Target layout | Default readable single column |
| Target content | Translation only |
| Viewer | Source / Target dual-document reading |
| Figures | Caption translatable; in-image text not translated; assets preserved |
| References | Not translated |
| SemanticDocument | Not user-editable; architecture reserves human correction |
| Translation | Provider agnostic; external services allowed |
| Runtime | Local-first |
| Server + Web | Post-Initial |

## Conflict review against existing design and implementation

Items are split into **must fix before M5** versus **align docs/plans now, implement later**. No large-scale refactor was requested.

### A. Must fix before M5 (implementation conflicts with v0.2)

The review also called excluding `BIBLIOGRAPHY_ENTRY` an M5 task, which conflicted with “must fix before M5.” That item landed before M5; see [References are not translated (FR-CITE-004)](../architecture/2026-09-06-bibliography-not-translated.en.md).

| Conflict | Evidence | Affected | Notes |
| --- | --- | --- | --- |
| References treated as translatable | `packages/python/llm/src/paper_llm/translation.py`: `TEXT_NODE_KINDS` included `BIBLIOGRAPHY_ENTRY`; `translate_document` prefixes reference entries with `[TRANSLATED]` | Translation layer (pre-M5) | **Resolved.** Violates PRD FR-CITE-004 / §43 “References not translated”. `BIBLIOGRAPHY_ENTRY` is now excluded from `TEXT_NODE_KINDS` with regression tests; this is not M5 scope. |

### B. Documentation and planning alignment (update docs now; code follows milestones)

| Conflict | Evidence | Affected | Notes |
| --- | --- | --- | --- |
| Roadmap M5 mentions `SourceDerivedProfile` | `docs/development/roadmap.md` next-step line | M5, R2 | v0.2 defers “inherit source layout characteristics” to Post-Initial (PRD §23, R2). M5 defaults to `readable-single-column`; `SourceDerivedProfile` is architectural reserve only. |
| Document Architecture does not stage OCR | `docs/architecture/document-architecture.en.md` §37 lists scanned PDF → OCR alongside born-digital paths without Post-Initial label | Architecture v0.1 | Architecture may keep extension paths but must state Initial Product does not support scanned input (PRD NG1, FR-PDF-002). |
| Roadmap corpus and M7 treat scanned PDF as first-class initial capability | `docs/development/roadmap.md` Phase 0.3, M7 Phase 7.3 | M0/M7 | Tier 4 scanned fixtures may remain **Post-Initial research placeholders** (`tests/fixtures/metadata/scanned-external.yaml`), not Initial Product input contract. |
| Born-digital input detection not implemented | No product-level rejection path for FR-PDF-002 | Pre-M5 product integration | Gap, not reverse implementation; Initial Product must reject scanned / no-text-layer PDFs clearly. |

### C. Already aligned or explicitly deferred (no refactor now)

| Topic | Status |
| --- | --- |
| Single-column target LaTeX | `templates/latex/generic-academic.tex` uses single-column `article`; matches FR-LAYOUT-004 |
| Translation-only, no bilingual PDF | Pipeline emits translation layer only; matches FR-OUTPUT-001 |
| Figure caption translatable | `TEXT_NODE_KINDS` includes `FIGURE_CAPTION` |
| Figure assets / in-image text | Asset chain still M5; not translating in-image text is product policy, not a conflict |
| Translation provider abstraction | `TranslationProvider` Protocol + `DummyTranslationProvider`; matches `FR-PROVIDER-*` |
| Source↔Target viewer | M2 walking skeleton validated dual-document semantic navigation; matches `FR-SYNC-*` / `FR-VIEW-*` |
| SemanticDocument not editable | No user edit UI; schema keeps stable IDs and provenance |
| Local-first, domain separate from UI | Core models in `schemas/`, `packages/python/`; `apps/` is thin shell |
| Bilingual PDF, figure internal translation, semantic editing, server deployment | PRD §44 Post-Initial; intentionally deferred |

## Alternatives considered

- Keep v0.1 and treat v0.2 as an appendix: creates dual sources of truth.
- Close the eight items only in the roadmap without bumping PRD version: cannot audit as a Requirements Change.
- Immediately refactor all code gaps: out of scope; only M5 blockers are flagged.

## Consequences

- All new plans, implementation decisions, and milestone acceptance use PRD v0.2 upstream.
- M5 kickoff checklist must cover: default single-column RenderProfile, born-digital input rejection (or equivalent UX). References-not-translated landed before M5; see [References are not translated (FR-CITE-004)](../architecture/2026-09-06-bibliography-not-translated.en.md).
- Architecture v0.1 and Roadmap v0.1 remain technical contract baselines; on product conflict, PRD v0.2 wins and alignment items are recorded.
- The “§36 must close” wording in [PRD v0.1 establishment](./2026-09-06-product-requirements.en.md) is superseded by this note.
