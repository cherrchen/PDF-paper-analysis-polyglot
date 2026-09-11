# Agent Note: M6 review repairs

Status: implemented

[中文](./2026-09-11-m6-review-repairs.md) | [English](./2026-09-11-m6-review-repairs.en.md)

## Problem

The 2026-09-11 code review kept M6 as a landed functional baseline but required retranslation correctness, async rendering, and published-asset consistency to be fixed before M7. This note supplements the [M6 Bidirectional Reader implementation note](../feature/2026-09-11-m6-bidirectional-reader.en.md). It does not add character-level mapping, MathML, vector figures, or parser specialists.

## Decision

1. **Provider identity**: `rerender_workspace` passes the actual `provider_model` / endpoint from `_build_translation_provider` into `retranslate_nodes`. New entries record the model that ran; the layer field is the latest translation pass, and mixed documents treat per-entry identity as authoritative. A real workspace (layer or any entry not dummy) with no configured provider raises `TranslationProviderNotConfiguredError` (API 503) instead of overwriting real text with dummy output.
2. **Forced retranslate**: user-initiated `retranslate_nodes` sets `skip_cache_read=True` for selected nodes and still writes the cache on success; unselected nodes keep their entries. Cache keys still include model and endpoint, so switching models on the same endpoint cannot hit the previous result.
3. **Render concurrency**: each pane's `PaneRenderer` / `ExclusiveRenderer` cancels the previous PDF.js `RenderTask`, waits for it to exit, and lets only the latest generation commit the canvas, page number, and geometry. A same-page request also invalidates an uncommitted older page turn before repainting the overlay.
4. **Artifact consistency**: compile, anchor recovery, and `validate_bundle_references` finish in a staging `build/.rerender-*` directory. On success the producer first writes immutable `revisions/<id>/`, then replaces stable aliases and the three workspace JSON files as one recoverable set, and commits `manifest.json` last. Any replacement failure restores every replaced file and removes the unpublished revision, keeping the viewer consistent with the workspace used by the next rerender. The Vite `serve-public-data` plugin serves `/data/*` from `public/data` on every request.
5. **Frontend refresh**: one load uses only mapping/meta/PDF URLs from one manifest. Only initial boot without a manifest uses all stable aliases together; per-file fallback cannot mix revisions. The candidate is fully loaded before switching. If its initial render fails after the switch, the reader restores the old model/PDF, rerenders the old target page, page chrome, overlay, focus, and both scroll positions, then destroys the candidate. `retranslateBusy` lives on the reader so changing nodes cannot start a second retranslate. `#viewer` exposes `data-busy` / `data-revision`.
6. **Unicode offsets**: marks use Unicode code points; the Inspector slices with `sliceByCodePoint`, covering mathematical letters and supplementary CJK.
7. **HTTP bounds**: reject negative `Content-Length` (400); oversize stays 413; body-read timeout is 408.
8. **E2E**: each click is bound to its own `waitForResponse` and a busy→idle revision change.
9. **`pickCounterpart`**: remains an intra-node landing heuristic (bindings decide identity; page/y are used only when character-level mapping is absent). The algorithm is unchanged; tests now cover widely different pagination. Clicks go through `hitTest` (smallest area first); `setActiveNode` is the single selection entry that refreshes the Inspector.
10. **Style follow-up**: `DualPaneReader` owns pane lifecycle, navigation, and retranslate state. `NodeContent` / marks / confidence are `Pick` projections of generated types, with `parseMappingBundle` at the load boundary. Provider-protocol and JSON-boundary pyright exemptions are line-scoped instead of module-wide.

## Alternatives considered

- Store `"mixed"` on the layer when entry models diverge: the schema has no enum, and existing dummy comparisons would break. Latest-pass plus authoritative entries is clearer.
- Point at the current viewer revision with a symlink: brittle on Windows and for Vite static serving. Atomic `manifest.json` replacement is enough.
- Always land `pickCounterpart` on the node's first fragment: that would break sync-scroll band correspondence. Leave it until character-level mapping exists.

## Consequences

- Retranslation no longer labels model-B text as model A, and cannot impersonate a real model with dummy output when config is missing.
- Rapid paging, clicks, and sync-scroll no longer let an old RenderTask overwrite the latest same-page request.
- After a mid-publish failure, the previous revision and workspace are restored together; the browser cannot assemble one reading state from files belonging to different revisions.
- A failed candidate first render reconstructs the old visible page instead of only rolling back in-memory references.
- Current state: [reader](../../../../docs/architecture/reader.en.md). Deferred items are unchanged.
