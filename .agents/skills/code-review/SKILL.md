---
name: code-review
description: Review a change for correctness, architecture, contracts, and Agent Notes.
---

# Code review

## When to use

Reviewing a pull request or a local diff before merge.

## Preconditions

Read the PR template answers. Open current architecture docs for touched areas. Search active Agent Notes.

## Workflow

Review at least: correctness, architecture, dependency direction, typing, error handling, security, performance, tests, LaTeX rendering implications, documentation (both languages for README / `docs/` / Agent Notes), Agent Notes, and generated files.

Reject reusable logic added under `apps/`. Reject parallel SemanticDocument types. Reject manual edits to generated files. Reject golden updates without contract justification. Reject a Chinese docs change without its English companion, or the reverse.

## Validation

Required CI gate is green or the review states why it is not yet.

## Failure handling

Request changes rather than patching over missing notes or tests.

## Documentation impact

If the review discovers a process gap, file a process Agent Note rather than only commenting once.
