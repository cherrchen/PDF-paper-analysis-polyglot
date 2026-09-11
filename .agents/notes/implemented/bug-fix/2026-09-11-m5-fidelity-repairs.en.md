# Agent Note: M5 fidelity and configuration repairs

Status: implemented

[中文](./2026-09-11-m5-fidelity-repairs.md) | [English](./2026-09-11-m5-fidelity-repairs.en.md)

## Problem

The 2026-09-11 audit kept M5 as a landed baseline but refused the full “reliable translation, complete academic content, natural reflow” gate. Layering is sound; the gaps are fidelity, hostile input, and policy follow-through: illegal scripts and unescaped `$` can fail a whole PDF; `√x` becomes `\sqrt{}x`; a Figure with several bound images renders only the first; an injected `httpx.Client` is closed after the first request; placeholder checks miss duplicates and still cache the result; cache keys omit endpoint, context, and prompt version; some `RenderPolicy` enums are accepted by schema and ignored at projection.

This note supplements the [M5 Translation & Rendering Pipeline implementation note](../architecture/2026-09-08-m5-translation-rendering-pipeline.en.md) and [M5 review repairs](./2026-09-08-m5-review-repairs.en.md). It does not redo schemas and does not add MathML, `dense-two-column`, or 1 Layout→N Semantic.

## Decision

1. **Equations**: parse only recognizable scripts and radical scope; standalone symbols still get `{}` boundaries; otherwise the whole span becomes fully escaped `\text{...}` (including `$`). `√x` / `√12` / `√(...)` become `\sqrt{...}`; ambiguous forms such as `√xy` keep the source text.
2. **Multi-image figures**: project every bound resource. If subfigure layout cannot be restored, stack the images and record a `RENDERING` Issue.
3. **HTTP client**: callers own injected `httpx.Client` instances; the provider only `with`-closes clients it creates.
4. **Placeholders**: use `⟦n:m⟧` tokens that do not collide with source `⟦n⟧`; validate index and multiplicity; reject duplicates, additions, and drops; do not cache failures.
5. **Cache key**: stable digest of node content, locale, model name, endpoint, terminology revision, candidate terms, prompt version, and translation context. Never store the API key.
6. **RenderPolicy**: figure/table `captionPosition` (with `SOURCE` approximated and an Issue), `wideFigureHandling` (`SCALE_DOWN` / `WIDE_FLOAT` / `INLINE`), and `tableOverflowHandling` (`SCALE_FONT` / `WIDE_FLOAT` / `WRAP` / `FAIL`) all participate in projection. `MULTILINE` equations without break points degrade to `SCALE_DOWN` with an Issue; `TRUNCATE` clips with `\makebox`.
7. **Terminology**: dummy still mints `[TERM]` preferred translations; real providers send discovered phrases as consistency candidates and do not invent preferred translations.
8. **Engineering**: PDFium and Chat Completions parsing live in small adapters; semantic tree walks are shared; translation context uses a neighbor index instead of a per-node suffix scan.

## Alternatives considered

- Keep treating `^_` as safe math characters: `x__1` looks safe and still fails to compile.
- Always append `{}` after every symbol: compiles, but changes the math; “compile succeeded” tests cannot see it.
- Render only the first figure resource and defer the rest as vector work: the missing bits are already-extracted rasters.
- Put an injected client in `with`: retries and a second request raise `Cannot reopen a client instance`.
- Key the cache on model name alone: switching endpoints or neighbor context can replay a stale translation.

## Consequences

- Hostile equations, multi-resource figures, duplicate placeholders, injected-client reuse, cache fingerprints, and policy enums have mechanical tests; equation regressions include real LuaLaTeX compiles.
- M5 remains a baseline, not the full exit gate: `source-derived` / `dense-two-column`, MathML, PDF/SVG figure assets, and 1 Layout→N Semantic stay deferred.
- Current state: [rendering](../../../../docs/architecture/rendering.en.md); roadmap: [roadmap](../../../../docs/development/roadmap.en.md).
