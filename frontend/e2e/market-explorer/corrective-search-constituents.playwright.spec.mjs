import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { ensureTools, newSession, openExplorer, URLS } from "./helpers.mjs";

const output = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/corrective_search_constituents_20261002");
async function capture(page, name) { fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true }); }

for (const fixture of [
  { name: "desktop", viewport: { width: 1440, height: 900 }, mobile: false },
  { name: "mobile", viewport: { width: 390, height: 844 }, mobile: true },
]) {
  test(`${fixture.name}: grouped Prismatic catalog pages and constituent continuation`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium", viewport: fixture.viewport, mobile: fixture.mobile });
    await openExplorer(page, URLS.v2);
    await ensureTools(page);
    const input = page.locator("[data-market-explorer-search-input]");
    await input.fill("prismatic");
    const panel = page.locator("[data-market-explorer-search-panel]");
    await expect(panel.locator('[data-search-result-kind="market"]')).toContainText("Prismatic Evolutions — Cards");
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(12);
    await expect(panel.locator('[data-search-result-kind="leaf"]').first()).toContainText("$499.00");
    await panel.locator("[data-market-explorer-search-more]").click();
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(24);
    await expect(panel.locator('[data-search-result-kind="market"]')).toHaveCount(1);
    await capture(page, `${fixture.name}-cards-prismatic-grouped-page-2`);

    await page.locator('[data-market-directory-asset="sealed"]').click();
    await input.fill("prismatic");
    await expect(panel.locator('[data-search-result-kind="market"]')).toContainText("Prismatic Evolutions — Sealed");
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(12);
    await panel.locator("[data-market-explorer-search-more]").click();
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toHaveCount(19);
    await capture(page, `${fixture.name}-sealed-prismatic-grouped-complete`);

    await page.locator('[data-market-directory-asset="cards"]').click();
    await input.fill("slow old");
    await input.fill("charizard");
    await expect(panel).toContainText("Charizard");
    await page.waitForTimeout(1600);
    await expect(panel).not.toContainText("STALE RESULT");

    await input.fill("prismatic");
    await panel.locator('[data-search-primary="market"]').click();
    await expect(page.locator('[data-market-explorer-active-chip="set:set-prismatic"]')).toBeVisible();
    if (fixture.mobile) await page.locator("[data-market-explorer-mobile-tools]").click();
    const details = fixture.mobile ? page.locator("[data-market-explorer-mobile-constituents]") : page.locator("[data-market-explorer-view-details]");
    await details.click();
    const uniqueRows = () => page.locator("[data-market-constituent]").evaluateAll((nodes) => new Set(nodes.map((node) => node.getAttribute("data-market-constituent"))).size);
    await expect.poll(uniqueRows).toBe(100);
    await page.locator("[data-market-constituents-load-more]").first().click();
    await expect.poll(uniqueRows).toBe(130);
    await capture(page, `${fixture.name}-prepared-constituents-page-2`);
    await context.close();
  });
}

test("warm Next dev first-result latency for exact card names", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium" });
  await openExplorer(page, URLS.v2);
  await ensureTools(page);
  const input = page.locator("[data-market-explorer-search-input]");
  const panel = page.locator("[data-market-explorer-search-panel]");
  await input.fill("warmup");
  await page.waitForTimeout(350);
  const timings = {};
  for (const [query, expected] of [["charizard", "Charizard"], ["pikachu", "Pikachu"]]) {
    const started = performance.now();
    await input.fill(query);
    await expect(panel.locator('[data-search-result-kind="leaf"]')).toContainText(expected);
    timings[query] = Math.round((performance.now() - started) * 10) / 10;
  }
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, "warm-search-latency-ms.json"), JSON.stringify(timings, null, 2));
  await context.close();
});
