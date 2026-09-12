# PDF 摄入

[中文](./pdf-ingestion.md) | [English](./pdf-ingestion.en.md)

PDF 摄入、parser 选择与自适应路由见 [`document-architecture.md`](document-architecture.md) 第 34–42、36–40 节。

要点：

- **Canonical Physical Backend**：PDFium → `PhysicalDocument`
- **Layout evidence（当前默认）**：确定性 `MockLayoutEvidenceProvider`（模拟 MinerU 类版面专家）。真实 MinerU / Docling adapter 映射 native dump（可选活服务），仍只输出 `EvidenceBundle`；默认 capability registry 不切换 primary。合成 dump 已测到 semantic recovery；真实工具输出未验证（[M8 准入](../development/m8.md)）。
- **Scholarly evidence**：默认 `grobid-sim`；真实 GROBID adapter 走同一 Protocol（dump / 可选 HTTP）。
- **Adaptive routing**：`DocumentProbe` 决定运行哪些 parser，不是每次都全跑

重型原生依赖（PDFium、MuPDF、Poppler、Ghostscript、OpenCV、Tesseract、Torch）在采用前需要 Agent Note。见 [`docs/development/dependencies.md`](../development/dependencies.md)。
