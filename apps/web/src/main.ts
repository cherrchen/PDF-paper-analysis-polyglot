/**
 * M6 bidirectional reader bootstrap.
 *
 * Pane lifecycle, navigation, and retranslate state live on DualPaneReader.
 * Jumping never assumes `source page ≈ target page` (FR-SYNC-004).
 */
import { workspaceLabel } from "@paper/ui";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { bootHistoryPanel } from "./history-panel.js";
import { bootImportPanel } from "./import-panel.js";
import { DualPaneReader } from "./reader.js";
import { requiredElement } from "./reader-dom.js";
import { bootSelectPanel } from "./select-panel.js";
import { bootStatusPanel } from "./status-panel.js";
import { bootSurfaceTabs } from "./surface-tabs.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

async function init(): Promise<void> {
  const status = requiredElement<HTMLElement>("#status");
  const viewerStatus = requiredElement<HTMLElement>("#viewer-status");
  try {
    const reader = await DualPaneReader.boot((url) => pdfjsLib.getDocument({ url }).promise);
    await reader.start();
    const tabs = bootSurfaceTabs();
    bootImportPanel(reader);
    bootSelectPanel(reader, tabs);
    bootHistoryPanel(reader, tabs);
    bootStatusPanel(reader, tabs);
    status.textContent = `${workspaceLabel()} workspace is running.`;
  } catch (error) {
    viewerStatus.textContent = `Viewer unavailable. Run “just viewer-fixture” to create the local data (${String(error)}).`;
  }
}

void init();
