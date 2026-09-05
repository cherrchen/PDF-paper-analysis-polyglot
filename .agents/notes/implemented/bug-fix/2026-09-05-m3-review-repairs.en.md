# Agent Note: M3 review repairs

Status: implemented

[中文](./2026-09-05-m3-review-repairs.md) | [English](./2026-09-05-m3-review-repairs.en.md)

## Problem

The 2026-09-05 code review found that the M3 Layout Recovery Engine had the modules but closed its exit gate too early. Tier-1 `twocolumn` fixtures were too short to fill the left column, so they still looked single-column, and `two-column.json` even asserted `singleColumnOnly`. The only default two-column check sat on gitignored arXiv PDFs. Page numbers entered `primaryFlow`, regions kept empty `provenanceIds`, table captions projected as `FIGURE_CAPTION`, math was labeled HEADING, and `match_key` plus tautological asserts were dead code.

This note supplements the existing [M3 Layout Recovery Engine implementation note](../architecture/2026-09-05-m3-layout-recovery-engine.en.md). It keeps XY-cut, mock Evidence, and structure-driven reading flow while correcting the completion evidence.

## Decision

Repair against the original exit gate. Do not rebuild the layout engine, and do not install real MinerU:

1. Lengthen `two-column`, `mixed-bands`, `footnote-multicolumn`, and `spanning-figure` so the left column fills and the right column has visible body text. Keep a full-width skip inside the `mixed-bands` `\twocolumn[...]` optional argument so one page has both `FULL_WIDTH` and `MULTI_COLUMN`, with the spanning figure as `SPANNING` on the next page.
2. Add `expectMultiColumn` to ground truth and assert at least one `MULTI_COLUMN` band with two columns. Mark BERT / Attention real-paper tests `@pytest.mark.slow`; default CI does not depend on external PDFs.
3. Relax the footer strip to 85% of page height so short numeric page numbers become FOOTER even at body size. Do not merge a footnote-marker line into the previous block.
4. Write each fused region's `provenanceIds`. Project `TABLE_BLOCK` as `TABLE_CAPTION`. Reject `=`-shaped text in `_is_heading_like`. Recompute `body_font` after furniture splitting.
5. Use `NormalizedCandidate.match_key()` as an observable co-location signal in fusion. Assign orphan columns by y-overlap. Drop graphics thinner than 2pt before column cuts. Quantize in-column y to 4pt so same-baseline items stay left-to-right.
6. Compute region precision only over non-empty `primaryFlow` text regions; do not invent a high precision gate. Leave footnote reference evidence to M4.

## Alternatives considered

- Keep M3 marked complete and leave two-column gating on external PDFs: clean-checkout CI cannot reproduce the exit gate.
- Replace XY-cut with a page-wide projection or merge adjacent `MULTI_COLUMN` bands into a full left-then-right pass: that would reverse the landed structure-detection decision. This round only repairs fixtures and sort jitter.
- Install real MinerU to support precision: heavy dependencies and unreproducible environments still fail the bar, and snippet-level ground truth cannot support region-level precision.

## Consequences

- The M3 exit gate closes after these review repairs: synthetic fixtures own two-column / spanning / footnote gates; the benchmark meets recall ≥ 0.9, pairwise ≥ 0.95, and exact sequences.
- The smoke golden changes on purpose: math is no longer HEADING, and the page number leaves the semantic tree.
- Known-limitation updates live on the M3 implementation note: region precision waits for region-level annotation; reference evidence remains M4.
