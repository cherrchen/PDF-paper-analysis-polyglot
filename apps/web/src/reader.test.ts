import type { PDFDocumentProxy } from "pdfjs-dist";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MappingBundle } from "./mapping.js";
import { DualPaneReader } from "./reader.js";
import type { ViewerMeta } from "./viewer-assets.js";

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
  sourcePageCount: 2,
  targetPageCount: 2,
  sourcePages: [
    { widthPt: 612, heightPt: 792 },
    { widthPt: 612, heightPt: 792 },
  ],
  targetPages: [
    { widthPt: 612, heightPt: 792 },
    { widthPt: 612, heightPt: 792 },
  ],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DualPaneReader render coordination", () => {
  it("invalidates an older page turn when the latest request is the current page", async () => {
    const invalidate = vi.fn();
    const redrawOverlay = vi.fn();
    const reader = Object.assign(Object.create(DualPaneReader.prototype), {
      meta,
      currentPage: { source: 0, target: 0 },
      renderers: { source: { invalidate, render: vi.fn() } },
      redrawOverlay,
    }) as DualPaneReader;

    await reader.showPage("source", 0);

    expect(invalidate).toHaveBeenCalledOnce();
    expect(redrawOverlay).toHaveBeenCalledWith("source");
  });

  it("re-renders the old target page and restores scroll after candidate render failure", async () => {
    const destroyCandidate = vi.fn(async () => undefined);
    const previousPdf = { loadingTask: { destroy: vi.fn() } } as unknown as PDFDocumentProxy;
    const candidatePdf = {
      loadingTask: { destroy: destroyCandidate },
    } as unknown as PDFDocumentProxy;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/retranslate") return jsonResponse({ revision: "next" });
        if (url === "/api/health") return jsonResponse({ ok: true });
        if (url.startsWith("/data/manifest.json")) {
          return jsonResponse({
            revision: "next",
            mapping: "/data/revisions/next/mapping.json",
            meta: "/data/revisions/next/viewer-meta.json",
            source: "/data/revisions/next/source.pdf",
            target: "/data/revisions/next/target.pdf",
          });
        }
        if (url.includes("mapping.json")) return jsonResponse(mapping);
        if (url.includes("viewer-meta.json")) return jsonResponse(meta);
        if (init?.method === "HEAD") {
          return new Response(null, {
            status: 200,
            headers: { "content-type": "application/pdf" },
          });
        }
        throw new Error(`unexpected fetch: ${url}`);
      }),
    );
    const sourceScroll = { scrollTop: 11 };
    const targetScroll = { scrollTop: 37 };
    const rendered: Array<{ pdf: PDFDocumentProxy | undefined; page: number }> = [];
    const reader = Object.assign(Object.create(DualPaneReader.prototype), {
      meta,
      revision: "previous",
      model: {
        pairs: new Map(),
        indexes: {},
      },
      pdfs: { source: previousPdf, target: previousPdf },
      currentPage: { source: 0, target: 1 },
      activeNodeId: undefined,
      apiAvailable: true,
      retranslateBusy: false,
      viewerStatus: { textContent: "" },
      loadPdf: vi.fn(async () => candidatePdf),
      setViewerChrome: vi.fn(),
      refreshInspector: vi.fn(),
      redrawOverlay: vi.fn(),
      focusRegion: vi.fn(),
      scrollContainer: (side: "source" | "target") =>
        side === "source" ? sourceScroll : targetScroll,
      showPage: async function (this: DualPaneReader, side: "source" | "target", page: number) {
        if (side === "source") return;
        rendered.push({ pdf: this.pdfs.target, page });
        if (this.pdfs.target === candidatePdf) {
          targetScroll.scrollTop = 0;
          throw new Error("candidate render failed");
        }
        this.currentPage.target = page;
      },
    }) as DualPaneReader;

    await reader.retranslate("node-1");

    expect(reader.pdfs.target).toBe(previousPdf);
    expect(reader.revision).toBe("previous");
    expect(reader.currentPage.target).toBe(1);
    expect(targetScroll.scrollTop).toBe(37);
    expect(sourceScroll.scrollTop).toBe(11);
    expect(rendered).toEqual([
      { pdf: candidatePdf, page: 0 },
      { pdf: previousPdf, page: 1 },
    ]);
    expect(destroyCandidate).toHaveBeenCalledOnce();
  });
});

