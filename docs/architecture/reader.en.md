# Reader (M6 Bidirectional Reader)

[中文](./reader.md) | [English](./reader.en.md)

The bidirectional-jump architecture lives in [`document-architecture.en.md`](document-architecture.en.md) §32–33. This page documents the current implementation: viewer data contract v2, the frontend spatial index, navigation/scroll/highlight/focus behavior, the Semantic Inspector, the reader API, and local re-rendering.

## Viewer data contract v2

`pdf_pipeline.pipeline._write_viewer_assets` is the only producer of the `viewerDataVersion: 2` package. Each publish first writes a complete immutable `revisions/<id>/` directory (`mapping.json`, `viewer-meta.json`, `source.pdf`, `target.pdf`), then replaces the stable aliases and rerendered workspace JSON as a recoverable file set, and atomically replaces `manifest.json` last. A mid-commit failure restores every replaced file and removes the unpublished revision. The reader loads all URLs from one manifest as a group; only initial boot without a manifest uses all stable aliases together, with no per-file fallback. The Vite `serve-public-data` plugin serves `/data/*` from `public/data` on every request so those paths never hit the SPA fallback. Canonical MappingBundle fields expand as before (the `mapping` schema stays at 0.1.0, zero changes), plus a viewer-private projection:

| Key | Contents |
| --- | --- |
| `semanticNodes` | all nodes (root skipped): `id/kind/parentId/content/confidence/provenanceIds`; content and confidence are canonical dumps |
| `semanticRelations` | full `semantic.relations` |
| `sourceRegions` | `{id, pageIndex, geometry}` (unchanged) |
| `renderAnchors` | RenderAnchor dumps (geometry stays in the viewer package, never in canonical mapping — see the [M2 note](../../.agents/notes/implemented/architecture/2026-09-04-m2-walking-skeleton.en.md)) |
| `translation` | `{targetLocale, sourceLocale?, providerModel?, terminologyRevision?, terminology?, entries[{semanticNodeId, content, confidence?, providerModel?, cacheKey?}]}` |
| `provenance` | `semantic.provenance.records` |
| `issues` | concatenation of semantic + mapping + translation IssueStore.issues |

`viewer-meta.json` carries per-page size arrays `sourcePages` / `targetPages` (`{widthPt, heightPt}[]`): scroll sync and any page geometry lookup must use the real per-page size, never page 0's.

`run_pipeline` also copies the input bytes to `source.pdf` in the workspace so `rerender_workspace` needs no user re-upload.

## Spatial index (6.1/6.2)

