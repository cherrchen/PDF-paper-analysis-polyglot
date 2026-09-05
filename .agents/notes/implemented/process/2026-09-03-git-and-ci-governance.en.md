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

Hooks stay fast. PR CI covers format, lint, types, unit tests, docs, schema, and LaTeX smoke. The Python job installs the same TeX Live package set as the LaTeX job, runs `just latex-smoke`, then `just test-python`, because fixture PDFs are not committed and the coverage gate needs them. Tests that need those PDFs skip when the files are missing. Nightly is reserved for corpus, fuzzing, and heavy audits. GitHub rulesets are not silently assumed to exist until applied. Fixture PDFs and the TikZ package set: [CI fixture and TikZ fix](../bug-fix/2026-09-05-ci-tikz-and-fixture-tests.en.md).
