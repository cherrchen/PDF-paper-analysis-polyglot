---
name: repo-bootstrap
description: Initialize or repair the polyglot repository toolchain, workspaces, and quality gates.
---

# Repo bootstrap

## When to use

Setting up a new clone, repairing toolchain drift, or adding a missing workspace quality check.

## Preconditions

Read `README.md`, `docs/development/setup.md`, and `justfile`.

## Workflow

1. `mise install`
2. `just setup`
3. `just doctor`
4. Fix missing LaTeX with the printed TeX Live guidance; do not skip it
5. `just check-fast`

## Validation

`just doctor` exits 0. Lockfiles exist. Lefthook is installed.

## Failure handling

Do not comment out checks. Fix the toolchain pin or the recipe.

## Documentation impact

Setup changes update `docs/development/setup.md` (and `setup.en.md`) and the tooling Agent Note if the decision changed.
