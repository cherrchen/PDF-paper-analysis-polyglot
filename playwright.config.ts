import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);

/**
 * e2e traffic goes through the vite *dev* server (serves public/ from disk per
 * request, so re-translate rewrites are visible) with the stdlib reader API on
 * :8000 proxied at /api and the job worker on .jobs — the same three-process
 * wiring as `just serve-reader`. Keep the two command strings in sync.
 */
const serveCommand =
  "sh -c 'uv run python -m paper_api --workspace apps/web/.viewer-fixture --data-dir apps/web/public/data --jobs-root .jobs & api=$!; uv run python -m paper_worker --jobs-root .jobs & worker=$!; trap \"kill $api $worker\" EXIT; pnpm --filter @paper/web exec vite --host 127.0.0.1 --port 4173 --strictPort'";

export default defineConfig({
  testDir: "tests/e2e",
  // Serial: apps/web/public/data is a shared mutable data root now that a
  // browser-submitted job (product-import spec) publishes new revisions into
  // it while other specs read or flip the manifest. One worker removes the
  // cross-spec revision races.
  fullyParallel: false,
  workers: 1,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  reporter: isCI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: serveCommand,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !isCI,
    stdout: "pipe",
    stderr: "pipe",
  },
});
