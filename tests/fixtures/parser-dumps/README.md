Native parser dumps for MinerU / Docling / GROBID adapters.

Classification (do not mix these):

- **synthetic-contract** — self-authored JSON/TEI shaped like native schemas.
  CI maps them into EvidenceBundle and through normalize / layout fusion /
  semantic recovery. They are not recordings of MinerU, Docling, or GROBID.
- **real-tool** — output produced by a named tool version from a named input.
  None are in this directory as of 2026-09-12: the CLIs/modules were not
  installed and `GROBID_URL` was unset. Do not invent recordings to fill
  that gap.

Provenance for each file: `provenance.json`.

Schema notes kept for the synthetic contract:

- Docling-core v2.48 `coord_origin` / `table_cells` / spanned `grid`
- MinerU multi-page `pdf_info` formula ids
- GROBID live path is contract-tested with a local HTTP stub (multipart
  `input`), not a real GROBID process

See `pdf_pipeline.evidence.mineru` (and siblings). Default ensemble remains
`mock` / `docling-sim` / `grobid-sim`.
