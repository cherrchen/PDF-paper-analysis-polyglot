#!/usr/bin/env python3
"""Validate canonical JSON Schema documents and fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema.validators import Draft202012Validator, validator_for
from referencing import Registry, Resource

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo import ROOT

SCHEMA_ROOT = ROOT / "schemas"
DOCUMENT_SCHEMAS = (
    "common",
    "physical-document",
    "evidence",
    "layout-document",
    "semantic-document",
    "translation-layer",
    "render-document",
    "resources",
    "mapping",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_registry() -> Registry:
    """Resolve canonical $id URIs and relative refs against schemas/."""

    def retrieve(uri: str) -> Resource:
        tail = uri.split("/schemas/", 1)[-1]
        path = SCHEMA_ROOT / tail
        if not path.is_file():
            raise FileNotFoundError(f"unresolvable schema reference: {uri}")
        return Resource.from_contents(_load_json(path))

    return Registry(retrieve=retrieve)


def _fixture_cases() -> list[tuple[Path, Path]]:
    """Every schemas/fixtures/<name>/*.valid.json validates against schemas/<name>/schema.json."""
    cases: list[tuple[Path, Path]] = []
    fixtures_root = SCHEMA_ROOT / "fixtures"
    for schema_name in DOCUMENT_SCHEMAS:
        schema_file = SCHEMA_ROOT / schema_name / "schema.json"
        if not schema_file.is_file():
            continue
        fixture_dir = fixtures_root / schema_name
        if not fixture_dir.is_dir():
            continue
        for fixture in sorted(fixture_dir.glob("*.valid.json")):
            cases.append((schema_file, fixture))
    return cases


def main() -> int:
    errors: list[str] = []
    registry = _build_registry()

    schemas = list(SCHEMA_ROOT.glob("**/schema.json"))
    if not schemas:
        print("no JSON Schema documents currently defined")
    for schema_path in sorted(schemas):
        try:
            document = _load_json(schema_path)
            validator_cls = validator_for(document)
            validator_cls.check_schema(document)
            print(f"ok  schema {schema_path.relative_to(ROOT)}")
        except Exception as exc:
            errors.append(f"{schema_path}: {exc}")

    for schema_file, fixture in _fixture_cases():
        try:
            schema = _load_json(schema_file)
            validator = Draft202012Validator(schema, registry=registry)
            validator.validate(_load_json(fixture))
            print(f"ok  fixture {fixture.relative_to(ROOT)}")
        except Exception as exc:
            errors.append(f"{fixture}: {exc}")

    openapi = list((SCHEMA_ROOT / "api").glob("*.yaml")) + list((SCHEMA_ROOT / "api").glob("*.yml"))
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
