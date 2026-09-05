# Golden tests

[中文](./golden.md) | [English](./golden.en.md)

Expected SemanticDocument output lives under `tests/golden/<fixture>/semantic.json`.

Canonicalize before comparison. Avoid nondeterministic ordering. Fixture PDFs come from each environment's `just latex-smoke` run and are not byte-identical across TeX installs; opaque IDs derived from the PDF fingerprint are remapped before comparison. Golden output locks node kinds, text, tree shape, and non-id attributes, not opaque identifiers. `smoke` keeps only strings that extract stably across TeX and PDFium; glyphs such as `\int` belong in `equation-heavy`.

Never update golden output merely to silence a failing test. Decide:

1. the implementation is wrong, or
2. the expected contract intentionally changed

Only (2) justifies `just test-update-golden`. Review the diff before committing.
