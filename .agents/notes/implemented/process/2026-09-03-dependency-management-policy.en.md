# Agent Note: Dependency management policy

Status: implemented

[中文](./2026-09-03-dependency-management-policy.md) | [English](./2026-09-03-dependency-management-policy.en.md)

## Problem

A polyglot repo can accumulate overlapping tools, license-incompatible crates, and undeclared TeX packages.

## Decision

uv, pnpm, and Cargo are the only language dependency managers. Renovate updates npm, Python, Cargo, and GitHub Actions. Dependabot is not configured for those ecosystems. `cargo-deny` enforces Rust advisory, license, ban, and source policy. TeX packages are listed in `tex/packages.txt` and are not faked through Renovate. Heavy native libraries require an Agent Note.

## Alternatives considered

- Poetry or Pipenv beside uv would split Python resolution.
- npm or yarn lockfiles beside pnpm would split JavaScript resolution.
- Dependabot plus Renovate would duplicate noise.

## Consequences

New tools that overlap Ruff, Biome, or rustfmt are forbidden without a process note. License metadata for this repository is custom (MIT plus Non-Commercial) and must not be labeled unmodified MIT in registries.
