// Shared Playwright helpers for the Market Explorer acceptance specs.
import fs from "node:fs";
import path from "node:path";

export const OUT_DIR = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/ui_regression_20260925");
export const URLS = {
  liveAnon: process.env.EXPLORER_LIVE_URL || "http://127.0.0.1:3200", // real backend, anonymous only
  v2: process.env.EXPLORER_FIXTURE_V2_URL || "http://127.0.0.1:3202", // FIXTURE V2
  v1: process.env.EXPLORER_FIXTURE_V1_URL || "http://127.0.0.1:3203", // FIXTURE V1
  backend: process.env.EXPLORER_FIXTURE_BACKEND_URL || "http://127.0.0.1:8201", // V2 fixture backend
  backendV1: process.env.EXPLORER_FIXTURE_BACKEND_V1_URL || "http://127.0.0.1:8202", // V1 fixture backend
};
export const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
export const PATH = "/Market/Explorer";

export async function newSession(browser, { base, plan = null, viewport = VIEWPORTS.desktop, mobile = false }) {
  const context = await browser.newContext({ viewport, hasTouch: mobile, isMobile: mobile });
  if (plan) await context.addCookies([{ name: "token", value: `fixture-${plan}`, url: base }]);
  const page = await context.newPage();
  const net = { failed: [], requests: [], consoleErrors: [] };
  page.on("console", (m) => { if (m.type() === "error") net.consoleErrors.push(m.text().slice(0, 240)); });
  page.on("request", (r) => { if (r.url().includes("/api/")) net.requests.push({ method: r.method(), url: r.url().replace(base, ""), body: r.postData() || null }); });
  page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) net.failed.push({ status: r.status(), url: r.url().replace(base, "") }); });
  return { context, page, net };
}

export async function openExplorer(page, base, query = "") {
  await page.goto(`${base}${PATH}${query}`, { waitUntil: "networkidle", timeout: 180000 });
  await page.waitForSelector("[data-market-explorer-workspace]", { timeout: 60000 });
}

/** On mobile the sidebar is behind "Markets / Tools"; open it if it is closed. */
export async function ensureTools(page) {
  const trigger = page.locator("[data-market-explorer-mobile-tools]");
  if (await trigger.isVisible().catch(() => false)) {
    if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click();
  }
}

export async function chooseCategory(page, category) {
  await ensureTools(page);
  const popover = page.locator("[data-market-directory-popover]");
  const trigger = page.locator(`[data-market-directory-category="${category}"]`);
  if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click();
  await popover.waitFor({ state: "visible" });
}

export async function pickRow(page, category, label) {
  await chooseCategory(page, category);
  const row = page.locator("[data-prepared-market]", { hasText: label }).first();
  await row.click();
}

export const activeChips = (page) => page.locator("[data-market-explorer-active-strip] [data-market-explorer-active-chip], [data-market-explorer-active-strip] [data-market-explorer-active-market]");

export async function shot(page, name) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(OUT_DIR, `${name}.png`) });
}

export async function fixtureRequests(backend = URLS.backend) {
  return (await fetch(`${backend}/__fixture/requests`)).json();
}
export const resetFixtureRequests = (backend = URLS.backend) => fetch(`${backend}/__fixture/reset`);
