# Agent Note: M8 batch B local job orchestration, failure attribution, and manual retry

Status: implemented

[中文](./2026-09-14-m8-batch-b-job-orchestration.md) | [English](./2026-09-14-m8-batch-b-job-orchestration.en.md)

## Problem

Batch B of the [M8 admission closeout](../process/2026-09-12-m8-admission-closeout.en.md) requires that `apps/api` expose job status (not only `POST /api/retranslate`), that `apps/worker` become a real executor instead of a liveness stub, that failures be written as Issues with a retry path, and that a killed process resumes from the batch A stage state without losing completed artifacts. Batch A landed only the **single** workspace stage state (`workspace.json`): no queue, no job lifecycle, no cross-workspace serialization, no failure attribution. Batch C (cache), D (failure isolation), and E (real parsers / migration) all need a queryable, retryable Job layer first.

## Decision

1. **Job storage lives in `pdf_pipeline.jobs` (new module), not under `apps/`.** `apps/api` and `apps/worker` only wire it up; repository rules keep reusable logic out of application directories. The job record and lock protocol are local implementation details, deliberately **outside the frozen schemas** and the `just schema` flow (the same class as batch A's `workspace.json`).
2. **File-backed queue with atomic renames.** The jobs root (default `.jobs/`) holds `queued/`, `running/`, `finished/`, and `locks/`; each job is one `<jobId>.json`. Records only move between directories by atomic rename, so a reader never sees a half-written record; `get_job` / `list_jobs` deduplicate with `queued > running > finished` priority, so a crash window never exposes two visible records.
3. **`flock` claiming with kernel-level death detection.** `claim_next` takes two exclusive POSIX `fcntl.flock` locks: per-job (worker mutual exclusion) and per-workspace (serialized, because `lualatex` shares one `build/` per workspace). A lock belongs to the open file description and **the kernel releases it when the process exits** — so `recover_running` distinguishes a dead owner (lock free → requeue as `queued`) from a live one (skip) with no heartbeat, lease, or timeout guessing. `FileLock` is the single platform replacement point (POSIX-only: macOS / Linux / Ubuntu CI).
4. **Manual retry only.** `failed → queued` happens only through `retry_job` (`attempt + 1`, clearing `stage`/`error`/`issues`); there is no automatic retry or backoff. Requeuing only rewinds the Job and **never** clears workspace artifacts — which stages rerun is decided by batch A's `stage_completed`, so completed artifacts are never lost.
5. **Worker concurrency is configurable (N) and one workspace always runs serially.** `JobWorker(concurrency=N)` bounds claims by N (a claimed-but-unexecuted job would waste its locks). The default is 1 because local single-document work needs no parallelism; raising the default touches only `apps/worker` argparse, not the storage or the protocol.
6. **Per-stage failure attribution.** `pipeline._execute_stage(stage, action)` wraps each stage body and raises `StageExecutionError` (carrying the `Stage`) on failure. `run_pipeline` / `rerender_workspace` signatures are unchanged, so existing call sites and tests need no edits.
7. **A stage → IssueCategory map** (`STAGE_ISSUE_CATEGORIES`). Job-level Issues reuse the frozen Issue taxonomy instead of inventing a job-private one: a failure inside a stage is severity `ERROR`, `recoverable: true`, with `stage` set to the stage name; a failure before any stage (unsupported input, unreadable source) is `FATAL`, `recoverable: false`, `stage: null`, category `PHYSICAL_EXTRACTION`. The Issue shape must validate against `document_model.generated.schema_models.Issue`.
8. **Job-level Issues are stored only in the job record**, never appended to `semantic.json`: otherwise one fact has two homes. In-document issues belong to batch D.
9. **HTTP contract**: `GET/POST /api/jobs`, `GET /api/jobs/<id>`, `POST /api/jobs/<id>/retry`; submission requires absolute paths (`source` must already exist). A known path with a wrong method gives 405, an unknown path gives 404, and the body limit is shared with `/api/retranslate` (`MAX_BODY_BYTES`). Endpoints keep importing `pdf_pipeline` lazily, so API startup does not load pdfium.

Current-state documentation: [`docs/architecture/storage.en.md`](../../../../docs/architecture/storage.en.md) (new "Jobs and job records" section) and [`docs/architecture/api.en.md`](../../../../docs/architecture/api.en.md) (endpoint table).

## Alternatives considered

- **Automatic retry with backoff**: on a local single-user setup it hides real failures and conflates transient with deterministic errors; writing an Issue and letting a human retry serves the traceability goal better.
- **A SQLite queue (e.g. `sqlite3` or APScheduler)**: an extra runtime dependency plus a migration path, when job counts are single-digit and atomic rename with one file lock covers the crash window.
- **TTL / lease + heartbeat timeout detection**: requires choosing a "how long is dead" threshold — below it truly dead jobs linger, above it a slow live job (`lualatex` compiles) is misjudged. `flock` is released by the kernel on exit, so the detection is exact.
- **Modeling the job record in a frozen schema**: the record is a local implementation detail that will evolve with batches C–F (cache keys, Project grouping); the frozen flow's cost is not justified.
- **No per-workspace lock, relying on `concurrency=1`**: concurrency N would silently race on the shared `build/` (mutual `lualatex` overwrites), and concurrency N is a stated product capability.
- **Unbounded claiming (claim every queued job at once)**: claimed-but-queued jobs would hold their job and workspace locks for a long time, blocking other workers.
- **Putting `StageExecutionError` under `apps/`**: the stage enum belongs to `pdf_pipeline`; attribution must sit next to the stage definition or `apps` has to re-interpret stage semantics.
- **Clearing the workspace before a retry**: that throws away batch A's value (reusing completed stages) and turns "retry" into "start over".

## Consequences

- `apps/worker` is now a real executor: `--jobs-root` / `--concurrency` / `--poll-interval` / `--once`, with `run_forever` recovering orphans before polling; `status()` is kept for liveness checks (so `test_worker_status.py` still holds).
- `apps/api` grows from a single `POST /api/retranslate` into a Job API with optional query/submit/retry, and `make_handler` gains a third required `jobs_root` parameter (`--jobs-root`, default `.jobs`). `.jobs/` is now in `.gitignore`.
- Crash-safety boundary: process killed → kernel releases the lock → the next start requeues via `recover_running` → the stage state decides what reruns. If `_execute` itself raises (so `future.result()` really raises), the `finally` releases the remaining claims and the record stays in `running/`, again reclaimed by the next `recover_running` — no artifact loss and no silent success.
- Batch C can extend cache keys on `StageExecutionError` / `input_fingerprint`; batch D can isolate specialist failures on an in-document Issue channel beside `job_failure_issue`; batch F, if it introduces Project grouping, is a new concept **above** the job record and leaves `source`/`workspace`/`viewerDataDir` untouched.
- Known boundaries (not defects): translation-config changes do not invalidate the TRANSLATE stage (batch C); `fcntl.flock` is POSIX-only; submission takes explicit absolute paths with no Project abstraction.
- Verification: new `test_jobs.py` (16), `test_job_worker.py` (6), `test_jobs_api.py` (12), `test_worker_cli.py` (2); `just lint-python`, `just typecheck-python`, `just test-python` (499 passed, 5 deselected), `just test-ts` (50 passed), `just docs-fast`, and `just check-fast` all green; a real `lualatex` end-to-end CLI smoke passed: API submit → `worker --once` → all 8 manifest stages completed with `target.pdf` produced; a broken input → failed job with `FATAL`/`recoverable: false` → retry 202 (attempt 2) → second retry 409; SIGKILL against a real `run_forever` worker (with `ingest`/`physical`/`evidence`/`layout` already committed) → the record stayed in `running/` → `recover_running` requeued it → `worker --once` finished it with the pre-kill artifacts byte-identical.
