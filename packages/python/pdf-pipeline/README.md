# pdf-pipeline (Python)

Owned Python pipeline logic for PDF ingestion and reconstruction.

Applications under `apps/` must call this package rather than duplicating pipeline code.

Default evidence providers are the deterministic `mock` / `docling-sim` / `grobid-sim` registry. Native MinerU / Docling / GROBID adapters map recorded dumps (optional live `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL` multipart `input`); extras `[mineru]` / `[docling]` / `[grobid]` are empty group names and do not pull models or Java. In-tree dumps are synthetic contracts (`tests/fixtures/parser-dumps/provenance.json`); the synthetic chain is tested through semantic recovery. Real-tool output is not verified and is not the default ensemble.
