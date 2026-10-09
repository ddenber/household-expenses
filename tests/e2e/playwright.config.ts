import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 180_000,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3417",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
