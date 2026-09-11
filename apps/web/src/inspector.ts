/**
 * M6 (6.5/6.6) Semantic Inspector: per-node provenance, text, translation,
 * relations, confidence, terminology, and citations for the selected region.
 * Pure DOM rendering; navigation callbacks are injected by DualPaneReader.
 */
import type {
  NodeContent,
  Pair,
  ReaderModel,
  RichTextContent,
  SemanticNodeView,
} from "./mapping.js";
import { codePointSliceOrOutOfRange } from "./unicode.js";

export type InspectorOptions = {
  apiAvailable: boolean;
  /** True while a reader-level retranslate is in flight (any node). */
  retranslateBusy?: boolean;
  /** Jump navigation to another semantic node (relation / citation targets). */
  onSelect: (nodeId: string) => void;
  /** Re-translate the current node via the reader API; disables button while running. */
  onRetranslate?: (nodeId: string) => Promise<void>;
};

const CITATION_MARK_TYPES = new Set([
  "CITATION",
  "FIGURE_REFERENCE",
  "TABLE_REFERENCE",
  "EQUATION_REFERENCE",
  "SECTION_REFERENCE",
  "FOOTNOTE_REFERENCE",
]);

function richTextOf(content: NodeContent): RichTextContent | null {
  if ("text" in content && typeof content.text === "string" && Array.isArray(content.marks)) {
    return content;
  }
  return null;
}

/** Human-readable projection of any canonical NodeContent (one branch per oneOf). */
export function nodePlainText(content: NodeContent): string {
  const rich = richTextOf(content);
  if (rich) return rich.text;
  if ("cells" in content && Array.isArray(content.cells)) {
    const shown = content.cells.slice(0, 20).map((cell) => cell.content.text);
    return shown.join(" | ") + (content.cells.length > 20 ? "…" : "");
  }
  if ("label" in content) return `Figure ${content.label ?? ""}`;
  if (
    "latex" in content ||
    "mathml" in content ||
    "unicodeText" in content ||
    "rawText" in content
  ) {
    return content.latex ?? content.mathml ?? content.unicodeText ?? content.rawText ?? "[preview]";
  }
  return "[preview]";
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
}

function section(id: string, title: string): HTMLElement {
  const wrapper = el("section");
  wrapper.id = id;
  wrapper.className = "inspector-section";
  wrapper.append(el("h3", title));
  return wrapper;
}

function anchorLine(
  side: "source" | "target",
  pageIndex: number,
  rect: { x: number; y: number; width: number; height: number },
): string {
  return `${side} p${pageIndex + 1} [${Math.round(rect.x)},${Math.round(rect.y)} ${Math.round(rect.width)}×${Math.round(rect.height)}]`;
}

export function citationMarksFor(model: ReaderModel, node: SemanticNodeView) {
  const out: { text: string; label: string; targetNodeId: string | null }[] = [];
  const texts: RichTextContent[] = [];
  const sourceRich = richTextOf(node.content);
  if (sourceRich) texts.push(sourceRich);
  const entry = model.translationByNodeId.get(node.id);
  const targetRich = entry ? richTextOf(entry.content) : null;
  if (targetRich) texts.push(targetRich);
  for (const content of texts) {
    for (const mark of content.marks) {
      if (!CITATION_MARK_TYPES.has(mark.type)) continue;
      const slice = codePointSliceOrOutOfRange(content.text, mark.start, mark.end);
      out.push({
        text: slice,
        label: `${mark.type}${mark.label ? ` ${mark.label}` : ""}`,
        targetNodeId: mark.targetNodeId ?? null,
      });
    }
  }
  return out;
}

function issuesFor(model: ReaderModel, node: SemanticNodeView): string[] {
  const anchorIds = new Set<string>();
  for (const binding of model.mappings.sourceSemanticBindings) {
    if (binding.semanticNodeId === node.id) {
      for (const id of binding.sourceAnchorIds) anchorIds.add(id);
    }
  }
  for (const anchor of model.mappings.renderAnchors) {
    if (anchor.semanticNodeId === node.id) anchorIds.add(anchor.id);
  }
  return model.mappings.issues
    .filter(
      (issue) =>
        issue.affectedIds.includes(node.id) || issue.affectedIds.some((id) => anchorIds.has(id)),
    )
    .map((issue) => `[${issue.severity}] ${issue.category} ${issue.message}`);
}

function provenanceFor(model: ReaderModel, node: SemanticNodeView): string[] {
  const records = new Map(model.mappings.provenance.map((record) => [record.id, record]));
  return node.provenanceIds
    .map((id) => records.get(id))
    .filter((record): record is (typeof model.mappings.provenance)[number] => record !== undefined)
    .map((record) => `${record.producer}@${record.producerVersion} ${record.operation}`);
}

