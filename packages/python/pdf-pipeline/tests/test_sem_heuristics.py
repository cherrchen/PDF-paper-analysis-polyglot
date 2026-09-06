"""Unit tests for M4 heuristic helpers that do not need a fixture PDF."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.sem_bibliography import citation_spans
from pdf_pipeline.sem_footnotes import body_reference_spans, footnote_marker_label
from pdf_pipeline.sem_tables import table_content


def test_citation_ranges_expand_inclusively() -> None:
    start, end, numbers = citation_spans("see [1-3] later")[0]
    assert (start, end) == (4, 9)
    assert numbers == ["1", "2", "3"]
    assert citation_spans("see [1\u20133] later")[0][2] == ["1", "2", "3"]
    assert citation_spans("see [1,2] later")[0][2] == ["1", "2"]
    assert citation_spans("see [1, 3] later")[0][2] == ["1", "3"]
    assert citation_spans("x[1] later") == []


def test_footnote_letter_glue_and_symbols() -> None:
    assert body_reference_spans("efficiency1 is high", {"1"}) == [(10, 11, "1")]
    assert body_reference_spans("footnote 1 adds", {"1"}) == [(9, 10, "1")]
    assert body_reference_spans("see 3 later", {"1"}) == []
    assert body_reference_spans("in 2020 we", {"20", "0"}) == []
    assert footnote_marker_label("1. A footnote") == "1"
    assert footnote_marker_label("* A footnote") == "*"
    assert body_reference_spans("note* follows", {"*"}) == [(4, 5, "*")]


def test_table_structure_evidence_wins_over_line_fallback() -> None:
    candidate = generated.TableCandidate(
        evidenceType="TABLE_STRUCTURE",
        id="00000000-0000-0000-0000-000000000001",
        pageId="00000000-0000-0000-0000-000000000002",
        geometry=generated.Rect(kind="rect", x=0, y=0, width=100, height=40),
        rowCount=1,
        columnCount=2,
        cells=[
            generated.TableCellCandidate(row=0, column=0, rowSpan=1, colSpan=1, text="A"),
            generated.TableCellCandidate(row=0, column=1, rowSpan=1, colSpan=1, text="B"),
        ],
        confidence=0.9,
        provenanceIds=[],
    )
    content, reason, _score = table_content(
        lines=None, region_text="ignored merged line", table_candidate=candidate
    )
    assert content.columns == 2
    assert content.rows == 1
    assert [cell.content.text for cell in content.cells] == ["A", "B"]
    assert "evidence" in reason
