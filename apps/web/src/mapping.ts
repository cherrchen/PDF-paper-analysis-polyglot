/**
 * Viewer data contract v2 (`viewerDataVersion: 2`) — M6 bidirectional reader.
 *
 * These types are a deliberately narrow, hand-written projection of the
 * viewer package that `pdf_pipeline.pipeline._write_viewer_assets` emits.
 * The package embeds the canonical MappingBundle fields but adds viewer-only
 * sections (translation, render anchors, per-page sizes), so it is NOT the
 * canonical schema; importing @paper/document-model here would pin the
 * viewer to full canonical types it never consumes. The canonical source of
 * truth stays in schemas/.
 */
import { type IndexedFragment, PageSpatialIndex } from "./spatial.js";

export type Rect = { kind: "rect"; x: number; y: number; width: number; height: number };
export type Fragment = { pageIndex: number; geometry: Rect };
export type SourceFragment = { fragmentType: "layoutRegion"; layoutRegionId: string };
export type SourceRegion = Fragment & { id: string };

export type InlineMark = {
  type: string;
  start: number;
  end: number;
  targetNodeId?: string | null;
  label?: string | null;
};
export type RichTextContent = { text: string; marks: InlineMark[] };
export type NodeContent =
  | RichTextContent
  | { label?: string | null; resources?: { embeddedImageIds: string[] } }
  | {
      rows: number;
      columns: number;
      cells: { row: number; column: number; content: RichTextContent }[];
      visualResourceId?: string | null;
    }
  | {
      latex?: string | null;
      mathml?: string | null;
      unicodeText?: string | null;
      rawText?: string | null;
      previewResourceId?: string | null;
    };

export type SemanticNodeView = {
  id: string;
  kind: string;
  parentId?: string;
  content: NodeContent;
  confidence: { score: number; reason?: string | null };
  provenanceIds: string[];
};

export type SemanticRelationView = {
  id: string;
  type: string;
  source: string;
  target: string;
  confidence?: number | null;
};

export type TranslationEntryView = {
  semanticNodeId: string;
  content: NodeContent;
  confidence?: number | null;
  providerModel?: string | null;
  cacheKey?: string | null;
};

export type TermView = {
  term: string;
  preferredTranslation: string;
  source: string;
  confidence: number;
  scope: string;
};

export type ProvenanceRecordView = {
  id: string;
  producer: string;
  producerVersion: string;
  operation: string;
  inputRefs: string[];
};

export type IssueView = {
  id: string;
  category: string;
  severity: string;
  producer: string;
  message: string;
  affectedIds: string[];
  recoverable: boolean;
};

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
