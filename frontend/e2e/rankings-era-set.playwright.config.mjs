import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: /rankings-era-set-locked\.spec\.js/,
  timeout: 60_000,
  use: { headless: true },
});
