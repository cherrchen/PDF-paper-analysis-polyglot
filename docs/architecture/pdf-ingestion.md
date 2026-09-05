# PDF 摄入

[中文](./pdf-ingestion.md) | [English](./pdf-ingestion.en.md)

PDF 摄入、parser 选择与自适应路由见 [`document-architecture.md`](document-architecture.md) 第 34–42、36–40 节。

要点：

- **Canonical Physical Backend**：PDFium → `PhysicalDocument`
- **Layout evidence（当前）**：确定性 `MockLayoutEvidenceProvider`（模拟 MinerU 类版面专家）。真实 MinerU / Docling 适配器是目标，尚未安装；接入时仍只输出 `EvidenceBundle`。
- **Scholarly evidence**：GROBID（目标，尚未接入）
- **Adaptive routing**：`DocumentProbe` 决定运行哪些 parser，不是每次都全跑

重型原生依赖（PDFium、MuPDF、Poppler、Ghostscript、OpenCV、Tesseract、Torch）在采用前需要 Agent Note。见 [`docs/development/dependencies.md`](../development/dependencies.md)。
