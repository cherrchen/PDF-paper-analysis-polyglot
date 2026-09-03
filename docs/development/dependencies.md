# 依赖

[中文](./dependencies.md) | [English](./dependencies.en.md)

评估新依赖时问：

- 标准库能否解决？
- 现有依赖是否已经解决？
- 运行时还是仅开发？
- 与本仓库 MIT 加非商用条款是否兼容，以及 Rust 侧是否符合 `deny.toml`
- 维护与安全
- 原生 / 二进制 / 浏览器 / WASM / 跨平台成本

重型原生库（PDFium、MuPDF、Poppler、Ghostscript、OpenCV、Tesseract、Torch）需要 architecture 或 process Agent Note。

TeX 宏包也是依赖。有具体需求时写入 `tex/packages.txt`。

更新器用 Renovate。不要为同一生态再加 Dependabot。TeX Live 年份升级是手工的；见 [`latex.md`](latex.md)。

策略：[`.agents/notes/implemented/process/2026-09-03-dependency-management-policy.md`](../../.agents/notes/implemented/process/2026-09-03-dependency-management-policy.md)。
