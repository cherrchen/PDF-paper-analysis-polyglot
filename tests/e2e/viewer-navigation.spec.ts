import { expect, test } from "@playwright/test";

/**
 * M6: bidirectional navigation on the paper-anatomy fixture. The mapping data
 * must yield pairs for HEADING, PARAGRAPH, and FIGURE_CAPTION nodes, expose
 * real multi-fragment render anchors, and cover the navigation kinds; clicking
 * a source region jumps to the target region and vice versa.
 */
const NAVIGATION_KINDS = [
  "HEADING",
  "PARAGRAPH",
  "FIGURE_CAPTION",
  "TABLE",
  "EQUATION",
  "FOOTNOTE",
  "BIBLIOGRAPHY_ENTRY",
];

test("mapping data covers heading, paragraph, and caption pairs", async ({ request }) => {
  const mappings = await request.get("/data/mapping.json").then((r) => r.json());
  const meta = await request.get("/data/viewer-meta.json").then((r) => r.json());

  expect(mappings.sourceSemanticBindings.length).toBeGreaterThan(0);
  expect(mappings.viewerDataVersion).toBe(2);
  expect(mappings.sourceRegions.length).toBeGreaterThan(0);
  expect(mappings.renderAnchors.length).toBeGreaterThan(0);
  expect(meta.sourcePageCount).toBeGreaterThan(0);
  expect(meta.targetPageCount).toBeGreaterThan(0);

  // v2 contract: reader data plane is emitted in full.
  for (const key of ["semanticRelations", "translation", "provenance", "issues"] as const) {
    expect(mappings).toHaveProperty(key);
  }
  expect(mappings.translation.entries.length).toBeGreaterThan(0);
  expect(Array.isArray(mappings.semanticNodes[0]?.content)).toBe(false);
  expect(mappings.semanticNodes[0]).toHaveProperty("confidence");

  // paper-anatomy fixture: two source pages, per-page geometry arrays.
  expect(meta.sourcePageCount).toBeGreaterThanOrEqual(2);
  expect(meta.sourcePages.length).toBe(meta.sourcePageCount);
  expect(meta.targetPages.length).toBe(meta.targetPageCount);

  // 6.4 data ground: at least one cross-page/multi-fragment render anchor.
  const multiFragment = mappings.renderAnchors.filter(
    (a: { fragments: unknown[] }) => a.fragments.length > 1,
  );
  expect(multiFragment.length).toBeGreaterThan(0);

  // Reflow evidence: for a multi-fragment anchor the source and target page
  // distributions differ (no page-number correspondence assumption).
  const boundNodes = new Map<string, { sourceAnchorIds: string[] }>(
    mappings.sourceSemanticBindings.map((b: { semanticNodeId: string }) => [b.semanticNodeId, b]),
  );
  const anchorById = new Map(mappings.sourceAnchors.map((a: { id: string }) => [a.id, a]));
  const regionByPage = new Map<string, number>(
    mappings.sourceRegions.map((r: { id: string; pageIndex: number }) => [r.id, r.pageIndex]),
  );
  for (const anchor of multiFragment) {
    const binding = boundNodes.get(anchor.semanticNodeId);
    expect(binding).toBeDefined();
    const sourcePages = new Set<number>();
    for (const id of binding?.sourceAnchorIds ?? []) {
      for (const fragment of anchorById.get(id)?.fragments ?? []) {
        sourcePages.add(regionByPage.get(fragment.layoutRegionId) as number);
      }
    }
    const targetPages = new Set(anchor.fragments.map((f: { pageIndex: number }) => f.pageIndex));
    const differs =
      sourcePages.size !== targetPages.size ||
      [...sourcePages].some((p) => !targetPages.has(p)) ||
      [...targetPages].some((p) => !sourcePages.has(p));
    expect(
      differs,
      `node ${anchor.semanticNodeId.slice(0, 8)}: src ${[...sourcePages]} vs tgt ${[...targetPages]}`,
    ).toBe(true);
  }

  // Every render anchor points at a node bound on the source side too.
  const anchoredNodes = new Set(
    mappings.renderAnchors.map((a: { semanticNodeId: string }) => a.semanticNodeId),
  );
  const intersection = [...anchoredNodes].filter((id) => boundNodes.has(id));
  expect(intersection.length).toBeGreaterThan(0);

  // Navigation coverage metric (Exit Gate DoD): paired (source binding AND
  // render anchor) nodes among the expected kinds >= 80%.
  const kindById = new Map<string, string>(
    mappings.semanticNodes.map((n: { id: string; kind: string }) => [n.id, n.kind]),
  );
  const expected = [...kindById].filter(([, kind]) => NAVIGATION_KINDS.includes(kind));
  const paired = expected.filter(([id]) => boundNodes.has(id) && anchoredNodes.has(id));
  const coverage = expected.length > 0 ? paired.length / expected.length : 0;
  expect(
    coverage,
    `navigation coverage ${paired.length}/${expected.length} = ${coverage.toFixed(2)}`,
  ).toBeGreaterThanOrEqual(0.8);

  const sourceRegionIds = new Set(
    mappings.sourceRegions.map((region: { id: string }) => region.id),
  );
  for (const anchor of mappings.sourceAnchors as {
    fragments: { layoutRegionId: string }[];
  }[]) {
    for (const fragment of anchor.fragments) {
      expect(sourceRegionIds.has(fragment.layoutRegionId)).toBe(true);
    }
  }
});

test("viewer loads both PDF panes with navigation data", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#status")).toContainText("workspace is running");
  await expect(page.locator("#viewer")).toBeVisible();
  await expect(page.locator("#viewer-status")).toContainText("Bidirectional navigation ready");
  await expect(page.locator("#source-canvas")).toBeVisible();
  await expect(page.locator("#target-canvas")).toBeVisible();
  await expect(page.locator("#source-page")).toContainText("1 /");
  await expect(page.locator("#target-page")).toContainText("1 /");
});

test("clicking a mapped region navigates and highlights both directions", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();

  const sourceRegion = page.locator("#source-overlay [data-node-id]").first();
  await expect(sourceRegion).toBeVisible();
  const nodeId = await sourceRegion.getAttribute("data-node-id");
  expect(nodeId).not.toBeNull();
  await sourceRegion.click();

  const targetRegion = page.locator(`#target-overlay [data-node-id="${nodeId}"]`);
  await expect(targetRegion).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#viewer-status")).toContainText("Linked region selected");

  await targetRegion.click();
  await expect(page.locator(`#source-overlay [data-node-id="${nodeId}"]`)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
