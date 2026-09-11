/**
 * Viewer data contract v2 (`viewerDataVersion: 2`) — M6 bidirectional reader.
 *
 * The viewer package is not a canonical schema: it embeds MappingBundle fields
 * plus viewer-only sections (translation, render anchors, per-page sizes).
 * Field shapes are projections of `@paper/document-model` generated types so
 * NodeContent / marks / confidence cannot drift from schemas/. Canonical
 * source of truth stays in schemas/.
 */
import type * as documentModel from "@paper/document-model";
import { type IndexedFragment, PageSpatialIndex } from "./spatial.js";

/** Viewer JSON may serialize absent optionals as `null`. */
type JsonOptional<T> = T | null;

export type Rect = documentModel.generated.Common.Rect;
export type Fragment = {
  pageIndex: documentModel.generated.Mapping.PDFRenderFragment["pageIndex"];
  geometry: Rect;
};
export type SourceFragment = Pick<
  documentModel.generated.Mapping.LayoutRegionRef,
  "fragmentType" | "layoutRegionId"
>;
export type SourceRegion = Fragment & { id: string };

export type InlineMark = Pick<
  documentModel.generated.SemanticDocument.InlineMark,
  "type" | "start" | "end"
> & {
  targetNodeId?: JsonOptional<
    NonNullable<documentModel.generated.SemanticDocument.InlineMark["targetNodeId"]>
  >;
  href?: JsonOptional<NonNullable<documentModel.generated.SemanticDocument.InlineMark["href"]>>;
  label?: JsonOptional<NonNullable<documentModel.generated.SemanticDocument.InlineMark["label"]>>;
};
export type RichTextContent = Pick<documentModel.generated.SemanticDocument.RichText, "text"> & {
  marks: InlineMark[];
};
export type FigureContent = documentModel.generated.SemanticDocument.FigureContent;
export type TableCellView = Omit<documentModel.generated.SemanticDocument.TableCell, "content"> & {
  content: RichTextContent;
};
export type TableContent = Omit<documentModel.generated.SemanticDocument.TableContent, "cells"> & {
  cells: TableCellView[];
};
export type EquationContent = documentModel.generated.SemanticDocument.EquationContent;
export type NodeContent = RichTextContent | FigureContent | TableContent | EquationContent;
export type NodeConfidence = documentModel.generated.SemanticDocument.NodeConfidence;

export type SemanticNodeView = Pick<
  documentModel.generated.SemanticDocument.SemanticNode,
  "id" | "kind" | "provenanceIds"
> & {
  parentId?: JsonOptional<
    NonNullable<documentModel.generated.SemanticDocument.SemanticNode["parentId"]>
  >;
  content: NodeContent;
  confidence: NodeConfidence;
};

export type SemanticRelationView = Pick<
  documentModel.generated.SemanticDocument.SemanticRelation,
  "id" | "type" | "source" | "target"
> & {
  confidence?: JsonOptional<
    NonNullable<documentModel.generated.SemanticDocument.SemanticRelation["confidence"]>
  >;
};

type TranslationEntry = documentModel.generated.TranslationLayer.TranslationEntry;
export type TranslationEntryView = Pick<TranslationEntry, "semanticNodeId"> &
  Partial<Pick<TranslationEntry, "providerModel" | "cacheKey">> & {
    content: NodeContent;
    confidence?: JsonOptional<NonNullable<TranslationEntry["confidence"]>>;
  };

export type TermView = documentModel.generated.TranslationLayer.Term;
export type ProvenanceRecordView = Pick<
  documentModel.generated.Common.ProvenanceRecord,
  "id" | "producer" | "producerVersion" | "operation" | "inputRefs"
>;
export type IssueView = Pick<
  documentModel.generated.Common.Issue,
  "id" | "category" | "severity" | "producer" | "message" | "affectedIds" | "recoverable"
>;

