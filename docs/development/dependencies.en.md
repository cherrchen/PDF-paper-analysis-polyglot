# Dependencies

[中文](./dependencies.md) | [English](./dependencies.en.md)

Evaluate new dependencies against:

- Can the standard library solve this?
- Does an existing dependency already solve it?
- Runtime or development-only?
- License compatibility with this repository's MIT plus Non-Commercial terms, and with `deny.toml` for Rust
- Maintenance and security
- Native / binary / browser / WASM / cross-platform cost

Heavy native libraries (PDFium, MuPDF, Poppler, Ghostscript, OpenCV, Tesseract, Torch) need an architecture or process Agent Note.

TeX packages are dependencies. Add them to `tex/packages.txt` with a concrete need.

Renovate is the updater. Do not add Dependabot for the same ecosystems. TeX Live year upgrades are manual; see [`latex.md`](latex.en.md).

Policy: [`.agents/notes/implemented/process/2026-09-03-dependency-management-policy.md`](../../.agents/notes/implemented/process/2026-09-03-dependency-management-policy.en.md).
