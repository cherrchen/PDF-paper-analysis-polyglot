"""Phase 4.5 equation recovery: display blocks and inline math marks.

PDFium fragments real display math (large delimiters, superscript limits)
into several small text regions that the reading flow links with
CONTINUATION edges. A display-equation candidate is therefore a
primary-flow run of short math fragments, optionally led by an
``...integral:`` intro and bracketed by its ``(1)`` number (either side).
Recognition may fail without losing content: every equation node keeps
the raw region text as fallback, and inline math becomes marks inside
its host paragraph, never a separate node.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pdf_pipeline.fusion import RegionLine

# Display-equation heuristics (Roadmap 4.5: deterministic, observable).
EQUATION_MAX_CHARS = 80
EQUATION_MATH_RATIO = 0.3
EQUATION_FRAGMENT_MAX_LINES = 3
EQUATION_LEADIN_MAX_CHARS = 60
EQUATION_SOLO_MAX_CHARS = 30
EQUATION_SOLO_RATIO = 0.5
EQUATION_NUMBER = re.compile(r"^\(\d{1,3}\)$")

# Four-letter English word: prose, not math. Single variables stay allowed.
_PROSE_WORD = re.compile(r"[A-Za-z]{4,}")

# Characters that mark text as mathematical rather than prose.
_MATH_CHARS = frozenset(
    "=+-\u2212\u00d7\u2211\u220f\u222b\u221a\u221e\u2260\u2264\u2265\u00b1"
    "^_\\()[]{}/0123456789"
    "\u03b1\u03b2\u03b3\u03b4\u03f5\u03b8\u03bb\u03bc\u03c0\u03c3\u03c6\u03c9"
    "xyzabcnfde"
    "XYZABCNFD"
)

# Inline windows: anchor on a relation/script operator, then expand over
# adjacent whitespace-separated tokens that are math-shaped.
_OPERATOR = re.compile(r"[=^_]")
_INLINE_WINDOW_MAX_CHARS = 40

# Short lone operands that only join an existing CONTINUATION chain (never
# start one): PDFium splits ``\frac{1}{3}`` into ``1`` / ``3`` regions.
_CHAIN_SOLOS = frozenset(str(n) for n in range(100))


def math_density(text: str) -> float:
    """Fraction of non-space characters that are math-ish."""
    chars = [char for char in text if not char.isspace()]
    if not chars:
        return 0.0
    math = sum(1 for char in chars if char in _MATH_CHARS)
    return math / len(chars)


def is_display_equation_text(text: str) -> bool:
    """A short, math-dense fragment that reads as display math, not prose.

    Any English-shaped word of four letters or more disqualifies the text:
    PDFium puts inline math and its sentence in one region, and a real
    display fragment never carries prose (``Inline identity f (x ) = x2
    appears beside prose.`` must stay a paragraph).
    """
    stripped = text.strip()
    if not stripped or len(stripped) > EQUATION_MAX_CHARS:
        return False
    if stripped.endswith((":", ";")):
        return False
    if _PROSE_WORD.search(stripped):
        return False
    return math_density(stripped) >= EQUATION_MATH_RATIO


def is_equation_number_text(text: str) -> bool:
    """``(12)`` equation-number label."""
    return bool(EQUATION_NUMBER.match(text.strip()))


def display_groups(
    primary_flow: Sequence[str],
    region_texts: Mapping[str, str],
    labels: Mapping[str, str | None],
    lines: Mapping[str, Sequence[RegionLine]],
    *,
    continuation: Mapping[tuple[str, str], float],
) -> list[list[str]]:
    """Disjoint primary-flow runs that each form one display equation.

    A group is a maximal chain of adjacent CONTINUATION-linked math
    fragments (or a single FORMULA-labeled region) starting at math; a
    ``...integral:`` lead-in joins the front and an ``(n)`` region joins
    on either side as the number. When no member is FORMULA-labeled, the
    combined text must be clearly display math (see :func:`_strong_math`)
    so stray short fragments in prose never become equations.
    """
    flow = [region_id for region_id in primary_flow if region_id in region_texts]
    scan = _Scan(flow, region_texts, labels, lines, continuation)
    groups: list[list[str]] = []
    consumed: set[str] = set()
    index = 0
    while index < len(flow):
        previous = flow[index - 1] if index > 0 else None
        prev_free = previous is not None and previous not in consumed
        run = scan.equation_run(index, prev_free=prev_free)
        if run is None:
            index += 1
            continue
        groups.append(run[0])
        consumed.update(run[0])
        index = run[1] + 1
    return groups


class _Scan:
    """Flow scan state for display-equation detection."""

    def __init__(
        self,
        flow: Sequence[str],
        region_texts: Mapping[str, str],
        labels: Mapping[str, str | None],
        lines: Mapping[str, Sequence[RegionLine]],
        continuation: Mapping[tuple[str, str], float],
    ) -> None:
        self._flow = flow
        self._texts = region_texts
        self._labels = labels
        self._lines = lines
        self._continuation = continuation

    def equation_run(self, start: int, *, prev_free: bool) -> tuple[list[str], int] | None:
        """(group, last flow index) for an equation at ``flow[start]``; None if not math."""
        position = start
        lead_in = self._lead_in(self._flow[start])
        if lead_in:
            if start + 1 >= len(self._flow) or not self._is_fragment(self._flow[start + 1]):
                return None
            position = start + 1
        if not self._is_fragment(self._flow[position]):
            return None
        run = [self._flow[position]]
        while position + 1 < len(self._flow):
            nxt = self._flow[position + 1]
            if is_equation_number_text(self._texts.get(nxt, "")):
                run.append(nxt)
                position += 1
                break
            if (run[-1], nxt) not in self._continuation or not self._is_fragment(nxt):
                break
            run.append(nxt)
            position += 1
        run, position = self._absorb_tail(run, position)
        if lead_in:
            run.insert(0, self._flow[start])
        elif (
            start > 0
            and prev_free
            and is_equation_number_text(self._texts.get(self._flow[start - 1], ""))
        ):
            # article places the (n) before the row when the equation body
            # is a FORMULA region; absorb the leading number.
            run.insert(0, self._flow[start - 1])
        if not any(self._labels.get(region_id) == "FORMULA" for region_id in run):
            math_members = [
                region_id
                for region_id in run
                if region_id != (self._flow[start] if lead_in else None)
                and not is_equation_number_text(self._texts.get(region_id, ""))
            ]
            combined = " ".join(
                self._texts.get(region_id, "") for region_id in math_members
            ).strip()
            if not _strong_math(combined):
                return None
        return (run, position)

    def _absorb_tail(self, run: list[str], position: int) -> tuple[list[str], int]:
        """Absorb ``digit..., (n)`` tails that lost their CONTINUATION edge.

        Align environments fragment into exponent digits immediately before
        the row number; when the region right after the run is one of those
        lone operands and the next one is an ``(n)`` number, both join.
        """
        while position + 2 < len(self._flow):
            nxt = self._flow[position + 1]
            after = self._flow[position + 2]
            text = self._texts.get(nxt, "").strip()
            if not (text.isdigit() and len(text) <= 2):
                break
            if not is_equation_number_text(self._texts.get(after, "")):
                break
            run.append(nxt)
            position += 1
        if position + 1 < len(self._flow) and is_equation_number_text(
            self._texts.get(self._flow[position + 1], "")
        ):
            run.append(self._flow[position + 1])
            position += 1
        return run, position

    def _is_fragment(self, region_id: str) -> bool:
        text = self._texts.get(region_id, "")
        stripped = text.strip()
        if not stripped or len(stripped) > EQUATION_MAX_CHARS:
            return False
        if self._labels.get(region_id) == "FORMULA":
            return True
        if len(self._lines.get(region_id, ())) > EQUATION_FRAGMENT_MAX_LINES:
            return False
        return is_display_equation_text(stripped) or stripped in _CHAIN_SOLOS

    def _lead_in(self, region_id: str) -> bool:
        """An intro sentence (``A displayed integral:``) that leads its math."""
        source = self._texts.get(region_id, "").strip()
        return source.endswith(":") and len(source) <= EQUATION_LEADIN_MAX_CHARS


def _strong_math(text: str) -> bool:
    """Unambiguous display math: short, dense, with a relation or script."""
    stripped = text.strip()
    if not stripped or len(stripped) > EQUATION_SOLO_MAX_CHARS:
        return False
    if not _OPERATOR.search(stripped):
        return False
    return math_density(stripped) >= EQUATION_SOLO_RATIO


def equation_content(
    region_texts: Mapping[str, str],
    group: Sequence[str],
    *,
    formula_candidate: generated.FormulaCandidate | None = None,
) -> generated.EquationContent:
    """Project a group into EquationContent with mandatory fallbacks."""
    parts = [region_texts.get(region_id, "").strip() for region_id in group]
    number = equation_number(region_texts, group)
    body = [part for part in parts if part and not is_equation_number_text(part)]
    raw_text = " ".join(body).strip()
    fields: dict[str, str] = {"unicodeText": raw_text, "rawText": raw_text}
    if formula_candidate is not None:
        fields["unicodeText"] = formula_candidate.unicodeText or raw_text
        fields["rawText"] = formula_candidate.rawText or raw_text
        optional = {
            "latex": formula_candidate.latex,
            "mathml": formula_candidate.mathml,
            "number": formula_candidate.number or number,
            "previewResourceId": formula_candidate.previewResourceId,
        }
        fields.update({key: value for key, value in optional.items() if value is not None})
    elif number is not None:
        fields["number"] = number
    return generated.EquationContent(**fields)


def equation_number(region_texts: Mapping[str, str], group: Sequence[str]) -> str | None:
    """``(n)`` fragment text minus parentheses, at either end of the group."""
    for region_id in (group[-1], group[0]) if group else ():
        text = region_texts.get(region_id, "").strip()
        if is_equation_number_text(text):
            return text[1:-1].strip()
    return None


def inline_equation_marks(text: str) -> list[generated.InlineMark]:
    """Detect short math windows inside a paragraph's joined text.

    Every ``=``/``^``/``_`` operator anchors a window that expands left
    and right over math-shaped whitespace tokens (single variables, digit
    runs, bracket runs) while it stays <= 40 characters. Prose words stop
    the expansion: ``f (x ) = x2`` is marked, ``appears beside prose.`` is
    not. Misses lose nothing — the text stays in the paragraph either way.
    """
    marks: list[generated.InlineMark] = []
    for operator in _OPERATOR.finditer(text):
        window = _window(text, operator.start())
        if window is None:
            continue
        start, end = window
        candidate = text[start:end]
        if _PROSE_WORD.search(candidate) or math_density(candidate) < EQUATION_MATH_RATIO:
            continue
        if marks and start < marks[-1].end:
            previous = marks[-1]
            marks[-1] = generated.InlineMark(
                type="INLINE_EQUATION",
                start=previous.start,
                end=max(previous.end, end),
            )
            continue
        marks.append(generated.InlineMark(type="INLINE_EQUATION", start=start, end=end))
    return marks


def _window(text: str, anchor: int) -> tuple[int, int] | None:
    """(start, end) of the math-token window around ``text[anchor]``.

    PDFium renders inline math with wide spacing (``f (x ) =  x2``), so
    tokens may hold only a fragment; the operand check runs on the
    whitespace-collapsed window instead of raw adjacency.
    """
    start = anchor
    end = anchor + 1
    expanded = True
    while expanded:
        expanded = False
        left = _token_before(text, start)
        if (
            left is not None
            and _math_token(text[left:start])
            and end - left <= _INLINE_WINDOW_MAX_CHARS
        ):
            start = left
            expanded = True
        right = _token_after(text, end)
        if (
            right is not None
            and _math_token(text[end:right])
            and right - start <= _INLINE_WINDOW_MAX_CHARS
        ):
            end = right
            expanded = True
    window = text[start:end].strip()
    if len(window) < 3 or len(window) > _INLINE_WINDOW_MAX_CHARS:
        return None
    # A bare ``_`` only counts as a subscript when a digit follows (``x_1``):
    # PDFium splits flattened identifiers like ``MULTI_COLUMN`` into ``COL``.
    joined = re.sub(r"\s+", " ", window)
    if not re.search(r"[\w)\]}]\s*[=^]\s*\w|[=^]\s*[\w(\[{]|\w\^|_\s*\d", joined):
        return None
    offset = text.index(window, max(start - 1, 0))
    return offset, offset + len(window)


def _token_before(text: str, position: int) -> int | None:
    """Index where the previous whitespace-separated token starts.

    ``position`` may sit inside whitespace; the token is the nearest
    non-space run to the left, spaces between included.
    """
    probe = position
    while probe > 0 and text[probe - 1].isspace():
        probe -= 1
    if probe == 0 or text[probe - 1].isspace():
        return None
    while probe > 0 and not text[probe - 1].isspace():
        probe -= 1
    return probe


def _token_after(text: str, position: int) -> int | None:
    """Index where the next whitespace-separated token ends."""
    probe = position
    while probe < len(text) and text[probe].isspace():
        probe += 1
    if probe == len(text) or text[probe].isspace():
        return None
    while probe < len(text) and not text[probe].isspace():
        probe += 1
    return probe


def _math_token(token: str) -> bool:
    """Math-shaped token: a variable, number run, group, or operator mix.

    A pure-alphabetic token of two or more letters is prose unless it is
    an ALL-CAPS identifier (``MAX``, ``MSE``): PDFium spaces inline math
    so aggressively that connectives (``and``, ``Let``) otherwise bridge
    two equations into one window.
    """
    stripped = token.strip()
    if not stripped:
        return False
    if _PROSE_WORD.search(stripped):
        return False
    if stripped.isalpha() and len(stripped) > 1 and not stripped.isupper():
        return False
    return bool(re.fullmatch(r"[\w()\[\]{}^_+\-*/\\.,\u2212\u00d7\u03c0]+", stripped))
