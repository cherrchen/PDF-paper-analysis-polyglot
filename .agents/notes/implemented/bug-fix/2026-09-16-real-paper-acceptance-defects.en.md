# Agent Note: Three defects found by a real-paper end-to-end acceptance run

Status: implemented

[中文](./2026-09-16-real-paper-acceptance-defects.md) | [English](./2026-09-16-real-paper-acceptance-defects.en.md)

## Problem

Running the PRD §40 product flow on a real paper (NIPS 2017 *Attention Is All You Need*, 11-page camera-ready, 569 KB) on the running local stack — `just serve-reader` (API + worker + Vite), import submitted from the browser panel, real provider (`deepseek-flash` @ `https://api.deepseek.com`, one call per node) — exposed three defects, none reachable through the synthetic fixtures.

**1. Duplicate Issue ids fail the whole run in its last stage.**

Semantic recovery records one Issue per occurrence of an unresolved citation, while `RecoveryBuilder.issue()` derives its id as `stable_uuid(layout.id, "issue", category, message)` — the content address of the pair. In the paper's results-table row (`Model EN-FR ByteNet [15] … GNMT + RL [31] … GNMT + RL Ensemble [31] …`) `[31]` appears twice, both unresolved, so two *identical* Issues are produced (same id, message, and `affectedIds`). The cost is not one extra warning:

```text
job e7e4da2b…  submitted 2026-09-16T10:50:17Z → failed 11:00:25Z (10m 08s)
stage: index
error: index stage failed: bundle reference issues:
       ['semantic document issues: duplicate id 88a3b837-2e79-b14a-7202-0affcd8d4195']
```

`_run_index_stage` / `rerender_workspace` run `validate_bundle_references` before publishing; `_check_local_stores` checks every bundle document's local store for repeated ids. A hit raises in INDEX, the job is `failed`, and **the viewer never publishes**. Physical/layout/semantic/translate/render had all completed: `translation.json`, `target.pdf`, and `build/` were on disk, ten minutes of provider calls were spent, and the user got no artifact. No synthetic fixture repeats the same citation number in one node, so the existing golden files, benchmark, and e2e suite stayed green.

**2. The import panel abandons a running job after 280 s.**

`import-panel.ts` had `POLL_DEADLINE_MS = 280_000`. Same paper: the panel submitted at 18:50:17, showed `Job still running · refresh to check` at 18:54:57 (second 280) and re-enabled the submit button, while the job actually ended at 19:00:25 (failed, above). The panel therefore **stops following**: even a job that succeeds afterwards never triggers `DualPaneReader.load()` to swap in place — the reader stays on the previous revision (`f0293403791d4287b2e9c5d10cc7e991`, the anatomy fixture) and only a manual reload helps. The batch-F e2e runs on tikz-vector, which finishes in ~2 s, so 280 s was never exercised; a real 11-page paper needs 183 calls (134 text nodes + 49 table cells) and about ten minutes.

**3. A warm cache cannot be read back: TRANSLATE raises a validation error.**

Rerunning the same workspace after fixing the two defects above, the TRANSLATE stage failed immediately:

```text
job 19d82d5a…  failed 2026-09-16T11:07:28Z
stage: translate
error: translate stage failed: 1 validation error for InlineMark
       Value error, explicit null is not allowed for: href
```

`TranslationCache.put` wrote rows with `mark.model_dump()`, which spells unset optional properties as `"href": null`; `InlineMark` declares `href` / `label` / `targetNodeId` as **non-nullable optional properties**, so `model_validate` rejects the row when the index is built. A cold first run only writes (never reads) the cache, which is why it looked healthy; every warm run — a rerun, a render-config change, a full `rerender_workspace` — dies while loading the cache. 24 of the 178 cached rows carry marks, and all of them were affected. The existing `test_cache.py` only covered "a failed translation is not cached"; nothing read a mark-bearing row back.

## Decision

