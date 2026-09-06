"""Phase 4.4 table recovery: TABLE region -> TableContent.

Structured ``TABLE_STRUCTURE`` evidence (MinerU/Docling class) wins when
present; otherwise a deterministic line fallback keeps the content — one
row per physical line, single column — so no cell text is ever lost.
Fallback tables are observable through their confidence reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdf_pipeline.fusion import RegionLine

CONFIDENCE_EVIDENCE_TABLE = 0.8
CONFIDENCE_FALLBACK_TABLE = 0.6


def table_content(
    *,
    lines: Sequence[RegionLine] | None,
    region_text: str,
    table_candidate: generated.TableCandidate | None,
) -> tuple[generated.TableContent, str, float]:
    """Build TableContent from evidence or the line fallback.

    Returns (content, reason, confidence). Cells are never dropped: the
    fallback row-per-line projection mirrors what the reader sees.
    """
    if table_candidate is not None and table_candidate.cells:
        return (
            generated.TableContent(
                rows=table_candidate.rowCount,
                columns=table_candidate.columnCount,
                cells=[
                    generated.TableCell(
                        row=cell.row,
                        column=cell.column,
                        rowSpan=cell.rowSpan,
                        colSpan=cell.colSpan,
                        content=generated.RichText(text=cell.text, marks=[]),
                    )
                    for cell in table_candidate.cells
                ],
            ),
            "table structure evidence",
            CONFIDENCE_EVIDENCE_TABLE,
        )
    rows = _fallback_rows(lines, region_text)
    cells = [
        generated.TableCell(
            row=index,
            column=0,
            rowSpan=1,
            colSpan=1,
            content=generated.RichText(text=row, marks=[]),
        )
        for index, row in enumerate(rows)
    ]
    return (
        generated.TableContent(rows=len(rows), columns=1 if rows else 0, cells=cells),
        "table fallback: line rows",
        CONFIDENCE_FALLBACK_TABLE,
    )


def _fallback_rows(lines: Sequence[RegionLine] | None, region_text: str) -> list[str]:
    if lines:
        rows = [line.text.strip() for line in lines if line.text.strip()]
        if rows:
            return rows
    return [part.strip() for part in region_text.split("\n") if part.strip()]


def table_candidate_for_region(
    region: generated.LayoutRegion,
    evidence: generated.EvidenceBundle | None,
) -> generated.TableCandidate | None:
    """TABLE_STRUCTURE candidate matched to a region via its label evidence."""
    if evidence is None:
        return None
    evidence_ids = {evidence_id for label in region.labels for evidence_id in label.evidenceIds}
    for candidate in evidence.candidates:
        if (
            isinstance(candidate, generated.TableCandidate)
            and candidate.id in evidence_ids
            and candidate.cells
        ):
            return candidate
    return None
