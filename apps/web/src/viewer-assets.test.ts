import type { PDFDocumentProxy } from "pdfjs-dist";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MappingBundle } from "./mapping.js";
import { fetchJson, loadViewerAssets, type ViewerManifest } from "./viewer-assets.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function htmlResponse(): Response {
  return new Response("<!doctype html>", {
    status: 200,
    headers: { "content-type": "text/html" },
  });
}

const mapping: MappingBundle = {
  viewerDataVersion: 2,
  sourceSemanticBindings: [],
  sourceAnchors: [],
  semanticNodes: [],
  semanticRelations: [],
  sourceRegions: [],
  renderAnchors: [],
  translation: { targetLocale: "zh-CN", entries: [] },
  provenance: [],
  issues: [],
};
const fakePdf = { loadingTask: { destroy: async () => undefined } } as unknown as PDFDocumentProxy;

describe("fetchJson", () => {
  it("rejects SPA HTML even when the status is 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => htmlResponse()),
    );
    await expect(fetchJson("/data/mapping.json")).rejects.toThrow(/expected JSON/);
  });
});

describe("loadViewerAssets", () => {
  it("rejects the whole revision instead of mixing in stable aliases", async () => {
    const manifest: ViewerManifest = {
      revision: "abc",
      mapping: "/data/revisions/abc/mapping.json",
      meta: "/data/revisions/abc/viewer-meta.json",
      source: "/data/revisions/abc/source.pdf",
      target: "/data/revisions/abc/target.pdf",
    };
    const fetched: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        fetched.push(`${init?.method ?? "GET"} ${url}`);
        if (url.includes("mapping.json")) return jsonResponse(mapping);
        if (url.includes("viewer-meta.json")) return htmlResponse();
        return new Response(null, {
          status: init?.method === "HEAD" ? 200 : 404,
          headers: { "content-type": "application/pdf" },
        });
      }),
    );
    await expect(loadViewerAssets(async () => fakePdf, manifest)).rejects.toThrow(/expected JSON/);
    expect(fetched.some((entry) => entry.includes("/revisions/abc/mapping.json"))).toBe(true);
    expect(fetched.some((entry) => entry.includes("/data/mapping.json"))).toBe(false);
    expect(fetched.some((entry) => entry.includes("target.pdf"))).toBe(false);
  });
});
