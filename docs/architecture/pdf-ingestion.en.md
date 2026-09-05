# PDF ingestion

[中文](./pdf-ingestion.md) | [English](./pdf-ingestion.en.md)

PDF ingestion, parser selection, and adaptive routing: [`document-architecture.en.md`](document-architecture.en.md) sections 34–42 and 36–40.

Key points:

- **Canonical Physical Backend**: PDFium → `PhysicalDocument`
- **Layout evidence (current)**: deterministic `MockLayoutEvidenceProvider` (MinerU-like layout specialist). A real MinerU / Docling adapter is the target and is not installed; when added it still emits only `EvidenceBundle`.
- **Scholarly evidence**: GROBID (target, not wired yet)
- **Adaptive routing**: `DocumentProbe` decides which parsers run; not every parser on every run

Heavy native dependencies (PDFium, MuPDF, Poppler, Ghostscript, OpenCV, Tesseract, Torch) require an Agent Note before adoption. See [`docs/development/dependencies.md`](../development/dependencies.en.md).
