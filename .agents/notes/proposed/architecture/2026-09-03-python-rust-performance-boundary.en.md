# Agent Note: Python / Rust performance boundary

Status: proposed

[中文](./2026-09-03-python-rust-performance-boundary.md) | [English](./2026-09-03-python-rust-performance-boundary.en.md)

## Problem

PDF parsing and layout may be too slow in Python, but moving too much into Rust too early raises FFI cost.

## Proposal

Keep orchestration, I/O, and LLM integration in Python. Place proven hot paths in `crates/`, exposed through `crates/bindings`. Do not rewrite the pipeline until measurements exist under `benchmarks/`.

## Alternatives considered

- All-Python would delay native cost but may cap throughput.
- All-Rust would slow iteration on research code.
- Ad-hoc FFI from `apps/` would hide the bindings crate.

## Acceptance criteria

- A measured hotspot exists before a rewrite
- FFI has a single owner crate
- An implemented note records the chosen split

## Risks

Premature FFI complexity. Duplicate logic across languages.
