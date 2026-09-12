Native parser dumps for MinerU / Docling / GROBID adapters.

These are synthetic, self-authored recordings shaped like native schemas
(Docling-core v2.48 `coord_origin` / `table_cells` / spanned `grid`,
MinerU multi-page `pdf_info`). CI maps them into EvidenceBundle; live
model/Java services are optional and off the default install. The GROBID
live path is contract-tested with a local HTTP stub (multipart `input`),
not a real GROBID process. See `pdf_pipeline.evidence.mineru` (and siblings).
