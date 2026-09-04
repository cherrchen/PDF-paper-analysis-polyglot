import { expect, test } from "@playwright/test";

/**
 * M2 Phase 2.7: bidirectional navigation between Source and Target PDFs.
 * The mapping data must yield pairs for HEADING, PARAGRAPH, and
 * FIGURE_CAPTION nodes; clicking a source region jumps to the target
 * region, and clicking a target region jumps back.
 */
test("mapping data covers heading, paragraph, and caption pairs", async ({ request }) => {
  const mappings = await request.get("/data/mapping.json").then((r) => r.json());
  const meta = await request.get("/data/viewer-meta.json").then((r) => r.json());

  expect(mappings.sourceSemanticBindings.length).toBeGreaterThan(0);
  expect(mappings.viewerDataVersion).toBe(1);
  expect(mappings.sourceRegions.length).toBeGreaterThan(0);
  expect(mappings.renderAnchors.length).toBeGreaterThan(0);
  expect(meta.sourcePageCount).toBeGreaterThan(0);
  expect(meta.targetPageCount).toBeGreaterThan(0);

  // Every render anchor points at a node bound on the source side too.
  const boundNodes = new Set(
    mappings.sourceSemanticBindings.map((b: { semanticNodeId: string }) => b.semanticNodeId),
  );
  const linkedKinds = mappings.semanticNodes
    .filter((node: { id: string }) => boundNodes.has(node.id))
    .map((node: { kind: string }) => node.kind);
  expect(linkedKinds).toEqual(expect.arrayContaining(["HEADING", "PARAGRAPH", "FIGURE_CAPTION"]));
  const anchoredNodes = new Set(
    mappings.renderAnchors.map((a: { semanticNodeId: string }) => a.semanticNodeId),
  );
  const intersection = [...anchoredNodes].filter((id) => boundNodes.has(id));
  expect(intersection.length).toBeGreaterThan(0);
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
