import { expect, type Page, test } from "@playwright/test";

/**
 * M6 6.5 Semantic Inspector: selecting a region surfaces the node identity,
 * anchors, original text, translation (or the explicit "Not translatable"
 * for kinds the PRD excludes from translation), relations, confidence, and
 * provenance. Assertions avoid dummy-provider marker strings so they hold
 * against a real provider too.
 */
type Mappings = {
  semanticNodes: { id: string; kind: string }[];
  sourceSemanticBindings: { semanticNodeId: string; sourceAnchorIds: string[] }[];
  sourceAnchors: { id: string; fragments: { layoutRegionId: string }[] }[];
  sourceRegions: { id: string; pageIndex: number }[];
  renderAnchors: { semanticNodeId: string }[];
  translation: { entries: { semanticNodeId: string }[] };
};

async function mappingsOf(page: Page): Promise<Mappings> {
  return page.request.get("/data/mapping.json").then((r) => r.json());
}

/** Click a node's source region, turning pages (awaited via the page label,
 * which renderPage updates only after the overlay is redrawn). */
async function clickSourceRegion(page: Page, nodeId: string): Promise<void> {
  const mappings = await mappingsOf(page);
  const binding = mappings.sourceSemanticBindings.find((b) => b.semanticNodeId === nodeId);
  const anchorIds = new Set(binding?.sourceAnchorIds ?? []);
  const regionIds = new Set(
    mappings.sourceAnchors
      .filter((a) => anchorIds.has(a.id))
      .flatMap((a) => a.fragments.map((f) => f.layoutRegionId)),
  );
  const pages = mappings.sourceRegions.filter((r) => regionIds.has(r.id)).map((r) => r.pageIndex);
  const wanted = Math.min(...pages);
  for (let guard = 0; guard <= pages.length + 2; guard += 1) {
    const shown = Number((await page.locator("#source-page").textContent())?.split(" / ")[0]) - 1;
    if (shown === wanted) break;
    await page.click(shown < wanted ? "#source-next" : "#source-previous");
    await expect(page.locator("#source-page")).toContainText(`${wanted + 1} /`, {
      timeout: 10_000,
    });
  }
  await page.locator(`#source-overlay [data-node-id="${nodeId}"]`).first().click();
  await expect(page.locator("#viewer-status")).toContainText("Linked region selected");
}

async function pairedNodesOfKind(page: Page, kind: string): Promise<string[]> {
  const mappings = await mappingsOf(page);
  const bound = new Set(mappings.sourceSemanticBindings.map((b) => b.semanticNodeId));
  const anchored = new Set(mappings.renderAnchors.map((a) => a.semanticNodeId));
  return mappings.semanticNodes
    .filter((n) => n.kind === kind && bound.has(n.id) && anchored.has(n.id))
    .map((n) => n.id);
}

test("inspector shows identity, anchors, text, and translation for a paragraph", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  const paragraphs = await pairedNodesOfKind(page, "PARAGRAPH");
  expect(paragraphs.length).toBeGreaterThan(0);
  const nodeId = paragraphs[0] as string;

  await clickSourceRegion(page, nodeId);

  await expect(page.locator("#inspector")).toBeVisible();
  await expect(page.locator("#inspector-node-id")).toHaveText(nodeId);
  await expect(page.locator("#inspector-kind")).toContainText("PARAGRAPH");

  const anchors = page.locator("#inspector-anchors li");
  expect(await anchors.count()).toBeGreaterThanOrEqual(2);
  const first = await anchors.first().textContent();
  expect(first).toMatch(/^source p\d+ \[\d+,\d+ \d+×\d+\]$/);

  await expect
    .poll(() =>
      page.locator("#inspector-source-text").evaluate((el) => el.textContent?.length ?? 0),
    )
    .toBeGreaterThan(10);
  await expect
    .poll(() =>
      page.locator("#inspector-translation").evaluate((el) => el.textContent?.length ?? 0),
    )
    .toBeGreaterThan(3);
  await expect(page.locator("#inspector-translation")).not.toHaveText("Not translatable");

  await expect(page.locator("#inspector-confidence")).toContainText("%");
  expect(await page.locator("#inspector-provenance li").count()).toBeGreaterThan(0);
  // Terminology panel exists; with no glossary file it degrades honestly.
  await expect(page.locator("#inspector-terminology li").first()).toBeVisible();
});

test("untranslated node kinds surface Not translatable", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  const mappings = await mappingsOf(page);
  const entries = new Set(mappings.translation.entries.map((e) => e.semanticNodeId));
  const bib = await pairedNodesOfKind(page, "BIBLIOGRAPHY_ENTRY");
  expect(bib.length, "fixture must contain a paired bibliography entry").toBeGreaterThan(0);
  const nodeId = bib.find((id) => !entries.has(id)) ?? (bib[0] as string);

  await clickSourceRegion(page, nodeId);

  await expect(page.locator("#inspector-kind")).toContainText("BIBLIOGRAPHY_ENTRY");
  await expect(page.locator("#inspector-translation")).toHaveText("Not translatable");
  await expect(page.locator("#retranslate-button")).toHaveCount(0);
});

test("caption relations are inspectable and jumpable", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  const captions = await pairedNodesOfKind(page, "FIGURE_CAPTION");
  expect(captions.length).toBeGreaterThan(0);

  await clickSourceRegion(page, captions[0] as string);
  const relations = page.locator("#inspector-relations button");
  expect(await relations.count()).toBeGreaterThanOrEqual(1);
  const label = await relations.first().textContent();
  expect(label).toMatch(/CAPTION_OF|REFERENCES|FOOTNOTE_OF/);

  // Jumping via a relation to a node that is itself paired re-selects it.
  const mappings = await mappingsOf(page);
  const bound = new Set(mappings.sourceSemanticBindings.map((b) => b.semanticNodeId));
  const anchored = new Set(mappings.renderAnchors.map((a) => a.semanticNodeId));
  const jumpable = await relations.evaluateAll((buttons) =>
    buttons.map((b) => (b as HTMLButtonElement).dataset.nodeId as string),
  );
  const target = jumpable.find((id) => bound.has(id) && anchored.has(id));
  test.skip(!target, "relation counterpart is not itself paired in this fixture");
  if (!target) return;
  await page.click(`#inspector-relations button[data-node-id="${target}"]`);
  await expect(page.locator("#inspector-node-id")).toHaveText(target);
});

test("inspector toggle hides and restores the panel without losing selection", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#viewer")).toBeVisible();
  await page.click("#source-overlay [data-node-id]");
  await expect(page.locator("#inspector")).toBeVisible();
  const selectedId = await page.locator("#inspector-node-id").textContent();

  await page.click("#inspector-toggle");
  await expect(page.locator("#inspector")).toBeHidden();
  // Selection persists: the source region stays pressed.
  await expect(
    page.locator(`#source-overlay [data-node-id="${selectedId}"][aria-pressed="true"]`).first(),
  ).toBeVisible();

  await page.click("#inspector-toggle");
  await expect(page.locator("#inspector")).toBeVisible();
  await expect(page.locator("#inspector-node-id")).toHaveText(selectedId as string);
});
