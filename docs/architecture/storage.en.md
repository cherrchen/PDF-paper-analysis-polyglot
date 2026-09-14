# Storage

[中文](./storage.md) | [English](./storage.en.md)

Persistent object storage, artifact layout, and dataset hosting remain **intentionally unresolved**; the local Project / Document Workspace and job-orchestration conventions were closed by [M8 v1 batches A–C](../development/m8.en.md), see below.

## Local workspace (M8 batches A / C, closed)

`run_pipeline(source_pdf, out_dir)` turns `out_dir` into a **resumable local workspace**. Directory layout:

```text
<workspace>/
  workspace.json          # ad-hoc manifest (probe.json class, outside frozen schemas)
  source.pdf              # source PDF bytes kept by INGEST
  physical.json …         # per-stage canonical JSON artifacts
  probe.json              # probe + routing diagnostics (ad-hoc)
  evidence-bundles.json   # ad-hoc persistence of per-provider bundles
  resources/              # images and figure PDF fragments
  target.pdf              # committed render artifact
  viewer-publication.json # viewer destination and publication hashes
  build/                  # LaTeX build output (target.pdf), not a manifest artifact
  viewer/data/            # viewer revisions (existing publish transaction)
```

### Stages and commit protocol

Stage enum: `INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX` (`pdf_pipeline.workspace`).

- Each stage records in `workspace.json`: status, artifact relative paths + sha256, producer version, and the stage cache key `inputFingerprint` (below).
- Commit order: artifacts are staged under `.staging/`, replaced one atomic rename at a time, and `workspace.json` is rewritten atomically last — the manifest is the **single commit pointer**.
- Resume: a stage is skipped only when `stage_completed` holds (COMPLETED + artifact hashes verify + cache key matches upstream records and stage config); otherwise it reruns. After an interrupt, restart reruns only unfinished stages; a half-written artifact set is never accepted as success.
- Source binding: the manifest's `sourceFingerprint` locks the source PDF; unknown `workspaceVersion` and a foreign source PDF are explicit errors (migration belongs to batch E).

Authoritative implementation: `packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` and the stage runners in `pipeline.py`; decision rationale in Agent Note `2026-09-12-m8-batch-a-workspace-stages`.

### Stage cache keys and invalidation (M8 batch C, closed)

The cache key is producer version + upstream artifact sha256 + stage configuration (`pipeline.stage_config_inputs`). `schemaVersion` and `pipelineVersion` are common to every stage; the rest is per stage:

| Input change | Stages invalidated |
| --- | --- |
| capability registry bytes (`registry_fingerprint`, sha256) | EVIDENCE, LAYOUT |
| parser dump bytes (resolved the way the adapters resolve them) / `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL` | EVIDENCE |
| translation config: target/source locale, provider model, endpoint, terminology file bytes | TRANSLATE |
| render profile / policy / LaTeX template bytes (`template_fingerprint`) | RENDER |
| stage code or schema version (`pipelineVersion` / `schemaVersion`) | every stage |
| upstream artifact hashes (pre-existing rule) | that stage and everything downstream |

- Config folds into the existing `inputFingerprint` field: **no new manifest field**, and `WORKSPACE_VERSION` stays `0.1.0`, because extending the key material only reruns an old workspace once (the safe direction), while bumping the version would reject existing workspaces — and migration/rejection boundaries belong to batch E.
- The registry and parser dumps key on **content digests**, not version constants: they are hand-edited data, and an edit that forgets to bump a version must still invalidate.
- API key, `timeout_s`, `max_retries`, and `cache_dir` are **not** keyed: they do not change produced artifacts.
- All three real parser adapters participate regardless of routing (which needs a probe): over-invalidating costs one rerun, a false hit goes silently stale.
- Explicit local rerun: `run_pipeline(..., rerun_from=<stage>)` and the CLI `--rerun-from <stage>` drop that stage and every downstream record before running (`WorkspaceManager.invalidate_from`); upstream records are untouched.
- Changed source PDF bytes raise `WorkspaceSourceMismatchError` by default; the explicit opt-in `accept_source_change=True` / CLI `--accept-source-change` rebinds `sourceFingerprint`, drops every stage record, and reruns the whole chain (old files on disk are overwritten by each stage rerun at its own declared paths).
- SEMANTIC clears `<ws>/resources/` before committing: that stage's artifact set is "every file in the directory", so without the purge a stale raster or figure fragment from an earlier run or source would be recorded as current output.

Translation cache rows (`paper_llm.cache.TranslationCache`) carry `cacheVersion` (`TRANSLATION_CACHE_VERSION`, currently `"1"`); the constant is also the **key-derivation version**, so rows from an unknown version are ignored and never migrated. Table nodes are cached per cell: for a TABLE the node-level `cacheKey` is a whole-table content/config digest, not a cache address.