export type MappingBundle = {
  viewerDataVersion: number;
  id?: string;
  schemaVersion?: string;
  physicalLayoutBindings?: { id: string; layoutRegionId: string }[];
  sourceSemanticBindings: { semanticNodeId: string; sourceAnchorIds: string[] }[];
  sourceAnchors: { id: string; fragments: SourceFragment[] }[];
  semanticNodes: SemanticNodeView[];
  semanticRelations: SemanticRelationView[];
  sourceRegions: SourceRegion[];
  renderAnchors: {
    id: string;
    semanticNodeId: string;
    fragments: Fragment[];
    confidence?: number;
  }[];
  translation: {
    targetLocale: string;
    sourceLocale?: string;
    providerModel?: string;
    terminologyRevision?: string;
    terminology?: TermView[];
    entries: TranslationEntryView[];
  };
  provenance: ProvenanceRecordView[];
  issues: IssueView[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireArray(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`invalid mapping bundle: ${label}`);
  return value;
}

function assertMarks(marks: unknown, label: string): void {
  if (!Array.isArray(marks)) throw new Error(`invalid mapping bundle: ${label} marks`);
  for (const mark of marks) {
    if (!isRecord(mark)) throw new Error(`invalid mapping bundle: ${label} mark`);
    if (typeof mark.type !== "string")
      throw new Error(`invalid mapping bundle: ${label} mark type`);
    if (typeof mark.start !== "number" || typeof mark.end !== "number") {
      throw new Error(`invalid mapping bundle: ${label} mark offsets`);
    }
  }
}

function assertNodeContent(content: unknown, label: string): void {
  if (!isRecord(content)) throw new Error(`invalid mapping bundle: ${label} content`);
  if ("marks" in content) assertMarks(content.marks, label);
  if ("cells" in content) {
    if (!Array.isArray(content.cells)) throw new Error(`invalid mapping bundle: ${label} cells`);
    for (const cell of content.cells) {
      if (!isRecord(cell) || !isRecord(cell.content)) {
        throw new Error(`invalid mapping bundle: ${label} cell`);
      }
      assertMarks(cell.content.marks, `${label} cell`);
    }
  }
}

function assertSemanticNode(value: unknown): void {
  if (!isRecord(value)) throw new Error("invalid mapping bundle: semantic node");
  if (typeof value.id !== "string" || typeof value.kind !== "string") {
    throw new Error("invalid mapping bundle: semantic node identity");
  }
  if (!isRecord(value.confidence) || typeof value.confidence.score !== "number") {
    throw new Error("invalid mapping bundle: semantic node confidence");
  }
  assertNodeContent(value.content, `node ${value.id}`);
}

/** Runtime check at the viewer load boundary; types remain a generated projection. */
export function parseMappingBundle(value: unknown): MappingBundle {
  if (!isRecord(value)) throw new Error("invalid mapping bundle");
  if (value.viewerDataVersion !== 2) {
    throw new Error(`unsupported viewer data version: ${String(value.viewerDataVersion)}`);
  }
  requireArray(value.sourceSemanticBindings, "sourceSemanticBindings");
  requireArray(value.sourceAnchors, "sourceAnchors");
  requireArray(value.sourceRegions, "sourceRegions");
  requireArray(value.renderAnchors, "renderAnchors");
  requireArray(value.semanticRelations, "semanticRelations");
  requireArray(value.provenance, "provenance");
  requireArray(value.issues, "issues");
  const nodes = requireArray(value.semanticNodes, "semanticNodes");
  for (const node of nodes) assertSemanticNode(node);
  if (!isRecord(value.translation) || !Array.isArray(value.translation.entries)) {
    throw new Error("invalid mapping bundle: translation");
  }
  for (const entry of value.translation.entries) {
    if (!isRecord(entry) || typeof entry.semanticNodeId !== "string") {
      throw new Error("invalid mapping bundle: translation entry");
    }
    assertNodeContent(entry.content, `translation ${entry.semanticNodeId}`);
  }
  return value as MappingBundle;
}

export type Side = "source" | "target";

/** A node's fragments on BOTH sides; multi-fragment (6.4) is first-class. */
export type Pair = { sources: Fragment[]; targets: Fragment[] };

export function buildPairs(mappings: MappingBundle): Map<string, Pair> {
  if (mappings.viewerDataVersion !== 2) {
    throw new Error(`unsupported viewer data version: ${mappings.viewerDataVersion}`);
  }
  const sourceRegionById = new Map(mappings.sourceRegions.map((region) => [region.id, region]));
  const sourceAnchorById = new Map(mappings.sourceAnchors.map((anchor) => [anchor.id, anchor]));
  const targetsByNodeId = new Map(
    mappings.renderAnchors
      .filter((anchor) => anchor.fragments.length > 0)
      .map((anchor) => [anchor.semanticNodeId, anchor.fragments]),
  );
  const pairs = new Map<string, Pair>();
  for (const binding of mappings.sourceSemanticBindings) {
    const sources: Fragment[] = [];
    for (const anchorId of binding.sourceAnchorIds) {
      const anchor = sourceAnchorById.get(anchorId);
      if (!anchor) continue;
      for (const fragment of anchor.fragments) {
        const region = sourceRegionById.get(fragment.layoutRegionId);
        if (region) sources.push(region);
      }
    }
    const targets = targetsByNodeId.get(binding.semanticNodeId);
    if (sources.length > 0 && targets) {
      pairs.set(binding.semanticNodeId, { sources, targets });
    }
  }
  return pairs;
}

export function fragmentsForSide(pair: Pair, side: Side): Fragment[] {
  return side === "source" ? pair.sources : pair.targets;
}

/**
 * Intra-node landing heuristic when character-level mapping is absent.
 *
 * Node identity comes from source↔target bindings, not from this function.
 * Among counterpart fragments, pick the closest y on the smallest page at or
 * after the origin page; when none exists at/after, take the first counterpart.
 * Cross-document page indexes and y coordinates are a fallback for "where
 * inside this node", not a substitute for FR-SYNC-004 identity. Sync-scroll
 * reuses the same landing rule so both panes stay on corresponding bands.
 */
export function pickCounterpart(pair: Pair, origin: Side, originRect: Fragment): Fragment {
  const counterparts = fragmentsForSide(pair, origin === "source" ? "target" : "source");
  const first = counterparts[0];
  if (!first) throw new Error("pickCounterpart requires a non-empty pair");
  const eligible = counterparts.filter((f) => f.pageIndex >= originRect.pageIndex);
  const pool = eligible.length > 0 ? eligible : counterparts;
  const pageIndex = Math.min(...pool.map((f) => f.pageIndex));
  let best = first;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const fragment of pool) {
    if (fragment.pageIndex !== pageIndex) continue;
    const distance = Math.abs(fragment.geometry.y - originRect.geometry.y);
    if (distance < bestDistance) {
      best = fragment;
      bestDistance = distance;
    }
  }
  return best;
}

