# Agent Note: Schema version boundary before the first feature

Status: implemented

[中文](./2026-09-04-pre-functional-schema-versioning.md) | [English](./2026-09-04-pre-functional-schema-versioning.en.md)

## Problem

M1 established the `0.1.0` schema development baseline, but the repository does not yet have a runnable end-to-end feature. Treating that baseline as a published compatibility freeze would force pre-feature contract corrections to create version bumps without real consumers or migration targets.

## Decision

All canonical document schemas keep `0.1.0` as their development target until the first functional vertical slice passes its exit gate. Breaking corrections may retain the version during this stage, provided the canonical schemas, fixtures, generated bindings, and cross-language tests change atomically.

The compatibility freeze takes effect when that vertical slice passes its exit gate, or earlier if any schema or generated package is published. Breaking changes after that point require a version change, migration, fixture, compatibility test, and Agent Note.

This decision defines the wire/schema compatibility boundary; it does not remove Document Architecture v0.1 as the architectural baseline. It supplements the freeze wording in [M1 Core Document Contracts](../architecture/2026-09-04-m1-core-document-contracts.en.md) and [M1 contract review repairs](../architecture/2026-09-04-m1-review-repairs.en.md).

## Alternatives considered

- Bump the version for every breaking development correction: without published consumers, versions and migrations would add noise rather than protection.
- Remove version governance entirely: this would leave no compatibility promise for persisted data after functionality exists.
- Freeze only at the first formal release: end-to-end functionality may create persisted data and internal consumers before that release, so this boundary is too late.

## Consequences

- Development-stage corrections such as `LayoutDocument.groups` may remain part of `0.1.0` without inventing a migration.
- Development contract changes must still pass `just schema`, language checks, and `just generate-check`.
- The first functional vertical slice or an earlier publication creates an explicit, reviewable compatibility freeze.
