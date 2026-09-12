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
| benchmark | corpus quality regression (`just benchmark` vs `tests/benchmark/baseline.json`) |

## Commands

`just test`, `just test-unit`, `just test-integration`, `just test-golden`, `just test-e2e`, `just latex-smoke`, `just benchmark`.

Empty categories print `no <kind> tests currently defined` instead of failing closed from misconfiguration.

The PR CI Python job runs `just benchmark` after compiling fixtures and `just test-python`. A missing fixture, a measurable metric becoming null, a metric drop, or an ERROR/FATAL increase fails the gate. Do not rewrite the baseline to go green. Details: [golden.md](golden.en.md) and [M8 admission](../development/m8.en.md).

Coverage target for core production Python is approximately 80%. Critical SemanticDocument, mapping, and serialization paths will need more later.

See [`fixtures.md`](fixtures.en.md), [`golden.md`](golden.en.md), [`rendering.md`](rendering.en.md).
