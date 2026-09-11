/**
 * M6 bidirectional reader bootstrap.
 *
 * Pane lifecycle, navigation, and retranslate state live on DualPaneReader.
 * Jumping never assumes `source page ≈ target page` (FR-SYNC-004).
 */
import { workspaceLabel } from "@paper/ui";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

async function init(): Promise<void> {
  const status = requiredElement<HTMLElement>("#status");
  const viewerStatus = requiredElement<HTMLElement>("#viewer-status");
  try {
    const reader = await DualPaneReader.boot((url) => pdfjsLib.getDocument({ url }).promise);
    await reader.start();
    status.textContent = `${workspaceLabel()} workspace is running.`;
  } catch (error) {
    viewerStatus.textContent = `Viewer unavailable. Run “just viewer-fixture” to create the local data (${String(error)}).`;
  }
}

void init();
