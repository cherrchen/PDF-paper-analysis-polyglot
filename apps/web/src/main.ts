/**
 * M6 bidirectional reader: spatial-index navigation, scroll/highlight/focus
 * sync (6.3/6.4), the Semantic Inspector (6.5), and reader-API translation
 * interaction (6.6). Jumping never assumes `source page ≈ target page`
 * (FR-SYNC-004): every destination comes from the paired RenderAnchor
 * fragments via `pickCounterpart`.
 */
import { workspaceLabel } from "@paper/ui";
import type { PDFDocumentProxy } from "pdfjs-dist";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { renderInspector } from "./inspector.js";
import {
  buildReaderModel,
  type Fragment,
  fragmentsForSide,
  type MappingBundle,
  type PageSize,
  pickCounterpart,
  type Side,
} from "./mapping.js";

type PageDimension = { widthPt: number; heightPt: number };
type ViewerMeta = {
  sourcePageCount: number;
  targetPageCount: number;
  sourcePages: PageDimension[];
  targetPages: PageDimension[];
};

const SCALE = 1.5;
/** Half-height of the sync-scroll band, in canonical page points. */
const SYNC_BAND_PT = 12;
/** Ignore programmatic-scroll echoes on the scrolled side for this long. */
const SUPPRESS_MS = 250;
const DATA_FILES = {
  mappings: "/data/mapping.json",
  meta: "/data/viewer-meta.json",
  source: "/data/source.pdf",
  target: "/data/target.pdf",
};

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`missing viewer element: ${selector}`);
  return element;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json() as Promise<T>;
}

async function probeApi(): Promise<boolean> {
  try {
    return (await fetch("/api/health")).ok;
  } catch {
    return false;
  }
}

