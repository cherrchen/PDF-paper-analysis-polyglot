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
  pickCounterpart,
  type ReaderModel,
  type Side,
} from "./mapping.js";
import { PaneRenderer, PDF_RENDER_SCALE } from "./pane-render.js";
import {
  fetchViewerManifest,
  loadViewerAssets,
  pageSizesFrom,
  type ViewerMeta,
} from "./viewer-assets.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const SYNC_BAND_PT = 12;
const SUPPRESS_MS = 250;

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`missing viewer element: ${selector}`);
  return element;
}

async function probeApi(): Promise<boolean> {
  try {
    return (await fetch("/api/health")).ok;
  } catch {
    return false;
  }
}

function loadPdf(url: string): Promise<PDFDocumentProxy> {
  return pdfjsLib.getDocument({ url }).promise;
}

async function init(): Promise<void> {
  const status = requiredElement<HTMLElement>("#status");
  const viewer = requiredElement<HTMLElement>("#viewer");
  const viewerStatus = requiredElement<HTMLElement>("#viewer-status");
  const inspectorRoot = requiredElement<HTMLElement>("#inspector");
  const inspectorToggle = requiredElement<HTMLButtonElement>("#inspector-toggle");
  const syncToggle = requiredElement<HTMLInputElement>("#sync-scroll");

  try {
    const initialManifest = await fetchViewerManifest({ fallback: true });
    const initial = await loadViewerAssets(loadPdf, initialManifest, { includeSource: true });
    if (!initial.source) throw new Error("source pdf missing");

    let meta: ViewerMeta = initial.meta;
    let revision = initial.revision;
    let model: ReaderModel = buildReaderModel(initial.mappings, pageSizesFrom(meta));
    const pdfs: Record<Side, PDFDocumentProxy | undefined> = {
      source: initial.source,
      target: initial.target,
    };
    let apiAvailable = await probeApi();
    let activeNodeId: string | undefined;
    let inspectorOpen = true;
    let lastOrigin: { side: Side; fragment: Fragment } | undefined;
    let retranslateBusy = false;
    const currentPage: Record<Side, number> = { source: -1, target: -1 };
    const suppressUntil: Record<Side, number> = { source: 0, target: 0 };
    const metrics: Record<Side, { widthPt: number; heightPt: number; canvasHeight: number }> = {
      source: { widthPt: 612, heightPt: 792, canvasHeight: 792 * PDF_RENDER_SCALE },
      target: { widthPt: 612, heightPt: 792, canvasHeight: 792 * PDF_RENDER_SCALE },
    };
    const pageCount = (side: Side): number =>
      side === "source" ? meta.sourcePageCount : meta.targetPageCount;
    const scrollContainer = (side: Side): HTMLElement =>
      requiredElement<HTMLElement>(`#${side}-pane .page-scroll`);

    const renderers: Record<Side, PaneRenderer> = {
      source: new PaneRenderer(
        requiredElement<HTMLCanvasElement>("#source-canvas"),
        () => pdfs.source,
        () => pageCount("source"),
      ),
      target: new PaneRenderer(
        requiredElement<HTMLCanvasElement>("#target-canvas"),
        () => pdfs.target,
        () => pageCount("target"),
      ),
    };

    const setViewerChrome = (): void => {
      viewer.dataset.revision = revision;
      viewer.dataset.busy = retranslateBusy ? "true" : "false";
      viewer.setAttribute("aria-busy", retranslateBusy ? "true" : "false");
    };

    const drawOverlay = (side: Side, pageIndex: number): void => {
      const overlay = requiredElement<HTMLElement>(`#${side}-overlay`);
      overlay.replaceChildren();
      const { widthPt: pageWidth, heightPt: pageHeight } = metrics[side];
      const buttons: { nodeId: string; fragment: Fragment; area: number }[] = [];
      for (const [nodeId, pair] of model.pairs) {
        for (const fragment of fragmentsForSide(pair, side)) {
          if (fragment.pageIndex !== pageIndex) continue;
          buttons.push({
            nodeId,
            fragment,
            area: fragment.geometry.width * fragment.geometry.height,
          });
        }
      }
      // Paint larger regions first so smaller overlapping hits sit on top.
      buttons.sort((a, b) => b.area - a.area);
      for (const { nodeId, fragment } of buttons) {
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
        button.addEventListener("click", (event) => {
          const chosen =
            event.detail === 0
              ? { nodeId, fragment }
              : (hitFromPointer(side, event) ?? { nodeId, fragment });
          void activate(chosen.nodeId, side, chosen.fragment);
        });
        overlay.append(button);
      }
    };

    const hitFromPointer = (
      side: Side,
      event: MouseEvent,
    ): { nodeId: string; fragment: Fragment } | undefined => {
      const canvas = requiredElement<HTMLCanvasElement>(`#${side}-canvas`);
      const bounds = canvas.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return undefined;
      const { widthPt, heightPt } = metrics[side];
      const x = ((event.clientX - bounds.left) / bounds.width) * widthPt;
      const y = ((event.clientY - bounds.top) / bounds.height) * heightPt;
      const hit = model.indexes[side].hitTest(currentPage[side], x, y)[0];
      if (!hit) return undefined;
      return { nodeId: hit.nodeId, fragment: { pageIndex: hit.pageIndex, geometry: hit.rect } };
    };

    const commitPage = (
      side: Side,
      commit: { pageIndex: number; widthPt: number; heightPt: number; canvasHeight: number },
    ): void => {
      currentPage[side] = commit.pageIndex;
      metrics[side] = {
        widthPt: commit.widthPt,
        heightPt: commit.heightPt,
        canvasHeight: commit.canvasHeight,
      };
      drawOverlay(side, commit.pageIndex);
      requiredElement<HTMLElement>(`#${side}-page`).textContent =
        `${commit.pageIndex + 1} / ${pageCount(side)}`;
      requiredElement<HTMLButtonElement>(`#${side}-previous`).disabled = commit.pageIndex === 0;
      requiredElement<HTMLButtonElement>(`#${side}-next`).disabled =
        commit.pageIndex === pageCount(side) - 1;
    };

    const showPage = async (side: Side, pageIndex: number): Promise<void> => {
      const bounded = Math.max(0, Math.min(pageIndex, pageCount(side) - 1));
      if (currentPage[side] === bounded) {
        drawOverlay(side, bounded);
        return;
      }
      const commit = await renderers[side].render(bounded);
      if (!commit) return;
      commitPage(side, commit);
    };

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
        retranslateBusy,
        onSelect: (nodeId) => void jumpTo(nodeId),
        onRetranslate: retranslateNode,
      });
      if (activeNodeId) inspectorRoot.hidden = !inspectorOpen;
    };

    const setActiveNode = (nodeId: string | undefined): void => {
      activeNodeId = nodeId;
      if (currentPage.source >= 0) drawOverlay("source", currentPage.source);
      if (currentPage.target >= 0) drawOverlay("target", currentPage.target);
      refreshInspector();
    };

    const activate = async (
      nodeId: string,
      origin: Side,
      originFragment: Fragment,
    ): Promise<void> => {
      const pair = model.pairs.get(nodeId);
      if (!pair) return;
      lastOrigin = { side: origin, fragment: originFragment };
      setActiveNode(nodeId);
      const destination: Side = origin === "source" ? "target" : "source";
      const counterpart = pickCounterpart(pair, origin, originFragment);
      await showPage(destination, counterpart.pageIndex);
      await showPage(origin, originFragment.pageIndex);
      scrollFragmentIntoCenter(destination, counterpart);
      focusRegion(destination, nodeId, counterpart.pageIndex);
      requiredElement<HTMLElement>(`#${destination}-pane`).scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
      viewerStatus.textContent = `Linked region selected · ${nodeId.slice(0, 8)}`;
    };

    const jumpTo = async (nodeId: string): Promise<void> => {
      const pair = model.pairs.get(nodeId);
      if (!pair) return;
      const origin: Side = lastOrigin?.side ?? "source";
      const samePage = fragmentsForSide(pair, origin).find(
        (fragment) => fragment.pageIndex === lastOrigin?.fragment.pageIndex,
      );
      const fragment = samePage ?? fragmentsForSide(pair, origin)[0];
      if (!fragment) return;
      await activate(nodeId, origin, fragment);
    };

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
      if (!hit) return;
      const pair = model.pairs.get(hit.nodeId);
      if (!pair) return;
      const originFragment: Fragment = { pageIndex: currentPage[side], geometry: hit.rect };
      const destination: Side = side === "source" ? "target" : "source";
      const counterpart = pickCounterpart(pair, side, originFragment);
      setActiveNode(hit.nodeId);
      await showPage(destination, counterpart.pageIndex);
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

    const retranslateNode = async (nodeId: string): Promise<void> => {
      if (retranslateBusy) return;
      retranslateBusy = true;
      setViewerChrome();
      viewerStatus.textContent = `Re-translating · ${nodeId.slice(0, 8)}`;
      refreshInspector();
      try {
        const response = await fetch("/api/retranslate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ nodeIds: [nodeId] }),
        });
        if (!response.ok) {
          viewerStatus.textContent = `Re-translate failed · ${response.status}`;
          return;
        }
        const body = (await response.json()) as { revision?: string };
        const bust = `r=${body.revision ?? String(Date.now())}`;
        const manifest = await fetchViewerManifest({ cacheBust: bust, fallback: false });
        const previous = { meta, model, revision, target: pdfs.target };
        let candidate: Awaited<ReturnType<typeof loadViewerAssets>> | undefined;
        try {
          candidate = await loadViewerAssets(loadPdf, manifest, { includeSource: false });
          const nextModel = buildReaderModel(candidate.mappings, pageSizesFrom(candidate.meta));
          meta = candidate.meta;
          model = nextModel;
          revision = candidate.revision;
          pdfs.target = candidate.target;
          currentPage.target = -1;
          apiAvailable = await probeApi();
          setViewerChrome();
          await Promise.all([
            showPage("source", Math.max(0, currentPage.source)),
            showPage("target", 0),
          ]);
        } catch (error) {
          const swapped = candidate !== undefined && pdfs.target === candidate.target;
          if (swapped) {
            meta = previous.meta;
            model = previous.model;
            revision = previous.revision;
            pdfs.target = previous.target;
            currentPage.target = -1;
          }
          if (candidate?.target && pdfs.target !== candidate.target) {
            await candidate.target.loadingTask.destroy();
          }
          throw error;
        }
        if (previous.target && previous.target !== pdfs.target) {
          await previous.target.loadingTask.destroy();
        }
        const reselect = activeNodeId && model.pairs.has(activeNodeId) ? activeNodeId : undefined;
        if (reselect && lastOrigin) {
          const pair = model.pairs.get(reselect);
          const fragment = pair ? fragmentsForSide(pair, lastOrigin.side)[0] : undefined;
          if (fragment) await activate(reselect, lastOrigin.side, fragment);
        } else {
          refreshInspector();
        }
        viewerStatus.textContent = `Node re-translated · ${nodeId.slice(0, 8)} · ${revision.slice(0, 8)}`;
      } catch (error) {
        viewerStatus.textContent = `Re-translate failed · ${String(error)}`;
      } finally {
        retranslateBusy = false;
        setViewerChrome();
        refreshInspector();
      }
    };

    for (const side of ["source", "target"] as const) {
      requiredElement<HTMLButtonElement>(`#${side}-previous`).addEventListener("click", () => {
        scrollContainer(side).scrollTop = 0;
        void showPage(side, currentPage[side] - 1);
      });
      requiredElement<HTMLButtonElement>(`#${side}-next`).addEventListener("click", () => {
        scrollContainer(side).scrollTop = 0;
        void showPage(side, currentPage[side] + 1);
      });
    }

    inspectorToggle.addEventListener("click", () => {
      inspectorOpen = !inspectorOpen;
      inspectorToggle.setAttribute("aria-expanded", String(inspectorOpen));
      refreshInspector();
    });

    setViewerChrome();
    await Promise.all([showPage("source", 0), showPage("target", 0)]);
    viewer.hidden = false;
    status.textContent = `${workspaceLabel()} workspace is running.`;
    viewerStatus.textContent = `Bidirectional navigation ready · ${model.pairs.size} linked regions`;
  } catch (error) {
    viewerStatus.textContent = `Viewer unavailable. Run “just viewer-fixture” to create the local data (${String(error)}).`;
  }
}

void init();
