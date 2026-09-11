import { expect, test } from "@playwright/test";

/**
 * M6 6.6 translation interaction: re-translate a node through the reader API.
 * The dummy provider is byte-deterministic, so these specs lock the protocol,
 * the status line, and the interface settling back — not text changes (those
 * require a real provider and are covered by M5 structure tests).
 */
test.describe.configure({ mode: "serial" });

test("re-translate button posts to the API and the reader settles back", async ({ page }) => {
  test.setTimeout(120_000); // full lualatex recompile per click
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();

  // Pick a translatable paragraph region and open the inspector on it.
  const mappings = await page.request.get("/data/mapping.json").then((r) => r.json());
  const entries = new Set(
    mappings.translation.entries.map((e: { semanticNodeId: string }) => e.semanticNodeId),
  );
  const bound = new Set<string>(
    mappings.sourceSemanticBindings.map((b: { semanticNodeId: string }) => b.semanticNodeId),
  );
  const anchored = new Set<string>(
    mappings.renderAnchors.map((a: { semanticNodeId: string }) => a.semanticNodeId),
  );
  const nodeId: string = mappings.semanticNodes
    .filter(
      (n: { id: string; kind: string }) =>
        n.kind === "PARAGRAPH" && bound.has(n.id) && anchored.has(n.id) && entries.has(n.id),
    )
    .map((n: { id: string }) => n.id)[0];
  expect(nodeId).toBeTruthy();

  let button = page.locator(`#source-overlay [data-node-id="${nodeId}"]`);
  if ((await button.count()) === 0) {
    await page.click("#source-next");
    await expect(page.locator("#source-page")).toContainText(/^2 /);
    button = page.locator(`#source-overlay [data-node-id="${nodeId}"]`);
  }
  await button.first().click();
  await expect(page.locator("#retranslate-button")).toBeVisible();

  await page.click("#retranslate-button");
  await expect(page.locator("#viewer-status")).toContainText("Node re-translated", {
    timeout: 110_000,
  });
  await expect(page.locator("#inspector-node-id")).toHaveText(nodeId);
  await expect(page.locator("#source-canvas")).toBeVisible();
  await expect(page.locator("#target-canvas")).toBeVisible();

  // A second click stays healthy (idempotent under the deterministic dummy).
  await page.click("#retranslate-button");
  await expect(page.locator("#viewer-status")).toContainText("Node re-translated", {
    timeout: 110_000,
  });
});

test("the API rejects unknown nodes with a structured 400", async ({ request }) => {
  const response = await request.post("/api/retranslate", {
    data: { nodeIds: ["00000000-0000-0000-0000-000000000000"] },
  });
  expect(response.status()).toBe(400);
  const body = await response.json();
  expect(body.ok).toBe(false);
  expect(String(body.error)).toContain("not re-translatable nodes");
});
