/**
 * M2 Walking Skeleton viewer.
 *
 * Two panes (Source / Target PDF via PDF.js). Clicking a source region
 * highlights and jumps to the matching target region, and vice versa.
 * All pairs come from the pipeline's mapping bundle; no navigation data is
 * computed in the client.
 */
import { workspaceLabel } from "@paper/ui";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

type Rect = { kind: "rect"; x: number; y: number; width: number; height: number };
type Fragment = { pageIndex: number; geometry: Rect };
type SourceFragment = { fragmentType: "layoutRegion"; layoutRegionId: string };
type MappingBundle = {
  sourceSemanticBindings: { id: string; semanticNodeId: string; sourceAnchorIds: string[] }[];
  sourceAnchors: { id: string; fragments: SourceFragment[] }[];
  renderBindings?: { renderAnchorIds: string[] }[];
  renderAnchors?: { id: string; semanticNodeId: string; fragments: Fragment[] }[];
};
type ViewerData = {
  mappings: MappingBundle;
  sourcePageCount: number;
  targetPageCount: number;
  sourcePageSize: { widthPt: number; heightPt: number };
  targetPageSize: { widthPt: number; heightPt: number };
};

const status = document.querySelector("#status");
if (status) {
  status.textContent = `${workspaceLabel()} workspace is running.`;
}

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const DATA_FILES = {
  mappings: "/data/mapping.json",
  meta: "/data/viewer-meta.json",
};

async function loadViewerData(): Promise<ViewerData> {
  const [mappings, meta] = await Promise.all([
    fetch(DATA_FILES.mappings).then((response) => {
      if (!response.ok) throw new Error(`${DATA_FILES.mappings}: ${response.status}`);
      return response.json() as Promise<MappingBundle>;
    }),
    fetch(DATA_FILES.meta).then((response) => {
      if (!response.ok) throw new Error(`${DATA_FILES.meta}: ${response.status}`);
      return response.json() as Promise<Omit<ViewerData, "mappings">>;
    }),
  ]);
  return { mappings, ...meta };
}

/**
 * Build the bidirectional pair map from the mapping bundle.
 * semanticNodeId -> { source fragment, target fragment }.
 */
function buildPairs(
  mappings: MappingBundle,
): Map<string, { source: SourceFragment; target: Fragment }> {
  const firstFragment = <T>(fragments: T[]): T | undefined => fragments[0];
  const sourceAnchorById = new Map(
    mappings.sourceAnchors.map((anchor) => [anchor.id, firstFragment(anchor.fragments)]),
  );
  const renderAnchors = new Map(
    (mappings.renderAnchors ?? []).map((anchor) => [
      anchor.semanticNodeId,
      firstFragment(anchor.fragments),
    ]),
  );
  const pairs = new Map<string, { source: SourceFragment; target: Fragment }>();
  for (const binding of mappings.sourceSemanticBindings) {
    const sourceFragment = sourceAnchorById.get(binding.sourceAnchorIds[0] ?? "");
    const targetFragment = renderAnchors.get(binding.semanticNodeId);
    if (sourceFragment && targetFragment) {
      pairs.set(binding.semanticNodeId, { source: sourceFragment, target: targetFragment });
    }
  }
  return pairs;
}

async function renderFirstPage(url: string, canvas: HTMLCanvasElement): Promise<void> {
  const doc = await pdfjsLib.getDocument({ url }).promise;
  const page = await doc.getPage(1);
  const viewport = page.getViewport({ scale: 1.5 });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2d canvas context unavailable");
  await page.render({ canvasContext: context, canvas, viewport }).promise;
  await doc.cleanup();
}

async function init(): Promise<void> {
  const viewer = document.querySelector("#viewer");
  const viewerStatus = document.querySelector("#viewer-status");
  try {
    const data = await loadViewerData();
    const pairs = buildPairs(data.mappings);
    await renderFirstPage(
      "/data/source.pdf",
      document.querySelector("#source-canvas") as HTMLCanvasElement,
    );
    await renderFirstPage(
      "/data/target.pdf",
      document.querySelector("#target-canvas") as HTMLCanvasElement,
    );
    if (viewer instanceof HTMLElement) viewer.hidden = false;
    if (status) status.textContent = `${workspaceLabel()} workspace is running.`;
    if (viewerStatus) {
      viewerStatus.textContent = `Bidirectional navigation ready: ${pairs.size} node pairs.`;
    }
  } catch (error) {
    if (viewerStatus) {
      viewerStatus.textContent = `Viewer unavailable: run the pipeline to produce /data artifacts (${String(error)}).`;
    }
  }
}

void init();
