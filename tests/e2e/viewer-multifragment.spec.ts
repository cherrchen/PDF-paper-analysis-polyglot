import { expect, type Page, test } from "@playwright/test";

/**
 * M6 6.4 multi-fragment highlight + 6.3 scroll sync. A node whose render
 * anchor reflows across pages must highlight every fragment on the visited
 * page, and sync scroll must pick the counterpart from spatial band data
 * only — never from a source≈target page-number assumption.
 */
type Fragment = { pageIndex: number };
type RenderAnchor = { semanticNodeId: string; fragments: Fragment[] };
type Mappings = {
  renderAnchors: RenderAnchor[];
  sourceSemanticBindings: { semanticNodeId: string }[];
};

async function mappingsOf(page: Page): Promise<Mappings> {
  return page.request.get("/data/mapping.json").then((r) => r.json());
}

async function multiFragmentNodeId(page: Page): Promise<string> {
  const mappings = await mappingsOf(page);
  const bound = new Set(mappings.sourceSemanticBindings.map((b) => b.semanticNodeId));
  const anchor = mappings.renderAnchors.find(
    (a) => a.fragments.length >= 2 && bound.has(a.semanticNodeId),
  );
  expect(anchor, "fixture must contain a bound multi-fragment render anchor").toBeDefined();
  return anchor?.semanticNodeId as string;
}

async function pressedCount(page: Page, nodeId: string): Promise<number> {
  return page.evaluate(
    ([id]) =>
      document.querySelectorAll(
        `#target-overlay [data-node-id="${CSS.escape(id)}"][aria-pressed="true"]`,
      ).length,
    [nodeId],
  );
}

test("a multi-fragment node highlights every fragment of the visited page", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  const nodeId = await multiFragmentNodeId(page);
  const sourceButton = page.locator(`#source-overlay [data-node-id="${nodeId}"]`).first();
  if (!(await sourceButton.isVisible().catch(() => false))) {
    await page.click("#source-next");
    await expect(page.locator("#source-page")).toContainText(/^2 /);
  }
  await page.locator(`#source-overlay [data-node-id="${nodeId}"]`).first().click();
  await expect(page.locator("#viewer-status")).toContainText("Linked region selected");

  const mappings = await mappingsOf(page);
  const anchor = mappings.renderAnchors.find((a) => a.semanticNodeId === nodeId) as RenderAnchor;
  const targetPages = new Set(anchor.fragments.map((f) => f.pageIndex));
  expect(targetPages.size).toBeGreaterThanOrEqual(2);

  // Destination pane landed on the counterpart page; pressed count equals the
  // node's fragment count on that page (all fragments, not just the first).
  const landedPage = Number((await page.locator("#target-page").textContent())?.split(" / ")[0]);
  const onLanded = anchor.fragments.filter((f) => f.pageIndex === landedPage - 1).length;
  expect(onLanded).toBeGreaterThanOrEqual(1);
  expect(await pressedCount(page, nodeId)).toBe(onLanded);

  // Turn to the anchor's other page: active highlight survives the turn.
  const otherPage = [...targetPages].find((p) => p + 1 !== landedPage) as number;
  if (otherPage + 1 > landedPage) {
    await page.click("#target-next");
  } else {
    await page.click("#target-previous");
  }
  await expect
    .poll(() => pressedCount(page, nodeId), { timeout: 5000 })
    .toBe(anchor.fragments.filter((f) => f.pageIndex === otherPage).length);
});

test("sync scroll activates a node from the source band, not a page guess", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  await page.check("#sync-scroll");

  await page.click("#source-next");
  await expect(page.locator("#source-page")).toContainText("2 /");

  // Scroll so a page-2 fragment sits at the pane midline, then report which
  // fragment ids cover the band (±18 px ≈ ±12 pt at SCALE 1.5) — the same
  // candidates `syncFrom` sees. Poll because the overlay renders async.
  let band: string[] | null = null;
  await expect
    .poll(
      async () => {
        band = await page.evaluate(() => {
          const scroll = document.querySelector("#source-pane .page-scroll") as HTMLElement;
          const relTop = (b: HTMLElement) =>
            b.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop;
          const buttons = [
            ...document.querySelectorAll('#source-overlay [data-node-id][data-page-index="1"]'),
          ] as HTMLButtonElement[];
          const tall = buttons.filter((b) => b.offsetHeight > 4);
          if (tall.length === 0) return null;
          const anchor = tall[Math.floor(tall.length / 2)];
          scroll.scrollTop = relTop(anchor) + anchor.offsetHeight / 2 - scroll.clientHeight / 2;
          const center = scroll.scrollTop + scroll.clientHeight / 2;
          const inBand = buttons
            .map((b) => {
              const top = relTop(b);
              return { id: b.dataset.nodeId as string, top, bottom: top + b.offsetHeight };
            })
            .filter((c) => c.top <= center + 18 && c.bottom >= center - 18);
          if (inBand.length === 0) return null;
          const minTop = Math.min(...inBand.map((c) => c.top));
          return [...new Set(inBand.filter((c) => c.top === minTop).map((c) => c.id))];
        });
        return band;
      },
      { timeout: 10_000, message: "page 2 must carry mapped fragments" },
    )
    .not.toBeNull();
  if (!band) return;

  // The target pane must press one of exactly those band nodes.
  await expect
    .poll(
      () =>
        page.evaluate(
          ([ids]) =>
            [...document.querySelectorAll('#target-overlay [aria-pressed="true"]')].filter((b) =>
              ids.includes((b as HTMLButtonElement).dataset.nodeId as string),
            ).length,
          [band],
        ),
      { timeout: 5000, message: `target pane should press a band node of ${band.join(",")}` },
    )
    .toBeGreaterThanOrEqual(1);
});
