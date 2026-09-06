import { describe, expect, it } from "vitest";
import { buildPairs, type Fragment, fragmentsForSide, type MappingBundle } from "./mapping.js";

const rect = (x: number): MappingBundle["sourceRegions"][number]["geometry"] => ({
  kind: "rect",
  x,
  y: 10,
  width: 40,
  height: 12,
});

function crossPageBundle(): MappingBundle {
  return {
    viewerDataVersion: 1,
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
      { id: "para-1", kind: "PARAGRAPH" },
      { id: "heading-1", kind: "HEADING" },
    ],
    sourceRegions: [
      { id: "region-p0", pageIndex: 0, geometry: rect(10) },
      { id: "region-p1", pageIndex: 1, geometry: rect(12) },
      { id: "region-h", pageIndex: 0, geometry: rect(8) },
    ],
    renderAnchors: [
      {
        semanticNodeId: "para-1",
        id: "render-1",
        fragments: [{ pageIndex: 0, geometry: rect(20) }],
      },
      {
        semanticNodeId: "heading-1",
        id: "render-h",
        fragments: [{ pageIndex: 0, geometry: rect(4) }],
      },
    ],
  };
}

describe("viewer mapping pairs", () => {
  it("keeps every source fragment of a cross-page paragraph", () => {
    const pairs = buildPairs(crossPageBundle());
    const pair = pairs.get("para-1");
    expect(pair).toBeDefined();
    if (!pair) return;
    expect(pair.sources).toHaveLength(2);
    expect(pair.sources.map((fragment: Fragment) => fragment.pageIndex)).toEqual([0, 1]);
    expect(fragmentsForSide(pair, "source")).toHaveLength(2);
    expect(fragmentsForSide(pair, "target")).toHaveLength(1);
    const page1 = pair.sources.filter((fragment: Fragment) => fragment.pageIndex === 1);
    expect(page1).toHaveLength(1);
  });

  it("still pairs single-fragment headings", () => {
    const pairs = buildPairs(crossPageBundle());
    expect(pairs.get("heading-1")?.sources).toHaveLength(1);
  });
});
