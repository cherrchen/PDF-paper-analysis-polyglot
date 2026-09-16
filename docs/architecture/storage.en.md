# Storage

[中文](./storage.md) | [English](./storage.en.md)

Persistent object storage, artifact layout, and dataset hosting remain **intentionally unresolved**; the local Project / Document Workspace and job-orchestration conventions were closed by [M8 v1 batches A–E](../development/m8.en.md), see below.

## Local workspace (M8 batches A / C / D / E, closed)

`run_pipeline(source_pdf, out_dir)` turns `out_dir` into a **resumable local workspace**. Directory layout:

```text
<workspace>/
  workspace.json          # ad-hoc manifest (probe.json class, outside frozen schemas)
  source.pdf              # source PDF bytes kept by INGEST
  physical.json …         # per-stage canonical JSON artifacts
  probe.json              # probe + routing diagnostics + provider degradations (ad-hoc)
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
- status is one of `pending` / `completed` / `degraded`. `degraded` (batch D) means "artifacts are usable, but the run recorded a degradation": `stage_completed` accepts only `completed`, so that stage **necessarily reruns on the next run** (a failure never becomes a cache hit), while the record still exists so downstream stages read its artifacts and continue. An unknown status is always an explicit error.
- Commit order: artifacts are staged under `.staging/`, replaced one atomic rename at a time, and `workspace.json` is rewritten atomically last — the manifest is the **single commit pointer**.
- Resume: a stage is skipped only when `stage_completed` holds (COMPLETED + artifact hashes verify + cache key matches upstream records and stage config); otherwise it reruns. After an interrupt, restart reruns only unfinished stages; a half-written artifact set is never accepted as success.
- Source binding: the manifest's `sourceFingerprint` locks the source PDF; an unknown `workspaceVersion` and a foreign source PDF are explicit errors. The readable set is the named constant `SUPPORTED_WORKSPACE_VERSIONS` (currently `("0.1.0",)`); a version outside it is refused **before any `self.*` assignment**, so a rejected workspace is untouched on disk and in memory and leaves no `.staging`. Batch E ships no version converter: batches A–D all wrote `"0.1.0"` and the manifest shape never changed (batch C changed the key material, batch D added a status value), so an old workspace reruns naturally through stale cache keys rather than needing migration — a converter would be dead code. A future bump either adds the old version to that set plus a real migration step in `_load_existing`, or keeps refusing.

Authoritative implementation: `packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` and the stage runners in `pipeline.py`; decision rationale in Agent Note `2026-09-12-m8-batch-a-workspace-stages`.

### Stage cache keys and invalidation (M8 batch C, closed)

The cache key is producer version + upstream artifact sha256 + stage configuration (`pipeline.stage_config_inputs`). `schemaVersion` and `pipelineVersion` are common to every stage; the rest is per stage:

| Input change | Stages invalidated |
| --- | --- |
| capability registry bytes **actually used** (bundled `data/capability-registry.toml`, or the file named by `PAPER_CAPABILITY_REGISTRY` / `--registry`; `registry_fingerprint`, sha256) | EVIDENCE, LAYOUT |
| parser dump bytes (resolved the way the adapters resolve them) / `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL` | EVIDENCE |
| translation config: target/source locale, provider model, endpoint, terminology file bytes | TRANSLATE |
| render profile / policy / LaTeX template bytes (`template_fingerprint`) | RENDER |
| stage code or schema version (`pipelineVersion` / `schemaVersion`) | every stage |
| upstream artifact hashes (pre-existing rule) | that stage and everything downstream |

- Config folds into the existing `inputFingerprint` field: **no new manifest field**, and `WORKSPACE_VERSION` stays `0.1.0`, because extending the key material only reruns an old workspace once (the safe direction), while bumping the version would reject existing workspaces — and migration/rejection boundaries belong to batch E.
- The registry and parser dumps key on **content digests**, not version constants: they are hand-edited data, and an edit that forgets to bump a version must still invalidate.
- Parser configuration has exactly one entry point (`pdf_pipeline.config.load_parser_config`, mirroring `paper_llm.config`): the `--registry` flag wins, then `PAPER_CAPABILITY_REGISTRY`, then the bundled registry. `run_pipeline` resolves `(Registry, digest)` with a single `resolve_registry` read **before the workspace is constructed**: the table used for routing and the digest written into the cache key must come from the same read, or an edit between two reads would record a digest that does not match the artifacts — a silent cache hit. An override file is **read fresh every time and never cached** (the operator may edit it at any moment); the bundled registry is immutable package data, parsed once and `lru_cache`d.
- The override path is only a source: **the path is not keyed**, so the same content at two paths yields one digest and a byte-identical copy of the bundled registry triggers no rerun.
- An unreadable or invalid override (TOML parse failure, missing internal capability, a provider listed twice for one capability) always raises `CapabilityRegistryError` and **never falls back to the bundled registry** — a silent fallback is a silent parser swap. The bundled primaries stay `mock` / `docling-sim` / `grobid-sim`; changing a bundled primary requires proving it first with an override file plus `just benchmark`.
- API key, `timeout_s`, `max_retries`, and `cache_dir` are **not** keyed: they do not change produced artifacts.
- All three real parser adapters participate regardless of routing (which needs a probe): over-invalidating costs one rerun, a false hit goes silently stale.
- Explicit local rerun: `run_pipeline(..., rerun_from=<stage>)` and the CLI `--rerun-from <stage>` drop that stage and every downstream record before running (`WorkspaceManager.invalidate_from`); upstream records are untouched.
- Changed source PDF bytes raise `WorkspaceSourceMismatchError` by default; the explicit opt-in `accept_source_change=True` / CLI `--accept-source-change` rebinds `sourceFingerprint`, drops every stage record, and reruns the whole chain (old files on disk are overwritten by each stage rerun at its own declared paths).
- SEMANTIC clears `<ws>/resources/` before committing: that stage's artifact set is "every file in the directory", so without the purge a stale raster or figure fragment from an earlier run or source would be recorded as current output.

Translation cache rows (`paper_llm.cache.TranslationCache`) carry `cacheVersion` (`TRANSLATION_CACHE_VERSION`, currently `"1"`); the constant is also the **key-derivation version**, so rows from an unknown version are ignored and never migrated. Marks are stored in canonical shape: `InlineMark`'s optional properties may not be explicit null, so null-valued properties are never written; the read side normalizes explicit nulls in older rows to "absent" (an unambiguous meaning, hence not a format change worth skipping). Table nodes are cached per cell: for a TABLE the node-level `cacheKey` is a whole-table content/config digest, not a cache address.

Authoritative implementation: `pipeline.stage_config_inputs`, `WorkspaceManager`, `paper_llm.cache`; decision rationale in Agent Note `2026-09-14-m8-batch-c-cache-keys-invalidation`.

### Evidence failure isolation and degradation (M8 batch D, closed)

EVIDENCE providers are optional specialists: one provider failing degrades only its own capability and never breaks the chain.

- `routing.collect_bundles` returns a `ProviderCollection(bundles, degradations)`; a provider exception is isolated at the boundary into one `ProviderDegradation` (`provider` / `capabilities` / `substitutes` / `errorType` / `message`, truncated to 500 characters).
- Substitution uses only the registry's `Capability.fallback` (never the challenger); each name is attempted at most once per run and **never recurses**. A fallback already collected in this run is reused rather than rerun, and `substitutes` lists only the names that actually produced a bundle; a failing substitute gets its own degradation entry.
- Each degradation produces one canonical Issue attributed to that provider: `severity = ERROR`, `recoverable = true`, `category` taken from the **existing** `IssueCategory` the capability maps to (`table.*` → `TABLE_RECOVERY`, `layout.region` → `LAYOUT_REGION`, `formula.*` → `FORMULA_RECOVERY`, `scholarly.metadata` → `SECTION_STRUCTURE`, `scholarly.bibliography` → `CITATION_RESOLUTION`), and `fallback` naming either `provider substitution: <names>` or the capability's internal degradation description; the id is derived deterministically from document id + provider + capability + message.
- `probe.json` gains a `degradations` array (`[]` when nothing failed; the shape is constant). The `evidence.json` `issues` store is the members' own issues plus the degradation Issues (the field is **omitted** when empty, so an undegraded run stays byte-identical).
- `_run_semantic_stage` folds those Issues into the `semantic.json` IssueStore (deduplicated by id, ordered existing issues → semantic-validation issues → evidence issues); that is the only channel carrying them to the viewer's issue list, `metrics.quality_report`, and the benchmark's ERROR count.
- Internal baselines keep a degraded run usable: layout regions come from geometric banding independently of any provider, TABLE degrades to a single-column row-per-line fallback (`confidence.reason == "table fallback: line rows"`), and scholarly metadata degrades to front-matter heuristics.
- EVIDENCE commits as `degraded`: artifacts are published and downstream continues, but the next run reruns that stage (failures are never cached); when the rerun reproduces identical bytes the downstream is still skipped. Only **every routed provider failing** (zero bundles) is a real failure, attributed to EVIDENCE by `_execute_stage`.
- `ROUTING_VERSION` / `PIPELINE_VERSION` therefore move to `0.2.0`: the former is part of the EVIDENCE cache key, the latter is a common key item for every stage (the fold-in logic changed, so existing workspaces rerun the whole chain once).

Authoritative implementation: `pdf_pipeline.routing`, `pdf_pipeline.evidence.normalize`, the EVIDENCE/SEMANTIC runners in `pdf_pipeline.pipeline`, and `WorkspaceManager.commit_stage(degraded=...)`; decision rationale in Agent Note `2026-09-15-m8-batch-d-specialist-isolation`.

### Current boundaries

- `workspace.json` is an ad-hoc file; its schema changes do not go through the `just schema` frozen flow.
- Viewer revision publishing keeps the existing `_publish_viewer_revision` transaction and is not tracked file-by-file in the manifest. `PAPER_PUBLISH_FAULT=<file name>` (batch F, `pdf_pipeline.config.load_publish_fault`) makes the commit of that named file raise `OSError` mid-transaction so operator/test processes can exercise the rollback path in a real process; unset means no behavior change, and the env is configuration only — it keys nothing and alters no published bytes.
- A changed source PDF supports only "error" or "rebind the whole chain"; per-stage merging is not implemented (Project grouping belongs to a later batch).
- No workspace version converter is written: a version outside the readable set is always refused, and that set currently holds only the written version `("0.1.0",)`.
- `apps/api` and `apps/worker` gain no registry argument: both paths end at the defaults of `run_pipeline` / `rerender_workspace`, which read the environment, so setting `PAPER_CAPABILITY_REGISTRY` on the worker process covers both.

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

The Issue shape must validate against `document_model.generated.schema_models.Issue` (including `id`, `producer`, `message`, `affectedIds`). A job-level Issue is stored **only in the job record** and records "which stage failed as a whole"; in-document Issues (including batch D provider degradations) are written into `semantic.json` by the EVIDENCE/SEMANTIC stages, see above.

Authoritative implementation: `packages/python/pdf-pipeline/src/pdf_pipeline/jobs.py` and `_execute_stage` in `pipeline.py`; HTTP contract in [HTTP API](api.en.md); decision rationale in Agent Note `2026-09-14-m8-batch-b-job-orchestration`.

## Still unresolved

Persistent object storage, multi-machine sharing, dataset hosting. A future external dataset system requires a testing or architecture Agent Note.

Keep Git history small. Do not commit a large PDF corpus.

## Review repairs

Resume compares each record against the current stage producer version and reads the committed root `target.pdf`; `build/` is disposable. INDEX records a publication receipt covering the viewer destination, manifest, stable aliases, and current revision; missing or changed output triggers republication. Partial retranslation publishes translation/render records and the root target PDF within the existing rollback transaction, invalidates INDEX, and preserves the new translation on the next pipeline run. Manifest write failures restore the in-memory stage record. Rationale: [batch A review repairs](../../.agents/notes/implemented/bug-fix/2026-09-12-m8-batch-a-review-repairs.en.md).

## M8 P1 concurrency repairs

`pdf_pipeline.locks` keys locks by canonical resource path and stores stable lock files in the parent's `.paper-pipeline-locks/` (never delete them while writers run). `run_pipeline` and `rerender_workspace` share a cross-process workspace lock from reads through commit. A separate Viewer directory lock covers creation, commit, rollback, pruning, and the INDEX receipt. Lock order is workspace → Viewer, with same-thread reentrancy. The queue workspace lock remains for scheduling; actual write exclusion is independent of jobs root. Retry validates and migrates under the job lock, returning a state conflict on contention; failed claims and write exceptions release descriptors not transferred to a claim.

Viewer manifests record the publishing workspace's absolute path; retranslation resolves that binding. Requests carrying a revision check it both when resolving the target and at final publication, rejecting stale revisions. INDEX producer `0.2.0` republishes bindings for existing workspaces without rerunning other stages. Rationale and regression scope: [P1 repair note](../../.agents/notes/implemented/bug-fix/2026-09-16-m8-p1-concurrency-and-binding.en.md).
