# Agent Note: Source-available MIT with Non-Commercial terms

Status: implemented

[中文](./2026-09-03-source-available-noncommercial-license.md) | [English](./2026-09-03-source-available-noncommercial-license.en.md)

## Problem

The project should remain easy to read, fork for research, and contribute to, without granting commercial use rights.

## Decision

The repository uses the MIT License text plus Additional Terms that prohibit commercial use. Personal, academic, educational, research, and internal evaluation use is allowed. Commercial use requires a separate written license. Package metadata points at `LICENSE` and does not claim unmodified OSI-approved MIT.

## Alternatives considered

- Unmodified MIT would permit commercial use, which is not wanted.
- Apache-2.0 would also permit commercial use and add patent grants without solving the commercial restriction.
- CC BY-NC is a poor fit for software.
- PolyForm Noncommercial is purpose-built but is not the requested MIT-shaped grant.

## Consequences

This is source-available, not OSI open source. Downstream must keep both the MIT notice and the Non-Commercial additional terms. `cargo-deny` still allows MIT/Apache dependencies; it does not reclassify this repository as MIT.
