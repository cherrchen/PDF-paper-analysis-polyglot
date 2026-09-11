import { describe, expect, it } from "vitest";
import type { Rect } from "./mapping.js";
import { type IndexedFragment, PageSpatialIndex } from "./spatial.js";

const pageSizes = [
  { width: 612, height: 792 },
  { width: 612, height: 792 },
];

const rect = (x: number, y: number, width: number, height: number): Rect => ({
  kind: "rect",
  x,
  y,
  width,
  height,
});

function fragment(
  nodeId: string,
  pageIndex: number,
  geometry: Rect,
  side: "source" | "target" = "source",
): IndexedFragment {
  return { nodeId, side, pageIndex, rect: geometry };
}

describe("PageSpatialIndex.hitTest", () => {
  it("returns fragments containing the point, smallest area first", () => {
    const index = new PageSpatialIndex(
      [
        fragment("outer", 0, rect(50, 50, 200, 200)),
        fragment("inner", 0, rect(100, 100, 40, 40)),
        fragment("other", 1, rect(100, 100, 40, 40)),
      ],
      pageSizes,
    );
    expect(index.hitTest(0, 110, 110).map((f) => f.nodeId)).toEqual(["inner", "outer"]);
    expect(index.hitTest(1, 110, 110).map((f) => f.nodeId)).toEqual(["other"]);
  });

  it("finds rects straddling cell boundaries from either cell", () => {
    // One full-width band across the page middle spans every column.
    const index = new PageSpatialIndex([fragment("band", 0, rect(0, 300, 612, 30))], pageSizes);
    expect(index.hitTest(0, 5, 310)).toHaveLength(1);
    expect(index.hitTest(0, 605, 310)).toHaveLength(1);
    expect(index.hitTest(0, 300, 310)).toHaveLength(1);
  });

  it("ignores zero-area fragments and empty pages", () => {
    const index = new PageSpatialIndex(
      [fragment("zero", 0, rect(10, 10, 0, 12)), fragment("ok", 0, rect(10, 10, 12, 12))],
      pageSizes,
    );
    expect(index.hitTest(0, 10, 10).map((f) => f.nodeId)).toEqual(["ok"]);
    expect(index.hitTest(1, 10, 10)).toEqual([]);
  });

  it("returns [] off-page without throwing", () => {
    const index = new PageSpatialIndex([fragment("a", 0, rect(1, 1, 10, 10))], pageSizes);
    expect(index.hitTest(0, -5, 5)).toEqual([]);
    expect(index.hitTest(7, 5, 5)).toEqual([]);
    expect(index.hitTest(0, 9999, 9999)).toEqual([]);
  });
});

describe("PageSpatialIndex.inBand", () => {
  it("returns intersecting fragments sorted by y", () => {
    const index = new PageSpatialIndex(
      [
        fragment("low", 0, rect(0, 300, 100, 20)),
        fragment("high", 0, rect(0, 100, 100, 20)),
        fragment("cross", 0, rect(0, 250, 100, 100)),
        fragment("page1", 1, rect(0, 100, 100, 20)),
      ],
      pageSizes,
    );
    expect(index.inBand(0, 290, 310).map((f) => f.nodeId)).toEqual(["cross", "low"]);
    expect(index.inBand(1, 0, 10)).toEqual([]);
  });

  it("handles empty index and inverted band without throwing", () => {
    const index = new PageSpatialIndex([], pageSizes);
    expect(index.inBand(0, 100, 200)).toEqual([]);
    expect(index.inBand(0, 200, 100)).toEqual([]);
  });

  it("falls back to the first known page size for unknown pages", () => {
    const index = new PageSpatialIndex([fragment("deep", 9, rect(10, 10, 50, 50))], pageSizes);
    // Page 9 has no meta entry; fallback (612×792) still indexes it.
    expect(index.hitTest(9, 20, 20).map((f) => f.nodeId)).toEqual(["deep"]);
  });
});
