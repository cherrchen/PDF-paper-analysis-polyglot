# Testing

[中文](./overview.md) | [English](./overview.en.md)

## Taxonomy

| Kind | Meaning |
| --- | --- |
| unit | small deterministic behavior |
| integration | multiple internal components |
| golden | canonical structured expected output |
| regression | previously observed bug reproduction |
| e2e | product-level workflow |
| rendering | SemanticDocument → LaTeX → PDF |
| benchmark | performance and memory |

## Commands

`just test`, `just test-unit`, `just test-integration`, `just test-golden`, `just test-e2e`, `just latex-smoke`.

Empty categories print `no <kind> tests currently defined` instead of failing closed from misconfiguration.

Coverage target for core production Python is approximately 80%. Critical SemanticDocument, mapping, and serialization paths will need more later.

See [`fixtures.md`](fixtures.en.md), [`golden.md`](golden.en.md), [`rendering.md`](rendering.en.md).
