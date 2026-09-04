"""Phase 2.1 validation against real-world public papers (Tier-4 external).

Downloads three well-known public arXiv papers (cached locally, never
committed) and asserts the Roadmap Phase 2.1 validation axes:

- page count correct (matches the officially published page count)
- text basically complete (title/abstract keywords extracted)
- coordinates correct (all geometry inside canonical page bounds)

Marked ``slow``/``integration``: needs network on first run.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.physical import extract_physical_document

if TYPE_CHECKING:
    from collections.abc import Callable

CACHE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/external/papers"


# arXiv IDs with published page counts for the arXiv version referenced here.
class PaperSpec(TypedDict):
    url: str
    pages: int
    expect_text: list[str]


PAPERS: dict[str, PaperSpec] = {
    "arxiv-1706.03762": {
        "url": "https://arxiv.org/pdf/1706.03762v7",
        "pages": 15,
        "expect_text": ["Attention Is All You Need", "Abstract"],
    },
    "arxiv-1810.04805": {
        "url": "https://arxiv.org/pdf/1810.04805v2",
        "pages": 16,
        "expect_text": ["BERT", "Pre-training of Deep Bidirectional Transformers"],
    },
    "arxiv-2005.14165": {
        "url": "https://arxiv.org/pdf/2005.14165v4",
        "pages": 75,
        "expect_text": ["Language Models are Few-Shot Learners", "GPT-3"],
    },
}


@pytest.fixture(scope="module")
def paper_bytes() -> Callable[[str], bytes]:
    """Return a loader that reads each cached paper, downloading if missing."""

    def _load(name: str) -> bytes:
        path = CACHE_DIR / f"{name}.pdf"
        if not path.exists():
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            url = PAPERS[name]["url"]
            assert url.startswith("https://"), url
            with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
                path.write_bytes(response.read())
        return path.read_bytes()

    return _load


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(PAPERS))
def test_real_paper_pages_text_geometry(paper_bytes: Callable[[str], bytes], name: str) -> None:
    spec = PAPERS[name]
    doc = extract_physical_document(paper_bytes(name))

    # Page count correct.
    assert len(doc.pages) == spec["pages"]

    # Text basically complete.
    text = " ".join(o.text for o in doc.objects if o.objectType == "textSpan")
    for expected in spec["expect_text"]:
        assert expected in text

    # Coordinates correct for the objects that drive reading: text spans sit
    # inside canonical page bounds. Embedded images may legitimately extend
    # beyond the page in real-world PDFs (clipped at render time), so the
    # physical layer records them faithfully without clamping.
    page_by_id = {page.id: page for page in doc.pages}
    for obj in doc.objects:
        if obj.objectType != "textSpan":
            continue
        page = page_by_id[obj.pageId]
        assert isinstance(obj.geometry, generated.Rect)
        rect = obj.geometry
        assert 0 <= rect.x <= page.geometry.widthPt
        assert 0 <= rect.y <= page.geometry.heightPt
