import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: ".", testMatch: /rankings-pack-economics\.spec\.js/, timeout: 60_000, use: { headless: true } });
