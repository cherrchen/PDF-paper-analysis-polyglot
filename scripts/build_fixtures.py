#!/usr/bin/env python3
"""Build deterministic schema fixtures under schemas/fixtures/.

The fixtures encode the Phase 1.4 / 1.6 validation scenarios:

- ``layout-document/two-column-spanning-figure.valid.json``
  two-column page with a full-width figure band and footnote
- ``mapping/three-binding-scenarios.valid.json``
  N-layout->1-semantic (column-spanning paragraph),
  1-layout->N-semantic (block split into heading + paragraph),
  N-layout->N-semantic (cross-page paragraph)
- one minimal valid document per remaining layer

Run ``uv run python scripts/build_fixtures.py`` after changing fixtures;
output is deterministic (fixed ULID-style IDs, sorted key order).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

sys_path = str(Path(__file__).resolve().parent)
import sys

sys.path.insert(0, sys_path)
from repo import ROOT

FIXTURES = ROOT / "schemas" / "fixtures"
V = "0.1.0"

# Deterministic opaque IDs: valid ULID-shaped Crockford base32, 26 chars.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class _Seq:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


_SEQ = _Seq()
_USED_IDS: dict[str, str] = {}


def _crockford_tag(tag: str, width: int) -> str:
    remap = {"I": "1", "L": "1", "O": "0", "U": "V"}
    mapped: list[str] = []
    for ch in tag.upper():
        if ch in remap:
            mapped.append(remap[ch])
        elif ch in _ALPHABET:
            mapped.append(ch)
        else:
            mapped.append("0")
    return "".join(mapped)[:width].ljust(width, "0")


def _fid(tag: str) -> str:
    """26-char Crockford id: 10-char prefix + 4-char tag + 12-char sequence.

    The sequence occupies the trailing characters so uniqueness is never
    truncated away. Colliding tags still produce distinct ids.
    """
    n = _SEQ.next()
    prefix = "01J5M1FXTR"
    tag_part = _crockford_tag(tag, 4)
    digits = ["0"] * 12
    tail = n
    for i in range(11, -1, -1):
        digits[i] = _ALPHABET[tail % 32]
        tail //= 32
    ident = prefix + tag_part + "".join(digits)
    if len(ident) != 26:
        raise RuntimeError(f"fixture id {ident!r} from {tag!r} is not 26 characters")
    previous = _USED_IDS.get(ident)
    if previous is not None:
        raise RuntimeError(f"fixture ID collision {ident} ({tag!r} vs {previous!r})")
    _USED_IDS[ident] = tag
    return ident


DOC = _fid("doc")
PAGE = _fid("pageA")
PAGE2 = _fid("pageB")
SPAN_L1 = _fid("sl1")
SPAN_L2 = _fid("sl2")
SPAN_R1 = _fid("sr1")
SPAN_R2 = _fid("sr2")
SPAN_P2 = _fid("sp2")
SPAN_P1X = _fid("sp1x")
FIG = _fid("fig")
CAPTION = _fid("capt")
FOOT = _fid("foot")
GROUP_FIG = _fid("gfig")
BAND_A = _fid("bandA")
BAND_B = _fid("bandB")
BAND_C = _fid("bandC")
COL_L = _fid("colL")
COL_R = _fid("colR")

SEMDOC = _fid("semdoc")
N_ROOT = _fid("root")
N_HEAD = _fid("head")
N_PARA = _fid("paraA")
N_PARA2 = _fid("paraB")
N_SPLIT = _fid("splt")
N_FIG = _fid("sfig")
N_FIGCAP = _fid("figcap")
N_FOOT = _fid("fn")
N_BIB = _fid("bib")
N_BIBE = _fid("bibe")
N_HEAD2 = _fid("head2")
REL_CAP = _fid("relcap")
REL_FOOT = _fid("relfoot")
REL_CITE = _fid("relcite")

PHYSDOC = _fid("physdoc")
OBJ_TL1 = _fid("objtl1")
OBJ_TL2 = _fid("objtl2")
OBJ_TR1 = _fid("objtr1")
OBJ_TR2 = _fid("objtr2")
OBJ_FIG = _fid("objfig")
OBJ_CAP = _fid("objcap")
OBJ_FOOT = _fid("objfoot")
OBJ_P2A = _fid("objp2a")
OBJ_P2B = _fid("objp2b")

EVIDDOC = _fid("eviddoc")
EV_M1 = _fid("evm1")
EV_M2 = _fid("evm2")
EV_F1 = _fid("evf1")
EV_S1 = _fid("evs1")
PROV_M = _fid("provm")
PROV_F = _fid("provf")
PROV_I = _fid("provi")

MAPDOC = _fid("mapdoc")
PLB_1 = _fid("plb1")
PLB_2 = _fid("plb2")
PLB_3 = _fid("plb3")
PLB_4 = _fid("plb4")
PLB_5 = _fid("plb5")
PLB_6 = _fid("plb6")
PLB_7 = _fid("plb7")
PLB_8 = _fid("plb8")
PLB_9 = _fid("plb9")
ANC_SPAN = _fid("ancA")
ANC_HEAD = _fid("ancB")
ANC_PARA = _fid("ancC")
ANC_PAGE = _fid("ancD")
ANC_PAGE2 = _fid("ancE")
ANC_FIG = _fid("ancF")
SSB_SPAN = _fid("ssb1")
SSB_HEAD = _fid("ssb2")
SSB_PARA = _fid("ssb3")
SSB_PAGE = _fid("ssb4")
SSB_FIG = _fid("ssb5")
SSB_CAP = _fid("ssb6")


def rect(x: float, y: float, w: float, h: float) -> dict[str, Any]:
    return {"kind": "rect", "x": x, "y": y, "width": w, "height": h}


def identity_matrix() -> dict[str, Any]:
    return {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0}


def provenance(record_id: str, producer: str, operation: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "producer": producer,
        "producerVersion": "0.1.0",
        "operation": operation,
        "inputRefs": [PHYSDOC],
    }


def physical_document() -> dict[str, Any]:
    """Two-page physical layer: text spans, figure image, footnote, link."""

    def page(pid: str, index: int) -> dict[str, Any]:
        return {
            "id": pid,
            "index": index,
            "geometry": {
                "widthPt": 612,
                "heightPt": 792,
                "rotation": 0,
                "rawToCanonical": identity_matrix(),
                "canonicalToRaw": identity_matrix(),
            },
            "objectIds": [],
        }

    def span(oid: str, pid: str, x: float, y: float, text: str) -> dict[str, Any]:
        return {
            "objectType": "textSpan",
            "id": oid,
            "pageId": pid,
            "text": text,
            "geometry": rect(x, y, 200, 40),
            "fontSize": 10,
        }

    objects = [
        span(OBJ_TL1, PAGE, 72, 300, "Left column paragraph part one."),
        span(OBJ_TL2, PAGE, 72, 340, "Left column paragraph part two."),
        span(OBJ_TR1, PAGE, 340, 300, "Right column paragraph part one."),
        span(OBJ_TR2, PAGE, 340, 340, "Right column paragraph part two."),
        {
            "objectType": "imageObject",
            "id": OBJ_FIG,
            "pageId": PAGE,
            "geometry": rect(72, 90, 468, 180),
        },
        span(OBJ_CAP, PAGE, 72, 270, "Figure 1: A spanning figure."),
        span(OBJ_FOOT, PAGE, 72, 700, "1. A footnote body."),
        span(OBJ_P2A, PAGE, 72, 650, "Cross-page paragraph first page part."),
        span(OBJ_P2B, PAGE2, 72, 300, "Cross-page paragraph second page part."),
    ]
    doc: dict[str, Any] = {
        "schemaVersion": V,
        "id": PHYSDOC,
        "sourceFingerprint": "sha256:fixture",
        "pages": [page(PAGE, 0), page(PAGE2, 1)],
        "objects": objects,
        "metadata": {"pageCount": 2},
    }
    first_page_objects: list[str] = [str(obj["id"]) for obj in objects if obj.get("pageId") == PAGE]
    second_page_objects: list[str] = [
        str(obj["id"]) for obj in objects if obj.get("pageId") == PAGE2
    ]
    doc["pages"][0]["objectIds"] = first_page_objects
    doc["pages"][1]["objectIds"] = second_page_objects
    return doc


def layout_document() -> dict[str, Any]:
    """Two-column page: bands (title area, 2-col, spanning figure, footnote)."""

    def region(rid: str, geometry: dict[str, Any], kind: str, objects: list[str]) -> dict[str, Any]:
        return {
            "id": rid,
            "pageId": PAGE,
            "geometry": geometry,
            "kind": kind,
            "childIds": [],
            "physicalObjectIds": objects,
            "labels": [
                {
                    "label": "PARAGRAPH_LIKE" if kind == "TEXT" else "FIGURE",
                    "confidence": 0.9,
                    "evidenceIds": [EV_M1],
                }
            ],
            "confidence": {"score": 0.92, "reason": "fixture"},
            "provenanceIds": [PROV_I],
        }

    regions = [
        region(SPAN_L1, rect(72, 300, 230, 80), "TEXT", [OBJ_TL1]),
        region(SPAN_L2, rect(72, 380, 230, 80), "TEXT", [OBJ_TL2]),
        region(SPAN_R1, rect(340, 300, 230, 80), "TEXT", [OBJ_TR1]),
        region(SPAN_R2, rect(340, 380, 230, 80), "TEXT", [OBJ_TR2]),
        region(FIG, rect(72, 90, 468, 180), "FIGURE", [OBJ_FIG]),
        {
            **region(CAPTION, rect(72, 270, 468, 24), "TEXT", [OBJ_CAP]),
            "labels": [{"label": "CAPTION_LIKE", "confidence": 0.88, "evidenceIds": [EV_M2]}],
        },
        {
            **region(FOOT, rect(72, 700, 230, 40), "FOOTNOTE", [OBJ_FOOT]),
            "labels": [{"label": "FOOTNOTE", "confidence": 0.8, "evidenceIds": [EV_M1]}],
        },
        {
            **region(SPAN_P1X, rect(72, 650, 468, 40), "TEXT", [OBJ_P2A]),
            "pageId": PAGE,
        },
        {
            **region(SPAN_P2, rect(72, 300, 230, 120), "TEXT", [OBJ_P2B]),
            "pageId": PAGE2,
        },
    ]
    bands = [
        {
            "id": BAND_A,
            "pageId": PAGE,
            "yStart": 0,
            "yEnd": 80,
            "layoutMode": "FULL_WIDTH",
            "columnIds": [],
        },
        {
            "id": BAND_B,
            "pageId": PAGE,
            "yStart": 80,
            "yEnd": 640,
            "layoutMode": "MULTI_COLUMN",
            "columnIds": [COL_L, COL_R],
        },
        {
            "id": BAND_C,
            "pageId": PAGE,
            "yStart": 640,
            "yEnd": 792,
            "layoutMode": "FULL_WIDTH",
            "columnIds": [],
        },
    ]
    columns = [
        {
            "id": COL_L,
            "pageId": PAGE,
            "bandId": BAND_B,
            "geometry": rect(72, 80, 230, 560),
            "regionIds": [SPAN_L1, SPAN_L2, FOOT],
        },
        {
            "id": COL_R,
            "pageId": PAGE,
            "bandId": BAND_B,
            "geometry": rect(340, 80, 230, 560),
            "regionIds": [SPAN_R1, SPAN_R2],
        },
    ]
    reading_flow = {
        "nodes": [SPAN_L1, SPAN_L2, SPAN_R1, SPAN_R2, FIG, CAPTION, SPAN_P1X, SPAN_P2, FOOT],
        "edges": [
            {"source": SPAN_L1, "target": SPAN_L2, "confidence": 0.98, "reason": "SAME_COLUMN"},
            {"source": SPAN_L2, "target": SPAN_R1, "confidence": 0.95, "reason": "NEXT_COLUMN"},
            {"source": SPAN_R1, "target": SPAN_R2, "confidence": 0.98, "reason": "SAME_COLUMN"},
            {"source": SPAN_R2, "target": SPAN_P1X, "confidence": 0.9, "reason": "NEXT_COLUMN"},
            {"source": SPAN_P1X, "target": SPAN_P2, "confidence": 0.94, "reason": "CONTINUATION"},
            {"source": FIG, "target": CAPTION, "confidence": 0.91, "reason": "CAPTION_ASSOCIATION"},
            {"source": FOOT, "target": FOOT, "confidence": 1.0, "reason": "FOOTNOTE_FLOW"},
        ],
    }
    return {
        "schemaVersion": V,
        "id": DOC,
        "physicalDocumentId": PHYSDOC,
        "pages": [
            {
                "pageId": PAGE,
                "regionIds": [r["id"] for r in regions if r["pageId"] == PAGE],
                "bandIds": [BAND_A, BAND_B, BAND_C],
            },
            {"pageId": PAGE2, "regionIds": [SPAN_P2], "bandIds": []},
        ],
        "regions": regions,
        "bands": bands,
        "columns": columns,
        "groups": [
            {
                "id": GROUP_FIG,
                "kind": "FIGURE_BLOCK",
                "memberIds": [FIG, CAPTION],
                "pageId": PAGE,
            }
        ],
        "readingFlow": reading_flow,
        "primaryFlow": [SPAN_L1, SPAN_L2, SPAN_R1, SPAN_R2, SPAN_P1X, SPAN_P2],
        "provenance": {"records": [provenance(PROV_I, "internal", "fixture-layout-recovery")]},
    }


def semantic_document() -> dict[str, Any]:
    """Section/heading/paragraph/figure+caption/footnote/bibliography."""

    def text_node(
        nid: str, kind: str, parent: str | None, text: str, children: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "id": nid,
            "kind": kind,
            "parentId": parent,
            "children": children or [],
            "content": {"text": text, "marks": []},
            "attributes": {},
            "confidence": {"score": 0.95},
            "provenanceIds": [PROV_I],
        }

    nodes: list[dict[str, Any]] = [
        text_node(
            N_ROOT,
            "DOCUMENT",
            None,
            "",
            [N_HEAD, N_PARA, N_HEAD2, N_SPLIT, N_PARA2, N_FIG, N_FIGCAP, N_FOOT, N_BIB],
        ),
        text_node(N_HEAD, "HEADING", N_ROOT, "1. Introduction"),
        text_node(N_PARA, "PARAGRAPH", N_ROOT, "Spanning paragraph across both columns."),
        text_node(N_HEAD2, "HEADING", N_ROOT, "2. A block split into heading and paragraph"),
        text_node(N_SPLIT, "PARAGRAPH", N_ROOT, "The paragraph that continues the split block."),
        text_node(N_PARA2, "PARAGRAPH", N_ROOT, "Cross-page paragraph."),
        {
            "id": N_FIG,
            "kind": "FIGURE",
            "parentId": N_ROOT,
            "children": [],
            "content": {"resources": {"embeddedImageIds": []}},
            "attributes": {},
            "confidence": {"score": 0.9},
            "provenanceIds": [PROV_I],
        },
        text_node(N_FIGCAP, "FIGURE_CAPTION", N_ROOT, "Figure 1: A spanning figure."),
        text_node(N_FOOT, "FOOTNOTE", N_ROOT, "1. A footnote body."),
        text_node(N_BIB, "BIBLIOGRAPHY", N_ROOT, "", [N_BIBE]),
        text_node(N_BIBE, "BIBLIOGRAPHY_ENTRY", N_BIB, "Author, Title, 2026."),
    ]
    paragraph = next(node for node in nodes if node["id"] == N_PARA)
    content = paragraph["content"]
    if not isinstance(content, dict):
        raise TypeError("paragraph content must be an object")
    content["marks"] = [
        {"type": "CITATION", "start": 30, "end": 34, "targetNodeId": N_BIBE, "label": "[1]"}
    ]
    relations = [
        {
            "id": REL_CAP,
            "type": "CAPTION_OF",
            "source": N_FIGCAP,
            "target": N_FIG,
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
        {
            "id": REL_FOOT,
            "type": "FOOTNOTE_OF",
            "source": N_FOOT,
            "target": N_PARA,
            "confidence": 0.95,
            "provenanceIds": [PROV_I],
        },
        {
            "id": REL_CITE,
            "type": "CITES",
            "source": N_PARA,
            "target": N_BIBE,
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
    ]
    return {
        "schemaVersion": V,
        "id": SEMDOC,
        "rootId": N_ROOT,
        "nodes": nodes,
        "relations": relations,
        "provenanceIds": [PROV_I],
        "provenance": {"records": [provenance(PROV_I, "internal", "fixture-semantic-recovery")]},
    }


def evidence_bundle() -> dict[str, Any]:
    """Mock provider evidence: region + formula + metadata candidates."""
    return {
        "schemaVersion": V,
        "provider": "mock",
        "providerVersion": "0.1.0",
        "candidates": [
            {
                "evidenceType": "REGION",
                "id": EV_M1,
                "pageId": PAGE,
                "geometry": rect(72, 300, 230, 80),
                "normalizedLabel": "PARAGRAPH_LIKE",
                "providerLabel": "text_block",
                "textPreview": "Left column paragraph part one.",
                "confidence": 0.9,
                "provenanceIds": [PROV_M],
            },
            {
                "evidenceType": "REGION",
                "id": EV_M2,
                "pageId": PAGE,
                "geometry": rect(72, 90, 468, 180),
                "normalizedLabel": "FIGURE",
                "providerLabel": "image",
                "confidence": 0.85,
                "provenanceIds": [PROV_M],
            },
            {
                "evidenceType": "FORMULA",
                "id": EV_F1,
                "pageId": PAGE,
                "geometry": rect(72, 500, 230, 30),
                "rawText": "E = m c^2",
                "confidence": 0.7,
                "provenanceIds": [PROV_F],
            },
            {
                "evidenceType": "STRUCTURE",
                "id": EV_S1,
                "role": "SECTION",
                "textPreview": "1. Introduction",
                "pageId": PAGE,
                "confidence": 0.8,
                "provenanceIds": [PROV_M],
            },
        ],
        "provenance": {
            "records": [
                provenance(PROV_M, "mock-mineru", "fixture-region-detection"),
                provenance(PROV_F, "mock-docling", "fixture-formula-recognition"),
            ]
        },
    }


def mapping_bundle() -> dict[str, Any]:
    """All three many-to-many scenarios from Phase 1.6, plus cross-page N→1.

    1. N Layout -> 1 Semantic: left+right column regions -> N_PARA.
    2. 1 Layout -> N Semantic: one region anchors both N_HEAD2 and N_SPLIT.
    3. N Layout -> N Semantic: figure + caption regions share one anchor that
       binds both N_FIG and N_FIGCAP.
    4. Cross-page N Layout -> 1 Semantic: page-1 + page-2 regions -> N_PARA2.
    """
    physical_layout = [
        {"id": PLB_1, "layoutRegionId": SPAN_L1, "physicalObjectIds": [OBJ_TL1]},
        {"id": PLB_2, "layoutRegionId": SPAN_R1, "physicalObjectIds": [OBJ_TR1]},
        {"id": PLB_3, "layoutRegionId": SPAN_L2, "physicalObjectIds": [OBJ_TL2]},
        {"id": PLB_4, "layoutRegionId": SPAN_R2, "physicalObjectIds": [OBJ_TR2]},
        {"id": PLB_5, "layoutRegionId": SPAN_P1X, "physicalObjectIds": [OBJ_P2A]},
        {"id": PLB_6, "layoutRegionId": SPAN_P2, "physicalObjectIds": [OBJ_P2B]},
        {"id": PLB_7, "layoutRegionId": FOOT, "physicalObjectIds": [OBJ_FOOT]},
        {"id": PLB_8, "layoutRegionId": FIG, "physicalObjectIds": [OBJ_FIG]},
        {"id": PLB_9, "layoutRegionId": CAPTION, "physicalObjectIds": [OBJ_CAP]},
    ]
    source_anchors = [
        {
            "id": ANC_SPAN,
            "fragments": [
                {"fragmentType": "layoutRegion", "layoutRegionId": SPAN_L1},
                {"fragmentType": "layoutRegion", "layoutRegionId": SPAN_R1},
            ],
            "confidence": 0.93,
            "provenanceIds": [PROV_I],
        },
        {
            "id": ANC_HEAD,
            "fragments": [{"fragmentType": "layoutRegion", "layoutRegionId": SPAN_L2}],
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
        {
            "id": ANC_PARA,
            "fragments": [{"fragmentType": "layoutRegion", "layoutRegionId": SPAN_L2}],
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
        {
            "id": ANC_PAGE,
            "fragments": [{"fragmentType": "layoutRegion", "layoutRegionId": SPAN_P1X}],
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
        {
            "id": ANC_PAGE2,
            "fragments": [{"fragmentType": "layoutRegion", "layoutRegionId": SPAN_P2}],
            "confidence": 0.9,
            "provenanceIds": [PROV_I],
        },
        {
            "id": ANC_FIG,
            "fragments": [
                {"fragmentType": "layoutRegion", "layoutRegionId": FIG},
                {"fragmentType": "layoutRegion", "layoutRegionId": CAPTION},
            ],
            "confidence": 0.92,
            "provenanceIds": [PROV_I],
        },
    ]
    source_semantic = [
        {"id": SSB_SPAN, "semanticNodeId": N_PARA, "sourceAnchorIds": [ANC_SPAN]},
        {"id": SSB_HEAD, "semanticNodeId": N_HEAD2, "sourceAnchorIds": [ANC_HEAD]},
        {"id": SSB_PARA, "semanticNodeId": N_SPLIT, "sourceAnchorIds": [ANC_PARA]},
        {"id": SSB_PAGE, "semanticNodeId": N_PARA2, "sourceAnchorIds": [ANC_PAGE, ANC_PAGE2]},
        {"id": SSB_FIG, "semanticNodeId": N_FIG, "sourceAnchorIds": [ANC_FIG]},
        {"id": SSB_CAP, "semanticNodeId": N_FIGCAP, "sourceAnchorIds": [ANC_FIG]},
    ]
    return {
        "schemaVersion": V,
        "id": MAPDOC,
        "physicalLayoutBindings": physical_layout,
        "sourceAnchors": source_anchors,
        "sourceSemanticBindings": source_semantic,
        "provenance": {"records": [provenance(PROV_I, "internal", "fixture-source-mapping")]},
    }


def write(name: str, schema_dir: str, filename: str, data: dict[str, Any]) -> None:
    out = FIXTURES / schema_dir / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> int:
    write("physical", "physical-document", "two-page-two-column.valid.json", physical_document())
    write("layout", "layout-document", "two-column-spanning-figure.valid.json", layout_document())
    write("semantic", "semantic-document", "paper-structure.valid.json", semantic_document())
    write("evidence", "evidence", "mock-providers.valid.json", evidence_bundle())
    write("mapping", "mapping", "three-binding-scenarios.valid.json", mapping_bundle())
    subprocess.run(
        ["pnpm", "exec", "biome", "check", "--write", str(FIXTURES)],
        check=True,
        cwd=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
