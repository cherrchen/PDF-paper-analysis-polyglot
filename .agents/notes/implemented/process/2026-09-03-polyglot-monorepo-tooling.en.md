# Agent Note: Polyglot monorepo tooling

Status: implemented

[中文](./2026-09-03-polyglot-monorepo-tooling.md) | [English](./2026-09-03-polyglot-monorepo-tooling.en.md)

## Problem

The repository must support Python, TypeScript, Rust, and LaTeX without each ecosystem becoming a disconnected toolchain.

## Decision

mise pins runtimes and developer tools. Language ecosystems keep native package managers: uv, pnpm, and Cargo. LaTeX uses TeX Live plus latexmk. Lockfiles are committed. Docker is not required for routine local development.

## Alternatives considered

- Language-native version files only (`.python-version`, `nvmrc`) would split the developer interface.
- Nix as the sole toolchain would raise the contribution bar for a student-maintained repo.
- Mandatory Docker for all development would hide native TeX and editor workflows.

## Consequences

`mise install` is the first setup step. CI installs the same mise tools. LaTeX remains an external TeX Live install verified by `just doctor`.
