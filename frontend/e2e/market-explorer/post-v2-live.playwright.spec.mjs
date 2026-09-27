import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, ensureTools } from "./helpers.mjs";

test.skip(process.env.EXPLORER_POST_V2_LIVE !== "1", "set EXPLORER_POST_V2_LIVE=1 for a frontend connected to live V2 authority");
const BASE = process.env.EXPLORER_LIVE_URL || "http://127.0.0.1:3204";
const OUT = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/post_v2_live_20260926");
const capture = async (page, name) => { fs.mkdirSync(OUT, { recursive: true }); await page.screenshot({ path: path.join(OUT, `${name}.png`) }); };

for (const viewport of [{ width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
  test(`live V2 desktop ${viewport.width}: rich leaves and final Sealed IA`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base: BASE, viewport });
    await openExplorer(page, BASE);
    const search = page.locator("[data-market-explorer-search-input]");
    await expect(search).toHaveAttribute("placeholder", "Search cards…");
    await search.fill("dragonite");
    const cardRows = page.locator('[data-search-result-kind="leaf"]');
    await expect(cardRows.first()).toContainText("Dragonite");
    await expect(cardRows.first().locator('[data-search-primary="basket"]')).toHaveCount(1);
    await expect(cardRows.first()).toContainText("$");
    await expect(page.locator("[data-market-explorer-search-panel]")).not.toContainText("Open Detail");
    await capture(page, `cards-dragonite-${viewport.width}`);

    await page.locator('[data-market-directory-asset="sealed"]').click();
    await expect(search).toHaveAttribute("placeholder", "Search sealed products…");
    await search.fill("three pack");
    await expect(page.locator('[data-search-result-kind="leaf"]').first()).toContainText(/3 Pack|Three Pack/);
    await capture(page, `sealed-three-pack-${viewport.width}`);
    await search.press("Escape");

    await page.locator('[data-market-directory-category="quick"]').click();
    const quick = page.locator("[data-market-directory-popover] [data-prepared-market]");
    await expect(quick).toHaveCount(6);
    for (const label of ["Obtainable", "Intermediate", "Premium", "New Releases", "Established", "Global Top 10"]) await expect(quick.filter({ hasText: label })).toHaveCount(1);
    await expect(page.locator("[data-market-directory-popover]")).not.toContainText("Cards");
    await capture(page, `sealed-quick-six-${viewport.width}`);

    await page.locator('[data-market-directory-category="sets"]').click();
    expect(await page.locator("[data-market-directory-popover] [data-prepared-market]").count()).toBeGreaterThan(100);
    await expect(page.locator("[data-market-directory-popover]")).not.toContainText("awaiting the current prepared generation");
    await page.locator('[data-market-directory-category="eras"]').click();
    await expect(page.locator("[data-market-directory-popover] [data-prepared-market]")).toHaveCount(15);
    await expect(page.locator("[data-market-directory-popover]")).not.toContainText("awaiting the current prepared generation");
    await page.keyboard.press("Escape");
    const sealedTypes = page.locator("[data-market-explorer-sealed-types]");
    for (const label of ["Case", "Display", "Booster Box", "Elite Trainer Box", "Three-Pack Blister", "Collection Product", "Loose Booster Pack"]) await expect(sealedTypes).toContainText(label);
    await expect(sealedTypes).toContainText("tracked separately from Total Sealed");
    await expect(page.locator('[data-market-screen="top-performers"]')).toBeVisible();
    await expect(page.locator('[data-market-screen="worst-performers"]')).toBeVisible();
    await context.close();
  });
}

test("live V2 anonymous one-market route remains ungated and focus does not reflow", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: BASE, viewport: { width: 1440, height: 900 } });
  await openExplorer(page, BASE);
  const chart = page.locator("[data-market-explorer-chart-pane]");
  const before = await chart.boundingBox();
  await page.locator('[data-market-explorer-active-focus-body="raw"]').click();
  await expect(page.locator("[data-market-explorer-focus-strip]")).toBeVisible();
  const after = await chart.boundingBox();
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(2);
  expect(Math.abs(after.height - before.height)).toBeLessThanOrEqual(2);
  await capture(page, "raw-focus-live-1440");
  await page.locator('[data-market-explorer-active-focus-body="raw"]').click();

  const requestBodies = [];
  for (const label of ["Jungle", "Fossil", "Base Set 2"]) {
    await page.locator('[data-market-directory-category="sets"]').click();
    const target = page.locator("[data-prepared-market]", { hasText: label }).first();
    const key = await target.getAttribute("data-prepared-market");
    await page.keyboard.press("Escape");
    const body = { marketKeys: [key], contextMarketKeys: [] }; requestBodies.push(body);
    const status = await page.evaluate(async (payload) => (await fetch("/api/market/explorer/prepared", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })).status, body);
    expect(status).toBe(200);
  }
  await page.locator('[data-market-directory-asset="sealed"]').click();
  for (const label of ["Booster Box", "Elite Trainer Box"]) {
    const key = await page.locator('[data-market-explorer-sealed-types] [data-sealed-type]', { hasText: label }).first().getAttribute("data-sealed-type");
    const body = { marketKeys: [key.startsWith("sealed-type:") ? key : `sealed-type:${key}`], contextMarketKeys: [] }; requestBodies.push(body);
    const status = await page.evaluate(async (payload) => (await fetch("/api/market/explorer/prepared", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })).status, body);
    expect(status).toBe(200);
  }
  await expect(page.locator("[data-market-explorer-compare-upgrade]")).toHaveCount(0);
  const posts = net.requests.filter((entry) => entry.method === "POST" && entry.url.includes("/api/market/explorer/prepared")).map((entry) => JSON.parse(entry.body));
  expect(posts.length).toBeGreaterThanOrEqual(5);
  expect(requestBodies).toHaveLength(5);
  for (const post of posts) expect(post.contextMarketKeys).toEqual([]);
  expect(net.failed.filter((entry) => entry.url.startsWith("/api/market/explorer/prepared") && [401, 403].includes(entry.status))).toEqual([]);
  await capture(page, "anonymous-replacement-live-1440");
  await context.close();
});

test("live V2 mobile 390 rich search and Sealed controls", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: BASE, viewport: { width: 390, height: 844 }, mobile: true });
  await openExplorer(page, BASE);
  await ensureTools(page);
  await page.locator("[data-market-explorer-search-input]").fill("dragonite");
  await expect(page.locator('[data-search-result-kind="leaf"]').first()).toContainText("Dragonite");
  await page.locator('[data-market-directory-asset="sealed"]').click();
  await expect(page.getByRole("heading", { name: "Sealed Types" })).toBeVisible();
  await capture(page, "post-v2-live-mobile-390");
  await context.close();
});
