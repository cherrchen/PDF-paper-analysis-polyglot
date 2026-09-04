"""Python view of the canonical document contracts.

Generated models in :mod:`document_model.generated` mirror
``schemas/*/schema.json`` and must never be edited by hand. This package adds
only conveniences that keep callers consistent with the canonical contracts:
opaque ID generation, serialization helpers, and cross-layer validators.
"""

from __future__ import annotations

from document_model.ids import SCHEMA_VERSION, new_id, stable_uuid
from document_model.serialize import dump_document, load_document
from document_model.validators import (
    validate_bundle_references,
    validate_layer_separation,
)

__all__ = [
    "SCHEMA_VERSION",
    "dump_document",
    "load_document",
    "new_id",
    "stable_uuid",
    "validate_bundle_references",
    "validate_layer_separation",
]
