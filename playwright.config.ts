import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);

/**
 * e2e traffic goes through the vite *dev* server (serves public/ from disk per
 * request, so re-translate rewrites are visible) with the stdlib reader API on
 * :8000 proxied at /api — the same wiring as `just serve-reader`.
 */
const serveCommand =
  "sh -c 'uv run python -m paper_api --workspace apps/web/.viewer-fixture --data-dir apps/web/public/data & api=$!; trap \"kill $api\" EXIT; pnpm --filter @paper/web exec vite --host 127.0.0.1 --port 4173 --strictPort'";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
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
