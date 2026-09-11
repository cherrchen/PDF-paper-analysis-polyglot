import { describe, expect, it } from "vitest";
import { ExclusiveRenderer, isRenderCancelled } from "./pane-render.js";
import { codePointLength, codePointSliceOrOutOfRange, sliceByCodePoint } from "./unicode.js";
import { pageSizesFrom } from "./viewer-assets.js";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

describe("code-point offsets", () => {
  it("slices mathematical letters the way Python str offsets do", () => {
    const text = "𝛼 [1]";
    expect(codePointLength(text)).toBe(5);
    expect(text.length).toBe(6);
    expect(sliceByCodePoint(text, 2, 5)).toBe("[1]");
    expect(text.slice(2, 5)).toBe(" [1");
    expect(codePointSliceOrOutOfRange(text, 2, 5)).toBe("[1]");
  });

  it("slices supplementary CJK before and after a citation", () => {
    const text = "见𰻞[1]后";
    expect(codePointLength(text)).toBe(6);
    expect(sliceByCodePoint(text, 2, 5)).toBe("[1]");
    expect(codePointSliceOrOutOfRange(text, 0, 2)).toBe("见𰻞");
    expect(codePointSliceOrOutOfRange(text, 5, 6)).toBe("后");
    expect(codePointSliceOrOutOfRange(text, 0, 99)).toBe("mark out of range");
  });
});

describe("ExclusiveRenderer", () => {
  it("commits only the latest overlapping run", async () => {
    const renderer = new ExclusiveRenderer<number>();
    const started: number[] = [];
    const cancelled: number[] = [];
    const run = (value: number, ms: number) =>
      renderer.run((_token) => {
        let stop = false;
        started.push(value);
        return {
          cancel: () => {
            stop = true;
            cancelled.push(value);
          },
          promise: delay(ms).then(() => {
            if (stop) {
              throw Object.assign(new Error("cancelled"), {
                name: "RenderingCancelledException",
              });
            }
            return value;
          }),
        };
      });
    const first = run(1, 40);
    const second = run(2, 10);
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBe(2);
    expect(cancelled).toContain(1);
    expect(started).toEqual([1, 2]);
  });

  it("recognizes PDF.js cancellation errors", () => {
    expect(isRenderCancelled({ name: "RenderingCancelledException" })).toBe(true);
    expect(isRenderCancelled(new Error("boom"))).toBe(false);
  });
});

describe("viewer meta helpers", () => {
  it("projects per-page sizes", () => {
    expect(
      pageSizesFrom({
        sourcePageCount: 1,
        targetPageCount: 1,
        sourcePages: [{ widthPt: 612, heightPt: 792 }],
        targetPages: [{ widthPt: 400, heightPt: 500 }],
      }),
    ).toEqual({
      source: [{ width: 612, height: 792 }],
      target: [{ width: 400, height: 500 }],
    });
  });
});