export type RelationForNode = { relation: SemanticRelationView; otherNodeId: string };

export type PageSize = { width: number; height: number };

/** Shared lookup model built once per mapping load; consumed by navigation + inspector. */
export type ReaderModel = {
  mappings: MappingBundle;
  pairs: Map<string, Pair>;
  nodeById: Map<string, SemanticNodeView>;
  translationByNodeId: Map<string, TranslationEntryView>;
  relationsByNodeId: Map<string, RelationForNode[]>;
  regionsById: Map<string, SourceRegion>;
  /** Per-side spatial indexes over every paired fragment (6.1/6.2). */
  indexes: Record<Side, PageSpatialIndex>;
};

export function buildReaderModel(
  mappings: MappingBundle,
  pageSizes: Record<Side, PageSize[]>,
): ReaderModel {
  const pairs = buildPairs(mappings);
  const fragmentsFor = (side: Side): IndexedFragment[] => {
    const out: IndexedFragment[] = [];
    for (const [nodeId, pair] of pairs) {
      for (const fragment of fragmentsForSide(pair, side)) {
        out.push({ nodeId, side, pageIndex: fragment.pageIndex, rect: fragment.geometry });
      }
    }
    return out;
  };
  return {
    mappings,
    pairs,
    nodeById: new Map(mappings.semanticNodes.map((node) => [node.id, node])),
    translationByNodeId: new Map(
      mappings.translation.entries.map((entry) => [entry.semanticNodeId, entry]),
    ),
    relationsByNodeId: (() => {
      const byNode = new Map<string, RelationForNode[]>();
      for (const relation of mappings.semanticRelations) {
        for (const [end, other] of [
          [relation.source, relation.target],
          [relation.target, relation.source],
        ] as const) {
          const list = byNode.get(end);
          const item = { relation, otherNodeId: other };
          if (list) list.push(item);
          else byNode.set(end, [item]);
        }
      }
      return byNode;
    })(),
    regionsById: new Map(mappings.sourceRegions.map((region) => [region.id, region])),
    indexes: {
      source: new PageSpatialIndex(fragmentsFor("source"), pageSizes.source),
      target: new PageSpatialIndex(fragmentsFor("target"), pageSizes.target),
    },
  };
}
