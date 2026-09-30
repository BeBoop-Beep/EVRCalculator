import { test, expect } from "@playwright/test";

const BASE = process.env.EXPLORER_BUCKET3_URL || "http://127.0.0.1:3000";

for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }, { width: 1728, height: 1000 }]) {
  test(`Bucket 3 desktop geometry ${viewport.width}x${viewport.height}`, async ({ browser }) => {
    const page = await browser.newPage({ viewport });
    await page.goto(`${BASE}/Market/Explorer`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await expect(page.locator("[data-market-explorer-workspace]")).toBeVisible({ timeout: 120000 });
    const metrics = await page.evaluate(() => {
      const box = (selector) => document.querySelector(selector)?.getBoundingClientRect();
      const workspace = box("[data-market-explorer-workspace]");
      const chart = box("[data-market-explorer-chart-pane]");
      const sidebar = box("[data-market-explorer-sidebar]");
      const details = box("[data-market-explorer-view-details]");
      const methodology = box("[data-market-explorer-methodology-trigger]");
      const browseCard = box('[data-market-explorer-zone="explore"]');
      return { viewport: innerHeight, workspace, chart, sidebar, details, methodology, browseCard };
    });
    expect(metrics.viewport - metrics.workspace.bottom).toBeLessThanOrEqual(20);
    expect(metrics.viewport - metrics.chart.bottom).toBeLessThanOrEqual(24);
    expect(metrics.methodology.top).toBeGreaterThanOrEqual(metrics.browseCard.bottom);
    const chartCenter = metrics.chart.left + metrics.chart.width / 2;
    const buttonCenter = metrics.details.left + metrics.details.width / 2;
    expect(Math.abs(chartCenter - buttonCenter)).toBeLessThanOrEqual(3);
    await page.close();
  });
}

test("Bucket 3 disclosure exclusivity and public Screens", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/Market/Explorer`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await expect(page.locator("[data-market-explorer-workspace]")).toBeVisible({ timeout: 120000 });
  await page.locator('[data-market-directory-category="sets"]').click();
  await expect(page.locator('[data-market-directory-category="sets"]')).toHaveAttribute("aria-expanded", "true");
  const rarity = page.locator('[data-market-asset-selector-trigger="rarities"]');
  await rarity.click();
  await expect(rarity).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator('[data-market-directory-category="sets"]')).toHaveAttribute("aria-expanded", "false");
  await page.locator('[data-market-directory-category="quick"]').click();
  await expect(rarity).toHaveAttribute("aria-expanded", "false");
  await page.locator('[data-market-directory-asset="sealed"]').click();
  const sealed = page.locator('[data-market-asset-selector-trigger="sealed-types"]');
  await sealed.click();
  await expect(sealed).toHaveAttribute("aria-expanded", "true");
  await page.locator('[data-market-directory-category="eras"]').click();
  await expect(sealed).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-market-directory-category="eras"]')).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("Locked", { exact: false })).toHaveCount(0);
  await page.locator('[data-market-screen="top-performers"]').click();
  await expect(page.locator("[data-market-screen-results]")).toBeVisible();
});
