import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { ensureTools, newSession, openExplorer } from "./helpers.mjs";

const BASE = process.env.EXPLORER_LIVE_URL || "http://127.0.0.1:3304";
const OUT = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/corrective_final_live_20261002");
const VIEWPORTS = [
  ["1728x1000", 1728, 1000], ["1440x900", 1440, 900],
  ["1024x768", 1024, 768], ["768x1024", 768, 1024],
  ["390x844", 390, 844], ["844x390", 844, 390],
];

const writeJson = (name, value) => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, name), JSON.stringify(value, null, 2));
};

for (const [name, width, height] of VIEWPORTS) {
  test(`live public matrix ${name}`, async ({ browser }) => {
    const mobile = width < 900;
    const { context, page, net } = await newSession(browser, { base: BASE, viewport: { width, height }, mobile });
    const responses = [];
    const startedAt = new WeakMap();
    page.on("request", (request) => {
      if (request.url().includes("/api/market/explorer/")) startedAt.set(request, Date.now());
    });
    page.on("response", (response) => {
      if (!response.url().includes("/api/market/explorer/")) return;
      responses.push({ route: new URL(response.url()).pathname + new URL(response.url()).search,
        status: response.status(), elapsedMs: Date.now() - (startedAt.get(response.request()) || Date.now()) });
    });
    await openExplorer(page, BASE);
    await expect(page.locator('[data-market-explorer-active-chip="raw"]')).toBeVisible();
    await expect(page.locator('[data-market-explorer-active-chip="sealedMarket"]')).toBeVisible();
    await ensureTools(page);
    const input = page.locator("[data-market-explorer-search-input]");
    const panel = page.locator("[data-market-explorer-search-panel]");
    await input.fill("prismatic");
    await expect(panel.locator('[data-search-result-kind="market"]')).toContainText("Prismatic Evolutions — Cards", { timeout: 30000 });
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(12);
    await expect(panel.locator('[data-search-result-price]').first()).toContainText("$1,337.97");
    await panel.locator("[data-market-explorer-search-more]").click();
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(24);
    fs.mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: path.join(OUT, `${name}-cards-search-page2.png`), fullPage: true });

    await page.locator('[data-market-directory-asset="sealed"]').click();
    await input.fill("prismatic");
    await expect(panel.locator('[data-search-result-kind="market"]')).toContainText("Prismatic Evolutions - Sealed", { timeout: 30000 });
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(12);
    await expect(panel.locator('[data-search-result-price]').first()).toContainText("$2,748.62");
    await panel.locator("[data-market-explorer-search-more]").click();
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(24);
    await page.screenshot({ path: path.join(OUT, `${name}-sealed-search-page2.png`), fullPage: true });
    const anonymousAuthProbeFailed = net.failed.some((entry) => entry.status === 401 && entry.url.startsWith("/api/auth/me"));
    const unexpectedConsoleErrors = net.consoleErrors.filter((message) =>
      !(anonymousAuthProbeFailed && /status of 401 \(Unauthorized\)/.test(message)),
    );
    writeJson(`${name}-network.json`, { explorerRoutes: responses, expectedAnonymousAuthProbe: anonymousAuthProbeFailed, unexpectedConsoleErrors });
    expect(net.failed.filter((entry) => entry.status >= 500)).toEqual([]);
    expect(unexpectedConsoleErrors).toEqual([]);
    await context.close();
  });
}
