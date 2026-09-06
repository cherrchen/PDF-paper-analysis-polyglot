# Agent Note: Product Requirements Document

Status: implemented

[中文](./2026-09-06-product-requirements.md) | [English](./2026-09-06-product-requirements.en.md)

## Problem

`docs/product/` was reserved for product requirements and UX notes, but lacked an authoritative end-user product requirements document. Architecture, schema, and milestone work had no explicit upstream product constraint.

## Decision

Establish PRD v0.1 at `docs/product/requirements.md` (Chinese primary) with English companion `requirements.en.md`. The document defines product goals, functional requirements, non-goals, acceptance criteria, and open questions. Architecture and development docs should treat it as upstream constraint rather than silently revising product requirements. `docs/product/README.md` indexes it; `docs/development/roadmap.md` references it as the requirements authority.

## Alternatives considered

- Placing the PRD under `docs/architecture/`: would mix product requirements with architecture contracts and break one-fact-one-home.
- Agent Note only: notes suit decision records, not a long-form, standalone product requirements source of truth.
- Chinese only, no English companion: violates the repository bilingual documentation convention.

## Consequences

For new or changed product behavior, check PRD v0.2 first and update the requirements doc. On technical conflict, revisit the technical plan. v0.1 establishment is in this directory; v0.2 closes the eight open questions—see [Product Requirements v0.2](./2026-09-06-product-requirements-v02.en.md).
