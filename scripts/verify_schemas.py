#!/usr/bin/env python3
"""Validate canonical JSON Schema documents and fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.validators import validator_for

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_schema(path: Path) -> None:
    document = _load_json(path)
    validator_cls = validator_for(document)
    validator_cls.check_schema(document)


def main() -> int:
    errors: list[str] = []
    schema_root = ROOT / "schemas"
    schemas = list(schema_root.glob("**/schema.json"))
    if not schemas:
        print("no JSON Schema documents currently defined")
    for schema_path in schemas:
        try:
            _check_schema(schema_path)
            print(f"ok  schema {schema_path.relative_to(ROOT)}")
        except Exception as exc:
            errors.append(f"{schema_path}: {exc}")

    fixture_dir = schema_root / "fixtures" / "semantic-document"
    schema_file = schema_root / "semantic-document" / "schema.json"
    if schema_file.is_file():
        schema = _load_json(schema_file)
        validator = jsonschema.Draft202012Validator(schema)
        for fixture in sorted(fixture_dir.glob("*.valid.json")):
            try:
                validator.validate(_load_json(fixture))
                print(f"ok  fixture {fixture.relative_to(ROOT)}")
            except Exception as exc:
                errors.append(f"{fixture}: {exc}")

    openapi = list((schema_root / "api").glob("*.yaml")) + list((schema_root / "api").glob("*.yml"))
    if not openapi:
        print("no OpenAPI documents currently defined")

    if errors:
        print("schema checks failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
