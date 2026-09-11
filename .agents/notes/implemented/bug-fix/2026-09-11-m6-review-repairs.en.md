# Agent Note: M6 review repairs

Status: implemented

[中文](./2026-09-11-m6-review-repairs.md) | [English](./2026-09-11-m6-review-repairs.en.md)

## Problem

The 2026-09-11 code review kept M6 as a landed functional baseline but required retranslation correctness, async rendering, and published-asset consistency to be fixed before M7. This note supplements the [M6 Bidirectional Reader implementation note](../feature/2026-09-11-m6-bidirectional-reader.en.md). It does not add character-level mapping, MathML, vector figures, or parser specialists.

## Decision

1. **Provider identity**: `rerender_workspace` passes the actual `provider_model` / endpoint from `_build_translation_provider` into `retranslate_nodes`. New entries record the model that ran; the layer field is the latest translation pass, and mixed documents treat per-entry identity as authoritative. A real workspace (layer or any entry not dummy) with no configured provider raises `TranslationProviderNotConfiguredError` (API 503) instead of overwriting real text with dummy output.
2. **Forced retranslate**: user-initiated `retranslate_nodes` sets `skip_cache_read=True` for selected nodes and still writes the cache on success; unselected nodes keep their entries. Cache keys still include model and endpoint, so switching models on the same endpoint cannot hit the previous result.
3. **Render concurrency**: each pane's `PaneRenderer` / `ExclusiveRenderer` cancels the previous PDF.js `RenderTask`, waits for it to exit, and lets only the latest generation commit the canvas, page number, and geometry. Same-page selection changes redraw the overlay only.
4. **Artifact consistency**: compile, anchor recovery, and `validate_bundle_references` finish in a staging `build/.rerender-*` directory. On success the producer writes `revisions/<id>/` then atomically replaces `manifest.json`, then updates stable aliases. Failure keeps the previous complete revision. Workspace JSON is replaced only after the viewer revision is published. The Vite `serve-public-data` plugin serves `/data/*` from `public/data` on every request so revision directories created after boot are not SPA-fallback to `index.html`.
5. **Frontend refresh**: load candidate mapping/meta/PDF fully, then switch. If a revision URL returns HTML or non-JSON, retry the stable aliases with the same revision cache-buster. Any failure rolls back and destroys the candidate. `retranslateBusy` lives on the reader so changing nodes cannot start a second retranslate. `#viewer` exposes `data-busy` / `data-revision`.
6. **Unicode offsets**: marks use Unicode code points; the Inspector slices with `sliceByCodePoint`, covering mathematical letters and supplementary CJK.
7. **HTTP bounds**: reject negative `Content-Length` (400); oversize stays 413; body-read timeout is 408.
8. **E2E**: each click is bound to its own `waitForResponse` and a busy→idle revision change.
9. **`pickCounterpart`**: remains an intra-node landing heuristic (bindings decide identity; page/y are used only when character-level mapping is absent). The algorithm is unchanged; tests now cover widely different pagination. Clicks go through `hitTest` (smallest area first); `setActiveNode` is the single selection entry that refreshes the Inspector.

## Alternatives considered

- Store `"mixed"` on the layer when entry models diverge: the schema has no enum, and existing dummy comparisons would break. Latest-pass plus authoritative entries is clearer.
- Point at the current viewer revision with a symlink: brittle on Windows and for Vite static serving. Atomic `manifest.json` replacement is enough.
- Always land `pickCounterpart` on the node's first fragment: that would break sync-scroll band correspondence. Leave it until character-level mapping exists.

## Consequences

- Retranslation no longer labels model-B text as model A, and cannot impersonate a real model with dummy output when config is missing.
- Rapid paging, clicks, and sync-scroll no longer run two RenderTasks on one canvas.
- After compile, validation, or publish failure, the previous revision's PDF/mapping/meta remain readable.
- Current state: [reader](../../../../docs/architecture/reader.en.md). Deferred items are unchanged.
