import type { PDFDocumentProxy } from "pdfjs-dist";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MappingBundle } from "./mapping.js";
import {
  FALLBACK_MANIFEST,
  fetchJson,
  loadViewerAssets,
  type ViewerManifest,
  type ViewerMeta,
} from "./viewer-assets.js";

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
const meta: ViewerMeta = {
  sourcePageCount: 1,
  targetPageCount: 1,
  sourcePages: [{ widthPt: 612, heightPt: 792 }],
  targetPages: [{ widthPt: 612, heightPt: 792 }],
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
  it("falls back to stable aliases when revision URLs return HTML", async () => {
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
        if (url.includes("/revisions/")) {
          if (init?.method === "HEAD") {
            return new Response(null, {
              status: 200,
              headers: { "content-type": "text/html" },
            });
          }
          return htmlResponse();
        }
        if (url.startsWith(FALLBACK_MANIFEST.mapping)) return jsonResponse(mapping);
        if (url.startsWith(FALLBACK_MANIFEST.meta)) return jsonResponse(meta);
        if (init?.method === "HEAD") {
          return new Response(null, {
            status: 200,
            headers: { "content-type": "application/pdf" },
          });
        }
        return new Response("not-json", { status: 404 });
      }),
    );
    const loaded = await loadViewerAssets(async (url) => {
      if (url.includes("/revisions/")) throw new Error(`unexpected revision pdf ${url}`);
      return fakePdf;
    }, manifest);
    expect(loaded.revision).toBe("abc");
    expect(loaded.mappings).toEqual(mapping);
    expect(loaded.meta).toEqual(meta);
    expect(loaded.target).toBe(fakePdf);
    expect(fetched.some((entry) => entry.includes("/revisions/abc/mapping.json"))).toBe(true);
    expect(fetched.some((entry) => entry.includes("/data/mapping.json"))).toBe(true);
  });
});
