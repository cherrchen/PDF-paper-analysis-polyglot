import { type ChildProcess, spawn } from "node:child_process";
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * M8 batch F: a real failed publish over HTTP leaves the previous revision
 * readable — the product-level counterpart of
 * `test_rerender_mid_publish_failure_rolls_back_viewer_and_workspace`
 * (packages/python/pdf-pipeline/tests/test_rerender_workspace.py).
 *
 * PAPER_PUBLISH_FAULT=target.pdf makes the publish transaction raise in the
 * middle of the alias replacement. The API restores every already-replaced
 * file, leaves manifest.json untouched, and removes the staged revision; the
 * viewer then boots against the untouched data (a second Vite serving the
 * copied data root via PAPER_VIEWER_DATA_DIR) and jumps still work.
 */

const API_PORT = 8010;
const VIEWER_PORT = 4183;
const ALIASES = ["mapping.json", "viewer-meta.json", "source.pdf", "target.pdf", "manifest.json"];

function readBytes(dataDir: string): Record<string, string> {
  const digest: Record<string, string> = {};
  for (const alias of ALIASES) {
    digest[alias] = readFileSync(path.join(dataDir, alias)).toString("hex");
  }
  return digest;
}

function delay(ms: number): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  setTimeout(resolve, ms);
  return promise;
}

async function waitHttp(url: string, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + 30_000;
  for (;;) {
    if (child.exitCode !== null) throw new Error(`process died early (code ${child.exitCode})`);
    const response = await fetch(url).catch(() => undefined);
    // Any HTTP answer means the server is listening (vite serves /, the API
    // health endpoint answers 200).
    if (response !== undefined) return;
    if (Date.now() > deadline) throw new Error(`timeout waiting for ${url}`);
    await delay(250);
  }
}

function exited(child: ChildProcess): Promise<unknown> {
  const { promise, resolve } = Promise.withResolvers<unknown>();
  if (child.exitCode !== null) resolve(null);
  else child.once("exit", resolve);
  return promise;
}

test("publish failure restores every file; viewer reads the previous revision", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const tmp = mkdtempSync(path.join(tmpdir(), "paper-e2e-fault-"));
  const dataDir = path.join(tmp, "data");
  const workspaceDir = path.join(tmp, "workspace");
  const jobsDir = path.join(tmp, "jobs");
  cpSync(path.resolve("apps/web/public/data"), dataDir, { recursive: true });
  cpSync(path.resolve("apps/web/.viewer-fixture"), workspaceDir, { recursive: true });

  const baselineBytes = readBytes(dataDir);
  const baselineRevisions = readdirSync(path.join(dataDir, "revisions")).sort();
  const baselineRevision = JSON.parse(readFileSync(path.join(dataDir, "manifest.json"), "utf8"))
    .revision as string;
  const mapping = JSON.parse(readFileSync(path.join(dataDir, "mapping.json"), "utf8")) as {
    translation: { entries: { semanticNodeId: string }[] };
  };
  // A translation entry is by construction re-translatable (BIBLIOGRAPHY
  // entries never reach the viewer translation layer).
  const nodeId = mapping.translation.entries[0].semanticNodeId;
  expect(nodeId).toBeTruthy();

  const api = spawn(
    "uv",
    [
      "run",
      "python",
      "-m",
      "paper_api",
      "--workspace",
      workspaceDir,
      "--data-dir",
      dataDir,
      "--jobs-root",
      jobsDir,
      "--port",
      String(API_PORT),
    ],
    { env: { ...process.env, PAPER_PUBLISH_FAULT: "target.pdf" }, stdio: "ignore" },
  );
  let vite: ChildProcess | undefined;
  try {
    await waitHttp(`http://127.0.0.1:${API_PORT}/api/health`, api);

    // Real retranslate through HTTP (full lualatex recompile); the publish
    // raises at target.pdf.
    const response = await page.request.post(`http://127.0.0.1:${API_PORT}/api/retranslate`, {
      data: { nodeIds: [nodeId] },
      timeout: 150_000,
    });
    expect(response.status()).toBe(500);
    const body = (await response.json()) as { ok: boolean; error: string };
    expect(body.ok).toBe(false);
    expect(body.error).toContain("publish fault injected for target.pdf");

    // Disk: manifest + every stable alias byte-identical, revision set intact.
    expect(readBytes(dataDir)).toEqual(baselineBytes);
    expect(readdirSync(path.join(dataDir, "revisions")).sort()).toEqual(baselineRevisions);

    // Browser: the previous revision still boots, renders, and jumps.
    vite = spawn(
      "pnpm",
      [
        "--filter",
        "@paper/web",
        "exec",
        "vite",
        "--host",
        "127.0.0.1",
        "--port",
        String(VIEWER_PORT),
        "--strictPort",
      ],
      { env: { ...process.env, PAPER_VIEWER_DATA_DIR: dataDir }, stdio: "ignore" },
    );
    await waitHttp(`http://127.0.0.1:${VIEWER_PORT}/`, vite);
    await page.goto(`http://127.0.0.1:${VIEWER_PORT}/`);
    await expect(page.locator("#viewer")).toBeVisible();
    await expect(page.locator("#viewer-status")).toContainText("Bidirectional navigation ready");
    await expect(page.locator("#viewer")).toHaveAttribute("data-revision", baselineRevision);

    const sourceRegion = page.locator("#source-overlay [data-node-id]").first();
    await expect(sourceRegion).toBeVisible();
    const jumpNodeId = await sourceRegion.getAttribute("data-node-id");
    expect(jumpNodeId).not.toBeNull();
    await sourceRegion.click();
    const targetRegion = page.locator(`#target-overlay [data-node-id="${jumpNodeId}"]`);
    await expect(targetRegion).toHaveAttribute("aria-pressed", "true");
    await targetRegion.click();
    await expect(page.locator(`#source-overlay [data-node-id="${jumpNodeId}"]`)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  } finally {
    api.kill("SIGTERM");
    vite?.kill("SIGTERM");
    await Promise.all([exited(api), vite ? exited(vite) : Promise.resolve(null)]);
    rmSync(tmp, { recursive: true, force: true });
  }
});
