---
name: release
description: Cut a v0.x GitHub release without publishing language registries.
---

# Release

## When to use

Creating a version tag on a releasable `main`.

## Preconditions

Read `docs/development/releases.md`. `main` CI gate is green. No unpublished product artifacts are required.

## Workflow

1. Confirm SemVer `v0.y.z`
2. Update `CHANGELOG.md` for the tag
3. Tag annotated `v0.y.z`
4. Allow the release workflow to create a GitHub Release from changelog notes
5. Do not publish to PyPI, npm, or crates.io

## Validation

The GitHub Release exists. No registry publish steps ran.

## Failure handling

Do not add fake publish secrets. Stop if changelog ownership is unclear.

## Documentation impact

Release policy changes need a process Agent Note.
