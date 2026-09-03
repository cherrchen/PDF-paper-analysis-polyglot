# Golden tests

[中文](./golden.md) | [English](./golden.en.md)

Expected SemanticDocument output lives under `tests/golden/<fixture>/document.json`.

Canonicalize before comparison. Avoid nondeterministic ordering.

Never update golden output merely to silence a failing test. Decide:

1. the implementation is wrong, or
2. the expected contract intentionally changed

Only (2) justifies `just test-update-golden`. Review the diff before committing.
