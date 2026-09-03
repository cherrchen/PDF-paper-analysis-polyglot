# Agent Note rules

[中文](./AGENTS.md) | [English](./AGENTS.en.md)

## Search first

Determine whether a change is a fact update, partial supersession, full supersession, or a new decision.

## Fact update

Paths or defaults changed, decision stands: update the implemented note.

## Decision change

Write a new note. Do not rewrite the old decision into its opposite.

## Partial supersession

Keep both active and cross-link.

## Full supersession

Preserve unique rationale, then archive the old implemented note.

## Proposed format

Starts with `# Agent Note:` and `Status: proposed`. English companions require: Problem, Proposal, Alternatives considered, Acceptance criteria, Risks. Chinese primaries use the matching Chinese headings.

## Implemented format

`Status: implemented`. English companions require: Problem, Decision, Alternatives considered, Consequences. Do not leave proposal-era sections. Chinese primaries use the matching Chinese headings.

Both files keep a language jump line. See [`docs/development/bilingual.md`](../../docs/development/bilingual.en.md).

## Rejected

`Status: rejected — <one-line reason>`. Keep the proposal as considered. Delete low-value rejected notes.

## Archived

Only implemented notes may be archived. Frozen. Not current authority.
