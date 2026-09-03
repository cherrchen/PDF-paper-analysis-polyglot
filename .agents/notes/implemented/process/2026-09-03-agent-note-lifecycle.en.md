# Agent Note: Agent Note lifecycle

Status: implemented

[中文](./2026-09-03-agent-note-lifecycle.md) | [English](./2026-09-03-agent-note-lifecycle.en.md)

## Problem

Architecture rationale must survive beyond commit messages and chat transcripts, without a second competing ADR system.

## Decision

Agent Notes under `.agents/notes/<lifecycle>/<class>/` are the only decision-record system. Lifecycles are proposed, implemented, rejected, and archived. Classes are feature, bug-fix, simplification, architecture, process, and testing. Validators enforce tree, filename, status, language-specific headings, bilingual pairing, and links as part of `just docs`. Pairing convention: [`.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md`](2026-09-03-bilingual-documentation.en.md).

## Alternatives considered

- `docs/adr/` plus chat notes would duplicate owners.
- Free-form markdown without validators would rot.
- Git history as the only rationale would hide rejected alternatives.

## Consequences

Non-trivial behavior, architecture, contract, process, and testing changes must add or update a note. Taxonomy changes require a process note and validator change.