1. **Deduplicate Issues by id (`pdf_pipeline.semantic`).** `RecoveryBuilder` gains `self._issue_ids`; `issue()` returns early when the id already exists, mirroring the existing `relation()` / `_relation_keys` pattern. The id is the content address, and unique `IssueStore.issues` ids are the document contract (`validate_bundle_references` enforces it, and publication depends on it), so one problem reported twice is still one issue. The validator is not relaxed: a duplicate id remains a real signal, recovery simply must not produce one.
2. **Bump the SEMANTIC producer `0.1.0` → `0.2.0` (`SEMANTIC_PRODUCER_VERSION`).** The stage artifact bytes change (one fewer Issue), so an existing workspace's SEMANTIC record must miss and rerun; otherwise a retry reuses a `semantic.json` that can never publish, and the GUI exposes no `--rerun-from` entry point — a permanent trap. This entails one golden update: 8 provenance `producerVersion` strings in `tests/golden/smoke/semantic.json` move from `0.1.0` to `0.2.0`, which is [golden policy](../../../../docs/testing/golden.md) case 2 (intentional contract change); nothing else in the file moved.
3. **The import panel follows the job to its terminal state (`apps/web/src/import-panel.ts`).** `POLL_DEADLINE_MS` and `Job still running · refresh to check` are gone; polling continues on `queued`/`running` and returns on `succeeded`/`failed`. The running status line becomes `Job <status> · <id prefix> · <elapsed>` (`elapsedLabel`), because a job record only carries `stage` on failure — local elapsed time is the only liveness signal a client can honestly show. The record stays authoritative: the panel neither guesses nor concludes early.
4. **Cache rows store marks in canonical shape, and the read side normalizes historic nulls (`paper_llm.cache`).** `put` now writes `mark.model_dump(exclude_none=True)`; loading drops null-valued properties via `_stored_mark` before `model_validate`. `TRANSLATION_CACHE_VERSION` stays `"1"`: the constant governs **key derivation and row meaning**, and on `InlineMark` "null property = unset" is unambiguous (the model has no required-nullable fields), so there is neither an ambiguous nor a wrong hit to prevent. Bumping it would discard 178 perfectly good translation rows and make users pay a provider bill again for a serialization defect.

## Alternatives considered

- **Relax `validate_bundle_references` for repeated ids**: that deletes the "store ids are unique" contract from the publication check and buys a blind spot that can never report duplicates; the real risk — duplicated ERROR counts and duplicated entries in the viewer's issue list — would remain. Fix the producer, keep the check.
- **Emit one Issue per occurrence with positional identity (mark offsets in the id)**: the messages carry no offsets, so two "same node, same number" Issues are indistinguishable to the user; distinguishing them by position needs a new message/identity model and is out of scope here.
- **Keep a deadline but raise it (say 30 minutes)**: it only postpones the same failure to a slower paper and turns "how long is enough" into yet another constant. The job record already has terminal states; a client has no reason to invent its own deadline.
- **Have the worker write the live stage into the job record (progress bar)**: that needs a pipeline stage callback into atomic record rewrites, touching batch B's state machine and concurrency semantics. This run only required the flow to stop breaking; progress reporting is a follow-up, not part of this note.
- **Skip the producer bump and let the user pick a new workspace or delete the directory**: it shifts the cost to the user, and the symptom is identical (the same `duplicate id`), so nothing in the failure tells them that rebuilding would help. The stage version is exactly the knob for "artifact semantics changed".
- **Re-enable submit after the deadline so the user reruns**: a rerun of the same workspace reuses the same completed stages and fails the same way; it solves nothing.
- **Bump `TRANSLATION_CACHE_VERSION` instead of normalizing on read**: it obeys the letter of "old rows are ignored", but throws away 178 semantically intact translation rows and bills real users again for a serialization defect; it also gives the fact "null means absent" no home, so the next writer that emits nulls repeats the mistake.
- **Fix only the writer and ignore rows already on disk**: the broken rows keep failing every later run while the cache loads, which quietly turns "rebuild the cache" into an unwritten user requirement.
- **Give `_CanonicalModel` a lenient mode that tolerates explicit nulls**: it would erase the contract's distinction between "present" and "null" for every canonical document, far beyond the scope of one cache row.

## Consequences

