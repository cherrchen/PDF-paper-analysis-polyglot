"""Local-first translation cache (M5 Phase 5.4, versioned in M8 batch C)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from pathlib import Path

    from paper_llm.types import TranslationResult

# Version of both the stored row shape and the cache-key derivation rules.
# Bump it whenever the key material in ``paper_llm.translation._cache_key``
# changes meaning: rows written under different rules are ignored, never
# migrated, so a format change can never produce a silent wrong hit.
TRANSLATION_CACHE_VERSION = "1"


@dataclass
class CachedTranslation:
    cache_key: str
    text: str
    marks: list[generated.InlineMark]
    confidence: float


class TranslationCache:
    """JSONL-backed cache keyed by TranslationEntry.cacheKey."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._index: dict[str, CachedTranslation] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("cacheVersion") != TRANSLATION_CACHE_VERSION:
                    continue
                item = CachedTranslation(
                    cache_key=payload["cacheKey"],
                    text=payload["text"],
                    marks=[
                        generated.InlineMark.model_validate(mark)
                        for mark in payload.get("marks", [])
                    ],
                    confidence=float(payload.get("confidence", 1.0)),
                )
                self._index[item.cache_key] = item

    def get(self, cache_key: str) -> CachedTranslation | None:
        return self._index.get(cache_key)

    def put(self, cache_key: str, result: TranslationResult) -> None:
        item = CachedTranslation(
            cache_key=cache_key,
            text=result.text,
            marks=result.marks,
            confidence=result.confidence,
        )
        self._index[cache_key] = item
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "cacheVersion": TRANSLATION_CACHE_VERSION,
                        "cacheKey": item.cache_key,
                        "text": item.text,
                        "marks": [mark.model_dump() for mark in item.marks],
                        "confidence": item.confidence,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
