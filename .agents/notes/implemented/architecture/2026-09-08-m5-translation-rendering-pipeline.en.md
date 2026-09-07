# Agent Note: M5 Translation & Rendering Pipeline — Implemented

Status: implemented

[中文](./2026-09-08-m5-translation-rendering-pipeline.md) | [English](./2026-09-08-m5-translation-rendering-pipeline.en.md)

## Problem

After M4, the translation layer still used a dummy prefix and the render layer only had paragraph/heading/figure placeholders, which could not satisfy the M5 exit gate: real translation, full academic content typesetting, natural single-column reflow, and multi-fragment RenderAnchors for all major nodes.

## Decision

1. **Schema 0.2.0** (additive): terminology/providerModel/cacheKey on `translation-layer`; Profile/Policy parameters and TABLE/EQUATION/BIBLIOGRAPHY blocks on `render-document`; new `ResourceDocument`.
2. **Translation stack** (`paper_llm`): structured `TranslationRequest/Result`; `build_translation_contexts`; terminology discovery and `PAPER_TERMINOLOGY_FILE` overrides; JSONL translation cache; `OpenAICompatProvider` (httpx, env-configured); CI defaults to Dummy/mock.
3. **Render stack** (`pdf_pipeline`): `compose_render_document(..., profile, policy, resources)`; `resource_store` embedded-image extraction; `math_latex` unicode fallback; real LaTeX tables/equations/bibliography/`\includegraphics`; dual hypertarget RenderAnchors.
4. **Deferred**: 1 Layout→N Semantic (proposed M7), MathML, `dense-two-column` profile.

## Alternatives considered

- Vendor SDKs: violate Provider Agnostic — rejected.
- Silent recovery for scanned PDFs: rejected at pipeline entry per FR-PDF-002 (Phase 5.0).
- Embedding ResourceStore in frozen `physical-document`: rejected; standalone `ResourceDocument` instead.

## Consequences

- `run_pipeline` emits `resources.json` and image files under `out/resources/`.
- Real LLM use requires `PAPER_LLM_ENDPOINT` and related env vars; golden/E2E remain Dummy-driven for determinism.
- Equation unicode→LaTeX is a limited deterministic conversion; failures fall back to `\text{...}` without losing content.
- The earlier proposed plan note (`2026-09-07-m5-...`) remains as historical planning reference.

## Acceptance

- `just test-unit`, `just schema`, and `just generate-check` pass.
- Tier-1 smoke fixture compiles end-to-end; bibliography entries are not translated; table cells appear in TranslationLayer.
- `docs/architecture/rendering.en.md` updated to M5 current state.