Authoritative implementation: `pipeline.stage_config_inputs`, `WorkspaceManager`, `paper_llm.cache`; decision rationale in Agent Note `2026-09-14-m8-batch-c-cache-keys-invalidation`.

### Current boundaries

- `workspace.json` is an ad-hoc file; its schema changes do not go through the `just schema` frozen flow.
- Viewer revision publishing keeps the existing `_publish_viewer_revision` transaction and is not tracked file-by-file in the manifest.
- A changed source PDF supports only "error" or "rebind the whole chain"; per-stage merging is not implemented (Project grouping belongs to a later batch).

## Jobs and job records (M8 batch B, closed)

`pdf_pipeline.jobs` wraps "one workspace run" in a **Job** that can be submitted, queried, and retried; the applications (`apps/api`, `apps/worker`) only wire it up. The jobs root defaults to `.jobs/`:

```text
<jobsRoot>/
  queued/    <jobId>.json     waiting for a claim
  running/   <jobId>.json     claimed by a live worker
  finished/  <jobId>.json     terminal (succeeded / failed)
  locks/     job-<jobId>.lock and workspace-<workspaceHash>.lock
```

Job record fields: `jobVersion` (currently `0.1.0`), `id` (32 lowercase hex), `status`, `source`, `workspace`, `viewerDataDir`, `attempt` (from 1), `createdAt`, `updatedAt`, `stage`, `error`, `issues`. Records move between the three directories by atomic rename; `get_job` / `list_jobs` deduplicate with `queued > running > finished` priority, so a crash window never exposes two visible records. An unknown `jobVersion`, an invalid `id`, and an unparsable record are all explicit errors.

### State machine and claiming

- `queued → running → succeeded | failed`; `failed → queued` only through a manual `retry_job` (`attempt + 1`, clearing `stage` / `error` / `issues`). `error is None` means `succeeded`. **There is no automatic retry or backoff.**
- `claim_next` takes the oldest queued job by `(createdAt, id)` and takes two POSIX `fcntl.flock` locks: a per-job lock (mutual exclusion between workers) and a per-workspace lock (jobs sharing one workspace run serially, because `lualatex` shares one `build/` per workspace).
- A `flock` belongs to the open file description, so the kernel releases it when the process exits. `recover_running` therefore distinguishes a dead owner (lock free → requeue as `queued`, `attempt` unchanged) from a live one (lock held → skip). Worker concurrency is configurable (`--concurrency`, default 1): different workspaces run in parallel, one workspace always serially.
- Requeuing only rewinds the Job and **never** touches workspace artifacts; which stages actually rerun is still decided by the batch A stage state, so completed artifacts are never lost.

### Failure attribution

Stage execution is wrapped in `pipeline._execute_stage`, which raises `StageExecutionError` carrying the `Stage`. `JobWorker` turns that into a canonical job-level Issue:

| Failure site | `severity` | `recoverable` | `category` |
| --- | --- | --- | --- |
| Inside a stage (`stage` is the stage name) | `ERROR` | `true` | `STAGE_ISSUE_CATEGORIES[stage]` (e.g. SEMANTIC → `SECTION_STRUCTURE`, TRANSLATE → `TRANSLATION`) |
| Before any stage (`stage: null`) | `FATAL` | `false` | `PHYSICAL_EXTRACTION` |

The Issue shape must validate against `document_model.generated.schema_models.Issue` (including `id`, `producer`, `message`, `affectedIds`). A job-level Issue is stored **only in the job record**, never appended to `semantic.json` (no second source of truth; in-document issues belong to batch D).

Authoritative implementation: `packages/python/pdf-pipeline/src/pdf_pipeline/jobs.py` and `_execute_stage` in `pipeline.py`; HTTP contract in [HTTP API](api.en.md); decision rationale in Agent Note `2026-09-14-m8-batch-b-job-orchestration`.

## Still unresolved

Persistent object storage, multi-machine sharing, dataset hosting. A future external dataset system requires a testing or architecture Agent Note.

Keep Git history small. Do not commit a large PDF corpus.

## Review repairs

Resume compares each record against the current stage producer version and reads the committed root `target.pdf`; `build/` is disposable. INDEX records a publication receipt covering the viewer destination, manifest, stable aliases, and current revision; missing or changed output triggers republication. Partial retranslation publishes translation/render records and the root target PDF within the existing rollback transaction, invalidates INDEX, and preserves the new translation on the next pipeline run. Manifest write failures restore the in-memory stage record. Rationale: [batch A review repairs](../../.agents/notes/implemented/bug-fix/2026-09-12-m8-batch-a-review-repairs.en.md).