`apps/web/src/spatial.ts::PageSpatialIndex` is a frontend per-page uniform grid (8 columns × 12 rows; cell size comes from that page's meta, missing pages fall back to the first known size on the same side):

- a fragment registers into every cell its rect covers; point and band queries gather deduplicated cell candidates, then exact rect-test them.
- `hitTest(page, x, y)`: fragments containing the point, ascending by area. `inBand(page, yMin, yMax)`: fragments intersecting the horizontal band, ascending by rect.y. Zero-area rects and unknown pages return empty, never throw.
- Paper-scale fragment counts stay < 10³, so cell lookup is O(1); a dense cell still scans its candidates. A real R-tree can replace the internals behind the same interface (see the [M6 note](../../.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.en.md)).

## Navigation behavior (6.3/6.4)

`Pair = { sources: Fragment[]; targets: Fragment[] }` in `apps/web/src/mapping.ts` collects every fragment on both sides (multi-fragment is first-class). Node identity comes from bindings. `pickCounterpart(pair, origin, originRect)` is an **intra-node landing heuristic** used when character-level mapping is absent: among counterpart fragments on the smallest page at/after the origin page, the closest y; when none exists at/after, the first counterpart. It does not decide FR-SYNC-004 identity. Pointer clicks go through spatial-index `hitTest` (smallest area first); keyboard activation still uses the focused button's fragment.

`activate(nodeId, origin, fragment)` in `apps/web/src/reader.ts` (`DualPaneReader`):

1. render the destination pane on the `pickCounterpart` page (each side's `PaneRenderer` cancels the previous PDF.js task and commits only the latest generation; a same-page request also invalidates an uncommitted older page turn before redrawing the overlay);
2. scroll that fragment to the vertical center of the pane viewport via `fragment.y / pageHeight × canvasHeight` (clamped);
3. `focus({preventScroll:true})` the destination overlay button;
4. the origin side redraws keeping its `aria-pressed` selection; the active state survives page turns. Selection updates go through `setActiveNode` so the overlay and Inspector stay in sync.

Sync scroll (`#sync-scroll`, off by default): a ±12 pt band around the scrolling pane's viewport midline goes through `inBand` → first hit with a paired node → `pickCounterpart` → the other side renders and scrolls into place. When no node is found, nothing happens (page-number-guess fallbacks are forbidden). Programmatic scrolls suppress the opposite side's scroll events for 250 ms to break loops.

## Semantic Inspector (6.5)

`apps/web/src/inspector.ts::renderInspector(root, model, nodeId, opts)`. Stable ids double as e2e selectors: `#inspector-node-id` (full SemanticNodeID), `#inspector-kind`, `#inspector-anchors` (per-side `source p{n} [x,y w×h]` lines), `#inspector-source-text`, `#inspector-translation` (`Not translatable` when there is no entry — BIBLIOGRAPHY_ENTRY is deliberately not translated per PRD FR-CITE-004), `#inspector-relations` (two-way relation buttons jump), `#inspector-confidence` (node score + reason + target anchor confidence), `#inspector-provenance`, `#inspector-issues` (only when non-empty), `#inspector-terminology`, `#inspector-citations` (six reference mark types sliced from source/translation text at Unicode code-point offsets with jumpable `targetNodeId`; out-of-range marks render `mark out of range` without throwing). Viewing original vs. translation is the two-pane reading itself; no pane content switching.

## Reader API and local re-render (6.6)

`apps/api` (stdlib ThreadingHTTPServer, no web framework):

- `GET /api/health` — same payload as `/health`; the frontend probes at startup and only renders `#retranslate-button` when `apiAvailable`.
- `POST /api/retranslate`, body `{"nodeIds": [...]}` — 200 `{"ok": true, "changed": [...], "revision": "..."}`; 400 for malformed bodies, unknown nodes, and negative `Content-Length`; 409 for an uninitialized workspace; 413 when `Content-Length` > 4096 bytes; 408 when the declared length exceeds the body and the read times out; 503 when a real workspace has no provider configured; 500 otherwise. A module-level `threading.Lock` serializes rerenders (shared lualatex output directory).

`pdf_pipeline.pipeline.rerender_workspace(workspace_dir, viewer_data_dir=…, node_ids=…)` (FR-TRANS-004: zero source-PDF re-parsing): load the six canonical workspace documents → validate `node_ids ⊆ translation.entries` keys → `retranslate_nodes` with the **current** provider identity (selected nodes skip cache reads) → compose → LaTeX projection + staged compile → `recover_render_anchors` → rebuild the MappingBundle reusing the source-side bindings from the old mapping → write the immutable viewer revision after validation, then commit stable aliases, the three workspace JSON files, and the manifest with rollback protection. A real workspace with no provider configured fails rather than falling back to dummy. Note that re-projecting recompiles the whole target document (seconds to tens of seconds); concentrating that cost in one compile is intentional.

Frontend wiring: the Vite `dev` and preview servers proxy `/api` to `:8000` and serve `/data/*` from `public/data` per request; `just serve-reader` starts both (the Playwright webServer uses the same command). `main.ts` only boots the app; `DualPaneReader` owns pane lifecycle, navigation, and retranslate state. After a successful retranslate the reader loads candidate mapping/meta/PDF as one group from the new manifest and only then swaps, destroying the old target document. A load failure keeps the previous reading state; if the candidate's first render fails after the swap, the reader redraws the old target page and restores page chrome, overlay, focus, and scroll positions. Status line `Node re-translated · <first 8 chars> · <revision 8 chars>`; `#viewer` `data-busy` / `data-revision` let e2e wait for busy→idle.

Correctness repairs: [M6 review repairs](../../.agents/notes/implemented/bug-fix/2026-09-11-m6-review-repairs.en.md).

## Fixture

`just viewer-fixture` runs the pipeline on `tests/fixtures/source/latex/build/paper-anatomy.pdf` (2 pages; figure/table/equation/footnote/bibliography, every element) and emits `apps/web/public/data/`, the complete e2e data source (gitignored). Multi-fragment assertions rely on its genuine cross-page RenderAnchor.

- M6 decisions: [`.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.en.md`](../../.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.en.md)
- Rendering chain: [`rendering.en.md`](rendering.en.md)
- Mapping chain: [`source-mapping.en.md`](source-mapping.en.md)
