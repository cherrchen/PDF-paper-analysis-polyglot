"""Shared SemanticDocument tree walks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated


def walk_semantic_nodes(semantic: generated.SemanticDocument) -> list[generated.SemanticNode]:
    """Return pre-order children of the document tree, excluding the root."""
    by_id = {node.id: node for node in semantic.nodes}
    ordered: list[generated.SemanticNode] = []
    seen: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        node = by_id.get(node_id)
        if node is None:
            return
        for child_id in node.children:
            if child_id in seen:
                continue
            child = by_id.get(child_id)
            if child is None:
                continue
            ordered.append(child)
            walk(child.id)

    walk(semantic.rootId)
    return ordered
