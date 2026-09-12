"""GROBID native dump adapter (scholarly metadata / bibliography).

Accepts recorded TEI XML or a compact JSON dump. Live invocation posts the
source PDF to ``GROBID_URL`` as multipart ``input`` (optional; never the
default CI path).
"""

from __future__ import annotations

import os
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.native import (
    as_list,
    as_mapping,
    load_json_dump,
    load_json_dump_text,
    page_id_at,
    parse_rect,
    resolve_dump_path,
    source_pdf_path,
)
from pdf_pipeline.evidence.providers import CandidateSink

GROBID_PROVIDER = "grobid"
GROBID_PROVIDER_VERSION = "0.8-dump"
GROBID_DUMP_ENV = "GROBID_DUMP"
GROBID_URL_ENV = "GROBID_URL"

_METADATA_CONFIDENCE = 0.9
_STRUCTURE_CONFIDENCE = 0.85
_TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
_ROLE_MAP: dict[str, generated.StructureRole] = {
    "title": "TITLE",
    "abstract": "ABSTRACT",
    "section": "SECTION",
    "subsection": "SUBSECTION",
    "acknowledgement": "ACKNOWLEDGEMENT",
    "acknowledgments": "ACKNOWLEDGEMENT",
    "references": "REFERENCES",
    "bibliography": "REFERENCES",
}


class GrobidEvidenceProvider:
    """EvidenceProvider for recorded (or optionally live) GROBID output."""

    name = GROBID_PROVIDER
    version = GROBID_PROVIDER_VERSION

    def __init__(
        self,
        fingerprint: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
        dump_path: Path | None = None,
        tei: str | None = None,
    ) -> None:
        self._explicit_fingerprint = fingerprint
        self._payload = payload
        self._dump_path = dump_path
        self._tei = tei

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        fingerprint = self._explicit_fingerprint or physical.sourceFingerprint or physical.id
        if self._payload is not None:
            return adapt_grobid_json(self._payload, physical, fingerprint)
        if self._tei is not None:
            return adapt_grobid_tei(self._tei, physical, fingerprint)
        path = self._resolved_path(fingerprint)
        if path is not None:
            return self._adapt_path(path, physical, fingerprint)
        live = _collect_live_grobid()
        if live is not None:
            if live.lstrip().startswith("<"):
                return adapt_grobid_tei(live, physical, fingerprint)
            return adapt_grobid_json(load_json_dump_text(live), physical, fingerprint)
        msg = (
            "grobid adapter has no dump: set GROBID_DUMP, PAPER_PARSER_DUMP_DIR, "
            "or GROBID_URL + PAPER_SOURCE_PDF"
        )
        raise FileNotFoundError(msg)

    def _resolved_path(self, fingerprint: str) -> Path | None:
        env_dump = os.environ.get(GROBID_DUMP_ENV)
        return resolve_dump_path(
            self.name, fingerprint, Path(env_dump) if env_dump else self._dump_path
        )

    def _adapt_path(
        self,
        path: Path,
        physical: generated.PhysicalDocument,
        fingerprint: str,
    ) -> generated.EvidenceBundle:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".xml", ".tei"} or path.name.endswith(".tei.xml"):
            return adapt_grobid_tei(text, physical, fingerprint)
        if text.lstrip().startswith("<"):
            return adapt_grobid_tei(text, physical, fingerprint)
        return adapt_grobid_json(load_json_dump(path), physical, fingerprint)


def adapt_grobid_json(
    payload: dict[str, Any],
    physical: generated.PhysicalDocument,
    fingerprint: str,
) -> generated.EvidenceBundle:
    """Map a compact GROBID JSON dump to EvidenceBundle."""
    sink = CandidateSink(fingerprint, GROBID_PROVIDER, GROBID_PROVIDER_VERSION, "grobid:")
    fields: list[generated.MetadataField] = []
    for name in ("title", "author", "abstract"):
        value = payload.get(name)
        if name == "author" and value is None:
            value = payload.get("authors")
        if isinstance(value, str) and value.strip():
            field_name = "author" if name == "author" else name
            fields.append(generated.MetadataField(name=field_name, value=value.strip()))
        elif name == "author":
            joined = ", ".join(str(item) for item in as_list(value) if str(item).strip())
            if joined:
                fields.append(generated.MetadataField(name="author", value=joined))
    if fields:
        sink.add_evidence(
            generated.MetadataCandidate(
                evidenceType="METADATA",
                id=sink.derived_id("metadata"),
                fields=fields,
                confidence=_METADATA_CONFIDENCE,
                provenanceIds=[],
            ),
            operation="grobid-metadata",
        )
    for index, raw_section in enumerate(as_list(payload.get("sections"))):
        section = as_mapping(raw_section)
        if section is None:
            continue
        role = _role_of(str(section.get("role") or "SECTION"))
        raw_page = section.get("page_idx")
        page_index = raw_page if isinstance(raw_page, int) and not isinstance(raw_page, bool) else 0
        preview = str(section.get("text") or "")
        structure: dict[str, object] = {
            "evidenceType": "STRUCTURE",
            "id": sink.derived_id(f"structure-{index}"),
            "role": role,
            "confidence": _STRUCTURE_CONFIDENCE,
            "provenanceIds": [],
        }
        if preview:
            structure["textPreview"] = preview[:200]
        if physical.pages:
            structure["pageId"] = page_id_at(physical, page_index)
        bbox = section.get("bbox")
        if bbox is not None:
            structure["geometry"] = parse_rect(bbox)
        sink.add_evidence(
            generated.StructureCandidate.model_validate(structure),
            operation="grobid-structure",
        )
    candidates, provenance = sink.finish()
    return generated.EvidenceBundle(
        schemaVersion="0.1.0",
        provider=GROBID_PROVIDER,
        providerVersion=GROBID_PROVIDER_VERSION,
        candidates=candidates,
        provenance=provenance,
    )


