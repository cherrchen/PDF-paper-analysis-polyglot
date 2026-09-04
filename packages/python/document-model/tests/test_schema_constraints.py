"""Python bindings must reject the same invalid documents as JSON Schema."""

from __future__ import annotations

from typing import Any

import document_model.generated.schema_models as m
import pytest
from document_model import new_id
from pydantic import ValidationError


@pytest.mark.unit
def test_rejects_illegal_id(physical_data: dict[str, Any]) -> None:
    polluted = dict(physical_data)
    polluted["id"] = "not-a-valid-id"
    with pytest.raises(ValidationError):
        m.PhysicalDocument.model_validate(polluted)


@pytest.mark.unit
def test_rejects_explicit_null_for_optional_title(physical_data: dict[str, Any]) -> None:
    polluted = dict(physical_data)
    polluted["metadata"] = {**physical_data["metadata"], "title": None}
    with pytest.raises(ValidationError):
        m.PhysicalDocument.model_validate(polluted)


@pytest.mark.unit
def test_accepts_omitted_optional_title(physical_data: dict[str, Any]) -> None:
    data = dict(physical_data)
    metadata = dict(physical_data["metadata"])
    metadata.pop("title", None)
    data["metadata"] = metadata
    m.PhysicalDocument.model_validate(data)


@pytest.mark.unit
@pytest.mark.parametrize(("value", "field"), [("2", "pageCount"), (True, "pageCount")])
def test_rejects_coercion_for_json_integer(
    physical_data: dict[str, Any], value: object, field: str
) -> None:
    polluted = dict(physical_data)
    polluted["metadata"] = {**physical_data["metadata"], field: value}
    with pytest.raises(ValidationError):
        m.PhysicalDocument.model_validate(polluted)


@pytest.mark.unit
def test_accepts_integral_json_number_for_integer(physical_data: dict[str, Any]) -> None:
    data = dict(physical_data)
    data["metadata"] = {**physical_data["metadata"], "pageCount": 2.0}
    document = m.PhysicalDocument.model_validate(data)
    assert document.metadata.pageCount == 2


@pytest.mark.unit
def test_rejects_string_for_json_number() -> None:
    with pytest.raises(ValidationError):
        m.Point.model_validate({"x": "1.25", "y": 0})


@pytest.mark.unit
def test_numeric_enum_distinguishes_boolean_from_zero() -> None:
    with pytest.raises(ValidationError):
        m.PageGeometry.model_validate(
            {
                "widthPt": 1,
                "heightPt": 1,
                "rotation": False,
                "rawToCanonical": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
                "canonicalToRaw": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
            }
        )


@pytest.mark.unit
def test_rejects_five_point_quad() -> None:
    points = [
        {"x": 0, "y": 0},
        {"x": 1, "y": 0},
        {"x": 1, "y": 1},
        {"x": 0, "y": 1},
        {"x": 0.5, "y": 0.5},
    ]
    with pytest.raises(ValidationError):
        m.Quad.model_validate({"kind": "quad", "points": points})


@pytest.mark.unit
def test_rejects_negative_byte_length() -> None:
    with pytest.raises(ValidationError):
        m.ResourceRecord.model_validate(
            {
                "id": new_id(),
                "kind": "SVG",
                "mediaType": "image/svg+xml",
                "origin": "EXTRACTED",
                "byteLength": -1,
            }
        )


@pytest.mark.unit
def test_accepts_omitted_byte_length() -> None:
    record = m.ResourceRecord.model_validate(
        {"id": new_id(), "kind": "SVG", "mediaType": "image/svg+xml", "origin": "EXTRACTED"}
    )
    assert record.byteLength is None


@pytest.mark.unit
def test_rich_text_alias_matches_architecture_name() -> None:
    assert m.TextNodeContent is m.RichText


@pytest.mark.unit
def test_equation_content_requires_a_representation() -> None:
    with pytest.raises(ValidationError, match="required-property group"):
        m.EquationContent.model_validate({})


@pytest.mark.unit
def test_formula_candidate_requires_a_representation() -> None:
    with pytest.raises(ValidationError, match="required-property group"):
        m.FormulaCandidate.model_validate(
            {
                "evidenceType": "FORMULA",
                "id": new_id(),
                "pageId": new_id(),
                "geometry": {"kind": "rect", "x": 0, "y": 0, "width": 1, "height": 1},
                "confidence": 0.5,
                "provenanceIds": [],
            }
        )
