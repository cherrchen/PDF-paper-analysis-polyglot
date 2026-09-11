# Agent Note: M6 Bidirectional Reader — Implemented

Status: implemented

[中文](./2026-09-11-m6-bidirectional-reader.md) | [English](./2026-09-11-m6-bidirectional-reader.en.md)

## Problem

After M5 the viewer (`apps/web`, the M2 skeleton) was still a click-to-jump comparison desk: targets kept only `fragments[0]` per node, jumps changed pages without locating y, and there was no spatial index, no Inspector, no scroll sync, and no translation interaction. The exit gate requires source↔target locating that never assumes `source page ≈ target page` (PRD FR-SYNC-004 forbids page/coordinate guessing), while the v1 viewer data plane emitted none of the text, confidence, relations, provenance, translation, or terminology the Inspector needs.

## Decision

1. **Viewer data contract v2** (sole producer: `_write_viewer_assets`): canonical MappingBundle fields expand unchanged; added `semanticNodes` (full content/confidence/parentId/provenanceIds), `semanticRelations`, `translation`, `provenance`, `issues`; `viewer-meta.json` replaces single-page sizes with per-page arrays; `run_pipeline` writes a `source.pdf` copy into the workspace; mapping/meta are written atomically (tmp + replace) so vite never reads a half-written file.
2. **Frontend grid spatial index** (`apps/web/src/spatial.ts`): a per-page 8×12 uniform grid sized from that page's meta (missing pages fall back to a known same-side size); `hitTest` (area-ascending) and `inBand` (y-ascending) narrow via cells then exact-test rects.
3. **Multi-fragment + deterministic jumps**: `Pair` collects every fragment on both sides; `pickCounterpart` takes the closest y on the smallest counterpart page at/after the origin page, else the first counterpart; `activate` renders the destination page, scrolls the fragment to center by rect ratio, and focuses the overlay button; sync scroll queries a ±12 pt midline band and does nothing when no node is found; programmatic scrolls suppress the other side for 250 ms to break loops.
4. **Semantic Inspector** (`apps/web/src/inspector.ts`): stable-id panel with anchors/original/translation/relations/confidence/provenance/issues/terminology/citations; `nodePlainText` discriminates the four canonical content branches; out-of-range marks render `mark out of range` without throwing.
5. **Local re-render** (FR-TRANS-004): `rerender_workspace(workspace_dir, *, viewer_data_dir, node_ids)` loads the six canonical workspace documents (`load_document`, kinds per `_ROOT_MODELS`), validates `node_ids ⊆ translation.entries` keys, then retranslate → compose → project/compile → recover RenderAnchors → rebuild the MappingBundle reusing old source-side bindings → rewrite workspace documents and the viewer package. Zero source-PDF re-parsing; provider/cache construction is shared with `run_pipeline` via `_build_translation_provider`.
6. **Stdlib reader API** (`apps/api`): `GET /api/health` + `POST /api/retranslate` (400/409/413/405/500 contract), `ThreadingHTTPServer` with a module-level `threading.Lock` serializing rerenders; business logic lives in `paper_api/retranslate.py`, `__main__` stays thin; heavy imports are lazy so startup stays <1 s.
7. **Viewer fixture switched to `paper-anatomy`** (2 pages, every element, a genuine cross-page RenderAnchor); `just serve-reader` and the Playwright webServer run the same `sh -c` (api on :8000 plus the Vite `dev` server on :4173), with `/api` proxied identically.

## Alternatives considered

- **Python-prebuilt spatial index / real R-tree**: the index serves frontend interaction (hit-test/band) at paper scale (<10³ rects); the grid is O(1) with zero dependencies, and prebuilding would bind interaction semantics to generation time. Swapping in an R-tree behind the unchanged `PageSpatialIndex` interface stays open.
- **Bumping the canonical mapping schema to 0.2.0 with a `renderAnchors` container**: would churn generated bindings, fixtures, and cross-language roundtrips; validator comments and the M2 note already externalize render-anchor geometry. Geometry stays in the viewer package until a server consumer needs it (M7/M8 schema note).
- **FastAPI**: the repo deliberately has zero web frameworks; two routes plus JSON fit stdlib.
- **Single-node LaTeX recompile**: node boundaries are unlocatable in the output stream; recompiling the whole target concentrates the cost (≈1.4 s on the dummy fixture).
- **Keeping figure-caption as viewer fixture**: single page, no cross-page/multi-fragment evidence — 6.4 and the exit gate would be unprovable.

## Consequences

- `apps/web/src/mapping.ts` throws `unsupported viewer data version: <n>`; only v2 is accepted (clean cutover, no v1 branch).
- `pickCounterpart`'s smallest-eligible-page rule is intentional determinism: with the origin on the last page it may jump to the counterpart's page 0; that is the "same page or next page preferred" constraint made total, not a bug.
- After a retranslate the target pdf.js document must be rebuilt (layout changed); stale page geometry would scroll to the wrong place. Dummy-provider output is byte-deterministic, so e2e locks the protocol and settle-back, not text change (real-provider paths are covered by M5 structure tests and manual verification).
- New viewer-package fields only extend viewer emission; the canonical schema is untouched. Any future canonical gap gets its own schema note, not an M6 version bump.
- Verification: `just test-python`, `pnpm exec vitest run` (37), `just test-integration`, and `just test-e2e` (12, including multi-fragment highlight, sync scroll, Inspector, and a real in-browser re-translate) are green. `tests/benchmark/test_semantic_benchmark.py` gains an `anchorCoverage ≥ 0.8` metric.
- Docs: [`docs/architecture/reader.en.md`](../../../../docs/architecture/reader.en.md) (中文 companion at `reader.md`) is the current-state source of truth.

## Acceptance

- Exit Gate: locating original↔translation uses bound fragments + spatial queries only; the e2e reflow assertions require multi-fragment anchors whose source and target page distributions differ.
- Re-translating one node through `POST /api/retranslate` rebuilds translation/render/mapping/workspace documents and the viewer package without re-running physical extraction (proved with an extraction-poisoning test).
- `just viewer-fixture`, `just test-e2e`, and `just serve-reader` run on paper-anatomy with the v2 contract.
