/**
 * Dual-pane reader session: pane lifecycle, navigation, and retranslate state.
 *
 * Overlay painting lives in `reader-overlay.ts`; asset loading lives in
 * `viewer-assets.ts`; PDF.js serialization lives in `pane-render.ts`.
 */
import type { PDFDocumentProxy } from "pdfjs-dist";
import { renderInspector } from "./inspector.js";
import {
  buildReaderModel,
  type Fragment,
  fragmentsForSide,
  pickCounterpart,
  type ReaderModel,
  type Side,
} from "./mapping.js";
import { PaneRenderer, PDF_RENDER_SCALE, type RenderCommit } from "./pane-render.js";
import { requiredElement } from "./reader-dom.js";
import { drawOverlay, type PageMetrics } from "./reader-overlay.js";
import {
  fetchViewerManifest,
  type LoadedViewerAssets,
  loadViewerAssets,
  type PdfLoader,
  pageSizesFrom,
  type ViewerMeta,
} from "./viewer-assets.js";

const SYNC_BAND_PT = 12;
const SUPPRESS_MS = 250;

export async function probeApi(): Promise<boolean> {
  try {
    return (await fetch("/api/health")).ok;
  } catch {
    return false;
  }
}

type RetranslateResponse = { revision?: string };

export class DualPaneReader {
  meta: ViewerMeta;
  revision: string;
  model: ReaderModel;
  readonly pdfs: Record<Side, PDFDocumentProxy | undefined>;
  apiAvailable: boolean;
  activeNodeId: string | undefined;
  inspectorOpen = true;
  lastOrigin: { side: Side; fragment: Fragment } | undefined;
  retranslateBusy = false;
  readonly currentPage: Record<Side, number> = { source: -1, target: -1 };
  readonly suppressUntil: Record<Side, number> = { source: 0, target: 0 };
  readonly metrics: Record<Side, PageMetrics> = {
    source: { widthPt: 612, heightPt: 792, canvasHeight: 792 * PDF_RENDER_SCALE },
    target: { widthPt: 612, heightPt: 792, canvasHeight: 792 * PDF_RENDER_SCALE },
  };

  readonly viewer = requiredElement<HTMLElement>("#viewer");
  readonly viewerStatus = requiredElement<HTMLElement>("#viewer-status");
  readonly inspectorRoot = requiredElement<HTMLElement>("#inspector");
  readonly inspectorToggle = requiredElement<HTMLButtonElement>("#inspector-toggle");
  readonly syncToggle = requiredElement<HTMLInputElement>("#sync-scroll");

  private readonly loadPdf: PdfLoader;
  private readonly renderers: Record<Side, PaneRenderer>;

  constructor(loadPdf: PdfLoader, initial: LoadedViewerAssets, apiAvailable: boolean) {
    if (!initial.source) throw new Error("source pdf missing");
    this.loadPdf = loadPdf;
    this.meta = initial.meta;
    this.revision = initial.revision;
    this.model = buildReaderModel(initial.mappings, pageSizesFrom(initial.meta));
    this.pdfs = { source: initial.source, target: initial.target };
    this.apiAvailable = apiAvailable;
    this.renderers = {
      source: new PaneRenderer(
        requiredElement<HTMLCanvasElement>("#source-canvas"),
        () => this.pdfs.source,
        () => this.pageCount("source"),
      ),
      target: new PaneRenderer(
        requiredElement<HTMLCanvasElement>("#target-canvas"),
        () => this.pdfs.target,
        () => this.pageCount("target"),
      ),
    };
  }

  static async boot(loadPdf: PdfLoader): Promise<DualPaneReader> {
    const initialManifest = await fetchViewerManifest({ fallback: true });
    const initial = await loadViewerAssets(loadPdf, initialManifest, { includeSource: true });
    return new DualPaneReader(loadPdf, initial, await probeApi());
  }

  pageCount(side: Side): number {
    return side === "source" ? this.meta.sourcePageCount : this.meta.targetPageCount;
  }

  scrollContainer(side: Side): HTMLElement {
    return requiredElement<HTMLElement>(`#${side}-pane .page-scroll`);
  }

  setViewerChrome(): void {
    this.viewer.dataset.revision = this.revision;
    this.viewer.dataset.busy = this.retranslateBusy ? "true" : "false";
    this.viewer.setAttribute("aria-busy", this.retranslateBusy ? "true" : "false");
  }

  refreshInspector(): void {
    renderInspector(this.inspectorRoot, this.model, this.activeNodeId ?? null, {
      apiAvailable: this.apiAvailable,
      retranslateBusy: this.retranslateBusy,
      onSelect: (nodeId) => void this.jumpTo(nodeId),
      onRetranslate: (nodeId) => this.retranslate(nodeId),
    });
    if (this.activeNodeId) this.inspectorRoot.hidden = !this.inspectorOpen;
  }

