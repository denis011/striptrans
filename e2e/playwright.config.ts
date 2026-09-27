import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://frontend:5173",
    acceptDownloads: true,
    viewport: { width: 1400, height: 1000 },
  },
});
