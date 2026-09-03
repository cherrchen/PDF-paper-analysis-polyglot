# Rendering tests

[中文](./rendering.md) | [English](./rendering.en.md)

Do not compare raw PDF bytes by default. Object order and metadata can vary.

Validation levels:

1. LaTeX compile success
2. PDF page count
3. text extraction sanity
4. expected structural metadata
5. visual regression with tolerance, only when a stable baseline exists

`just latex-smoke` covers (1) for first-party fixtures. Pixel-diff is not implemented.
