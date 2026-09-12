# Agent Note: Git and CI governance

Status: implemented

[中文](./2026-09-03-git-and-ci-governance.md) | [English](./2026-09-03-git-and-ci-governance.en.md)

## Problem

`main` must remain releasable while still allowing fast local iteration.

## Decision

Trunk-based development on `main`. Squash merges. Conventional Commits. Lefthook for pre-commit and pre-push (`just check-fast`). GitHub Actions split by ecosystem with a single `CI / gate` status. Linux is exhaustive CI. macOS and Windows are later portability smokes. Branch protection settings are documented and must be applied on the GitHub remote.

## Alternatives considered

- A permanent `develop` branch would delay releasability without a current need.
- One giant workflow would be unmaintainable.
- Full E2E and corpus tests on every pre-commit would destroy hook latency.

## Consequences

Hooks stay fast. PR CI covers format, lint, types, unit tests, docs, schema, LaTeX smoke, and the `just benchmark` quality gate after `just latex-smoke` and `just test-python` in the Python job. The Python job installs the same TeX Live package set as the LaTeX job, because fixture PDFs are not committed and the coverage and benchmark gates need them. Tests that need those PDFs skip when the files are missing. Nightly reuses the same `ci-python.yml` (including benchmark) instead of a second TeX install. GitHub rulesets are not silently assumed to exist until applied. Fixture PDFs and the TikZ package set: [CI fixture and TikZ fix](../bug-fix/2026-09-05-ci-tikz-and-fixture-tests.en.md). Benchmark on PR CI: [M8 admission closeout](./2026-09-12-m8-admission-closeout.en.md).