def adapt_grobid_tei(
    tei: str,
    physical: generated.PhysicalDocument,
    fingerprint: str,
) -> generated.EvidenceBundle:
    """Map GROBID TEI XML to EvidenceBundle."""
    root = ET.fromstring(tei)  # noqa: S314 — recorded TEI dumps, not untrusted XML
    payload: dict[str, Any] = {"sections": []}
    title = _tei_text(root, ".//tei:titleStmt/tei:title") or _tei_text(
        root, ".//tei:docTitle/tei:titlePart"
    )
    if title:
        payload["title"] = title
    authors = [
        " ".join(part.strip() for part in (name.itertext()) if part.strip())
        for name in root.findall(".//tei:sourceDesc//tei:persName", _TEI_NS)
        or root.findall(".//tei:fileDesc//tei:persName", _TEI_NS)
    ]
    if not authors:
        authors = [
            " ".join(part.strip() for part in (name.itertext()) if part.strip())
            for name in root.findall(".//tei:persName", _TEI_NS)
        ]
    if authors:
        payload["author"] = authors
    abstract = _tei_text(root, ".//tei:profileDesc/tei:abstract") or _tei_text(
        root, ".//tei:div[@type='abstract']"
    )
    if abstract:
        payload["abstract"] = abstract
        payload["sections"].append({"role": "ABSTRACT", "text": "Abstract", "page_idx": 0})
    for head in root.findall(".//tei:body//tei:head", _TEI_NS):
        text = "".join(head.itertext()).strip()
        if text:
            payload["sections"].append({"role": "SECTION", "text": text, "page_idx": 0})
    if (
        root.find(".//tei:div[@type='references']", _TEI_NS) is not None
        or root.find(".//tei:listBibl", _TEI_NS) is not None
    ):
        payload["sections"].append({"role": "REFERENCES", "text": "References", "page_idx": 0})
    return adapt_grobid_json(payload, physical, fingerprint)


def _role_of(raw: str) -> generated.StructureRole:
    return _ROLE_MAP.get(raw.strip().lower(), "SECTION" if raw else "UNKNOWN")


def _tei_text(root: ET.Element, xpath: str) -> str | None:
    node = root.find(xpath, _TEI_NS)
    if node is None:
        node = root.find(xpath.replace("tei:", ""))
    if node is None:
        return None
    text = " ".join(part.strip() for part in node.itertext() if part.strip())
    return text or None


def encode_multipart_pdf(*, field_name: str, filename: str, pdf_bytes: bytes) -> tuple[bytes, str]:
    """Encode a PDF as one multipart/form-data file field for GROBID."""
    boundary = f"----PaperPolyglotForm{uuid.uuid4().hex}"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
    ).encode()
    body = header + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def post_process_fulltext_document(base_url: str, pdf_path: Path) -> str:
    """POST ``/api/processFulltextDocument`` with the PDF in the ``input`` field."""
    url = base_url.rstrip("/") + "/api/processFulltextDocument"
    if not url.startswith(("http://", "https://")):
        msg = "GROBID_URL must be an http(s) URL"
        raise ValueError(msg)
    body, content_type = encode_multipart_pdf(
        field_name="input",
        filename=pdf_path.name,
        pdf_bytes=pdf_path.read_bytes(),
    )
    request = Request(url, data=body, method="POST")  # noqa: S310
    request.add_header("Content-Type", content_type)
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 — live optional path
            return response.read().decode("utf-8")
    except URLError as error:
        msg = f"GROBID live request failed: {error}"
        raise RuntimeError(msg) from error


def _collect_live_grobid() -> str | None:
    base = os.environ.get(GROBID_URL_ENV)
    pdf = source_pdf_path()
    if not base or pdf is None:
        return None
    return post_process_fulltext_document(base, pdf)
