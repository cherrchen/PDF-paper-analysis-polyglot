"""Phase 1.1 validation: identity, provenance, resources, issues."""

from __future__ import annotations

import document_model.generated.schema_models as m
import pytest
from document_model import new_id
from pydantic import ValidationError


@pytest.mark.unit
def test_id_format_is_opaque_and_valid() -> None:
    ids = {new_id() for _ in range(100)}
    assert len(ids) == 100, "IDs must be unique"
    for value in ids:
        assert len(value) == 26
        assert not any(ch in "ILOU" for ch in value)


@pytest.mark.unit
def test_ids_sort_by_creation_order() -> None:
    first = new_id()
    second = new_id()
    assert first < second


@pytest.mark.unit
def test_serialization_roundtrip_provenance_record() -> None:
    record = m.ProvenanceRecord(
        id=new_id(),
        producer="mineru",
        producerVersion="2.5.0",
        operation="layout-region-detection",
        inputRefs=[new_id()],
        parametersHash="sha256:abc",
    )
    data = record.model_dump(exclude_none=True)
    restored = m.ProvenanceRecord.model_validate(data)
    assert restored == record


@pytest.mark.unit
def test_issue_requires_taxonomy_and_recoverability() -> None:
    issue = m.Issue(
        id=new_id(),
        category="LAYOUT_REGION",
        severity="WARNING",
        producer="internal",
        message="ambiguous column boundary",
        affectedIds=[new_id()],
        recoverable=True,
    )
    assert issue.recoverable is True
    with pytest.raises(ValidationError):
        m.Issue(
            id=new_id(),
            category="NOT_A_CATEGORY",  # type: ignore[arg-type]
            severity="WARNING",
            producer="internal",
            message="x",
            affectedIds=[],
            recoverable=False,
        )


@pytest.mark.unit
def test_resource_store_accepts_vector_over_raster_kinds() -> None:
    store = m.ResourceStore(
        resources=[
            m.ResourceRecord(
                id=new_id(), kind="PDF_FRAGMENT", mediaType="application/pdf", origin="EXTRACTED"
            ),
            m.ResourceRecord(
                id=new_id(), kind="RASTER_PREVIEW", mediaType="image/png", origin="EXTRACTED"
            ),
        ]
    )
    assert store.resources[0].kind == "PDF_FRAGMENT"


@pytest.mark.unit
def test_origin_kind_marks_generated_content() -> None:
    with pytest.raises(ValidationError):
        m.ResourceRecord(
            id=new_id(),
            kind="SVG",
            mediaType="image/svg+xml",
            origin="LLM",  # type: ignore[arg-type]
        )
    record = m.ResourceRecord(
        id=new_id(), kind="SVG", mediaType="image/svg+xml", origin="GENERATED"
    )
    assert record.origin == "GENERATED"
