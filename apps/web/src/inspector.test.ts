import { describe, expect, it } from "vitest";
import { citationMarksFor, nodePlainText } from "./inspector.js";
import {
  buildReaderModel,
  type MappingBundle,
  type NodeContent,
  type SemanticNodeView,
} from "./mapping.js";

const rect = { kind: "rect", x: 0, y: 0, width: 10, height: 10 } as const;

function bundleWith(node: SemanticNodeView, translationContent?: NodeContent): MappingBundle {
  return {
    viewerDataVersion: 2,
    schemaVersion: "0.1.0",
    id: "m",
    physicalLayoutBindings: [],
    sourceSemanticBindings: [{ semanticNodeId: node.id, sourceAnchorIds: ["a1"] }],
    sourceAnchors: [
      { id: "a1", fragments: [{ fragmentType: "layoutRegion", layoutRegionId: "r1" }] },
    ],
    semanticNodes: [node],
    semanticRelations: [],
    sourceRegions: [{ id: "r1", pageIndex: 0, geometry: { ...rect } }],
    renderAnchors: [
      {
        id: node.id,
        semanticNodeId: node.id,
        fragments: [{ pageIndex: 0, geometry: { ...rect } }],
      },
    ],
    translation: {
      targetLocale: "zh-CN",
      entries: translationContent ? [{ semanticNodeId: node.id, content: translationContent }] : [],
    },
    provenance: [],
    issues: [],
  };
}

function node(
  id: string,
  content: NodeContent,
  extra: Partial<SemanticNodeView> = {},
): SemanticNodeView {
  return {
    id,
    kind: "PARAGRAPH",
    content,
    confidence: { score: 1 },
    provenanceIds: [],
    ...extra,
  };
}

describe("nodePlainText", () => {
  it("renders rich text verbatim", () => {
    expect(nodePlainText({ text: "Hello world", marks: [] })).toBe("Hello world");
  });

  it("renders equation fallbacks in canonical priority order", () => {
    expect(nodePlainText({ latex: "x^2", mathml: "<m/>" })).toBe("x^2");
    expect(nodePlainText({ mathml: "<m/>", unicodeText: "x²" })).toBe("<m/>");
    expect(nodePlainText({ unicodeText: "x²", rawText: "x^2" })).toBe("x²");
    expect(nodePlainText({ rawText: "x^2" })).toBe("x^2");
    expect(nodePlainText({ previewResourceId: "res-1" })).toBe("[preview]");
  });

  it("labels figures and joins table cells with truncation", () => {
    expect(nodePlainText({ label: "1", resources: { embeddedImageIds: [] } })).toBe("Figure 1");
    const cells = Array.from({ length: 25 }, (_, i) => ({
      row: i,
      column: 0,
      content: { text: `c${i}`, marks: [] },
    }));
    const rendered = nodePlainText({ rows: 25, columns: 1, cells });
    expect(rendered.split(" | ").length).toBe(20);
    expect(rendered.endsWith("c19…")).toBe(true);
  });
});

describe("citationMarksFor", () => {
  it("extracts reference-mark slices with labels and targets", () => {
    const paragraph = node("n1", {
      text: "See Figure 1 and [1].",
      marks: [
        { type: "FIGURE_REFERENCE", start: 4, end: 12, targetNodeId: "fig-1", label: "1" },
        { type: "CITATION", start: 17, end: 20, targetNodeId: "ref-9" },
        { type: "BOLD", start: 0, end: 3 },
      ],
    });
    const model = buildReaderModel(bundleWith(paragraph), {
      source: [{ width: 612, height: 792 }],
      target: [{ width: 612, height: 792 }],
    });
    expect(citationMarksFor(model, paragraph)).toEqual([
      { text: "Figure 1", label: "FIGURE_REFERENCE 1", targetNodeId: "fig-1" },
      { text: "[1]", label: "CITATION", targetNodeId: "ref-9" },
    ]);
  });

  it("flags out-of-range marks instead of throwing", () => {
    const paragraph = node("n1", {
      text: "short",
      marks: [{ type: "CITATION", start: 100, end: 200, targetNodeId: null }],
    });
    const model = buildReaderModel(bundleWith(paragraph), {
      source: [{ width: 612, height: 792 }],
      target: [{ width: 612, height: 792 }],
    });
    expect(citationMarksFor(model, paragraph)[0]?.text).toBe("mark out of range");
  });

  it("includes translation-side marks", () => {
    const paragraph = node("n1", { text: "source text", marks: [] });
    const model = buildReaderModel(
      bundleWith(paragraph, {
        text: "见图 2",
        marks: [{ type: "TABLE_REFERENCE", start: 1, end: 3, targetNodeId: "tab-1", label: "2" }],
      }),
      { source: [{ width: 612, height: 792 }], target: [{ width: 612, height: 792 }] },
    );
    const marks = citationMarksFor(model, paragraph);
    expect(marks).toEqual([{ text: "图 ", label: "TABLE_REFERENCE 2", targetNodeId: "tab-1" }]);
  });
});
