import { test, expect } from "@playwright/test";
import { newSession, openExplorer, ensureTools, shot, URLS } from "./helpers.mjs";

const box = (page) => page.locator("[data-market-explorer-chart-pane]").boundingBox();
const expectStable = (before, after) => {
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(2);
  expect(Math.abs(after.height - before.height)).toBeLessThanOrEqual(2);
};

for (const viewport of [{ width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
  test(`UI correction desktop ${viewport.width}: leaf search, arbitration, focus geometry, IA`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium", viewport });
    await openExplorer(page, URLS.v2);

    const search = page.locator("[data-market-explorer-search-input]");
    await expect(search).toHaveAttribute("placeholder", "Search cards…");
    await page.locator('[data-market-directory-category="sets"]').click();
    await expect(page.locator("[data-market-directory-popover]")).toBeVisible();
    await search.fill("gengar");
    await expect(page.locator("[data-market-explorer-search-panel]")).toBeVisible();
    await expect(page.locator("[data-market-directory-popover]")).toHaveCount(0);
    const row = page.locator('[data-search-result-kind="leaf"]');
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("Fixture Gengar");
    await expect(row.locator('[data-search-primary="basket"]')).toHaveCount(1);
    await expect(row).not.toContainText("Open Detail");
    await page.locator('[data-market-directory-category="eras"]').click();
    await expect(page.locator("[data-market-explorer-search-panel]")).toHaveCount(0);
    await expect(page.locator("[data-market-directory-popover]")).toBeVisible();
    await page.locator("[data-prepared-market]").first().click();
    await expect(page.locator("[data-market-explorer-active-chip]")).toHaveCount(2, { timeout: 30000 });

    const chartBefore = await box(page);
    await page.locator('[data-market-explorer-active-focus-body="raw"]').click();
    await expect(page.locator("[data-market-explorer-focus-strip]")).toBeVisible();
    expectStable(chartBefore, await box(page));
    const dimmed = page.locator('[data-market-explorer-active-chip-dimmed="true"]').first();
    await expect(dimmed).toHaveCSS("opacity", "0.45");
    await page.locator('[data-market-explorer-active-focus-body="raw"]').click();
    await expect(page.locator("[data-market-explorer-focus-strip]")).toHaveCount(0);
    expectStable(chartBefore, await box(page));

    await page.locator('[data-market-directory-asset="sealed"]').click();
    await expect(search).toHaveAttribute("placeholder", "Search sealed products…");
    await expect(page.getByRole("heading", { name: "Sealed Types" })).toBeVisible();
    await expect(page.locator('[data-market-directory-category="types"]')).toHaveCount(0);
    await expect(page.locator('[data-market-directory-category="sets"]')).toHaveCount(1);
    await expect(page.locator('[data-market-directory-category="eras"]')).toHaveCount(1);
    await expect(page.locator('[data-market-directory-category="quick"]')).toHaveCount(1);
    await expect(page.locator('[data-market-screen="top-performers"]')).toBeVisible();
    await expect(page.locator('[data-market-screen="worst-performers"]')).toBeVisible();
    await shot(page, `ui-correction-${viewport.width}`);
    await context.close();
  });
}

test("UI correction mobile 390: final Cards/Sealed IA remains reachable", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium", viewport: { width: 390, height: 844 }, mobile: true });
  await openExplorer(page, URLS.v2);
  await ensureTools(page);
  await expect(page.locator('[data-market-directory-category="sets"]')).toBeVisible();
  await expect(page.locator('[data-market-directory-category="eras"]')).toBeVisible();
  await expect(page.locator('[data-market-directory-category="quick"]')).toBeVisible();
  await page.locator('[data-market-directory-asset="sealed"]').click();
  await expect(page.getByRole("heading", { name: "Sealed Types" })).toBeVisible();
  await shot(page, "ui-correction-mobile-390");
  await context.close();
});

test("Basic notice overlay does not reflow the chart", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, viewport: { width: 1440, height: 900 } });
  await openExplorer(page, URLS.v2);
  const before = await box(page);
  await page.locator('[data-market-screen="top-performers"]').click({ force: true });
  await expect(page.locator("[data-market-explorer-compare-upgrade]")).toBeVisible();
  expectStable(before, await box(page));
  await context.close();
});
