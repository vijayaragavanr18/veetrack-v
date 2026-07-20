/**
 * Export brief e2e tests.
 *
 * ExportBriefButton only renders when a user is authenticated
 * (checks user && accessToken in the auth store). We use the same
 * route-mock login pattern to authenticate and then verify:
 *   1. The Export button is visible in the feed header sidebar area.
 *   2. Clicking "Export PDF" triggers a download event.
 */

import { test, expect } from "@playwright/test";

const FAKE_USER = {
  id: "user-e2e-001",
  email: "admin@test.com",
  role: "admin",
  workspace_id: "ws-e2e-001",
};

const FAKE_TOKEN = "e2e-access-token-placeholder";

/** Shared setup: mock auth + navigate to /feed */
async function loginAndGoToFeed(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: FAKE_TOKEN, token_type: "bearer" }),
    }),
  );

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FAKE_USER),
    }),
  );

  // Let the feed API call fail so the app falls back to mock data
  await page.route("**/api/v1/feed**", (route) =>
    route.fulfill({ status: 401 }),
  );

  await page.goto("/login");
  await page.fill("#email", "admin@test.com");
  await page.fill("#password", "TestPassword123!");
  await page.fill("#workspace-id", "ws-e2e-001");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/feed", { timeout: 10_000 });
}

test.describe("Export Brief", () => {
  test("Export Brief button is visible in the feed header sidebar", async ({
    page,
  }) => {
    await loginAndGoToFeed(page);

    // ExportBriefButton renders a button with aria-label "Export executive brief"
    // inside the aside sidebar on desktop viewports.
    const exportBtn = page.getByRole("button", {
      name: /export executive brief/i,
    });
    await expect(exportBtn).toBeVisible({ timeout: 8_000 });
  });

  test("clicking PDF option in the dropdown triggers a download", async ({
    page,
  }) => {
    await loginAndGoToFeed(page);

    // Mock the export endpoint — return a small PDF blob
    await page.route("**/api/v1/exports/brief**", async (route) => {
      // Minimal valid PDF magic bytes
      const fakePdfBytes = Buffer.from("%PDF-1.4 fake pdf content for e2e");
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": 'attachment; filename="veetrack_brief.pdf"',
        },
        body: fakePdfBytes,
      });
    });

    // Open the export dropdown
    const exportBtn = page.getByRole("button", {
      name: /export executive brief/i,
    });
    await expect(exportBtn).toBeVisible({ timeout: 8_000 });
    await exportBtn.click();

    // The dropdown should show PDF and PPT options
    const pdfOption = page.getByRole("button", { name: /export pdf/i });
    await expect(pdfOption).toBeVisible({ timeout: 3_000 });

    // Start waiting for a download event before clicking the option
    const downloadPromise = page.waitForEvent("download", { timeout: 8_000 });

    await pdfOption.click();

    // Verify the download event fired
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
  });
});
