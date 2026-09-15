# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Parser configuration and registry override (M8 batch E).

The bundled registry stays the default. An operator may point
``PAPER_CAPABILITY_REGISTRY`` (or ``--registry``) at a TOML file with the
same shape; the override's *bytes* — never its path — enter the
EVIDENCE/LAYOUT cache keys, so switching parser invalidates exactly those
stages. A broken override is refused rather than silently falling back to
the bundled providers.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest
from pdf_pipeline.capabilities import (
    CapabilityRegistryError,
    load_registry,
    registry_fingerprint,
    registry_text,
    resolve_registry,
)
from pdf_pipeline.config import (
    PUBLISH_FAULT_ENV,
    REGISTRY_PATH_ENV,
    load_parser_config,
    load_publish_fault,
)

if TYPE_CHECKING:
    from pathlib import Path


def _registry_file(path: Path, capability: str, **changes: str) -> Path:
    """Write the bundled registry with one capability slot's providers changed."""
    data = tomllib.loads(registry_text())
    domain, slot = capability.split(".")
    data[domain][slot].update(changes)
    lines: list[str] = []
    for domain_name, domain_slots in data.items():
        for slot_name, providers in domain_slots.items():
            lines.append(f"[{domain_name}.{slot_name}]")
            lines.extend(f'{key} = "{value}"' for key, value in providers.items())
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_parser_config_defaults_to_bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REGISTRY_PATH_ENV, raising=False)
    assert load_parser_config().registry_path is None


def test_parser_config_reads_registry_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "registry.toml"
    monkeypatch.setenv(REGISTRY_PATH_ENV, str(override))
    assert load_parser_config().registry_path == override


def test_override_changes_routing_and_fingerprint(tmp_path: Path) -> None:
    override = _registry_file(tmp_path / "registry.toml", "layout.region", primary="mineru")

    assert load_registry()["layout.region"].primary == "mock"
    assert load_registry(override)["layout.region"].primary == "mineru"
    # The digest follows the effective registry, not the bundled one.
    assert registry_fingerprint(override) != registry_fingerprint()


def test_fingerprint_keys_on_content_not_path(tmp_path: Path) -> None:
    text = registry_text()
    first = tmp_path / "a.toml"
    second = tmp_path / "nested" / "b.toml"
    second.parent.mkdir()
    first.write_text(text, encoding="utf-8")
    second.write_text(text, encoding="utf-8")

    assert registry_fingerprint(first) == registry_fingerprint(second)
    # An unmodified copy is indistinguishable from the bundled registry.
    assert registry_fingerprint(first) == registry_fingerprint()


def test_fingerprint_tracks_an_edit_between_calls(tmp_path: Path) -> None:
    override = _registry_file(tmp_path / "registry.toml", "layout.region", primary="mineru")
    before = registry_fingerprint(override)
    _registry_file(override, "layout.region", primary="mock")

    assert registry_fingerprint(override) != before


def test_missing_override_is_refused_not_fallen_back(tmp_path: Path) -> None:
    with pytest.raises(CapabilityRegistryError, match="cannot read capability registry"):
        load_registry(tmp_path / "absent.toml")


def test_unparsable_override_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("[not toml", encoding="utf-8")

    with pytest.raises(CapabilityRegistryError, match=str(broken)):
        load_registry(broken)


def test_override_missing_internal_capability_is_refused(tmp_path: Path) -> None:
    override = tmp_path / "registry.toml"
    text = registry_text()
    start = text.index("[semantic.document]")
    override.write_text(text[:start], encoding="utf-8")

    with pytest.raises(CapabilityRegistryError, match="misses internal capabilities"):
        load_registry(override)


def test_resolve_registry_reads_once(tmp_path: Path) -> None:
    """The routing table and its digest must describe the same file state."""
    override = _registry_file(tmp_path / "registry.toml", "layout.region", primary="mineru")

    registry, digest = resolve_registry(override)
    edited = _registry_file(override, "layout.region", primary="grobid-sim")

    assert registry["layout.region"].primary == "mineru"
    assert digest != registry_fingerprint(edited)
    assert resolve_registry(edited)[1] == registry_fingerprint(edited)


def test_resolve_registry_defaults_to_bundled() -> None:
    registry, digest = resolve_registry()
    assert registry["layout.region"].primary == "mock"
    assert digest == registry_fingerprint()


def test_publish_fault_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PUBLISH_FAULT_ENV, raising=False)
    assert load_publish_fault() is None


def test_publish_fault_empty_string_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PUBLISH_FAULT_ENV, "")
    assert load_publish_fault() is None


def test_publish_fault_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PUBLISH_FAULT_ENV, "target.pdf")
    assert load_publish_fault() == "target.pdf"
