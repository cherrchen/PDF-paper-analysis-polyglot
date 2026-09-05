# Agent Note: CI fixture PDFs and TikZ packages

Status: implemented

[中文](./2026-09-05-ci-tikz-and-fixture-tests.md) | [English](./2026-09-05-ci-tikz-and-fixture-tests.en.md)

## Problem

The `CI / gate` for `c83086a` failed in the Python and LaTeX jobs. The Python job has no TeX and does not compile PDFs under `tests/fixtures/source/latex/build/`; `test_render.py` and the golden tests opened those files directly and raised 13 `FileNotFoundError`s. After the remaining fixture tests skipped, coverage was about 66%, below `fail_under = 80`. The LaTeX job failed compiling `tikz-vector.tex` because `tikz.sty` was missing: `tex/packages.txt` did not declare `pgf` and its dependencies.

## Decision

1. Add `pgf`, `xcolor`, and `everyshi` to `tex/packages.txt`. `tikz-vector` needs TikZ, and the slim TeX Live used in CI does not install undeclared packages. TeX Live 2026 tlmgr has no standalone `ms` package (same class of failure as `array`); `everyshi` is the split successor.
2. Every test that needs a fixture PDF `pytest.skip`s when the file is missing and tells the operator to run `just latex-smoke`. A local run without a prior compile must not crash.
3. The Python job installs the same TeX Live 2026 set as the LaTeX job (`tex/packages.txt`) and runs `just latex-smoke` before `just test-python`. That way the coverage gate and the 11 Tier-1 full-pipeline tests actually execute on a clean checkout, without forking `just test-python` into a second CI-only command.

This note extends [first CI gate fixes](../process/2026-09-03-ci-first-run-fixes.en.md) and [Git and CI governance](../process/2026-09-03-git-and-ci-governance.en.md). It does not change the per-ecosystem job split or the LuaLaTeX backend.

## Alternatives considered

- Committing compiled PDFs would break the fixture rule that sources are tracked and PDFs come from `latex-smoke`, and would bloat Git history.
- Skipping without compiling fixtures in the Python job leaves coverage around 66%, so `just test-python` still fails.
- Dropping the coverage gate to a warning, or inventing a CI-only pytest command, would let GitHub Actions drift from the `justfile`.
- Running pytest only in the LaTeX job and disabling `fail_under` in the Python job would move fixture regressions out of the Python job, and local `just test-python` without a compile would still fail coverage.
- Keeping `ms` in the list makes the TeX Live installer fail on TeX Live 2026 with `package ms not present in repository`.

## Consequences

On a clean checkout, the Python job compiles fixtures before testing. Missing PDFs skip instead of crashing. New fixtures that need TikZ or other TeX packages must update `tex/packages.txt` in the same change. Both the Python and LaTeX jobs install TeX; the shared TeX Live cache makes the second install cheap. Golden comparison remaps PDF-fingerprint IDs: MacTeX and CI TeX Live do not produce byte-identical `smoke.pdf` files, so opaque identifier equality is not the contract.
