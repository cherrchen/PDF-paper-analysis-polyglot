import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Demo console surfaces: upload / select / history / status as tabs over the
 * reader, with every information panel in a floating right drawer that never
 * narrows the PDFs.
 *
 * Runs on the real three-process stack (API :8000 + worker + vite :4173). The
 * spec seeds its own terminal job, because a clean checkout has no job history
 * and this file sorts before `product-import.spec.ts`; a non-PDF source fails
 * before any stage, so seeding costs no lualatex run.
 */

type JobRecord = { id: string; status: string; workspace: string };

const SURFACES = ["upload", "select", "history", "status"] as const;

test("console surfaces switch, report the stack, and open a workspace", async ({ page }) => {
  test.setTimeout(120_000);
  const scratch = mkdtempSync(path.join(tmpdir(), "paper-e2e-console-"));
  try {
    const source = path.join(scratch, "not-a-pdf.txt");
    writeFileSync(source, "this is not a PDF\n");
    const submitted = await page.request.post("/api/jobs", {
      data: { source, workspace: path.join(scratch, "ws") },
    });
    expect(submitted.status()).toBe(202);
    const submittedBody = (await submitted.json()) as { job: JobRecord };
    const seeded = submittedBody.job;
    await expect
      .poll(
        async () => {
          const payload = (await page.request
            .get(`/api/jobs/${seeded.id}`)
            .then((r) => r.json())) as { job: JobRecord };
          return payload.job.status;
        },
        { timeout: 90_000, intervals: [500] },
      )
      .toBe("failed");

    await page.goto("/");
    await expect(page.locator("#viewer")).toBeVisible();

    for (const id of SURFACES) {
      await expect(page.locator(`#panel-${id}`)).toBeHidden();
    }

    // The masthead's green primary action opens the upload surface.
    await page.click("#open-upload");
    await expect(page.locator("#panel-upload")).toBeVisible();
    await expect(page.locator("#tab-upload")).toHaveAttribute("aria-selected", "true");
    await page.click("#tab-upload");
    await expect(page.locator("#panel-upload")).toBeHidden();

    await page.click("#tab-status");
    await expect(page.locator("#panel-status")).toBeVisible();
    await expect(page.locator("#status-api")).toContainText("API ok");
    await expect(page.locator("#status-worker")).toContainText("Worker running");
    await expect(page.locator("#status-jobs")).toContainText("Queued");

    await page.click("#tab-history");
    await expect(page.locator("#panel-history")).toBeVisible();
    const row = page.locator(`#history-list li[data-job-id="${seeded.id}"]`);
    await expect(row).toBeVisible();
    await expect(row.locator(".history-retry")).toBeVisible();

    await page.click("#tab-select");
    await expect(page.locator("#panel-select")).toBeVisible();
    const current = page.locator('#select-list li[data-current="true"]');
    await expect(current).toHaveCount(1);
    const revisionBefore = await page.locator("#viewer").getAttribute("data-revision");
    expect(revisionBefore).toBeTruthy();

    await current.locator(".select-open").click();
    await expect(page.locator("#select-status")).toContainText("Opened ·");
    await expect(page.locator("#viewer")).not.toHaveAttribute(
      "data-revision",
      revisionBefore ?? "",
      { timeout: 60_000 },
    );
    await expect(page.locator("#viewer-status")).toContainText("Bidirectional navigation ready");

    // The active tab closes the drawer on a second click.
    await page.click("#tab-select");
    await expect(page.locator("#panel-select")).toBeHidden();
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
