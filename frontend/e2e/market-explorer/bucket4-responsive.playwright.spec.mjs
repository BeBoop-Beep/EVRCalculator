import { test, expect } from "@playwright/test";

const BASE = process.env.EXPLORER_BUCKET4_URL || "http://127.0.0.1:3000";
const viewports = [
  [1280, 720], [1440, 900], [1728, 1000],
  [1024, 768], [834, 1194], [768, 1024],
  [390, 844], [412, 915], [844, 390],
];

for (const [width, height] of viewports) {
  test(`Bucket 4 responsive geometry ${width}x${height}`, async ({ browser }) => {
    test.setTimeout(60000);
    const page = await browser.newPage({ viewport: { width, height } });
    await page.goto(`${BASE}/Market/Explorer`, { waitUntil: "domcontentloaded", timeout: 120000 });
    const workspace = page.locator("[data-market-explorer-workspace]").first();
    await expect(workspace).toBeVisible({ timeout: 120000 });
    const desktop = width >= 1200;
    const trigger = page.locator("[data-market-explorer-mobile-tools]").first();
    if (desktop) {
      await expect(trigger).toBeHidden();
      await expect(page.locator("[data-market-explorer-sidebar]").first()).toBeVisible();
    } else {
      await expect(trigger).toBeVisible();
      await expect(page.locator("[data-market-explorer-mobile-analysis-actions]").first()).toBeVisible();
      const stateBefore = await workspace.getAttribute("data-market-explorer-timeframe");
      await trigger.click();
      const drawer = page.locator("[data-market-explorer-sidebar]").first();
      await expect(drawer).toBeVisible();
      await expect(page.locator("[data-market-explorer-close-controls]").first()).toBeFocused();
      expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");
      const geometry = await page.evaluate(() => {
        const rect = (selector) => document.querySelector(selector)?.getBoundingClientRect();
        return { drawer: rect("[data-market-explorer-sidebar]"), trigger: rect("[data-market-explorer-mobile-tools]"), actions: rect("[data-market-explorer-mobile-analysis-actions]"), overflow: document.documentElement.scrollWidth - innerWidth };
      });
      expect(geometry.overflow).toBeLessThanOrEqual(1);
      expect(geometry.drawer.bottom).toBeLessThanOrEqual(height - 75);
      expect(geometry.trigger.bottom).toBeLessThanOrEqual(geometry.actions.top);
      console.log(`B4_GEOMETRY ${width}x${height} ${JSON.stringify(geometry)}`);
      await trigger.click();
      await expect(drawer).toBeHidden();
      await expect(trigger).toBeFocused();
      await trigger.click();
      await expect(drawer).toBeVisible();
      if (width >= 600) {
        await page.locator("[data-market-explorer-controls-backdrop]").click({ position: { x: width - 8, y: 8 } });
        await expect(drawer).toBeHidden();
        await trigger.click();
        await expect(drawer).toBeVisible();
      }
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
      await expect(trigger).toBeFocused();
      expect(await workspace.getAttribute("data-market-explorer-timeframe")).toBe(stateBefore);
      await page.locator("[data-market-explorer-mobile-methodology]").first().click();
      await expect(page.locator("[data-market-explorer-methodology-takeover]").first()).toBeVisible();
      await page.locator("[data-market-explorer-close-methodology]").first().click();
      await expect(page.locator("[data-market-explorer-methodology-takeover]").first()).toBeHidden();
      const constituents = page.locator("[data-market-explorer-mobile-constituents]").first();
      await expect(constituents).toBeEnabled();
      await constituents.click();
      const results = page.locator("[data-market-explorer-compare-results]").first();
      await expect(results).toBeVisible();
      await page.locator("[data-market-explorer-hide-details]").first().click();
      await expect(results).toBeHidden();
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    console.log(`B4_OVERFLOW ${width}x${height} ${overflow}`);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.close();
  });
}
