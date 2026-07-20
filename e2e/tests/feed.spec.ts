/**
 * Feed page e2e tests.
 *
 * The feed page falls back to MOCK_STORIES (8 stories, defined in
 * lib/mock-data.ts) whenever there is no access token — useFeedQuery()
 * checks for accessToken and returns MOCK_STORIES immediately when absent.
 *
 * Because the Zustand auth store is in-memory only (not persisted to
 * localStorage), these tests work against the mock data path: navigate
 * to /feed without auth and MOCK_STORIES render immediately.
 *
 * Keyboard navigation is registered via useKeyboardNav on the <body>
 * (window.addEventListener). Playwright's page.keyboard.press() fires
 * the event on the active element, which propagates to window — we just
 * need to make sure no input has focus first.
 */

import { test, expect } from "@playwright/test";

// Helper: navigate to /feed with mock data (no auth required)
async function goToFeed(page: import("@playwright/test").Page) {
  // Block any API calls so we always use mock data
  await page.route("**/api/v1/**", (route) => route.abort());
  await page.goto("/feed");
  // Wait for at least one story card to appear
  await page.waitForSelector('[aria-current]', { timeout: 15_000 }).catch(() => {
    // aria-current may not be set on first render; fall back to checking the sidebar
  });
}

// Blur any focused element so keyboard events reach the window handler
async function blurActiveElement(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    el?.blur();
  });
}

test.describe("Feed page", () => {
  test("loads and shows story cards in the sidebar", async ({ page }) => {
    await goToFeed(page);

    // The sidebar (<aside>) should list story card buttons.
    // On desktop (default viewport 1280×720) the aside is visible.
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();

    // At least one StoryCard button should be present
    const cards = sidebar.locator("button");
    await expect(cards).toHaveCount(await cards.count());
    expect(await cards.count()).toBeGreaterThan(0);
  });

  test("sidebar shows at least one story on desktop viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await goToFeed(page);

    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();

    const cards = sidebar.locator("button");
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("ArrowDown navigates to the next story", async ({ page }) => {
    await goToFeed(page);
    await blurActiveElement(page);

    // Read which story is active before navigation
    const viewport = page.locator('[data-testid="story-viewport"]');
    await expect(viewport).toBeVisible();

    // The active story card has aria-current="true"
    const activeBefore = page.locator('[aria-current="true"]');
    const headlineBefore = await activeBefore
      .locator("p.text-sm.font-semibold")
      .first()
      .textContent();

    await page.keyboard.press("ArrowDown");

    // Wait briefly for the state update to render
    await page.waitForTimeout(300);

    const activeAfter = page.locator('[aria-current="true"]');
    const headlineAfter = await activeAfter
      .locator("p.text-sm.font-semibold")
      .first()
      .textContent();

    // The active card headline should have changed (moved to story index 1)
    expect(headlineAfter).not.toBe(headlineBefore);
  });

  test("ArrowRight swipes to page 2 (AI Insight tab)", async ({ page }) => {
    await goToFeed(page);
    await blurActiveElement(page);

    // The page indicator tabs have aria-label per PAGE_LABELS in PageSwiper
    const insightTab = page.getByRole("tab", { name: "Insight" });
    await expect(insightTab).toBeVisible();

    // Should start on page 1 (Original)
    const originalTab = page.getByRole("tab", { name: "Original" });
    await expect(originalTab).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(300);

    await expect(insightTab).toHaveAttribute("aria-selected", "true");
  });

  test("ArrowRight again swipes to page 3 (Cluster)", async ({ page }) => {
    await goToFeed(page);
    await blurActiveElement(page);

    // Navigate to page 3 via two ArrowRight presses
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(200);
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(300);

    const clusterTab = page.getByRole("tab", { name: "Cluster" });
    await expect(clusterTab).toHaveAttribute("aria-selected", "true");
  });

  test("ArrowRight again swipes to page 4 (Actions/Recommendations)", async ({
    page,
  }) => {
    await goToFeed(page);
    await blurActiveElement(page);

    // Navigate to page 4 via three ArrowRight presses
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(200);
    }

    const actionsTab = page.getByRole("tab", { name: "Actions" });
    await expect(actionsTab).toHaveAttribute("aria-selected", "true");
  });

  test("ArrowLeft swipes back from page 4 to page 3", async ({ page }) => {
    await goToFeed(page);
    await blurActiveElement(page);

    // Go to page 4
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press("ArrowRight");
      await page.waitForTimeout(200);
    }

    // Go back one
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(300);

    const clusterTab = page.getByRole("tab", { name: "Cluster" });
    await expect(clusterTab).toHaveAttribute("aria-selected", "true");
  });
});
