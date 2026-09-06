# Agent Note: SemanticDocument canonical model

Status: rejected — landed by later implemented notes; no longer current authority

[中文](./2026-09-03-semantic-document-canonical-model.md) | [English](./2026-09-03-semantic-document-canonical-model.en.md)

## Problem

Python, TypeScript, and Rust will all need a document model. Independent types will diverge.

## Proposal

Keep JSON Schema in `schemas/semantic-document/` as the only canonical contract. Generate language bindings later from that schema. Define Page, Block, TextSpan, BoundingBox, Figure, Table, Equation, Citation, and SourceMapping once the product fields are known.

## Alternatives considered

- Hand-written models per language, synchronized by convention, will drift.
- Protobuf is unnecessary without an RPC or binary-contract need.

## Acceptance criteria

- One schema owns identity and required fields
- Generated bindings have a freshness check
- Language packages do not invent parallel required fields

## Risks

Locking fields too early will force breaking schema bumps during research.