describe("DualPaneReader.load first-page transaction", () => {
  it.each(["getPage", "render", "success"])(
    "prepares both panes before committing: %s",
    async (failure) => {
      const oldSource = { loadingTask: { destroy: vi.fn() } };
      const oldTarget = { loadingTask: { destroy: vi.fn() } };
      let finishSource!: () => void;
      let sourceStarted!: () => void;
      const started = new Promise<void>((resolve) => {
        sourceStarted = resolve;
      });
      const pending = new Promise<void>((resolve) => {
        finishSource = resolve;
      });
      const makePdf = (side: string) => ({
        loadingTask: { destroy: vi.fn(async () => undefined) },
        getPage: vi.fn(async () => {
          if (side === "target" && failure === "getPage") throw new Error("getPage failed");
          return {
            getViewport: () => ({ width: 900, height: 1200 }),
            render: () => {
              if (side === "source") sourceStarted();
              return {
                cancel: vi.fn(),
                promise:
                  side === "source"
                    ? pending
                    : failure === "render"
                      ? Promise.reject(new Error("render failed"))
                      : Promise.resolve(),
              };
            },
          };
        }),
      });
      const source = makePdf("source");
      const target = makePdf("target");
      const live = { width: 123, height: 456, getContext: () => ({ drawImage }) };
      const drawImage = vi.fn();
      vi.stubGlobal("document", {
        createElement: () => ({ getContext: () => ({}) }),
        querySelector: () => live,
      });
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
          const url = String(input);
          if (url.includes("manifest.json"))
            return jsonResponse({
              revision: "next",
              mapping: "/mapping.json",
              meta: "/meta.json",
              source: "/source.pdf",
              target: "/target.pdf",
            });
          if (url.includes("mapping.json")) return jsonResponse(mapping);
          if (url.includes("meta.json")) return jsonResponse(meta);
          if (init?.method === "HEAD") return new Response(null, { status: 200 });
          throw new Error(url);
        }),
      );
      const previousModel = { pairs: new Map() };
      const origin = { side: "source", fragment: {} };
      const reader = Object.assign(Object.create(DualPaneReader.prototype), {
        meta,
        revision: "previous",
        model: previousModel,
        pdfs: { source: oldSource, target: oldTarget },
        currentPage: { source: 1, target: 1 },
        activeNodeId: "selected",
        lastOrigin: origin,
        loadPdf: async (url: string) => (url.includes("source.pdf") ? source : target),
        renderers: { source: { invalidate: vi.fn() }, target: { invalidate: vi.fn() } },
        setViewerChrome: vi.fn(),
        refreshInspector: vi.fn(),
        viewerStatus: { textContent: "old" },
        commitPage: vi.fn(),
      }) as DualPaneReader;
      const outcome = reader.load("next").then(
        () => undefined,
        (error: unknown) => error,
      );
      await started;
      expect(reader.revision).toBe("previous");
      expect(drawImage).not.toHaveBeenCalled();
      expect(source.loadingTask.destroy).not.toHaveBeenCalled();
      finishSource();
      const error = await outcome;
      if (failure === "success") {
        expect(error).toBeUndefined();
        expect(reader.revision).toBe("next");
        expect(drawImage).toHaveBeenCalledTimes(2);
        expect(oldSource.loadingTask.destroy).toHaveBeenCalledOnce();
        expect(oldTarget.loadingTask.destroy).toHaveBeenCalledOnce();
        expect(source.loadingTask.destroy).not.toHaveBeenCalled();
      } else {
        expect(String(error)).toContain(`${failure} failed`);
        expect(reader.revision).toBe("previous");
        expect(reader.model).toBe(previousModel);
        expect(reader.meta).toBe(meta);
        expect(reader.pdfs).toEqual({ source: oldSource, target: oldTarget });
        expect(reader.currentPage).toEqual({ source: 1, target: 1 });
        expect(reader.activeNodeId).toBe("selected");
        expect(reader.lastOrigin).toBe(origin);
        expect(reader.viewerStatus.textContent).toBe("old");
        expect(reader.commitPage).not.toHaveBeenCalled();
        expect(reader.refreshInspector).not.toHaveBeenCalled();
        expect(drawImage).not.toHaveBeenCalled();
        expect(live.width).toBe(123);
        expect(live.height).toBe(456);
        expect(source.loadingTask.destroy).toHaveBeenCalledOnce();
        expect(target.loadingTask.destroy).toHaveBeenCalledOnce();
        expect(oldSource.loadingTask.destroy).not.toHaveBeenCalled();
        expect(oldTarget.loadingTask.destroy).not.toHaveBeenCalled();
      }
    },
  );
});
