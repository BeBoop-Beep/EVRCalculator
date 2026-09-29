import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: ".", testMatch: "rankings-products-redesign.spec.js", timeout: 60_000, use: { browserName: "chromium", headless: true }, workers: 1 });
