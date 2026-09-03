from __future__ import annotations

import pytest
from document_model import SCHEMA_STATUS, __version__


@pytest.mark.unit
def test_schema_status_is_unresolved() -> None:
    assert SCHEMA_STATUS == "unresolved"
    assert __version__ == "0.0.0"
