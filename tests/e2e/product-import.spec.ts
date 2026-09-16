import { cpSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, type Page, test } from "@playwright/test";

/**
 * M8 batch F: PRD §40 product flow end to end — import a PDF through the
 * browser, the queue worker analyzes it, the published revision reloads in
 * the viewer, and bidirectional jumps work on the new document.
 *
 * Runs on the real three-process stack (API :8000 + worker + vite :4173 from
 * the playwright webServer) with the real lualatex pipeline; a different PDF
 * than the anatomy fixture proves a genuinely new document entered the
 * product. The job publishes into the shared apps/web/public/data root, so
 * the spec snapshots that directory and restores it afterwards: the anatomy
 * fixture is what the viewer-* specs assert against.
 */

const DATA_DIR = path.resolve("apps/web/public/data");
const SOURCE_PDF = path.resolve("tests/fixtures/source/latex/build/tikz-vector.pdf");

type JobRecord = {
  id: string;
  status: string;
  workspace: string;
  stage?: string | null;
  error?: string | null;
};

type ViewerMeta = { targetPageCount: number };

type Probe = { nodeId: string; x: number; y: number };

function restoreDataDir(backupRoot: string): void {
  for (const entry of readdirSync(DATA_DIR)) {
    rmSync(path.join(DATA_DIR, entry), { recursive: true, force: true });
  }
  cpSync(backupRoot, DATA_DIR, { recursive: true });
}

/**
 * One hittable point per mapped node in a pane's overlay: a point inside the
 * button whose `document.elementFromPoint` is a mapped-region button (a real
 * pointer landing there activates *some* node — the loop in the test verifies
 * it activates this one; overlap geometry decides). Retries while smooth
 * scrolling settles.
 */
async function regionProbes(page: Page, side: "source" | "target"): Promise<Probe[]> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const probes = await page.evaluate(
      ({ side }) => {
        const byNode = new Map<string, HTMLElement>();
        for (const button of Array.from(
          document.querySelectorAll<HTMLElement>(`#${side}-overlay .mapped-region`),
        )) {
          if (button.dataset.nodeId && !byNode.has(button.dataset.nodeId)) {
            byNode.set(button.dataset.nodeId, button);
          }
        }
        const found: Array<{ nodeId: string; x: number; y: number }> = [];
        for (const [nodeId, button] of byNode) {
          const rect = button.getBoundingClientRect();
          const left = Math.max(rect.x, 0);
          const top = Math.max(rect.y, 0);
          const right = Math.min(rect.right, innerWidth);
          const bottom = Math.min(rect.bottom, innerHeight);
          if (right - left < 8 || bottom - top < 8) continue;
          outer: for (const fy of [0.5, 0.3, 0.7]) {
            for (const fx of [0.5, 0.3, 0.7]) {
              const x = left + (right - left) * fx;
              const y = top + (bottom - top) * fy;
              const hit = document.elementFromPoint(x, y);
              if (hit instanceof HTMLElement && hit.classList.contains("mapped-region")) {
                found.push({ nodeId, x, y });
                break outer;
              }
            }
          }
        }
        return found;
      },
      { side },
    );
    if (probes.length > 0) return probes;
    await page.waitForTimeout(250);
  }
  throw new Error(`no hittable mapped region on ${side}`);
}

async function pressStatus(page: Page): Promise<void> {
  await expect(page.locator("#viewer-status")).toContainText("Linked region selected");
}

/**
 * Round trip (source→target, target→source) on the first node whose overlay
 * geometry survives the click: overlapping mapped regions on this document
 * mean some probes land on a covering button and activate another node.
 */
async function jumpRoundTrip(page: Page): Promise<void> {
  const sources = await regionProbes(page, "source");
  const failures: string[] = [];
  for (const probe of sources) {
    await page.mouse.click(probe.x, probe.y);
    await pressStatus(page);
    const target = page.locator(`#target-overlay [data-node-id="${probe.nodeId}"]`);
    const forward = await target
      .first()
      .getAttribute("aria-pressed")
      .catch(() => null);
    if (forward !== "true") {
      failures.push(`${probe.nodeId.slice(0, 8)}: forward=${String(forward)}`);
      continue;
    }
    // Click the counterpart back. The reverse may activate a different node
    // (overlap); accept only a round trip on the same node.
    const landings = await regionProbes(page, "target");
    const landing = landings.find((candidate) => candidate.nodeId === probe.nodeId);
    if (!landing) {
      failures.push(`${probe.nodeId.slice(0, 8)}: no hittable landing on target`);
      continue;
    }
    await page.mouse.click(landing.x, landing.y);
    await pressStatus(page);
    const back = await page
      .locator(`#source-overlay [data-node-id="${probe.nodeId}"]`)
      .first()
      .getAttribute("aria-pressed");
    if (back === "true") return;
    failures.push(`${probe.nodeId.slice(0, 8)}: back=${back}`);
  }
  throw new Error(`no node completed the round trip: ${failures.join(" | ")}`);
}

