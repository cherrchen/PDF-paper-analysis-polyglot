import type { Fragment, ReaderModel, Side } from "./mapping.js";
import { fragmentsForSide } from "./mapping.js";
import { requiredElement } from "./reader-dom.js";

export type PageMetrics = { widthPt: number; heightPt: number; canvasHeight: number };

export type OverlayHost = {
  model: ReaderModel;
  activeNodeId: string | undefined;
  metrics: Record<Side, PageMetrics>;
  currentPage: Record<Side, number>;
};

export function drawOverlay(
  side: Side,
  pageIndex: number,
  host: OverlayHost,
  onActivate: (nodeId: string, side: Side, fragment: Fragment) => void,
): void {
  const overlay = requiredElement<HTMLElement>(`#${side}-overlay`);
  overlay.replaceChildren();
  const { widthPt: pageWidth, heightPt: pageHeight } = host.metrics[side];
  const buttons: { nodeId: string; fragment: Fragment; area: number }[] = [];
  for (const [nodeId, pair] of host.model.pairs) {
    for (const fragment of fragmentsForSide(pair, side)) {
      if (fragment.pageIndex !== pageIndex) continue;
      buttons.push({
        nodeId,
        fragment,
        area: fragment.geometry.width * fragment.geometry.height,
      });
    }
  }
  buttons.sort((a, b) => b.area - a.area);
  for (const { nodeId, fragment } of buttons) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mapped-region";
    button.dataset.nodeId = nodeId;
    button.dataset.side = side;
    button.dataset.pageIndex = String(fragment.pageIndex);
    button.setAttribute("aria-label", `${side} mapped region ${nodeId}`);
    button.setAttribute("aria-pressed", String(nodeId === host.activeNodeId));
    button.style.left = `${(fragment.geometry.x / pageWidth) * 100}%`;
    button.style.top = `${(fragment.geometry.y / pageHeight) * 100}%`;
    button.style.width = `${(fragment.geometry.width / pageWidth) * 100}%`;
    button.style.height = `${(fragment.geometry.height / pageHeight) * 100}%`;
    button.addEventListener("click", (event) => {
      const chosen =
        event.detail === 0
          ? { nodeId, fragment }
          : (hitFromPointer(side, event, host) ?? { nodeId, fragment });
      onActivate(chosen.nodeId, side, chosen.fragment);
    });
    overlay.append(button);
  }
}

export function hitFromPointer(
  side: Side,
  event: MouseEvent,
  host: OverlayHost,
): { nodeId: string; fragment: Fragment } | undefined {
  const canvas = requiredElement<HTMLCanvasElement>(`#${side}-canvas`);
  const bounds = canvas.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return undefined;
  const { widthPt, heightPt } = host.metrics[side];
  const x = ((event.clientX - bounds.left) / bounds.width) * widthPt;
  const y = ((event.clientY - bounds.top) / bounds.height) * heightPt;
  const hit = host.model.indexes[side].hitTest(host.currentPage[side], x, y)[0];
  if (!hit) return undefined;
  return { nodeId: hit.nodeId, fragment: { pageIndex: hit.pageIndex, geometry: hit.rect } };
}
