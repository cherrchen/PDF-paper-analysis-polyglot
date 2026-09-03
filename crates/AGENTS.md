# Rust crates

## Ownership

Performance-critical PDF, layout, and FFI code lives under `crates/`.

- `pdf-core` — PDF primitives
- `layout` — layout reconstruction
- `bindings` — cross-language FFI surface

Do not put reusable Rust logic inside applications.

## Unsafe

`unsafe` requires a documented invariant next to the block. Prefer safe wrappers. Do not use `unsafe` for convenience.

## FFI

All cross-language FFI goes through `crates/bindings`. Python and TypeScript packages must not grow parallel native bindings.

## Clippy

CI runs `cargo clippy --workspace --all-targets --all-features -- -D warnings`. Warnings are errors. Use narrow, documented allow attributes.

## Panic / errors

Library crates return `Result`. Do not panic on expected user or document input. `unwrap` is limited to proven invariant bugs.

## Benchmarks

Add benchmarks under `benchmarks/` when a path is performance-critical. Do not commit unexplained numbers.

## Cross-language ownership

Shared document structure is owned by `schemas/`. Rust types that represent SemanticDocument must track the canonical schema, including generated bindings once they exist.
