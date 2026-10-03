import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const base = process.env.EXPLORER_PERF_URL || "http://127.0.0.1:3202";
const mode = process.env.EXPLORER_PERF_MODE || "dev";
const cycles = Number(process.env.EXPLORER_PERF_CYCLES || 10);
const outputDir = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/explorer_review_readpath_performance_20261003");
fs.mkdirSync(outputDir, { recursive: true });

test(`Rankings to Explorer ${mode} navigation and read-path timings`, async ({ browser }) => {
  test.setTimeout(600_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addCookies([{ name: "token", value: "fixture-premium", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  const consoleErrors = [];
  const failures = [];
  const navigationAborts = [];
  const requests = [];
  page.on("console", (message) => { if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("request", (request) => { if (request.url().includes("/api/market/explorer/")) request.__startedAt = performance.now(); });
  page.on("response", (response) => { const request = response.request(); if (request.__startedAt != null) requests.push({ method: request.method(), path: new URL(request.url()).pathname + new URL(request.url()).search, status: response.status(), elapsedMs: Math.round((performance.now() - request.__startedAt) * 10) / 10 }); });
  page.on("requestfailed", (request) => { if (request.url().includes("/api/market/explorer/")) { const entry = { path: new URL(request.url()).pathname, error: request.failure()?.errorText || "failed" }; if (entry.error === "net::ERR_ABORTED") navigationAborts.push(entry); else failures.push(entry); } });

  const navigation = [];
  for (let index = 0; index < cycles; index += 1) {
    await page.goto(`${base}/Rankings`, { waitUntil: "domcontentloaded" });
    const started = performance.now();
    const explorerLinks = await page.locator('a[href="/Market/Explorer"]').all();
    let visibleLink = null;
    for (const link of explorerLinks) { if (await link.isVisible()) { visibleLink = link; break; } }
    if (visibleLink) await visibleLink.click();
    else await page.goto(`${base}/Market/Explorer`, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/Market\/Explorer/);
    await expect(page.locator('[data-market-explorer-active-chip="raw"]')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('[data-market-explorer-active-chip="sealedMarket"]')).toBeVisible({ timeout: 30000 });
    await expect(page.locator("[data-market-explorer-chart-plot]")).toBeVisible();
    await expect(page.locator("[data-market-explorer-prepared-error]")).toHaveCount(0);
    await page.waitForTimeout(250);
    navigation.push({ cycle: index + 1, elapsedMs: Math.round((performance.now() - started) * 10) / 10,
      activeSeries: await page.locator("[data-market-explorer-active-chip]").count() });
  }

  const exactSearch = [];
  const screens = [];
  for (const screen of ["top-performers-sealed", "worst-performers-sealed", "rarity-leaders", "sealed-format-leaders"]) {
    const started = performance.now();
    const [response] = await Promise.all([
      page.waitForResponse((candidate) => candidate.url().includes("/api/market/explorer/prepared?kind=screen") && candidate.url().includes(`screen=${screen.startsWith("top-") ? "top-performers" : screen.startsWith("worst-") ? "worst-performers" : screen}`)),
      page.locator(`[data-market-screen="${screen}"]`).click(),
    ]);
    await page.waitForFunction((id) => [...document.querySelectorAll(`[data-market-screen-results-for="${id}"]`)].some((node) => node.getClientRects().length > 0), screen);
    screens.push({ screen, status: response.status(), elapsedMs: Math.round((performance.now() - started) * 10) / 10 });
  }
  await page.locator("[data-market-explorer-build-trigger]").click();
  const input = page.locator("[data-market-exact-search]");
  for (const query of ["Dragonite", "Dragonite ex", "Umbreon", "Evolving Skies", "booster bundle"]) {
    await input.fill(""); const started = performance.now();
    const [response] = await Promise.all([
      page.waitForResponse((candidate) => candidate.url().includes("/api/market/explorer/instruments/search") && new URL(candidate.url()).searchParams.get("q") === query),
      input.fill(query),
    ]);
    await expect(page.getByText("Searching…", { exact: true })).toHaveCount(0);
    exactSearch.push({ query, status: response.status(), elapsedMs: Math.round((performance.now() - started) * 10) / 10,
      resultCount: await page.locator('[aria-label="Search results"] [role="option"]').count() });
  }
  await page.screenshot({ path: path.join(outputDir, `${mode}-readpath.png`), fullPage: true });
  const evidence = { mode, base, cycles, navigation, screens, exactSearch, requests, failures, navigationAborts, consoleErrors,
    unexpected5xx: requests.filter((entry) => entry.status >= 500), timeoutBanners: await page.locator("text=/took too long|timed out/i").count() };
  fs.writeFileSync(path.join(outputDir, `${mode}-timings.json`), `${JSON.stringify(evidence, null, 2)}\n`);
  expect(failures).toEqual([]);
  expect(evidence.unexpected5xx).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(evidence.timeoutBanners).toBe(0);
  expect(navigation.every((entry) => entry.activeSeries >= 2)).toBe(true);
  await context.close();
});
