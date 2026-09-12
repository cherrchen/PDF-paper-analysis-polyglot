# pdf-pipeline (Python)

Owned Python pipeline logic for PDF ingestion and reconstruction.

Applications under `apps/` must call this package rather than duplicating pipeline code.

Default evidence providers are the deterministic `mock` / `docling-sim` / `grobid-sim` registry. Native MinerU / Docling / GROBID adapters map recorded dumps (optional live `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL`); extras `[mineru]` / `[docling]` / `[grobid]` are empty group names and do not pull models or Java.
