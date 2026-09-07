"""Local-first translation cache (M5 Phase 5.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from pathlib import Path

    from paper_llm.types import TranslationResult


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
                        "cacheKey": item.cache_key,
                        "text": item.text,
                        "marks": [mark.model_dump() for mark in item.marks],
                        "confidence": item.confidence,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
