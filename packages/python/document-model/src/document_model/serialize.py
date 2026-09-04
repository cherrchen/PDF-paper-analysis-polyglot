"""Serialization helpers shared by every canonical document layer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from pathlib import Path

_TModel = TypeVar("_TModel", bound=BaseModel)

_ROOT_MODELS: dict[str, type[BaseModel]] = {
    "physical-document": generated.PhysicalDocument,
    "evidence": generated.EvidenceBundle,
    "layout-document": generated.LayoutDocument,
    "semantic-document": generated.SemanticDocument,
    "mapping": generated.MappingBundle,
}


def dump_document(model: BaseModel, *, path: Path | None = None) -> dict[str, Any]:
    """Serialize a canonical model to JSON-compatible data.

    Fields left at their default are dropped, matching the JSON Schema
    semantics where optional properties may be absent. Required nullable
    fields (e.g. SemanticNode.parentId) that were set explicitly are kept,
    including an explicit null.
    """
    data = json.loads(model.model_dump_json(exclude_unset=True))
    if path is not None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def load_document(kind: str, data: dict[str, Any]) -> BaseModel:
    """Parse and validate a canonical document of ``kind``.

    ``kind`` is the schema directory name, e.g. ``"semantic-document"``.
    Raises ``ValueError`` with the validation detail on malformed input.
    """
    model_cls = _ROOT_MODELS.get(kind)
    if model_cls is None:
        raise ValueError(f"unknown document kind: {kind!r}")
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid {kind} document: {exc}") from exc
