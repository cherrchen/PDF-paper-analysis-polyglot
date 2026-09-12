# Storage

[中文](./storage.md) | [English](./storage.en.md)

Persistent object storage, artifact layout, and dataset hosting remain **intentionally unresolved**; the local Project / Document Workspace convention was closed by [M8 v1 batch A](../development/m8.en.md), see below.

## Local workspace (M8 batch A, closed)

`run_pipeline(source_pdf, out_dir)` turns `out_dir` into a **resumable local workspace**. Directory layout:

```text
<workspace>/
  workspace.json          # ad-hoc manifest (probe.json class, outside frozen schemas)
  source.pdf              # source PDF bytes kept by INGEST
  physical.json …         # per-stage canonical JSON artifacts
  probe.json              # probe + routing diagnostics (ad-hoc)
  evidence-bundles.json   # ad-hoc persistence of per-provider bundles
  resources/              # images and figure PDF fragments
  build/                  # LaTeX build output (target.pdf), not a manifest artifact
  viewer/data/            # viewer revisions (existing publish transaction)
```

### Stages and commit protocol

Stage enum: `INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX` (`pdf_pipeline.workspace`).

- Each stage records in `workspace.json`: status, artifact relative paths + sha256, producer version, and an input fingerprint (producer version + upstream artifact hashes).
- Commit order: artifacts are staged under `.staging/`, replaced one atomic rename at a time, and `workspace.json` is rewritten atomically last — the manifest is the **single commit pointer**.
- Resume: a stage is skipped only when `stage_completed` holds (COMPLETED + artifact hashes verify + input fingerprint matches upstream records); otherwise it reruns. After an interrupt, restart reruns only unfinished stages; a half-written artifact set is never accepted as success.
- Source binding: the manifest's `sourceFingerprint` locks the source PDF; unknown `workspaceVersion` and a foreign source PDF are explicit errors (migration belongs to batch E).

Authoritative implementation: `packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` and the stage runners in `pipeline.py`; decision rationale in Agent Note `2026-09-12-m8-batch-a-workspace-stages`.

### Current boundaries

- `workspace.json` is an ad-hoc file; its schema changes do not go through the `just schema` frozen flow.
- Stage invalidation on translation-config changes and cross-config cache keys belong to batch C; this version's resume only compares upstream artifact hashes.
- Viewer revision publishing keeps the existing `_publish_viewer_revision` transaction and is not tracked file-by-file in the manifest.

## Still unresolved

Persistent object storage, multi-machine sharing, dataset hosting. A future external dataset system requires a testing or architecture Agent Note.

Keep Git history small. Do not commit a large PDF corpus.
