# Fixtures

[中文](./fixtures.md) | [English](./fixtures.en.md)

Commit synthetic, self-authored, public-domain, or explicitly redistributable documents only.

Prefer:

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

Each non-trivial fixture has metadata in `tests/fixtures/metadata/`.

Do not commit a huge PDF corpus. Git history must stay small.

Command: `just latex-smoke`.
