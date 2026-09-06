"""Semantic recovery: LayoutDocument -> SemanticDocument (M4).

The semantic layer owns paper semantics and carries no geometry. Since M4
it consumes everything M3 deferred: CONTINUATION flow edges merge split
paragraphs into one node whose anchor spans every source region,
headings receive numbered levels and nest into SECTION containers behind
a FRONT_MATTER title block, TABLE regions become structured cells,
display and inline math become EQUATION nodes and marks, footnote bodies
link to their in-text markers through FOOTNOTE_OF relations plus
FOOTNOTE_REFERENCE marks, and a reference section yields a BIBLIOGRAPHY
with resolvable CITATION marks.

Recovery never loses content: unrecognized math keeps its raw text,
unresolved citations keep their brackets and report an issue. The
post-recovery audit lives in :mod:`pdf_pipeline.sem_validate`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.sem_bibliography import citation_spans, entry_label
from pdf_pipeline.sem_equations import display_groups, equation_content, inline_equation_marks
from pdf_pipeline.sem_footnotes import body_reference_spans, footnote_marker_label
from pdf_pipeline.sem_paragraphs import (
    clean_text,
    continuation_pairs,
    group_continuation_confidence,
    merged_region_text,
)
from pdf_pipeline.sem_sections import (
    classify_front_matter,
    heading_decision,
    is_bibliography_heading,
)
from pdf_pipeline.sem_tables import table_candidate_for_region, table_content

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from document_model.generated.schema_models import LayoutRegion

    from pdf_pipeline.fusion import RegionLine

SEMANTIC_PRODUCER = "pdf-pipeline.semantic"

CONFIDENCE_HEADING = 0.6
CONFIDENCE_PARAGRAPH = 0.8
CONFIDENCE_MERGED_PARAGRAPH = 0.75
CONFIDENCE_FIGURE = 0.7
CONFIDENCE_CAPTION = 0.7
CONFIDENCE_FOOTNOTE = 0.7
CONFIDENCE_SECTION = 0.65
CONFIDENCE_FRONT_MATTER = 0.65
CONFIDENCE_EQUATION = 0.55
CONFIDENCE_BIBLIOGRAPHY = 0.7
CONFIDENCE_ENTRY = 0.75
CONFIDENCE_RELATION = 0.7

_FIGURE_LABEL = re.compile(r"^(?:Figure|Fig\.?)\s+([\w.\-]+)", re.IGNORECASE)

# Region kinds that are visual blocks; captions bind through layout groups.
_BLOCK_KINDS = frozenset({"FIGURE", "TABLE", "IMAGE"})


def _region_label(region: LayoutRegion) -> str | None:
    for label in region.labels:
        return label.label
    return None


def _caption_bindings(
    layout: generated.LayoutDocument,
    regions_by_id: Mapping[str, LayoutRegion],
) -> dict[str, tuple[str, str]]:
    """Caption region id -> (main region id, group kind), from layout groups."""
    bindings: dict[str, tuple[str, str]] = {}
    for group in layout.groups:
        if group.kind not in {"FIGURE_BLOCK", "TABLE_BLOCK"} or len(group.memberIds) != 2:
            continue
        main, caption = (regions_by_id.get(member) for member in group.memberIds)
        if main is None or caption is None:
            continue
        if main.kind in {"FIGURE", "TABLE"} and caption.kind == "TEXT":
            bindings[caption.id] = (main.id, group.kind)
        elif caption.kind in {"FIGURE", "TABLE"} and main.kind == "TEXT":
            bindings[main.id] = (caption.id, group.kind)
    return bindings


class _Claims:
    """Region -> role assignments plus the derived tables the pass needs."""

    def __init__(self) -> None:
        self.roles: dict[str, str] = {}
        self.headings: dict[str, tuple[int, str | None]] = {}
        self.captions: dict[str, tuple[str, str]] = {}
        self.equation_groups: list[list[str]] = []
        self.entry_groups: list[list[str]] = []
        self.group_starts: dict[str, tuple[str, list[str]]] = {}
        self.skipped: set[str] = set()
        self.entries_by_label: dict[str, str] = {}
        self.footnotes_by_label: dict[str, str] = {}
        self.footnote_pages: dict[str, set[str]] = {}
        self.parents: dict[str, str] = {}
        self.region_nodes: dict[str, str] = {}

    def assign(self, region_id: str, role: str) -> None:
        self.roles[region_id] = role

    def get(self, region_id: str) -> str | None:
        return self.roles.get(region_id)

    def register_groups(self, kind: str, groups: list[list[str]]) -> None:
        for group in groups:
            self.group_starts[group[0]] = (kind, group)
            self.skipped.update(group[1:])


class _Recovery:
    """One M4 recovery pass over a LayoutDocument."""

    def __init__(
        self,
        layout: generated.LayoutDocument,
        region_texts: Mapping[str, str],
        lines: Mapping[str, Sequence[RegionLine]],
        evidence: generated.EvidenceBundle | None,
    ) -> None:
        self._layout = layout
        self._lines = lines
        self._evidence = evidence
        self._texts = {
            region_id: clean_text(text).strip() for region_id, text in region_texts.items()
        }
        self._regions_by_id: dict[str, LayoutRegion] = {
            region.id: region for region in layout.regions
        }
        self._pairs = continuation_pairs(layout)
        self._bibliography_ids: set[str] = set()
        self.nodes: list[generated.SemanticNode] = []
        self.relations: list[generated.SemanticRelation] = []
        self.issues: list[generated.Issue] = []
        self._relation_keys: set[tuple[str, str, str]] = set()

    # ------------------------------------------------------------ plumbing
    def _node_id(self, *parts: object) -> str:
        return stable_uuid(self._layout.id, "node", *parts)

    def make(
        self,
        node_id: str,
        kind: generated.NodeKind,
        parent_id: str | None,
        content: generated.NodeContent,
        *,
        score: float,
        reason: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        node = generated.SemanticNode(
            id=node_id,
            kind=kind,
            parentId=parent_id,
            children=[],
            content=content,
            attributes={"layoutRegionIds": [], **(attributes or {})},
            confidence=generated.NodeConfidence(score=score, reason=reason),
            provenanceIds=[],
        )
        self.nodes.append(node)
        return node.id

    def text_of(self, region_ids: Sequence[str]) -> str:
        return merged_region_text(region_ids, self._texts)

    def relation(
        self,
        kind: generated.RelationType,
        source: str,
        target: str,
        *,
        confidence: float = CONFIDENCE_RELATION,
    ) -> None:
        key = (kind, source, target)
        if key in self._relation_keys:
            return
        self._relation_keys.add(key)
        self.relations.append(
            generated.SemanticRelation(
                id=stable_uuid(self._layout.id, "rel", *key),
                type=kind,
                source=source,
                target=target,
                confidence=confidence,
                provenanceIds=[],
            )
        )

    def issue(
        self,
        category: generated.IssueCategory,
        message: str,
        affected_ids: Sequence[str],
        *,
        severity: generated.IssueSeverity = "WARNING",
    ) -> None:
        self.issues.append(
            generated.Issue(
                id=stable_uuid(self._layout.id, "issue", category, message),
                category=category,
                severity=severity,
                producer=SEMANTIC_PRODUCER,
                message=message,
                affectedIds=list(affected_ids),
                recoverable=True,
            )
        )

    # -------------------------------------------------------------- phases
    def recover(self) -> generated.SemanticDocument:
        layout = self._layout
        flow = [region_id for region_id in layout.primaryFlow if region_id in self._regions_by_id]
        labels = {region_id: _region_label(self._regions_by_id[region_id]) for region_id in flow}
        page_one: set[str] = set(layout.pages[0].regionIds) if layout.pages else set()
        front_roles = classify_front_matter(
            [
                (region_id, self._texts.get(region_id, ""))
                for region_id in flow
                if region_id in page_one
            ],
            labels,
            self._lines,
        )
        root_id = self.make(
            self._node_id("root"),
            "DOCUMENT",
            None,
            generated.RichText(text="", marks=[]),
            score=1.0,
            reason="document root",
        )
        claims = self._claim_flow(flow, labels, front_roles)
        self._build_tree(root_id, flow, front_roles, claims)
        self._link_captions(claims)
        self._append_footnotes(root_id, claims)
        self._apply_marks(claims)
        self._wire_children()
        document_id = stable_uuid(layout.id, "semantic-document")
        document = generated.SemanticDocument(
            schemaVersion="0.1.0",
            id=document_id,
            layoutDocumentId=layout.id,
            rootId=root_id,
            nodes=self.nodes,
            relations=self.relations,
            provenanceIds=[],
        )
        if not self.issues:
            return document
        return document.model_copy(update={"issues": generated.IssueStore(issues=self.issues)})

    # ------------------------------------------------------- flow claiming
    def _claim_flow(
        self,
        flow: Sequence[str],
        labels: Mapping[str, str | None],
        front_roles: Mapping[str, str],
    ) -> _Claims:
        """Assign every flow region exactly one semantic role, in precedence order."""
        claims = _Claims()
        claims.captions = _caption_bindings(self._layout, self._regions_by_id)
        for caption_id, (main_id, _) in claims.captions.items():
            claims.assign(caption_id, "caption")
            claims.assign(main_id, "block")

        for region_id in flow:
            if self._regions_by_id[region_id].kind in _BLOCK_KINDS:
                claims.assign(region_id, "block")

        candidates = [
            region_id
            for region_id in flow
            if region_id not in front_roles and claims.get(region_id) is None
        ]
        groups = display_groups(
            candidates, self._texts, labels, self._lines, continuation=self._pairs
        )
        for group in groups:
            for region_id in group:
                claims.assign(region_id, "equation")
        claims.equation_groups = list(groups)
        claims.register_groups("equation", list(groups))

        for region_id in candidates:
            if claims.get(region_id) is not None:
                continue
            text = self._texts.get(region_id, "")
            decision = heading_decision(text, labels.get(region_id))
            if decision is not None:
                claims.headings[region_id] = decision
                claims.assign(region_id, "heading")

        self._claim_bibliography(flow, claims)

        for region_id in candidates:
            if claims.get(region_id) is None:
                claims.assign(region_id, "paragraph")

        paragraph_runs = [
            [region_id] for region_id in candidates if claims.get(region_id) == "paragraph"
        ]
        merged = _chain_runs(paragraph_runs, self._pairs)
        claims.register_groups("paragraph", merged)
        return claims

    def _claim_bibliography(self, flow: Sequence[str], claims: _Claims) -> None:
        """Group post-``References`` paragraph regions into entry fragment runs."""
        active = False
        fragments: list[list[str]] = []
        for region_id in flow:
            kind = claims.get(region_id)
            if kind == "heading":
                active = is_bibliography_heading(self._texts.get(region_id, ""))
                fragments = [] if active else fragments
                continue
            if not active or (kind is not None and kind != "paragraph"):
                continue
            if kind is None:
                claims.assign(region_id, "paragraph")
            if entry_label(self._texts.get(region_id, "")) is not None or not fragments:
                fragments.append([region_id])
            else:
                fragments[-1].append(region_id)
        claims.entry_groups = [fragment for fragment in fragments if fragment]
        for fragment in claims.entry_groups:
            for region_id in fragment:
                claims.assign(region_id, "entry")
        claims.register_groups("entry", claims.entry_groups)

    # ---------------------------------------------------------- tree build
    def _build_tree(
        self,
        root_id: str,
        flow: Sequence[str],
        front_roles: Mapping[str, str],
        claims: _Claims,
    ) -> None:
        if front_roles:
            self._build_front_matter(root_id, flow, front_roles, claims)
        stack: list[tuple[int, str]] = []
        bibliography_node: str | None = None
        for region_id in flow:
            if region_id in front_roles or region_id in claims.skipped:
                continue
            kind = claims.get(region_id)
            if kind == "heading":
                level, numbering = claims.headings[region_id]
                bibliography_node = self._open_section(stack, root_id, level, numbering, region_id)
                continue
            if kind is None:
                continue
            parent = bibliography_node or (stack[-1][1] if stack else root_id)
            start = claims.group_starts.get(region_id)
            group = start[1] if start is not None and start[0] == kind else [region_id]
            if kind == "equation":
                self._emit_equation(parent, group, claims)
            elif kind == "block":
                self._emit_block(parent, region_id, claims)
            elif kind == "caption":
                self._emit_caption(parent, region_id, claims)
            elif kind == "entry":
                self._emit_entry(parent, group, claims)
            else:
                self._emit_paragraph(parent, group, claims)

    def _build_front_matter(
        self,
        root_id: str,
        flow: Sequence[str],
        front_roles: Mapping[str, str],
        claims: _Claims,
    ) -> None:
        front_id = self._node_id("front-matter")
        self.make(
            front_id,
            "FRONT_MATTER",
            root_id,
            generated.RichText(text="", marks=[]),
            score=CONFIDENCE_FRONT_MATTER,
            reason="page-1 title block",
        )
        claims.parents[front_id] = root_id
        for region_id in flow:
            role = front_roles.get(region_id)
            if role is None or region_id in claims.skipped:
                continue
            node_id = self._node_id(region_id)
            as_heading = role in {"title", "abstract-title"}
            self.make(
                node_id,
                "HEADING" if as_heading else "PARAGRAPH",
                front_id,
                generated.RichText(text=self._texts.get(region_id, ""), marks=[]),
                score=CONFIDENCE_HEADING if as_heading else CONFIDENCE_PARAGRAPH,
                reason=f"front matter {role}",
                attributes={"level": 1, "role": role} if as_heading else {"role": role},
            )
            self._bind_regions(node_id, [region_id])
            claims.parents[node_id] = front_id
            claims.region_nodes[region_id] = node_id

    def _open_section(
        self,
        stack: list[tuple[int, str]],
        root_id: str,
        level: int,
        numbering: str | None,
        region_id: str,
    ) -> str | None:
        """Section the heading opens; returns a bibliography container id if any."""
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else root_id
        section_id = stable_uuid(self._layout.id, "section", region_id)
        heading_text = self._texts.get(region_id, "")
        self.make(
            section_id,
            "SECTION",
            parent,
            generated.RichText(text="", marks=[]),
            score=CONFIDENCE_SECTION,
            reason="section tree",
            attributes={"level": level, "numbering": numbering, "title": heading_text},
        )
        heading_id = self._node_id(region_id)
        self.make(
            heading_id,
            "HEADING",
            section_id,
            generated.RichText(text=heading_text, marks=[]),
            score=CONFIDENCE_HEADING,
            reason="numbered section heading" if numbering else "layout heading label",
            attributes={"level": level, **({"numbering": numbering} if numbering else {})},
        )
        self._bind_regions(heading_id, [region_id])
        stack.append((level, section_id))
        if not is_bibliography_heading(heading_text):
            return None
        bibliography_id = stable_uuid(self._layout.id, "bibliography", region_id)
        self.make(
            bibliography_id,
            "BIBLIOGRAPHY",
            section_id,
            generated.RichText(text="", marks=[]),
            score=CONFIDENCE_BIBLIOGRAPHY,
            reason="reference section",
        )
        self._bibliography_ids.add(bibliography_id)
        return bibliography_id

    def _emit_paragraph(self, parent_id: str, group: Sequence[str], claims: _Claims) -> None:
        text = self.text_of(group)
        if not text:
            return
        if len(group) > 1:
            score = min(
                CONFIDENCE_MERGED_PARAGRAPH, group_continuation_confidence(group, self._pairs)
            )
            reason = f"paragraph merge: {len(group)} regions"
        else:
            score = CONFIDENCE_PARAGRAPH
            reason = "layout text region"
        node_id = self._node_id(group[0])
        self.make(
            node_id,
            "PARAGRAPH",
            parent_id,
            generated.RichText(text=text, marks=[]),
            score=score,
            reason=reason,
        )
        self._bind_regions(node_id, list(group))
        claims.parents[node_id] = parent_id
        claims.region_nodes[group[0]] = node_id

    def _emit_equation(self, parent_id: str, group: Sequence[str], claims: _Claims) -> None:
        node_id = self._node_id(group[0])
        self.make(
            node_id,
            "EQUATION",
            parent_id,
            equation_content(self._texts, group, formula_candidate=self._formula_candidate(group)),
            score=CONFIDENCE_EQUATION,
            reason=f"display equation: {len(group)} regions",
        )
        self._bind_regions(node_id, list(group))
        claims.parents[node_id] = parent_id
        claims.region_nodes[group[0]] = node_id

    def _formula_candidate(self, group: Sequence[str]) -> generated.FormulaCandidate | None:
        if self._evidence is None:
            return None
        evidence_ids = {
            evidence_id
            for region_id in group
            for label in self._regions_by_id[region_id].labels
            for evidence_id in label.evidenceIds
        }
        for candidate in self._evidence.candidates:
            if isinstance(candidate, generated.FormulaCandidate) and candidate.id in evidence_ids:
                return candidate
        return None

    def _emit_block(self, parent_id: str, region_id: str, claims: _Claims) -> None:
        region = self._regions_by_id[region_id]
        node_id = self._node_id(region_id)
        if region.kind == "TABLE":
            content, reason, score = table_content(
                lines=self._lines.get(region_id),
                region_text=self._texts.get(region_id, ""),
                table_candidate=table_candidate_for_region(region, self._evidence),
            )
            if not content.cells:
                self.issue(
                    "TABLE_RECOVERY", f"table region {region_id} recovered no cells", [region_id]
                )
            self.make(node_id, "TABLE", parent_id, content, score=score, reason=reason)
        else:
            label = self._figure_label(region_id, claims)
            self.make(
                node_id,
                "FIGURE",
                parent_id,
                generated.FigureContent(
                    resources=generated.FigureResource(embeddedImageIds=[]),
                    **({"label": label} if label is not None else {}),
                ),
                score=CONFIDENCE_FIGURE,
                reason="layout figure region",
            )
        self._bind_regions(node_id, [region_id])
        claims.parents[node_id] = parent_id
        claims.region_nodes[region_id] = node_id

    def _figure_label(self, region_id: str, claims: _Claims) -> str | None:
        """Figure number taken from the caption bound to this block region."""
        for caption_id, (main_id, _) in claims.captions.items():
            if main_id != region_id:
                continue
            match = _FIGURE_LABEL.match(self._texts.get(caption_id, ""))
            if match:
                return match.group(1).rstrip(".")
        return None

    def _emit_caption(self, parent_id: str, region_id: str, claims: _Claims) -> None:
        _, group_kind = claims.captions[region_id]
        kind: generated.NodeKind = (
            "TABLE_CAPTION" if group_kind == "TABLE_BLOCK" else "FIGURE_CAPTION"
        )
        node_id = self._node_id(region_id)
        self.make(
            node_id,
            kind,
            parent_id,
            generated.RichText(text=self._texts.get(region_id, ""), marks=[]),
            score=CONFIDENCE_CAPTION,
            reason="layout caption group",
        )
        self._bind_regions(node_id, [region_id])
        claims.parents[node_id] = parent_id
        claims.region_nodes[region_id] = node_id

    def _link_captions(self, claims: _Claims) -> None:
        """CAPTION_OF relations after all blocks and captions exist."""
        for caption_id in claims.captions:
            caption_node = claims.region_nodes.get(caption_id)
            main_node = claims.region_nodes.get(claims.captions[caption_id][0])
            if caption_node is not None and main_node is not None:
                self.relation("CAPTION_OF", caption_node, main_node)

    def _emit_entry(self, parent_id: str, group: Sequence[str], claims: _Claims) -> None:
        text = self.text_of(group)
        label = entry_label(text)
        node_id = self._node_id(group[0])
        if label is not None and label in claims.entries_by_label:
            self.issue(
                "CITATION_RESOLUTION",
                f"duplicate bibliography entry label [{label}]",
                [node_id],
            )
        self.make(
            node_id,
            "BIBLIOGRAPHY_ENTRY",
            parent_id,
            generated.RichText(text=text, marks=[]),
            score=CONFIDENCE_ENTRY if label else CONFIDENCE_PARAGRAPH,
            reason="bibliography entry" if label else "bibliography fragment",
            attributes={"label": label} if label is not None else {},
        )
        self._bind_regions(node_id, list(group))
        claims.parents[node_id] = parent_id
        claims.region_nodes[group[0]] = node_id
        if label is not None:
            claims.entries_by_label.setdefault(label, node_id)

    def _bind_regions(self, node_id: str, region_ids: Sequence[str]) -> None:
        for node in self.nodes:
            if node.id == node_id:
                node.attributes["layoutRegionIds"] = list(region_ids)
                return

    # ---------------------------------------------------------- footnotes
    def _append_footnotes(self, root_id: str, claims: _Claims) -> None:
        for region in self._layout.regions:
            if region.kind != "FOOTNOTE":
                continue
            text = self._texts.get(region.id, "")
            node_id = self._node_id(region.id)
            if not text:
                self.issue(
                    "LAYOUT_REGION",
                    f"footnote region {region.id} recovered with empty text",
                    [region.id],
                )
            self.make(
                node_id,
                "FOOTNOTE",
                root_id,
                generated.RichText(text=text, marks=[]),
                score=CONFIDENCE_FOOTNOTE,
                reason="layout footnote region",
            )
            self._bind_regions(node_id, [region.id])
            label = footnote_marker_label(text)
            if label is not None and label not in claims.footnotes_by_label:
                claims.footnotes_by_label[label] = node_id
                claims.footnote_pages[label] = {region.pageId}

    # --------------------------------------------------------------- marks
    def _apply_marks(self, claims: _Claims) -> None:
        """Attach inline-math, citation, and footnote-reference marks."""
        used_footnotes: set[str] = set()
        for index, node in enumerate(self.nodes):
            content = node.content
            if not isinstance(content, generated.RichText) or not content.text:
                continue
            if node.kind != "PARAGRAPH":
                continue
            marks = list(content.marks)
            marks.extend(inline_equation_marks(content.text))
            marks.extend(self._citation_marks(node, content.text, claims))
            marks.extend(self._footnote_marks(node, content.text, claims, used_footnotes))
            if marks:
                ordered = sorted(marks, key=lambda item: (item.start, item.end, item.type))
                self.nodes[index] = node.model_copy(
                    update={"content": content.model_copy(update={"marks": ordered})}
                )

    def _citation_marks(
        self,
        node: generated.SemanticNode,
        text: str,
        claims: _Claims,
    ) -> list[generated.InlineMark]:
        if self._under_bibliography(node, claims):
            return []
        marks: list[generated.InlineMark] = []
        for start, end, numbers in citation_spans(text):
            label = text[start:end]
            for number in numbers:
                target = claims.entries_by_label.get(number)
                if target is None:
                    self.issue(
                        "CITATION_RESOLUTION",
                        f"unresolved citation [{number}] ({label}) in node {node.id}",
                        [node.id],
                    )
                    continue
                marks.append(
                    generated.InlineMark(
                        type="CITATION",
                        start=start,
                        end=end,
                        targetNodeId=target,
                        label=label,
                    )
                )
                self.relation("CITES", node.id, target)
        return marks

    def _under_bibliography(self, node: generated.SemanticNode, claims: _Claims) -> bool:
        parent = node.parentId
        while parent is not None and parent in claims.parents:
            if parent in self._bibliography_ids:
                return True
            parent = claims.parents.get(parent)
        return node.parentId in self._bibliography_ids

    def _footnote_marks(
        self,
        node: generated.SemanticNode,
        text: str,
        claims: _Claims,
        used: set[str],
    ) -> list[generated.InlineMark]:
        if not claims.footnotes_by_label:
            return []
        pages = {
            region.pageId
            for region_id in node.attributes.get("layoutRegionIds", [])
            if (region := self._regions_by_id.get(str(region_id))) is not None
        }
        marks: list[generated.InlineMark] = []
        for start, end, label in body_reference_spans(text, set(claims.footnotes_by_label)):
            if label in used:
                continue
            footnote_pages = claims.footnote_pages[label]
            if pages and footnote_pages and not (pages & footnote_pages):
                continue  # same marker, different page
            used.add(label)
            target = claims.footnotes_by_label[label]
            marks.append(
                generated.InlineMark(
                    type="FOOTNOTE_REFERENCE",
                    start=start,
                    end=end,
                    targetNodeId=target,
                    label=label,
                )
            )
            self.relation("FOOTNOTE_OF", target, node.id)
        return marks

    # ------------------------------------------------------------ finalize
    def _wire_children(self) -> None:
        children: dict[str, list[str]] = {}
        for node in self.nodes:
            if node.parentId:
                children.setdefault(node.parentId, []).append(node.id)
        for index, node in enumerate(self.nodes):
            self.nodes[index] = node.model_copy(update={"children": children.get(node.id, [])})


def _chain_runs(
    runs: list[list[str]],
    pairs: Mapping[tuple[str, str], float],
) -> list[list[str]]:
    """Merge adjacent singleton runs linked by CONTINUATION edges."""
    groups: list[list[str]] = []
    current: list[str] = []
    for run in runs:
        region_id = run[0]
        if current and (current[-1], region_id) in pairs:
            current.append(region_id)
            continue
        if len(current) > 1:
            groups.append(current)
        current = list(run)
    if len(current) > 1:
        groups.append(current)
    return groups


def recover_semantic_document(
    layout: generated.LayoutDocument,
    region_texts: Mapping[str, str],
    *,
    lines: Mapping[str, Sequence[RegionLine]] | None = None,
    evidence: generated.EvidenceBundle | None = None,
) -> generated.SemanticDocument:
    """Build the SemanticDocument from a recovered LayoutDocument.

    Nodes follow reading order inside a SECTION tree; footnote bodies
    close the document. ``lines`` and ``evidence`` enrich recovery and may
    be omitted (heuristics then degrade gracefully).
    """
    return _Recovery(layout, region_texts, lines or {}, evidence).recover()
