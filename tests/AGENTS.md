# Tests

## Fixture licensing

Commit only synthetic, self-authored, public-domain, or explicitly redistributable documents. Do not add arbitrary copyrighted academic PDFs.

Prefer LaTeX source → deterministic compilation → PDF over unexplained binary PDFs.

Every non-trivial PDF fixture needs metadata under `tests/fixtures/metadata/`.

## Golden updates

Never update golden output merely to silence a failing test. Decide whether the implementation is wrong or the contract intentionally changed. Only the second case justifies `just test-update-golden`.

## Binary size

Do not commit a large PDF corpus. Future large datasets need an Agent Note and an external artifact system.

## Rendering tests

Do not use raw PDF binary equality as the default check. Prefer compile success, page count, text extraction sanity, structural metadata, and visual regression only when a stable baseline exists.