async function init(): Promise<void> {
  const status = requiredElement<HTMLElement>("#status");
  const viewer = requiredElement<HTMLElement>("#viewer");
  const viewerStatus = requiredElement<HTMLElement>("#viewer-status");
  const inspectorRoot = requiredElement<HTMLElement>("#inspector");
  const inspectorToggle = requiredElement<HTMLButtonElement>("#inspector-toggle");
  const syncToggle = requiredElement<HTMLInputElement>("#sync-scroll");

  try {
    const [initialMappings, initialMeta, initialSource, initialTarget] = await Promise.all([
      fetchJson<MappingBundle>(DATA_FILES.mappings),
      fetchJson<ViewerMeta>(DATA_FILES.meta),
      pdfjsLib.getDocument({ url: DATA_FILES.source }).promise,
      pdfjsLib.getDocument({ url: DATA_FILES.target }).promise,
    ]);
    let meta = initialMeta;
    const pageSizes = (dimensions: PageDimension[]): PageSize[] =>
      dimensions.map((p) => ({ width: p.widthPt, height: p.heightPt }));
    let model = buildReaderModel(initialMappings, {
      source: pageSizes(meta.sourcePages),
      target: pageSizes(meta.targetPages),
    });
    const pdfs: Record<Side, PDFDocumentProxy | undefined> = {
      source: initialSource,
      target: initialTarget,
    };
    let apiAvailable = await probeApi();
    let activeNodeId: string | undefined;
    let inspectorOpen = true;
    let lastOrigin: { side: Side; fragment: Fragment } | undefined;
    const currentPage: Record<Side, number> = { source: 0, target: 0 };
    const suppressUntil: Record<Side, number> = { source: 0, target: 0 };
    const metrics: Record<Side, { widthPt: number; heightPt: number; canvasHeight: number }> = {
      source: { widthPt: 612, heightPt: 792, canvasHeight: 792 * SCALE },
      target: { widthPt: 612, heightPt: 792, canvasHeight: 792 * SCALE },
    };
    const pageCount = (side: Side): number =>
      side === "source" ? meta.sourcePageCount : meta.targetPageCount;
    const scrollContainer = (side: Side): HTMLElement =>
      requiredElement<HTMLElement>(`#${side}-pane .page-scroll`);

    const drawOverlay = (side: Side, pageIndex: number): void => {
      const overlay = requiredElement<HTMLElement>(`#${side}-overlay`);
      overlay.replaceChildren();
      const { widthPt: pageWidth, heightPt: pageHeight } = metrics[side];
      for (const [nodeId, pair] of model.pairs) {
        for (const fragment of fragmentsForSide(pair, side)) {
          if (fragment.pageIndex !== pageIndex) continue;
          const button = document.createElement("button");
          button.type = "button";
          button.className = "mapped-region";
          button.dataset.nodeId = nodeId;
          button.dataset.side = side;
          button.dataset.pageIndex = String(fragment.pageIndex);
          button.setAttribute("aria-label", `${side} mapped region ${nodeId}`);
          button.setAttribute("aria-pressed", String(nodeId === activeNodeId));
          button.style.left = `${(fragment.geometry.x / pageWidth) * 100}%`;
          button.style.top = `${(fragment.geometry.y / pageHeight) * 100}%`;
          button.style.width = `${(fragment.geometry.width / pageWidth) * 100}%`;
          button.style.height = `${(fragment.geometry.height / pageHeight) * 100}%`;
          button.addEventListener("click", () => void activate(nodeId, side, fragment));
          overlay.append(button);
        }
      }
    };

    const renderPage = async (side: Side, pageIndex: number): Promise<void> => {
      const pdf = pdfs[side];
      if (!pdf) throw new Error(`pdf document unavailable for ${side}`);
      const boundedPage = Math.max(0, Math.min(pageIndex, pageCount(side) - 1));
      currentPage[side] = boundedPage;
      const page = await pdf.getPage(boundedPage + 1);
      const viewport = page.getViewport({ scale: SCALE });
      const canvas = requiredElement<HTMLCanvasElement>(`#${side}-canvas`);
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("2d canvas context unavailable");
      await page.render({ canvas, canvasContext: context, viewport }).promise;
      metrics[side] = {
        widthPt: viewport.width / SCALE,
        heightPt: viewport.height / SCALE,
        canvasHeight: viewport.height,
      };
      drawOverlay(side, boundedPage);
      requiredElement<HTMLElement>(`#${side}-page`).textContent =
        `${boundedPage + 1} / ${pageCount(side)}`;
      requiredElement<HTMLButtonElement>(`#${side}-previous`).disabled = boundedPage === 0;
      requiredElement<HTMLButtonElement>(`#${side}-next`).disabled =
        boundedPage === pageCount(side) - 1;
    };

    /** Scroll `side`'s container so `fragment` sits vertically centered. */
    const scrollFragmentIntoCenter = (side: Side, fragment: Fragment): void => {
      const container = scrollContainer(side);
      const { heightPt, canvasHeight } = metrics[side];
      const fragmentCenterPx =
        ((fragment.geometry.y + fragment.geometry.height / 2) / heightPt) * canvasHeight;
      const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight);
      suppressUntil[side] = performance.now() + SUPPRESS_MS;
      container.scrollTop = Math.max(
        0,
        Math.min(fragmentCenterPx - container.clientHeight / 2, maxScroll),
      );
    };

    const focusRegion = (side: Side, nodeId: string, pageIndex: number): void => {
      const button = requiredElement<HTMLElement>(`#${side}-overlay`).querySelector(
        `[data-node-id="${CSS.escape(nodeId)}"][data-page-index="${pageIndex}"]`,
      ) as HTMLButtonElement | null;
      button?.focus({ preventScroll: true });
    };

    const refreshInspector = (): void => {
      renderInspector(inspectorRoot, model, activeNodeId ?? null, {
        apiAvailable,
        onSelect: (nodeId) => void jumpTo(nodeId),
        onRetranslate: retranslateNode,
      });
      if (activeNodeId) inspectorRoot.hidden = !inspectorOpen;
    };

    /** 6.3: click → jump + center + focus on the counterpart fragment. */
    const activate = async (
      nodeId: string,
      origin: Side,
      originFragment: Fragment,
    ): Promise<void> => {
      const pair = model.pairs.get(nodeId);
      if (!pair) return;
      activeNodeId = nodeId;
      lastOrigin = { side: origin, fragment: originFragment };
      const destination: Side = origin === "source" ? "target" : "source";
      const counterpart = pickCounterpart(pair, origin, originFragment);
      await renderPage(destination, counterpart.pageIndex);
      await renderPage(origin, originFragment.pageIndex);
      scrollFragmentIntoCenter(destination, counterpart);
      focusRegion(destination, nodeId, counterpart.pageIndex);
      requiredElement<HTMLElement>(`#${destination}-pane`).scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
      viewerStatus.textContent = `Linked region selected · ${nodeId.slice(0, 8)}`;
      refreshInspector();
    };

    /** Inspector relation/citation jump: navigate from the side being watched. */
    const jumpTo = async (nodeId: string): Promise<void> => {
      const pair = model.pairs.get(nodeId);
      if (!pair) return;
      const origin: Side = lastOrigin?.side ?? "source";
      const samePage = fragmentsForSide(pair, origin).find(
        (f) => f.pageIndex === lastOrigin?.fragment.pageIndex,
      );
      const fragment = samePage ?? fragmentsForSide(pair, origin)[0];
      if (!fragment) return;
      await activate(nodeId, origin, fragment);
    };

    /** 6.3 scroll semantics: band query on the scrolling side, no page guessing. */
    const syncFrom = async (side: Side): Promise<void> => {
      if (!syncToggle.checked) return;
      if (performance.now() < suppressUntil[side]) return;
      const container = scrollContainer(side);
      const { heightPt, canvasHeight } = metrics[side];
      const centerPt =
        ((container.scrollTop + container.clientHeight / 2) * heightPt) / canvasHeight;
      const hits = model.indexes[side].inBand(
        currentPage[side],
        centerPt - SYNC_BAND_PT,
        centerPt + SYNC_BAND_PT,
      );
      const hit = hits.find((candidate) => model.pairs.has(candidate.nodeId));
      if (!hit) return; // nothing mapped in this band: do nothing (exit-gate rule)
      const pair = model.pairs.get(hit.nodeId);
      if (!pair) return;
      const originFragment: Fragment = { pageIndex: currentPage[side], geometry: hit.rect };
      const destination: Side = side === "source" ? "target" : "source";
      const counterpart = pickCounterpart(pair, side, originFragment);
      activeNodeId = hit.nodeId;
      if (currentPage[destination] !== counterpart.pageIndex) {
        await renderPage(destination, counterpart.pageIndex);
      } else {
        drawOverlay(destination, currentPage[destination]);
      }
      drawOverlay(side, currentPage[side]);
      scrollFragmentIntoCenter(destination, counterpart);
    };

    let syncQueued = false;
    for (const side of ["source", "target"] as const) {
      scrollContainer(side).addEventListener("scroll", () => {
        if (!syncToggle.checked || syncQueued) return;
        syncQueued = true;
        const scrollSide = side;
        requestAnimationFrame(() => {
          syncQueued = false;
          void syncFrom(scrollSide);
        });
      });
    }

    /** 6.6: retranslate via the reader API, then rebuild the target view. */
    const retranslateNode = async (nodeId: string): Promise<void> => {
      let response: Response;
      try {
        response = await fetch("/api/retranslate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ nodeIds: [nodeId] }),
        });
      } catch (error) {
        viewerStatus.textContent = `Re-translate failed · ${String(error)}`;
        return;
      }
      if (!response.ok) {
        viewerStatus.textContent = `Re-translate failed · ${response.status}`;
        return;
      }
      const bust = `r=${Date.now()}`;
      const [freshMappings, freshMeta] = await Promise.all([
        fetchJson<MappingBundle>(`${DATA_FILES.mappings}?${bust}`),
        fetchJson<ViewerMeta>(`${DATA_FILES.meta}?${bust}`),
      ]);
      meta = freshMeta;
      model = buildReaderModel(freshMappings, {
        source: pageSizes(freshMeta.sourcePages),
        target: pageSizes(freshMeta.targetPages),
      });
      // Re-translating reflows the target: the old document geometry is stale.
      const staleTarget = pdfs.target;
      if (staleTarget) await staleTarget.loadingTask.destroy();
      pdfs.target = await pdfjsLib.getDocument({ url: `${DATA_FILES.target}?${bust}` }).promise;
      apiAvailable = await probeApi();
      const reselect = activeNodeId && model.pairs.has(activeNodeId) ? activeNodeId : undefined;
      await Promise.all([
        renderPage("source", Math.min(currentPage.source, freshMeta.sourcePageCount - 1)),
        renderPage("target", Math.min(currentPage.target, freshMeta.targetPageCount - 1)),
      ]);
      if (reselect && lastOrigin) {
        const pair = model.pairs.get(reselect);
        const fragment = pair ? fragmentsForSide(pair, lastOrigin.side)[0] : undefined;
        if (fragment) await activate(reselect, lastOrigin.side, fragment);
      }
      refreshInspector();
      viewerStatus.textContent = `Node re-translated · ${nodeId.slice(0, 8)}`;
    };

    for (const side of ["source", "target"] as const) {
      requiredElement<HTMLButtonElement>(`#${side}-previous`).addEventListener("click", () => {
        scrollContainer(side).scrollTop = 0;
        void renderPage(side, currentPage[side] - 1);
      });
      requiredElement<HTMLButtonElement>(`#${side}-next`).addEventListener("click", () => {
        scrollContainer(side).scrollTop = 0;
        void renderPage(side, currentPage[side] + 1);
      });
    }

    inspectorToggle.addEventListener("click", () => {
      inspectorOpen = !inspectorOpen;
      inspectorToggle.setAttribute("aria-expanded", String(inspectorOpen));
      refreshInspector();
    });

    await Promise.all([renderPage("source", 0), renderPage("target", 0)]);
    viewer.hidden = false;
    status.textContent = `${workspaceLabel()} workspace is running.`;
    viewerStatus.textContent = `Bidirectional navigation ready · ${model.pairs.size} linked regions`;
  } catch (error) {
    viewerStatus.textContent = `Viewer unavailable. Run “just viewer-fixture” to create the local data (${String(error)}).`;
  }
}

void init();
