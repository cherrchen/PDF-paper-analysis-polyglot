/**
 * M6 (6.1/6.2) frontend spatial index over source/target fragment rectangles.
 *
 * A uniform grid per page (8 × 12 cells) is deliberately not an R-tree: at
 * paper scale the fragment count stays below 10³, cell lookup is O(1), and no
 * third-party dependency is introduced. A dense cell still scans its
 * candidates, so heavily overlapping fragments degrade toward scanning the
 * page set. If a future corpus exceeds ~10⁴ fragments, swap the internals
 * behind this same `PageSpatialIndex` interface.
 */
import type { Rect } from "./mapping.js";

export type IndexedFragment = {
  nodeId: string;
  side: "source" | "target";
  pageIndex: number;
  rect: Rect;
};

/** Grid resolution per page (columns × rows). */
const GRID_COLUMNS = 8;
const GRID_ROWS = 12;

type PageGeometry = { width: number; height: number };

/**
 * Page-space index for one side. `pageSizes` are PDF points, indexed by page;
 * a missing entry falls back to the first known size on the same side.
 */
export class PageSpatialIndex {
  private readonly cells = new Map<number, IndexedFragment[]>();
  private readonly pageSizes: (PageGeometry | undefined)[];
  private readonly fallbackSize: PageGeometry | undefined;

  constructor(fragments: IndexedFragment[], pageSizes: PageGeometry[]) {
    this.pageSizes = pageSizes;
    this.fallbackSize = pageSizes.find((size) => size && size.width > 0 && size.height > 0);
    for (const fragment of fragments) {
      this.insert(fragment);
    }
  }

  private sizeFor(pageIndex: number): PageGeometry | undefined {
    const size = this.pageSizes[pageIndex] ?? this.fallbackSize;
    if (!size || size.width <= 0 || size.height <= 0) return undefined;
    return size;
  }

  private cellKey(pageIndex: number, cell: number): number {
    // Pack page + cell into one number (cell < GRID_COLUMNS * GRID_ROWS).
    return pageIndex * (GRID_COLUMNS * GRID_ROWS) + cell;
  }

  private cellRange(size: PageGeometry, rect: Rect): [number, number, number, number] {
    const cellWidth = size.width / GRID_COLUMNS;
    const cellHeight = size.height / GRID_ROWS;
    const minCol = Math.max(0, Math.min(GRID_COLUMNS - 1, Math.floor(rect.x / cellWidth)));
    const maxCol = Math.max(
      0,
      Math.min(GRID_COLUMNS - 1, Math.floor((rect.x + rect.width) / cellWidth)),
    );
    const minRow = Math.max(0, Math.min(GRID_ROWS - 1, Math.floor(rect.y / cellHeight)));
    const maxRow = Math.max(
      0,
      Math.min(GRID_ROWS - 1, Math.floor((rect.y + rect.height) / cellHeight)),
    );
    return [minCol, maxCol, minRow, maxRow];
  }

  private insert(fragment: IndexedFragment): void {
    const { rect } = fragment;
    if (rect.width <= 0 || rect.height <= 0) return; // degenerate: never hit-testable
    const size = this.sizeFor(fragment.pageIndex);
    if (!size) return;
    const [minCol, maxCol, minRow, maxRow] = this.cellRange(size, rect);
    for (let row = minRow; row <= maxRow; row += 1) {
      for (let col = minCol; col <= maxCol; col += 1) {
        const key = this.cellKey(fragment.pageIndex, row * GRID_COLUMNS + col);
        const bucket = this.cells.get(key);
        if (bucket) bucket.push(fragment);
        else this.cells.set(key, [fragment]);
      }
    }
  }

  private candidates(
    pageIndex: number,
    minCol: number,
    maxCol: number,
    minRow: number,
    maxRow: number,
  ): IndexedFragment[] {
    const seen = new Set<IndexedFragment>();
    for (let row = minRow; row <= maxRow; row += 1) {
      for (let col = minCol; col <= maxCol; col += 1) {
        for (const fragment of this.cells.get(this.cellKey(pageIndex, row * GRID_COLUMNS + col)) ??
          []) {
          seen.add(fragment);
        }
      }
    }
    return [...seen];
  }

  /** Fragments whose rect contains (x, y), ascending by area (smallest first). */
  hitTest(pageIndex: number, x: number, y: number): IndexedFragment[] {
    const size = this.sizeFor(pageIndex);
    if (!size) return [];
    const cellWidth = size.width / GRID_COLUMNS;
    const cellHeight = size.height / GRID_ROWS;
    const col = Math.floor(x / cellWidth);
    const row = Math.floor(y / cellHeight);
    if (col < 0 || col >= GRID_COLUMNS || row < 0 || row >= GRID_ROWS) return [];
    const hits = this.candidates(pageIndex, col, col, row, row).filter(
      ({ rect }) =>
        x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height,
    );
    return hits.sort((a, b) => a.rect.width * a.rect.height - b.rect.width * b.rect.height);
  }

  /** Fragments intersecting the horizontal band [yMin, yMax], ascending by rect.y. */
  inBand(pageIndex: number, yMin: number, yMax: number): IndexedFragment[] {
    const size = this.sizeFor(pageIndex);
    if (!size || yMax < yMin) return [];
    const cellHeight = size.height / GRID_ROWS;
    const minRow = Math.max(0, Math.min(GRID_ROWS - 1, Math.floor(yMin / cellHeight)));
    const maxRow = Math.max(0, Math.min(GRID_ROWS - 1, Math.floor(yMax / cellHeight)));
    const hits = this.candidates(pageIndex, 0, GRID_COLUMNS - 1, minRow, maxRow).filter(
      ({ rect }) => rect.y <= yMax && rect.y + rect.height >= yMin,
    );
    return hits.sort((a, b) => a.rect.y - b.rect.y);
  }
}
