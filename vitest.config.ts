import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["packages/typescript/**/*.test.ts", "apps/web/**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/dist/**", "tests/e2e/**"],
  },
});