test("import PDF → analyze → translate → target PDF → jumps", async ({ page }) => {
  test.setTimeout(300_000);
  const workspace = mkdtempSync(path.join(tmpdir(), "paper-e2e-import-"));
  const dataBackup = mkdtempSync(path.join(tmpdir(), "paper-e2e-data-"));
  const backupRoot = path.join(dataBackup, "data");
  cpSync(DATA_DIR, backupRoot, { recursive: true });
  try {
    const previousSource = await page.request.get("/data/source.pdf").then((r) => r.body());

    await page.goto("/");
    await expect(page.locator("#viewer")).toBeVisible();
    const revisionBefore = await page.locator("#viewer").getAttribute("data-revision");
    expect(revisionBefore).toBeTruthy();

    await page.fill("#import-source", SOURCE_PDF);
    await page.fill("#import-workspace", workspace);
    await page.click("#import-submit");
    // The panel acknowledges within one poll interval and then rewrites the
    // line with progress, so assert the shared "Job …" prefix rather than the
    // transient "Job submitted" text.
    await expect(page.locator("#import-status")).toContainText(/Job /, {
      timeout: 10_000,
    });

    // The queue drains via the real worker (1 s poll interval) with a real
    // lualatex RENDER stage; succeed within 280 s.
    await expect
      .poll(
        async () => {
          const payload = (await page.request
            .get("/api/jobs")
            .then((r) => r.json())) as unknown as { jobs: JobRecord[] };
          const job = payload.jobs.find((candidate) => candidate.workspace === workspace);
          if (job?.status === "failed") {
            throw new Error(`job failed · ${job.stage ?? "fatal"} · ${job.error ?? ""}`);
          }
          return job?.status ?? "missing";
        },
        { timeout: 280_000, intervals: [2_000] },
      )
      .toBe("succeeded");

    // The panel notices on its own poll and reloads the viewer in place.
    await expect(page.locator("#import-status")).toContainText("Job succeeded", {
      timeout: 10_000,
    });
    await expect(page.locator("#viewer")).not.toHaveAttribute(
      "data-revision",
      revisionBefore ?? "",
      {
        timeout: 60_000,
      },
    );
    await expect(page.locator("#viewer-status")).toContainText("Bidirectional navigation ready");

    // Page counts can coincide for different documents. Verify source identity
    // directly and check the displayed target count against the published metadata.
    const targetPage = (await page.locator("#target-page").textContent()) ?? "";
    const shownPages = Number(targetPage.split("/")[1]?.trim());
    expect(Number.isNaN(shownPages)).toBe(false);
    const importedSource = await page.request.get("/data/source.pdf").then((r) => r.body());
    expect(importedSource.equals(readFileSync(SOURCE_PDF))).toBe(true);
    expect(importedSource.equals(previousSource)).toBe(false);
    const newMeta = await page.request
      .get("/data/viewer-meta.json")
      .then((r) => r.json() as Promise<ViewerMeta>);
    expect(newMeta.targetPageCount).toBe(shownPages);

    // Click-jump round trip both directions on the job-published revision.
    await jumpRoundTrip(page);

    // Retranslate a node belonging to the imported document, then reject the old revision.
    const manifest = await page.request.get("/data/manifest.json").then((r) => r.json());
    expect(manifest.workspace).toBe(realpathSync(workspace));
    const mapping = await page.request.get(manifest.mapping).then((r) => r.json());
    const nodeId = mapping.translation.entries[0].semanticNodeId;
    const translated = await page.request.post("/api/retranslate", {
      data: { nodeIds: [nodeId], revision: manifest.revision },
      timeout: 120_000,
    });
    expect(translated.status()).toBe(200);
    expect((await translated.json()).changed).toContain(nodeId);
    const stale = await page.request.post("/api/retranslate", {
      data: { nodeIds: [nodeId], revision: manifest.revision },
    });
    expect(stale.status()).toBe(409);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
    // Restore the anatomy-published data root for the later viewer-* specs.
    restoreDataDir(backupRoot);
    rmSync(dataBackup, { recursive: true, force: true });
  }
});
