# Python packages

## Ownership

Reusable Python logic lives here, not under `apps/`.

- `document-model` — Python view of SemanticDocument. Canonical schema is `schemas/`.
- `pdf-pipeline` — ingestion, layout recovery, semantic recovery, mapping, and render composition.
- `llm` — model-client and prompt-assembly helpers.

## Typing

Pyright runs in `strict` mode. Unbounded `Any` propagation is forbidden in production code. Exceptions are local, documented, and limited to third-party, parser, serialization, or FFI boundaries.

## Async

Use `async` only at I/O boundaries. Do not mark CPU-bound pure transforms as async without a reason.

## Exceptions

Raise specific exceptions. Do not swallow errors. Convert third-party exceptions at the I/O boundary rather than leaking them through public APIs.

## Public API

Packages must have a deliberate public surface. Prefer explicit `__all__`. Do not re-export another package's types as if they were owned here when `schemas/` is the contract owner.

## I/O

Keep filesystem, network, and process I/O at the edges. Core document transforms should be pure functions of in-memory values.

## Schema ownership

Do not independently maintain an authoritative SemanticDocument in Python. Generate or implement from `schemas/`.