  setActiveNode(nodeId: string | undefined): void {
    this.activeNodeId = nodeId;
    if (this.currentPage.source >= 0) this.redrawOverlay("source");
    if (this.currentPage.target >= 0) this.redrawOverlay("target");
    this.refreshInspector();
  }

  redrawOverlay(side: Side): void {
    drawOverlay(side, this.currentPage[side], this, (nodeId, origin, fragment) => {
      void this.activate(nodeId, origin, fragment);
    });
  }

  commitPage(side: Side, commit: RenderCommit): void {
    this.currentPage[side] = commit.pageIndex;
    this.metrics[side] = {
      widthPt: commit.widthPt,
      heightPt: commit.heightPt,
      canvasHeight: commit.canvasHeight,
    };
    this.redrawOverlay(side);
    requiredElement<HTMLElement>(`#${side}-page`).textContent =
      `${commit.pageIndex + 1} / ${this.pageCount(side)}`;
    requiredElement<HTMLButtonElement>(`#${side}-previous`).disabled = commit.pageIndex === 0;
    requiredElement<HTMLButtonElement>(`#${side}-next`).disabled =
      commit.pageIndex === this.pageCount(side) - 1;
  }

  async showPage(side: Side, pageIndex: number): Promise<void> {
    const bounded = Math.max(0, Math.min(pageIndex, this.pageCount(side) - 1));
    if (this.currentPage[side] === bounded) {
      this.renderers[side].invalidate();
      this.redrawOverlay(side);
      return;
    }
    const commit = await this.renderers[side].render(bounded);
    if (!commit) return;
    this.commitPage(side, commit);
  }

