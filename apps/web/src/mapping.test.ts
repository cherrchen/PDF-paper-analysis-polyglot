import { describe, expect, it } from "vitest";
import {
  buildPairs,
  buildReaderModel,
  type Fragment,
  fragmentsForSide,
  type MappingBundle,
  pickCounterpart,
} from "./mapping.js";

const rect = (x: number): MappingBundle["sourceRegions"][number]["geometry"] => ({
  kind: "rect",
  x,
  y: 10,
  width: 40,
  height: 12,
});

function crossPageBundle(): MappingBundle {
  return {
    viewerDataVersion: 2,
    schemaVersion: "0.1.0",
    id: "mapping-1",
    physicalLayoutBindings: [],
    sourceSemanticBindings: [
      { semanticNodeId: "para-1", sourceAnchorIds: ["anchor-1"] },
      { semanticNodeId: "heading-1", sourceAnchorIds: ["anchor-h"] },
    ],
    sourceAnchors: [
      {
        id: "anchor-1",
        fragments: [
          { fragmentType: "layoutRegion", layoutRegionId: "region-p0" },
          { fragmentType: "layoutRegion", layoutRegionId: "region-p1" },
        ],
      },
      {
        id: "anchor-h",
        fragments: [{ fragmentType: "layoutRegion", layoutRegionId: "region-h" }],
      },
    ],
    semanticNodes: [
      {
        id: "para-1",
        kind: "PARAGRAPH",
        content: { text: "Body text", marks: [] },
        confidence: { score: 0.9 },
        provenanceIds: [],
      },
      {
        id: "heading-1",
        kind: "HEADING",
        parentId: "para-1",
        content: { text: "A heading", marks: [] },
        confidence: { score: 1 },
        provenanceIds: [],
      },
    ],
    semanticRelations: [{ id: "rel-1", type: "CAPTION_OF", source: "heading-1", target: "para-1" }],
    sourceRegions: [
      { id: "region-p0", pageIndex: 0, geometry: rect(10) },
      { id: "region-p1", pageIndex: 1, geometry: rect(12) },
      { id: "region-h", pageIndex: 0, geometry: rect(8) },
    ],
    renderAnchors: [
      {
        semanticNodeId: "para-1",
        id: "render-1",
        fragments: [
          { pageIndex: 0, geometry: { kind: "rect", x: 20, y: 30, width: 40, height: 12 } },
          { pageIndex: 0, geometry: { kind: "rect", x: 20, y: 220, width: 40, height: 12 } },
        ],
      },
      {
        semanticNodeId: "heading-1",
        id: "render-h",
        fragments: [{ pageIndex: 0, geometry: rect(4) }],
      },
    ],
    translation: {
      targetLocale: "zh-CN",
      entries: [
        { semanticNodeId: "para-1", content: { text: "正文", marks: [] } },
        { semanticNodeId: "heading-1", content: { text: "标题", marks: [] } },
      ],
    },
    provenance: [],
    issues: [],
  };
}

describe("viewer mapping pairs (v2)", () => {
  it("keeps every source fragment of a cross-page paragraph", () => {
    const pairs = buildPairs(crossPageBundle());
    const pair = pairs.get("para-1");
    expect(pair).toBeDefined();
    if (!pair) return;
    expect(pair.sources).toHaveLength(2);
    expect(pair.sources.map((fragment: Fragment) => fragment.pageIndex)).toEqual([0, 1]);
    expect(fragmentsForSide(pair, "source")).toHaveLength(2);
  });

  it("keeps every target fragment of a multi-fragment render anchor (6.4)", () => {
    const pairs = buildPairs(crossPageBundle());
    const pair = pairs.get("para-1");
    expect(pair?.targets).toHaveLength(2);
    expect(fragmentsForSide(pair ?? { sources: [], targets: [] }, "target")).toHaveLength(2);
  });

  it("still pairs single-fragment headings", () => {
    const pairs = buildPairs(crossPageBundle());
    expect(pairs.get("heading-1")?.sources).toHaveLength(1);
  });

  it("rejects non-v2 contracts", () => {
    expect(() => buildPairs({ ...crossPageBundle(), viewerDataVersion: 1 })).toThrow(
      "unsupported viewer data version: 1",
    );
  });
});

describe("pickCounterpart", () => {
  const fragment = (pageIndex: number, y: number): Fragment => ({
    pageIndex,
    geometry: { kind: "rect", x: 0, y, width: 10, height: 10 },
  });

  it("prefers the smallest counterpart page at or after the origin page", () => {
    const pair = { sources: [fragment(0, 100)], targets: [fragment(0, 10), fragment(1, 50)] };
    // Origin on page 1: only the page-1 target qualifies.
    expect(pickCounterpart(pair, "source", fragment(1, 400)).pageIndex).toBe(1);
    // Origin on page 0: page 0 is the smallest eligible page even though the
    // page-2 fragment has a closer y — never jump backwards past a candidate.
    const later = {
      sources: [fragment(0, 100)],
      targets: [fragment(1, 500), fragment(2, 120), fragment(2, 480)],
    };
    expect(pickCounterpart(later, "source", fragment(0, 100)).pageIndex).toBe(1);
  });

  it("picks the closest y among fragments on the winning page", () => {
    const pair = {
      sources: [fragment(0, 100)],
      targets: [fragment(1, 500), fragment(1, 120), fragment(1, 480)],
    };
    const picked = pickCounterpart(pair, "source", fragment(0, 100));
    expect(picked.pageIndex).toBe(1);
    expect(picked.geometry.y).toBe(120);
  });

  it("falls back to the earliest counterpart page when nothing lies at/after", () => {
    const pair = { sources: [fragment(2, 100)], targets: [fragment(0, 300), fragment(1, 10)] };
    expect(pickCounterpart(pair, "source", fragment(2, 100)).pageIndex).toBe(0);
  });
});

describe("buildReaderModel", () => {
  it("exposes node, translation, relation, and index lookups", () => {
    const bundle = crossPageBundle();
    const model = buildReaderModel(bundle, {
      source: [
        { width: 612, height: 792 },
        { width: 612, height: 792 },
      ],
      target: [{ width: 612, height: 792 }],
    });
    expect(model.pairs.size).toBe(2);
    expect(model.nodeById.get("heading-1")?.kind).toBe("HEADING");
    expect(model.translationByNodeId.get("para-1")?.content).toEqual({ text: "正文", marks: [] });
    const relations = model.relationsByNodeId.get("para-1");
    expect(relations).toHaveLength(1);
    expect(relations?.[0]?.otherNodeId).toBe("heading-1");
    // Source index sees the cross-page paragraph; target index orders y-ascending.
    expect(model.indexes.source.hitTest(1, 12 + 20, 10 + 6).map((h) => h.nodeId)).toContain(
      "para-1",
    );
    expect(model.indexes.target.inBand(0, 0, 792).map((h) => h.nodeId)).toEqual([
      "heading-1",
      "para-1",
      "para-1",
    ]);
  });
});
