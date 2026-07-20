/**
 * Auth setup — runs once before the main test projects.
 *
 * The login page hits the real API (localhost:8000). Since the e2e suite
 * runs against the Next.js dev server only (no backend), we intercept the
 * two auth endpoints with page.route() and return fake-but-valid responses.
 *
 * After a successful login the browser navigates to /feed. We then save
 * storageState (cookies + localStorage) to .auth/user.json so dependent
 * projects can load it.
 *
 * NOTE: The auth Zustand store is in-memory only (no localStorage persist).
 * Tests that need a populated auth store (watchlist, export) re-do the login
 * flow in their own beforeEach using the same route-mocking pattern.
 */

import { test as setup, expect } from "@playwright/test";
import path from "path";

const AUTH_FILE = path.join(__dirname, "..", ".auth", "user.json");

const FAKE_USER = {
  id: "user-e2e-001",
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@test.com",
  role: "admin",
  workspace_id: "ws-e2e-001",
};

const FAKE_TOKEN = "e2e-access-token-placeholder";

setup("authenticate", async ({ page }) => {
  // ------------------------------------------------------------------
  // Intercept the API server calls made by the login page.
  // The API base is http://localhost:8000; these routes must be caught
  // before the page submits the form.
  // ------------------------------------------------------------------
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: FAKE_TOKEN, token_type: "bearer" }),
    });
  });

  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FAKE_USER),
    });
  });

  // ------------------------------------------------------------------
  // Fill in and submit the login form.
  // ------------------------------------------------------------------
  await page.goto("/login");

  await page.fill("#email", process.env.E2E_ADMIN_EMAIL ?? "admin@test.com");
  await page.fill(
    "#password",
    process.env.E2E_ADMIN_PASSWORD ?? "TestPassword123!",
  );
  // workspace-id is a required field on the login form
  await page.fill("#workspace-id", "ws-e2e-001");

  await page.getByRole("button", { name: "Sign in" }).click();

  // Wait for the redirect — login page pushes router.push("/feed")
  await page.waitForURL("**/feed", { timeout: 10_000 });

  await expect(page).toHaveURL(/\/feed/);

  // ------------------------------------------------------------------
  // Save browser context state (cookies, localStorage, sessionStorage).
  // The Zustand auth store is in-memory only, so auth state is NOT in
  // this snapshot — but the file must exist for Playwright's dependency
  // resolution and any httpOnly refresh cookies are captured here.
  // ------------------------------------------------------------------
  await page.context().storageState({ path: AUTH_FILE });
});
