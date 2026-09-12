# Agent Note: Optional real parser dependencies

Status: implemented

[中文](./2026-09-12-optional-parser-adapters.md) | [English](./2026-09-12-optional-parser-adapters.en.md)

## Problem

PRD §34 requires MinerU / Docling / GROBID as Evidence Providers, but the dependency policy forbids installing heavy native libraries and unreproducible models by default. CI also cannot download multi-GB weights or start a Java service.

## Decision

1. **Default install unchanged.** `pdf-pipeline` still depends on `pypdfium2` at runtime. The default capability registry stays `mock` / `docling-sim` / `grobid-sim`.
2. **Real adapters are dump mappers.** `pdf_pipeline.evidence.mineru` / `docling` / `grobid` implement `EvidenceProvider` and map recorded native JSON/TEI into `EvidenceBundle`. CI fixtures live in `tests/fixtures/parser-dumps/`. Provider schemas must not leak.
3. **Live services are optional and env-driven.** `MINERU_CMD` / `DOCLING_CMD` emit JSON from `PAPER_SOURCE_PDF`; `GROBID_URL` HTTP-POSTs the same PDF as `multipart/form-data` with field `input`. Unconfigured `collect()` fails with dump instructions. The `pdf-pipeline` extras `[mineru]` / `[docling]` / `[grobid]` are group names only; they do not pull MinerU/Docling/Torch/GROBID into the lockfile or required extras. Docling dumps must convert `coord_origin` and consume `table_cells`; MinerU formula IDs include the page. Contract tests: [M8-pre review repairs](../bug-fix/2026-09-12-m8-pre-review-repairs.en.md).
4. **Upgrades still follow roadmap §11.** Switching a registry primary to `mineru`/`docling`/`grobid` requires a benchmark; adapters existing is not enough to replace the production provider.

## Alternatives considered

- Install MinerU/Docling/GROBID as default dependencies: violates the heavy-native Agent Note reproducibility rule and breaks CI.
- Keep sims only and skip native mapping: the PRD §34 adapter boundary could not be tested without models.

## Consequences

- `build_provider("mineru"|"docling"|"grobid")` instantiates; default `route_providers` still selects sim names.
- The live path is a local experiment, not a CI gate.
- The synthetic-dump adapter → normalize/fusion → semantic chain is tested; on 2026-09-12 no real-tool output was available. Gap: [M8 admission closeout](../process/2026-09-12-m8-admission-closeout.en.md).
