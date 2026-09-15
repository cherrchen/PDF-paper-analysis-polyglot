# pdf-pipeline (Python)

Owned Python pipeline logic for PDF ingestion and reconstruction.

Applications under `apps/` must call this package rather than duplicating pipeline code.

Default evidence providers are the deterministic `mock` / `docling-sim` / `grobid-sim` registry. Native MinerU / Docling / GROBID adapters map recorded dumps (optional live `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL` multipart `input`); extras `[mineru]` / `[docling]` / `[grobid]` are empty group names and do not pull models or Java. In-tree dumps are synthetic contracts (`tests/fixtures/parser-dumps/provenance.json`); the synthetic chain is tested through semantic recovery. Real-tool output is not verified and is not the default ensemble.

## Parser configuration

Which provider owns which capability is data, not code. Point `PAPER_CAPABILITY_REGISTRY` — or the CLI flag `--registry <file>` on `python -m pdf_pipeline`, which wins over the environment — at a TOML file with the same shape as `src/pdf_pipeline/data/capability-registry.toml` to route with a different provider ensemble; unset, the bundled registry applies. `just benchmark` reads the same variable, so a replacement can be proved with `PAPER_CAPABILITY_REGISTRY=<file> just benchmark`.

- The override's **bytes**, never its path, key the EVIDENCE/LAYOUT stages: switching parser reruns exactly those stages, and a byte-identical copy at another path reruns nothing.
- The file is read fresh on every run (never cached), and an unreadable or invalid override raises `CapabilityRegistryError` instead of falling back to the bundled providers.
- Changing a *bundled* primary is a deliberate replacement: prove it with an override file plus `just benchmark` first, then commit it separately.
