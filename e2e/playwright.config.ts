import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: isCI ? 0 : 1,
  workers: 1,
  reporter: isCI ? "list" : "html",

  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },

  projects: [
    // Setup project — runs auth.setup.ts to produce .auth/user.json
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },

    // Main test project — depends on setup, uses saved auth state
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
      },
      dependencies: ["setup"],
      testIgnore: /auth\.setup\.ts/,
    },
  ],
});
