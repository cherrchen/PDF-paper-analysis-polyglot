# Agent Note: M8 P2 reader first-page transaction

Status: implemented

[中文](./2026-09-16-m8-p2-reader-load.md) | [English](./2026-09-16-m8-p2-reader-load.en.md)

## Problem

Import load replaced state before first-page rendering, leaving mixed revisions on getPage or render failure.

## Decision

Render both first pages offscreen with PaneRenderer and wait for both before committing state and pixels. Preparation failure destroys candidate PDFs and preserves old PDFs, pages, selection, scrolling, focus and Inspector. Success destroys old PDFs.

## Alternatives considered

Re-rendering old PDFs after swapping can itself fail and briefly shows mixed documents.

## Consequences

Tests directly call real load and PaneRenderer for getPage failure, render failure and success; a delayed sibling verifies cleanup timing. This supplements [P1 repairs](2026-09-16-m8-p1-concurrency-and-binding.en.md) without changing existing retranslation loading. Current state lives in the [reader architecture](../../../../docs/architecture/reader.en.md).