export function renderInspector(
  root: HTMLElement,
  model: ReaderModel,
  nodeId: string | null,
  opts: InspectorOptions,
): void {
  const node = nodeId ? model.nodeById.get(nodeId) : undefined;
  if (!nodeId || !node || !model.pairs.has(nodeId)) {
    root.hidden = true;
    return;
  }
  root.hidden = false;
  root.replaceChildren();
  const pair = model.pairs.get(nodeId) as Pair;

  const identity = section("inspector-identity", "Semantic node");
  const idLine = el("code", node.id);
  idLine.id = "inspector-node-id";
  const kindLine = el("p");
  kindLine.id = "inspector-kind";
  kindLine.append(el("strong", node.kind));
  identity.append(idLine, kindLine);
  root.append(identity);

  const anchors = section("inspector-anchor-section", "Anchors");
  const anchorList = el("ul");
  anchorList.id = "inspector-anchors";
  for (const fragment of pair.sources) {
    anchorList.append(el("li", anchorLine("source", fragment.pageIndex, fragment.geometry)));
  }
  for (const fragment of pair.targets) {
    anchorList.append(el("li", anchorLine("target", fragment.pageIndex, fragment.geometry)));
  }
  anchors.append(anchorList);
  root.append(anchors);

  const sourceText = nodePlainText(node.content);
  const sourceSection = section("inspector-source-section", "Original");
  const sourceBody = el("p", sourceText);
  sourceBody.id = "inspector-source-text";
  sourceSection.append(sourceBody);
  root.append(sourceSection);

  const entry = model.translationByNodeId.get(nodeId);
  const translationSection = section("inspector-translation-section", "Translation");
  const translationBody = el("p", entry ? nodePlainText(entry.content) : "Not translatable");
  translationBody.id = "inspector-translation";
  translationSection.append(translationBody);
  if (entry && opts.apiAvailable) {
    const button = el("button", opts.retranslateBusy ? "Re-translating…" : "Re-translate node");
    button.id = "retranslate-button";
    button.type = "button";
    button.disabled = Boolean(opts.retranslateBusy);
    button.addEventListener("click", () => {
      if (!opts.onRetranslate || opts.retranslateBusy) return;
      button.disabled = true;
      void opts.onRetranslate(nodeId);
    });
    translationSection.append(button);
  }
  root.append(translationSection);

  const relations = section("inspector-relation-section", "Relations");
  const relationList = el("div");
  relationList.id = "inspector-relations";
  for (const { relation, otherNodeId } of model.relationsByNodeId.get(nodeId) ?? []) {
    const other = model.nodeById.get(otherNodeId);
    const button = el(
      "button",
      `${relation.type} ${other?.kind ?? "?"} ${otherNodeId.slice(0, 8)}`,
    );
    button.type = "button";
    button.dataset.nodeId = otherNodeId;
    button.addEventListener("click", () => opts.onSelect(otherNodeId));
    relationList.append(button);
  }
  if (!model.relationsByNodeId.has(nodeId)) relationList.append(el("p", "No relations"));
  relations.append(relationList);
  root.append(relations);

  const confidence = section("inspector-confidence-section", "Confidence");
  const confidenceBody = el("p");
  confidenceBody.id = "inspector-confidence";
  const parts = [`${Math.round(node.confidence.score * 100)}%`];
  if (node.confidence.reason) parts.push(node.confidence.reason);
  const renderAnchor = model.mappings.renderAnchors.find((a) => a.semanticNodeId === nodeId);
  if (typeof renderAnchor?.confidence === "number") {
    parts.push(`target anchor ${Math.round(renderAnchor.confidence * 100)}%`);
  }
  confidenceBody.textContent = parts.join(" · ");
  confidence.append(confidenceBody);
  root.append(confidence);

  const provenance = section("inspector-provenance-section", "Provenance");
  const details = el("details");
  details.append(el("summary", `${node.provenanceIds.length} records`));
  const detailsList = el("ul");
  detailsList.id = "inspector-provenance";
  for (const line of provenanceFor(model, node)) detailsList.append(el("li", line));
  details.append(detailsList);
  provenance.append(details);
  root.append(provenance);

  const issueLines = issuesFor(model, node);
  if (issueLines.length > 0) {
    const issues = section("inspector-issue-section", "Issues");
    const list = el("ul");
    list.id = "inspector-issues";
    for (const line of issueLines) list.append(el("li", line));
    issues.append(list);
    root.append(issues);
  }

  const terminology = section("inspector-terminology-section", "Terminology");
  const termList = el("ul");
  termList.id = "inspector-terminology";
  const targetText = entry ? nodePlainText(entry.content) : "";
  const allTerms = model.mappings.translation.terminology ?? [];
  const matched = allTerms.filter(
    (term) => sourceText.includes(term.term) || targetText.includes(term.term),
  );
  const pool = matched.length > 0 ? matched : allTerms;
  if (pool.length === 0) {
    termList.append(el("li", "No terminology recorded"));
  } else {
    for (const term of pool) {
      termList.append(
        el(
          "li",
          `${term.term} → ${term.preferredTranslation} (${term.source}, ${Math.round(term.confidence * 100)}%)`,
        ),
      );
    }
  }
  terminology.append(termList);
  root.append(terminology);

  const citations = section("inspector-citation-section", "Citations");
  const citationList = el("div");
  citationList.id = "inspector-citations";
  const marks = citationMarksFor(model, node);
  if (marks.length === 0) citationList.append(el("p", "No citation marks"));
  for (const mark of marks) {
    if (mark.targetNodeId && model.nodeById.has(mark.targetNodeId)) {
      const targetId = mark.targetNodeId;
      const button = el("button", `${mark.text} — ${mark.label}`);
      button.type = "button";
      button.dataset.nodeId = targetId;
      button.addEventListener("click", () => opts.onSelect(targetId));
      citationList.append(button);
    } else {
      citationList.append(el("p", `${mark.text} — ${mark.label}`));
    }
  }
  citations.append(citationList);
  root.append(citations);
}
