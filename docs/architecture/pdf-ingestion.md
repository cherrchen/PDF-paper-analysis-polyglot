# PDF 摄入

[中文](./pdf-ingestion.md) | [English](./pdf-ingestion.en.md)

PDF 摄入、parser 选择与自适应路由见 [`document-architecture.md`](document-architecture.md) 第 34–42、36–40 节。

要点：

- **Canonical Physical Backend**：PDFium → `PhysicalDocument`
- **Layout evidence**：MinerU（primary）、Docling（challenger / table）
- **Scholarly evidence**：GROBID
- **Adaptive routing**：`DocumentProbe` 决定运行哪些 parser，不是每次都全跑

重型原生依赖（PDFium、MuPDF、Poppler、Ghostscript、OpenCV、Tesseract、Torch）在采用前需要 Agent Note。见 [`docs/development/dependencies.md`](../development/dependencies.md)。
