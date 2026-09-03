import { expect, test } from "@playwright/test";

test("web workspace smoke", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#title")).toHaveText("PDF Paper Analysis");
  await expect(page.locator("#status")).toContainText("workspace is running");
});
