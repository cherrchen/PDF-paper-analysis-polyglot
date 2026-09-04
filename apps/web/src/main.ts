/** M2 source/target PDF viewer with mapping-driven bidirectional navigation. */
import { workspaceLabel } from "@paper/ui";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

type Rect = { kind: "rect"; x: number; y: number; width: number; height: number };
type Fragment = { pageIndex: number; geometry: Rect };
type SourceFragment = { fragmentType: "layoutRegion"; layoutRegionId: string };
type SourceRegion = Fragment & { id: string };
type MappingBundle = {
  viewerDataVersion: number;
  sourceSemanticBindings: { semanticNodeId: string; sourceAnchorIds: string[] }[];
  sourceAnchors: { id: string; fragments: SourceFragment[] }[];
  semanticNodes: { id: string; kind: string }[];
  sourceRegions: SourceRegion[];
  renderAnchors: { id: string; semanticNodeId: string; fragments: Fragment[] }[];
};
type ViewerMeta = {
  sourcePageCount: number;
  targetPageCount: number;
};
type Pair = { source: Fragment; target: Fragment };
type Side = "source" | "target";

const SCALE = 1.5;
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

function buildPairs(mappings: MappingBundle): Map<string, Pair> {
  if (mappings.viewerDataVersion !== 1) {
    throw new Error(`unsupported viewer data version: ${mappings.viewerDataVersion}`);
  }
  const sourceRegionById = new Map(mappings.sourceRegions.map((region) => [region.id, region]));
  const sourceAnchorById = new Map(
    mappings.sourceAnchors.map((anchor) => [
      anchor.id,
      sourceRegionById.get(anchor.fragments[0]?.layoutRegionId ?? ""),
    ]),
  );
  const targetByNodeId = new Map(
    mappings.renderAnchors.map((anchor) => [anchor.semanticNodeId, anchor.fragments[0]]),
  );
  const pairs = new Map<string, Pair>();
  for (const binding of mappings.sourceSemanticBindings) {
    const source = sourceAnchorById.get(binding.sourceAnchorIds[0] ?? "");
    const target = targetByNodeId.get(binding.semanticNodeId);
    if (source && target) pairs.set(binding.semanticNodeId, { source, target });
  }
  return pairs;
}

async function init(): Promise<void> {
  const status = requiredElement<HTMLElement>("#status");
  const viewer = requiredElement<HTMLElement>("#viewer");
  const viewerStatus = requiredElement<HTMLElement>("#viewer-status");

  try {
    const [mappings, meta, sourcePdf, targetPdf] = await Promise.all([
      fetchJson<MappingBundle>(DATA_FILES.mappings),
      fetchJson<ViewerMeta>(DATA_FILES.meta),
      pdfjsLib.getDocument({ url: DATA_FILES.source }).promise,
      pdfjsLib.getDocument({ url: DATA_FILES.target }).promise,
    ]);
    const pairs = buildPairs(mappings);
    let activeNodeId: string | undefined;
    const currentPage: Record<Side, number> = { source: 0, target: 0 };
    const pdfs = { source: sourcePdf, target: targetPdf };
    const pageCounts = { source: meta.sourcePageCount, target: meta.targetPageCount };

    const drawOverlay = (
      side: Side,
      pageIndex: number,
      pageWidth: number,
      pageHeight: number,
    ): void => {
      const overlay = requiredElement<HTMLElement>(`#${side}-overlay`);
      overlay.replaceChildren();
      for (const [nodeId, pair] of pairs) {
        const fragment = pair[side];
        if (fragment.pageIndex !== pageIndex) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "mapped-region";
        button.dataset.nodeId = nodeId;
        button.dataset.side = side;
        button.setAttribute("aria-label", `${side} mapped region ${nodeId}`);
        button.setAttribute("aria-pressed", String(nodeId === activeNodeId));
        button.style.left = `${(fragment.geometry.x / pageWidth) * 100}%`;
        button.style.top = `${(fragment.geometry.y / pageHeight) * 100}%`;
        button.style.width = `${(fragment.geometry.width / pageWidth) * 100}%`;
        button.style.height = `${(fragment.geometry.height / pageHeight) * 100}%`;
        button.addEventListener("click", () => void activate(nodeId, side));
        overlay.append(button);
      }
    };

    const renderPage = async (side: Side, pageIndex: number): Promise<void> => {
      const pdf = pdfs[side];
      const boundedPage = Math.max(0, Math.min(pageIndex, pageCounts[side] - 1));
      currentPage[side] = boundedPage;
      const page = await pdf.getPage(boundedPage + 1);
      const viewport = page.getViewport({ scale: SCALE });
      const canvas = requiredElement<HTMLCanvasElement>(`#${side}-canvas`);
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("2d canvas context unavailable");
      await page.render({ canvas, canvasContext: context, viewport }).promise;
      drawOverlay(side, boundedPage, viewport.width / SCALE, viewport.height / SCALE);
      requiredElement<HTMLElement>(`#${side}-page`).textContent =
        `${boundedPage + 1} / ${pageCounts[side]}`;
      requiredElement<HTMLButtonElement>(`#${side}-previous`).disabled = boundedPage === 0;
      requiredElement<HTMLButtonElement>(`#${side}-next`).disabled =
        boundedPage === pageCounts[side] - 1;
    };

    const activate = async (nodeId: string, origin: Side): Promise<void> => {
      const pair = pairs.get(nodeId);
      if (!pair) return;
      activeNodeId = nodeId;
      const destination: Side = origin === "source" ? "target" : "source";
      await renderPage(destination, pair[destination].pageIndex);
      await renderPage(origin, currentPage[origin]);
      requiredElement<HTMLElement>(`#${destination}-pane`).scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
      viewerStatus.textContent = `Linked region selected · ${nodeId.slice(0, 8)}`;
    };

    for (const side of ["source", "target"] as const) {
      requiredElement<HTMLButtonElement>(`#${side}-previous`).addEventListener("click", () => {
        void renderPage(side, currentPage[side] - 1);
      });
      requiredElement<HTMLButtonElement>(`#${side}-next`).addEventListener("click", () => {
        void renderPage(side, currentPage[side] + 1);
      });
    }

    await Promise.all([renderPage("source", 0), renderPage("target", 0)]);
    viewer.hidden = false;
    status.textContent = `${workspaceLabel()} workspace is running.`;
    viewerStatus.textContent = `Bidirectional navigation ready · ${pairs.size} linked regions`;
  } catch (error) {
    viewerStatus.textContent = `Viewer unavailable. Run “just viewer-fixture” to create the local data (${String(error)}).`;
  }
}

void init();
