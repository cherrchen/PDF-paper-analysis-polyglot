# PDF ingestion

[中文](./pdf-ingestion.md) | [English](./pdf-ingestion.en.md)

PDF ingestion, parser selection, and adaptive routing: [`document-architecture.en.md`](document-architecture.en.md) sections 34–42 and 36–40.

Key points:

- **Canonical Physical Backend**: PDFium → `PhysicalDocument`
- **Layout evidence (current default)**: deterministic `MockLayoutEvidenceProvider` (MinerU-like layout specialist). Real MinerU / Docling adapters map native dumps (optional live services) and still emit only `EvidenceBundle`; the default capability registry does not swap the primary.
- **Scholarly evidence**: default `grobid-sim`; the real GROBID adapter uses the same Protocol (dumps / optional HTTP).
- **Adaptive routing**: `DocumentProbe` decides which parsers run; not every parser on every run

Heavy native dependencies (PDFium, MuPDF, Poppler, Ghostscript, OpenCV, Tesseract, Torch) require an Agent Note before adoption. See [`docs/development/dependencies.md`](../development/dependencies.en.md).
