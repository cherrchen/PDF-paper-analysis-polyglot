# Agent Note: First CI gate fixes

Status: implemented

[中文](./2026-09-03-ci-first-run-fixes.md) | [English](./2026-09-03-ci-first-run-fixes.en.md)

## Problem

The first `CI / gate` run failed on the LaTeX, docs, and security jobs even though Python, TypeScript, and Rust passed.

## Decision

TeX Live 2026 tlmgr has no standalone `array` package (it ships in `tools`). The CI package list installs `chktex` and `latexindent` instead of `array`. Vale uses a project vocabulary so tool names are not spelling errors. Every `actions/checkout` sets `persist-credentials: false`. Same-repo reusable workflows keep `./` paths: GitHub Actions and actionlint both reject `$/`, so zizmor's `self-repository` rule is disabled in `.github/zizmor.yml` and ignored on the caller lines. Rust CI runs `rustup component add rustfmt clippy` after mise, because a `minimal` toolchain profile does not include them. Action pin comments use two spaces before `#` to satisfy yamllint.

## Alternatives considered

- Dropping Vale or zizmor to warning-only would hide real issues.
- Keeping `array` in `tex/packages.txt` makes `zauguin/install-texlive` fail on TeX Live 2026.

## Consequences

Later docs and workflow edits must keep the Vale vocabulary and zizmor checkout rule. The CI LaTeX job installs the Debian Perl packages latexindent needs.