  scrollFragmentIntoCenter(side: Side, fragment: Fragment): void {
    const container = this.scrollContainer(side);
    const { heightPt, canvasHeight } = this.metrics[side];
    const fragmentCenterPx =
      ((fragment.geometry.y + fragment.geometry.height / 2) / heightPt) * canvasHeight;
    const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight);
    this.suppressUntil[side] = performance.now() + SUPPRESS_MS;
    container.scrollTop = Math.max(
      0,
      Math.min(fragmentCenterPx - container.clientHeight / 2, maxScroll),
    );
  }

  focusRegion(side: Side, nodeId: string, pageIndex: number): void {
    const button = requiredElement<HTMLElement>(`#${side}-overlay`).querySelector(
      `[data-node-id="${CSS.escape(nodeId)}"][data-page-index="${pageIndex}"]`,
    );
    if (button instanceof HTMLButtonElement) button.focus({ preventScroll: true });
  }

  async activate(nodeId: string, origin: Side, originFragment: Fragment): Promise<void> {
    const pair = this.model.pairs.get(nodeId);
    if (!pair) return;
    this.lastOrigin = { side: origin, fragment: originFragment };
    this.setActiveNode(nodeId);
    const destination: Side = origin === "source" ? "target" : "source";
    const counterpart = pickCounterpart(pair, origin, originFragment);
    await this.showPage(destination, counterpart.pageIndex);
    await this.showPage(origin, originFragment.pageIndex);
    this.scrollFragmentIntoCenter(destination, counterpart);
    this.focusRegion(destination, nodeId, counterpart.pageIndex);
    requiredElement<HTMLElement>(`#${destination}-pane`).scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
    this.viewerStatus.textContent = `Linked region selected · ${nodeId.slice(0, 8)}`;
  }

  async jumpTo(nodeId: string): Promise<void> {
    const pair = this.model.pairs.get(nodeId);
    if (!pair) return;
    const origin: Side = this.lastOrigin?.side ?? "source";
    const samePage = fragmentsForSide(pair, origin).find(
      (fragment) => fragment.pageIndex === this.lastOrigin?.fragment.pageIndex,
    );
    const fragment = samePage ?? fragmentsForSide(pair, origin)[0];
    if (!fragment) return;
    await this.activate(nodeId, origin, fragment);
  }

  async syncFrom(side: Side): Promise<void> {
    if (!this.syncToggle.checked) return;
    if (performance.now() < this.suppressUntil[side]) return;
    const container = this.scrollContainer(side);
    const { heightPt, canvasHeight } = this.metrics[side];
    const centerPt = ((container.scrollTop + container.clientHeight / 2) * heightPt) / canvasHeight;
    const hits = this.model.indexes[side].inBand(
      this.currentPage[side],
      centerPt - SYNC_BAND_PT,
      centerPt + SYNC_BAND_PT,
    );
    const hit = hits.find((candidate) => this.model.pairs.has(candidate.nodeId));
    if (!hit) return;
    const pair = this.model.pairs.get(hit.nodeId);
    if (!pair) return;
    const originFragment: Fragment = { pageIndex: this.currentPage[side], geometry: hit.rect };
    const destination: Side = side === "source" ? "target" : "source";
    const counterpart = pickCounterpart(pair, side, originFragment);
    this.setActiveNode(hit.nodeId);
    await this.showPage(destination, counterpart.pageIndex);
    this.scrollFragmentIntoCenter(destination, counterpart);
  }

  async retranslate(nodeId: string): Promise<void> {
    if (this.retranslateBusy) return;
    this.retranslateBusy = true;
    this.setViewerChrome();
    this.viewerStatus.textContent = `Re-translating · ${nodeId.slice(0, 8)}`;
    this.refreshInspector();
    try {
      const response = await fetch("/api/retranslate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ nodeIds: [nodeId] }),
      });
      if (!response.ok) {
        this.viewerStatus.textContent = `Re-translate failed · ${response.status}`;
        return;
      }
      const body = (await response.json()) as RetranslateResponse;
      const bust = `r=${body.revision ?? String(Date.now())}`;
      const manifest = await fetchViewerManifest({ cacheBust: bust, fallback: false });
      const previous = {
        meta: this.meta,
        model: this.model,
        revision: this.revision,
        target: this.pdfs.target,
        targetPage: this.currentPage.target,
        sourceScrollTop: this.scrollContainer("source").scrollTop,
        targetScrollTop: this.scrollContainer("target").scrollTop,
      };
      let candidate: LoadedViewerAssets | undefined;
      try {
        candidate = await loadViewerAssets(this.loadPdf, manifest, { includeSource: false });
        this.meta = candidate.meta;
        this.model = buildReaderModel(candidate.mappings, pageSizesFrom(candidate.meta));
        this.revision = candidate.revision;
        this.pdfs.target = candidate.target;
        this.currentPage.target = -1;
        this.apiAvailable = await probeApi();
        this.setViewerChrome();
        await Promise.all([
          this.showPage("source", Math.max(0, this.currentPage.source)),
          this.showPage("target", 0),
        ]);
      } catch (error) {
        const swapped = candidate !== undefined && this.pdfs.target === candidate.target;
        try {
          if (swapped) {
            this.meta = previous.meta;
            this.model = previous.model;
            this.revision = previous.revision;
            this.pdfs.target = previous.target;
            this.currentPage.target = -1;
            await this.showPage("target", Math.max(0, previous.targetPage));
            this.scrollContainer("source").scrollTop = previous.sourceScrollTop;
            this.scrollContainer("target").scrollTop = previous.targetScrollTop;
            this.redrawOverlay("source");
            this.redrawOverlay("target");
            if (this.activeNodeId && previous.targetPage >= 0) {
              this.focusRegion("target", this.activeNodeId, previous.targetPage);
            }
          }
        } finally {
          if (candidate?.target && this.pdfs.target !== candidate.target) {
            await candidate.target.loadingTask.destroy();
          }
        }
        throw error;
      }
      if (previous.target && previous.target !== this.pdfs.target) {
        await previous.target.loadingTask.destroy();
      }
      const reselect =
        this.activeNodeId && this.model.pairs.has(this.activeNodeId)
          ? this.activeNodeId
          : undefined;
      if (reselect && this.lastOrigin) {
        const pair = this.model.pairs.get(reselect);
        const fragment = pair ? fragmentsForSide(pair, this.lastOrigin.side)[0] : undefined;
        if (fragment) await this.activate(reselect, this.lastOrigin.side, fragment);
      } else {
        this.refreshInspector();
      }
      this.viewerStatus.textContent = `Node re-translated · ${nodeId.slice(0, 8)} · ${this.revision.slice(0, 8)}`;
    } catch (error) {
      this.viewerStatus.textContent = `Re-translate failed · ${String(error)}`;
    } finally {
      this.retranslateBusy = false;
      this.setViewerChrome();
      this.refreshInspector();
    }
  }

  bindEvents(): void {
    let syncQueued = false;
    for (const side of ["source", "target"] as const) {
      this.scrollContainer(side).addEventListener("scroll", () => {
        if (!this.syncToggle.checked || syncQueued) return;
        syncQueued = true;
        const scrollSide = side;
        requestAnimationFrame(() => {
          syncQueued = false;
          void this.syncFrom(scrollSide);
        });
      });
      requiredElement<HTMLButtonElement>(`#${side}-previous`).addEventListener("click", () => {
        this.scrollContainer(side).scrollTop = 0;
        void this.showPage(side, this.currentPage[side] - 1);
      });
      requiredElement<HTMLButtonElement>(`#${side}-next`).addEventListener("click", () => {
        this.scrollContainer(side).scrollTop = 0;
        void this.showPage(side, this.currentPage[side] + 1);
      });
    }
    this.inspectorToggle.addEventListener("click", () => {
      this.inspectorOpen = !this.inspectorOpen;
      this.inspectorToggle.setAttribute("aria-expanded", String(this.inspectorOpen));
      this.refreshInspector();
    });
  }

  async start(): Promise<void> {
    this.bindEvents();
    this.setViewerChrome();
    await Promise.all([this.showPage("source", 0), this.showPage("target", 0)]);
    this.viewer.hidden = false;
    this.viewerStatus.textContent = `Bidirectional navigation ready · ${this.model.pairs.size} linked regions`;
  }
}
