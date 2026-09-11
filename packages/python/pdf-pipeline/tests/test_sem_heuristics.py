"""Unit tests for M4 heuristic helpers that do not need a fixture PDF."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.fusion import RegionLine
from pdf_pipeline.sem_bibliography import author_year_spans, citation_spans, entry_author_year_key
from pdf_pipeline.sem_footnotes import (
    FootnoteBody,
    ParagraphWindow,
    assign_footnote_references,
    body_reference_spans,
    footnote_marker_label,
)
from pdf_pipeline.sem_paragraphs import split_region_paragraphs
from pdf_pipeline.sem_sections import classify_front_matter
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


def test_table_number_does_not_steal_footnote_reference() -> None:
    text = "See Table 1 for results. Actual footnote1 follows."
    assignments, _messages = assign_footnote_references(
        [ParagraphWindow("p", text, frozenset({"page-1"}))],
        [FootnoteBody("fn-1", "1", "page-1")],
    )
    assert len(assignments) == 1
    assert text[assignments[0].start : assignments[0].end] == "1"
    assert assignments[0].start == text.index("footnote1") + len("footnote")


def test_same_label_footnotes_on_later_pages_both_link() -> None:
    assignments, messages = assign_footnote_references(
        [
            ParagraphWindow("p1", "claim1 on the first page", frozenset({"page-a"})),
            ParagraphWindow("p2", "other1 on the second page", frozenset({"page-b"})),
        ],
        [
            FootnoteBody("fn-a", "1", "page-a"),
            FootnoteBody("fn-b", "1", "page-b"),
        ],
    )
    by_id = {item.footnote_id: item for item in assignments}
    assert by_id["fn-a"].paragraph_id == "p1"
    assert by_id["fn-b"].paragraph_id == "p2"
    assert not any("unlinked" in message for message in messages)


def test_unnumbered_introduction_is_not_swallowed_by_front_matter() -> None:
    roles = classify_front_matter(
        [
            ("title", "Paper Title Here"),
            ("author", "Alice Smith"),
            ("intro", "Introduction"),
            ("body", "This body sentence is long enough to count as a prose paragraph."),
        ],
        {
            "title": "HEADING_LIKE",
            "author": "HEADING_LIKE",
            "intro": "HEADING_LIKE",
            "body": "PARAGRAPH_LIKE",
        },
        {},
    )
    assert roles["title"] == "title"
    assert roles["author"] == "author"
    assert "intro" not in roles


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


# --- Phase 4.1 (M7): 1 Layout -> N Semantic paragraph splitting -----------


def _line(y: float, text: str, height: float = 11.0) -> RegionLine:
    from document_model.generated import schema_models as generated

    return RegionLine(
        rect=generated.Rect(kind="rect", x=70, y=y, width=460, height=height),
        text=text,
        font_size=height,
    )


def test_split_region_keeps_single_paragraph_intact() -> None:
    lines = [_line(100, "One paragraph flows"), _line(114, "across two lines.")]
    pieces = split_region_paragraphs("r1", lines)
    assert len(pieces) == 1
    assert pieces[0].text == "One paragraph flows across two lines."
    assert pieces[0].is_heading is False


def test_split_region_on_paragraph_gap() -> None:
    lines = [
        _line(100, "First paragraph ends here."),
        _line(170, "Second paragraph starts after a wide gap."),
    ]
    pieces = split_region_paragraphs("r1", lines)
    assert [piece.text for piece in pieces] == [
        "First paragraph ends here.",
        "Second paragraph starts after a wide gap.",
    ]


def test_split_region_on_embedded_heading() -> None:
    lines = [
        _line(100, "Intro prose before the heading."),
        _line(120, "2 Methods"),
        _line(134, "Body text of the methods section."),
    ]
    pieces = split_region_paragraphs("r1", lines)
    assert [piece.is_heading for piece in pieces] == [False, True, False]
    assert pieces[1].text == "2 Methods"


def test_split_region_math_line_is_not_heading() -> None:
    lines = [_line(100, "Prose line one."), _line(130, "2 dx = dy")]
    pieces = split_region_paragraphs("r1", lines)
    assert all(not piece.is_heading for piece in pieces)


# --- Phase 4.7 (M7): author-year citations --------------------------------


def test_author_year_spans_extract_keys() -> None:
    text = "Shown by (Vaswani et al., 2017) and (Smith 2020b); math x(1) stays out."
    spans = author_year_spans(text)
    keys = [key for _, _, key in spans]
    assert keys == ["vaswani:2017", "smith:2020b"]
    assert text[spans[0][0] : spans[0][1]] == "(Vaswani et al., 2017)"


def test_author_year_spans_ignore_subscript_brackets() -> None:
    assert author_year_spans("array index x(2019) is not a citation") == []


def test_entry_author_year_key_matches_marker() -> None:
    entry = "[1] Smith, J. Deterministic recovery. Fixture Journal, 2020b."
    assert entry_author_year_key(entry) == "smith:2020b"
    assert entry_author_year_key("no surname, no year") is None