- `packages/python/pdf-pipeline/src/pdf_pipeline/semantic.py`: `_issue_ids` plus an idempotent `issue()` (with an explanatory docstring); `SEMANTIC_PRODUCER_VERSION = "0.2.0"`.
- `apps/web/src/import-panel.ts`: `POLL_DEADLINE_MS` removed, `elapsedLabel` added, `pollJob` follows to the terminal state and shows `Job <status> · <id prefix> · <elapsed>`.
- `packages/python/llm/src/paper_llm/cache.py`: `put` writes `mark.model_dump(exclude_none=True)`; `_stored_mark` drops null properties while loading; `TRANSLATION_CACHE_VERSION` stays `"1"` with a comment on why null normalization is not a version change.
- Tests: `packages/python/pdf-pipeline/tests/test_semantic.py::test_repeated_unresolved_citation_is_one_issue` (two `[99]` in one node → one Issue, unique ids; fails on the old implementation), `apps/web/src/import-panel.test.ts::bootImportPanel > keeps following a slow job instead of giving up on the client` (fake clock advanced 15 minutes / 400 polls, job then `succeeded` → exactly one `load()`; fails on the old implementation), and `packages/python/llm/tests/test_cache.py` (a row with marks written and read back yields the same marks; a historic row carrying explicit nulls still hits — both fail on the old implementation). The existing panel case that asserted `Job submitted` before anything else drops that assertion, because the running status line now rewrites the text; its other assertions are unchanged.
- `tests/golden/smoke/semantic.json`: 8 provenance `producerVersion` values updated (decision 2).
- Docs: `docs/architecture/reader.md` / `reader.en.md` (import-panel polling semantics), `docs/architecture/semantic-document.md` / `.en.md` (issue identity and id uniqueness as a publication precondition), `docs/architecture/storage.md` / `.en.md` (canonical mark shape and read-side null normalization).
- `tests/e2e/product-import.spec.ts`: the `#import-status` assertion moves from the literal `Job submitted` to the `Job …` prefix (the submitted line is rewritten by progress within one poll interval; the exact wording is covered by the vitest unit tests).
- Verification: `uv run pytest -m "not e2e and not slow"` 558 passed / 5 deselected; `uv run pytest tests/golden -m golden` passed; `pnpm exec vitest run` 59 passed (10 files); `just test-e2e` 14 passed; `just benchmark` reported `unchanged (all metrics within tolerance)`; `just check-fast` passed (fmt/lint/typecheck/test-unit/schema/docs-fast/latex-check).
- Real-paper re-verification (same browser session, every user action in the browser): the rerun of the same workspace finished `succeeded` in 3 s (SEMANTIC reran on the version bump, TRANSLATE/RENDER were skipped because their artifacts were byte-identical, INDEX succeeded for the first time); the panel followed to the terminal state and swapped in place onto revision `66b6115c`; source 1/11 pages ↔ target 1/14 pages, 158 linked regions, cross-page jumps in both directions (target→source, source p4→target p4); the Inspector showed original/translation/anchors/confidence; its `Re-translate node` action completed a real-provider single-node retranslation in 18 s and published revision `1d415311` (that path loads the same cache file, which raised a validation error before the fix). The published `semantic.json` holds 43 Issues with unique ids (44 with one duplicated pair before the fix).
- Open (observed in this run, not fixed, recorded as symptoms): on the real paper 36 `CITATION_RESOLUTION` warnings (only 12 `BIBLIOGRAPHY_ENTRY` recovered out of 40 references, so most `[n]` stay unresolved), 6 `SOURCE_MAPPING` footnote warnings (footnote text merged into body paragraphs), the equation fragment `1 dk` and the table-note fragment `positional embedding instead of sinusoids` classified as HEADING, results-table rows flattened into PARAGRAPH, and the Figure 1 caption rendered as `Figure 1: 图 1: Transformer——模型架构。` because text extraction from the source PDF duplicates and interleaves that line ("Figure 1:Figure The1:Transformer - model architecture."). A separate pre-existing path unrelated to these fixes: `just viewer-fixture` / `serve-reader` / `test-e2e` fail with `WorkspaceSourceMismatchError` once the compiled fixture PDF changes bytes, so `apps/web/.viewer-fixture` must be removed (or the recipe made to accept the source change); this run followed the error message's first remedy and left the recipe alone.
