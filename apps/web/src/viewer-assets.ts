/**
 * Viewer asset loading: manifest-addressed revisions of mapping/meta/PDFs.
 *
 * `_write_viewer_assets` publishes a complete `revisions/<id>/` directory and
 * then flips `manifest.json`. Loading uses exactly the URLs in one manifest so
 * mapping, meta, and PDFs cannot be mixed across revisions. Stable aliases are
 * only used together when no manifest exists (the legacy boot fallback).
 */
import type { PDFDocumentProxy } from "pdfjs-dist";
import { type MappingBundle, type PageSize, parseMappingBundle } from "./mapping.js";

export type ViewerMeta = {
  sourcePageCount: number;
  targetPageCount: number;
  sourcePages: { widthPt: number; heightPt: number }[];
  targetPages: { widthPt: number; heightPt: number }[];
};

export type ViewerManifest = {
  revision: string;
  mapping: string;
  meta: string;
  source: string;
  target: string;
};

export const FALLBACK_MANIFEST: ViewerManifest = {
  revision: "stable",
  mapping: "/data/mapping.json",
  meta: "/data/viewer-meta.json",
  source: "/data/source.pdf",
  target: "/data/target.pdf",
};

export function pageSizesFrom(meta: ViewerMeta): { source: PageSize[]; target: PageSize[] } {
  const toSize = (pages: { widthPt: number; heightPt: number }[]): PageSize[] =>
    pages.map((page) => ({ width: page.widthPt, height: page.heightPt }));
  return { source: toSize(meta.sourcePages), target: toSize(meta.targetPages) };
}

export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("html")) {
    throw new Error(`${url}: expected JSON, got ${contentType}`);
  }
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`${url}: expected JSON, got ${contentType || "unknown"}`);
  }
}

function isManifest(value: unknown): value is ViewerManifest {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.revision === "string" &&
    record.revision.length > 0 &&
    typeof record.mapping === "string" &&
    typeof record.meta === "string" &&
    typeof record.source === "string" &&
    typeof record.target === "string"
  );
}

export async function fetchViewerManifest(options?: {
  cacheBust?: string;
  fallback?: boolean;
}): Promise<ViewerManifest> {
  const cacheBust = options?.cacheBust;
  const url = cacheBust ? `/data/manifest.json?${cacheBust}` : "/data/manifest.json";
  try {
    const payload: unknown = await fetchJson(url);
    if (!isManifest(payload)) throw new Error("invalid viewer manifest");
    return payload;
  } catch (error) {
    if (options?.fallback) return FALLBACK_MANIFEST;
    throw error;
  }
}

export type LoadedViewerAssets = {
  revision: string;
  mappings: MappingBundle;
  meta: ViewerMeta;
  source?: PDFDocumentProxy | undefined;
  target: PDFDocumentProxy;
};

export type PdfLoader = (url: string) => Promise<PDFDocumentProxy>;

function withRevision(url: string, revision: string): string {
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}r=${encodeURIComponent(revision)}`;
}

async function loadPdfOrThrow(loadPdf: PdfLoader, url: string): Promise<PDFDocumentProxy> {
  const probe = await fetch(url, { method: "HEAD" }).catch(() => undefined);
  if (probe && probe.status !== 405 && probe.status !== 501) {
    if (!probe.ok) throw new Error(`${url}: ${probe.status}`);
    const contentType = probe.headers.get("content-type") ?? "";
    if (contentType.includes("html")) {
      throw new Error(`${url}: expected PDF, got ${contentType}`);
    }
  }
  return loadPdf(url);
}

export async function loadViewerAssets(
  loadPdf: PdfLoader,
  manifest: ViewerManifest,
  options?: { includeSource?: boolean },
): Promise<LoadedViewerAssets> {
  const revision = manifest.revision;
  const includeSource = options?.includeSource ?? true;
  const mappings = parseMappingBundle(
    await fetchJson<unknown>(withRevision(manifest.mapping, revision)),
  );
  const meta = await fetchJson<ViewerMeta>(withRevision(manifest.meta, revision));
  if (!Array.isArray(meta.sourcePages) || !Array.isArray(meta.targetPages)) {
    throw new Error("invalid viewer meta");
  }
  const target = await loadPdfOrThrow(loadPdf, withRevision(manifest.target, revision));
  let source: PDFDocumentProxy | undefined;
  if (includeSource) {
    try {
      source = await loadPdfOrThrow(loadPdf, withRevision(manifest.source, revision));
    } catch (error) {
      await target.loadingTask.destroy();
      throw error;
    }
  }
  return { revision, mappings, meta, source, target };
}
