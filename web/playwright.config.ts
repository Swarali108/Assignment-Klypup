import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end suite for FinSight. The app must already be running (./demo.sh start): web on :3000 proxying /api to the
 * API on 127.0.0.1:8000. Nothing here starts or stops it.
 *
 *   cd web && npx playwright test              # everything (desktop 1440x900 + the @mobile subset at 390x844)
 *   npx playwright test e2e/03-chat.spec.ts    # one area
 *   npx playwright test --project=mobile       # only the mobile subset
 *
 * The HTML report goes to ../../e2e-report (next to the repository folder).
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  workers: 2,
  retries: 0,
  fullyParallel: false,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [["list"], ["html", { outputFolder: path.resolve(__dirname, "../../e2e-report"), open: "never" }]],
  use: {
    baseURL: BASE_URL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
      grepInvert: /@mobile/,
    },
    {
      name: "mobile",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
      grep: /@mobile/,
    },
  ],
});
