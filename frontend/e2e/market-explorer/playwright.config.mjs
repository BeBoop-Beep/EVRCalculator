// Run (servers are NOT started by this config; see README block in helpers.mjs / evidence doc):
//   FIXTURE_BACKEND_MODE=v2 FIXTURE_BACKEND_PORT=8201 node e2e/market-explorer/fixtureBackend.mjs
//   FIXTURE_BACKEND_MODE=v1 FIXTURE_BACKEND_PORT=8202 node e2e/market-explorer/fixtureBackend.mjs
//   PERF_AUDIT_DIST_DIR=.next-fx-v2 BACKEND_API_BASE_URL=http://127.0.0.1:8201 NEXT_PUBLIC_BACKEND_API_BASE_URL=http://127.0.0.1:8201 npx next dev -p 3202
//   PERF_AUDIT_DIST_DIR=.next-fx-v1 BACKEND_API_BASE_URL=http://127.0.0.1:8202 NEXT_PUBLIC_BACKEND_API_BASE_URL=http://127.0.0.1:8202 npx next dev -p 3203
//   npx playwright test -c e2e/market-explorer/playwright.config.mjs
// Optional live-anonymous project: set EXPLORER_LIVE_URL to a Next server pointed at a real backend.
import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.playwright\.spec\.mjs/,
  outputDir: path.join(os.tmpdir(), "pw-market-explorer-results"),
  workers: 1,
  timeout: 180000,
  reporter: [["list"]],
  use: { headless: true, trace: "off" },
});
