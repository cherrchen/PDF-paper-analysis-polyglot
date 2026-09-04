import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { type JsonValue, SCHEMA_VERSION, validateDocument } from "./index.js";

const FIXTURE_CASES: Array<{ schemaName: Parameters<typeof validateDocument>[0]; file: string }> = [
  { schemaName: "physical-document", file: "two-page-two-column.valid.json" },
  { schemaName: "evidence", file: "mock-providers.valid.json" },
  { schemaName: "layout-document", file: "two-column-spanning-figure.valid.json" },
  { schemaName: "semantic-document", file: "paper-structure.valid.json" },
  { schemaName: "mapping", file: "three-binding-scenarios.valid.json" },
];

function loadFixture(file: string): JsonValue {
  const root = path.resolve(import.meta.dirname, "..", "..", "..", "..");
  return JSON.parse(
    readFileSync(path.join(root, "schemas", "fixtures", file), "utf8"),
  ) as JsonValue;
}

describe("canonical document contracts", () => {
  it("reports the frozen schema version", () => {
    expect(SCHEMA_VERSION).toBe("0.1.0");
  });

  for (const { schemaName, file } of FIXTURE_CASES) {
    it(`validates ${file} against ${schemaName}`, () => {
      const errors = validateDocument(schemaName, loadFixture(`${schemaName}/${file}`));
      expect(errors).toEqual([]);
    });
  }

  it("rejects documents with unknown properties", () => {
    const doc = loadFixture("semantic-document/paper-structure.valid.json") as {
      nodes: Array<Record<string, unknown>>;
    };
    const firstNode = doc.nodes[0];
    if (!firstNode) throw new Error("fixture must have a node");
    firstNode.bbox = [0, 0, 1, 1];
    const errors = validateDocument("semantic-document", doc as JsonValue);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("rejects invalid node kinds", () => {
    const doc = loadFixture("semantic-document/paper-structure.valid.json") as {
      nodes: Array<{ kind: string }>;
    };
    const firstNode = doc.nodes[0];
    if (!firstNode) throw new Error("fixture must have a node");
    firstNode.kind = "PAGE";
    const errors = validateDocument("semantic-document", doc as JsonValue);
    expect(errors.some((e) => e.message.includes("enum"))).toBe(true);
  });

  it("rejects malformed identifiers", () => {
    const doc = loadFixture("semantic-document/paper-structure.valid.json") as {
      id: string;
    };
    doc.id = "not-a-valid-id";
    const errors = validateDocument("semantic-document", doc as JsonValue);
    expect(errors.some((e) => e.message.includes("pattern"))).toBe(true);
  });

  it("rejects explicit null for an optional string", () => {
    const doc = loadFixture("physical-document/two-page-two-column.valid.json") as {
      metadata: { title?: string | null };
    };
    doc.metadata.title = null;
    const errors = validateDocument("physical-document", doc as JsonValue);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("rejects a five-point quad", () => {
    const errors = validateDocument("physical-document", {
      schemaVersion: "0.1.0",
      id: "01J5M1FXTRES0AAAAAAA0DOC00",
      pages: [],
      objects: [
        {
          objectType: "textSpan",
          id: "01J5M1FXTRES0AAAAAAA0OBJ00",
          pageId: "01J5M1FXTRES0AAAAAAA0PAGE0",
          text: "x",
          geometry: {
            kind: "quad",
            points: [
              { x: 0, y: 0 },
              { x: 1, y: 0 },
              { x: 1, y: 1 },
              { x: 0, y: 1 },
              { x: 0.5, y: 0.5 },
            ],
          },
        },
      ],
      metadata: {},
    });
    expect(errors.length).toBeGreaterThan(0);
  });

  it("accepts an omitted optional title", () => {
    const doc = loadFixture("physical-document/two-page-two-column.valid.json") as {
      metadata: Record<string, unknown>;
    };
    delete doc.metadata.title;
    expect(validateDocument("physical-document", doc as JsonValue)).toEqual([]);
  });

  it("rejects formula candidates without a representation", () => {
    const doc = loadFixture("evidence/mock-providers.valid.json") as {
      candidates: Array<Record<string, unknown>>;
    };
    const formula = doc.candidates.find((candidate) => candidate.evidenceType === "FORMULA");
    if (!formula) throw new Error("fixture must have a formula candidate");
    delete formula.latex;
    delete formula.mathml;
    delete formula.unicodeText;
    delete formula.rawText;
    delete formula.previewResourceId;
    const errors = validateDocument("evidence", doc as JsonValue);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("continues object validation after a matching anyOf branch", () => {
    const doc = loadFixture("evidence/mock-providers.valid.json") as {
      candidates: Array<Record<string, unknown>>;
    };
    const formula = doc.candidates.find((candidate) => candidate.evidenceType === "FORMULA");
    if (!formula) throw new Error("fixture must have a formula candidate");
    delete formula.id;
    const errors = validateDocument("evidence", doc as JsonValue);
    expect(errors.length).toBeGreaterThan(0);
  });
});
