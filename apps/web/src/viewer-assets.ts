/**
 * Viewer asset loading: manifest-addressed revisions of mapping/meta/PDFs.
 *
 * `_write_viewer_assets` publishes a complete `revisions/<id>/` directory and
 * then flips `manifest.json`. Loading prefers those revision URLs so mapping,
 * meta, and PDFs stay on one revision. Vite's SPA fallback can hide directories
 * created after boot, so a failed revision fetch retries the stable aliases
 * (`/data/mapping.json` and friends) with the same revision cache-buster.
 */
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { MappingBundle, PageSize } from "./mapping.js";

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

type PdfLoader = (url: string) => Promise<PDFDocumentProxy>;

function withRevision(url: string, revision: string): string {
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}r=${encodeURIComponent(revision)}`;
}

function uniqueUrls(urls: string[]): string[] {
  return [...new Set(urls)];
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
  const mappingCandidates = uniqueUrls([
    withRevision(manifest.mapping, revision),
    withRevision(FALLBACK_MANIFEST.mapping, revision),
  ]);
  const metaCandidates = uniqueUrls([
    withRevision(manifest.meta, revision),
    withRevision(FALLBACK_MANIFEST.meta, revision),
  ]);
  const targetCandidates = uniqueUrls([
    withRevision(manifest.target, revision),
    withRevision(FALLBACK_MANIFEST.target, revision),
  ]);
  const sourceCandidates = uniqueUrls([
    withRevision(manifest.source, revision),
    withRevision(FALLBACK_MANIFEST.source, revision),
  ]);
  const mappings = await fetchJsonFirst<MappingBundle>(mappingCandidates);
  const meta = await fetchJsonFirst<ViewerMeta>(metaCandidates);
  const target = await loadPdfFirst(loadPdf, targetCandidates);
  const source = includeSource ? await loadPdfFirst(loadPdf, sourceCandidates) : undefined;
  if (mappings.viewerDataVersion !== 2) {
    throw new Error(`unsupported viewer data version: ${String(mappings.viewerDataVersion)}`);
  }
  if (!Array.isArray(meta.sourcePages) || !Array.isArray(meta.targetPages)) {
    throw new Error("invalid viewer meta");
  }
  return { revision, mappings, meta, source, target };
}

async function fetchJsonFirst<T>(urls: string[]): Promise<T> {
  let lastError: unknown;
  for (const url of urls) {
    try {
      return await fetchJson<T>(url);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("failed to load JSON asset");
}

async function loadPdfFirst(loadPdf: PdfLoader, urls: string[]): Promise<PDFDocumentProxy> {
  let lastError: unknown;
  for (const url of urls) {
    try {
      return await loadPdfOrThrow(loadPdf, url);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("failed to load PDF asset");
}
