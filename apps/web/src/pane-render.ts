/**
 * Serialize PDF.js renders onto one canvas.
 *
 * PDF.js throws if two RenderTasks target the same canvas. Rapid paging,
 * overlay clicks, and sync-scroll can all request a render independently;
 * only the latest request may commit page metrics and overlay state.
 */
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

export type Cancelable<T> = {
  cancel: () => void;
  promise: Promise<T>;
};

export type RenderCommit = {
  pageIndex: number;
  widthPt: number;
  heightPt: number;
  canvasHeight: number;
};

export function isRenderCancelled(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name: string }).name === "RenderingCancelledException"
  );
}

function cancelledError(): Error {
  return Object.assign(new Error("cancelled"), { name: "RenderingCancelledException" });
}

/**
 * One-at-a-time render slot. `run` cancels the previous task, waits for it to
 * finish, then starts `work`. A superseded run resolves to `undefined` instead
 * of committing.
 */
export class ExclusiveRenderer<T> {
  private generation = 0;
  private task: Cancelable<unknown> | null = null;

  get currentGeneration(): number {
    return this.generation;
  }

  isCurrent(token: number): boolean {
    return token === this.generation;
  }

  invalidate(): void {
    this.generation += 1;
    this.task?.cancel();
  }

  async run(work: (token: number) => Cancelable<T>): Promise<T | undefined> {
    const token = this.generation + 1;
    this.generation = token;
    const previous = this.task;
    this.task = null;
    if (previous) {
      previous.cancel();
      try {
        await previous.promise;
      } catch {
        // Stale work was cancelled or failed; the latest request still proceeds.
      }
    }
    if (!this.isCurrent(token)) return undefined;
    const task = work(token);
    this.task = task;
    try {
      const result = await task.promise;
      if (!this.isCurrent(token)) return undefined;
      return result;
    } catch (error) {
      if (isRenderCancelled(error) || !this.isCurrent(token)) return undefined;
      throw error;
    } finally {
      if (this.task === task) this.task = null;
    }
  }
}

export const PDF_RENDER_SCALE = 1.5;

export class PaneRenderer {
  private readonly exclusive = new ExclusiveRenderer<RenderCommit>();

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly getPdf: () => PDFDocumentProxy | undefined,
    private readonly getPageCount: () => number,
    private readonly scale = PDF_RENDER_SCALE,
  ) {}

  invalidate(): void {
    this.exclusive.invalidate();
  }

  async render(pageIndex: number): Promise<RenderCommit | undefined> {
    return this.exclusive.run((token) => {
      let cancelled = false;
      let pdfTask: RenderTask | null = null;
      const promise = (async (): Promise<RenderCommit> => {
        const pdf = this.getPdf();
        if (!pdf) throw new Error("pdf document unavailable");
        const bounded = Math.max(0, Math.min(pageIndex, Math.max(0, this.getPageCount() - 1)));
        const page = await pdf.getPage(bounded + 1);
        if (cancelled || !this.exclusive.isCurrent(token)) throw cancelledError();
        const viewport = page.getViewport({ scale: this.scale });
        this.canvas.width = viewport.width;
        this.canvas.height = viewport.height;
        const context = this.canvas.getContext("2d");
        if (!context) throw new Error("2d canvas context unavailable");
        const task = page.render({ canvas: this.canvas, canvasContext: context, viewport });
        pdfTask = task;
        if (cancelled) {
          task.cancel();
          throw cancelledError();
        }
        try {
          await task.promise;
        } catch (error) {
          if (isRenderCancelled(error) || cancelled || !this.exclusive.isCurrent(token)) {
            throw cancelledError();
          }
          throw error;
        }
        if (cancelled || !this.exclusive.isCurrent(token)) throw cancelledError();
        return {
          pageIndex: bounded,
          widthPt: viewport.width / this.scale,
          heightPt: viewport.height / this.scale,
          canvasHeight: viewport.height,
        };
      })();
      return {
        cancel: () => {
          cancelled = true;
          pdfTask?.cancel();
        },
        promise,
      };
    });
  }
}
