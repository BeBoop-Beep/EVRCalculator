import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, URLS } from "./helpers.mjs";

const output = path.resolve(process.cwd(), "../backend/artifacts/market_activity_v1/fma3");
const normalUrl = process.env.EXPLORER_NORMAL_URL || "http://127.0.0.1:3204";
const capture = async (page, name) => {
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
};

async function focusCards(page) {
  const cards = page.locator("[data-market-explorer-active-chip]").filter({ has: page.locator("[data-market-explorer-active-focus]") }).first();
  await cards.locator("[data-market-explorer-active-focus]").click();
  await expect(page.locator("[data-market-chart-view='activity']")).toHaveAttribute("data-market-chart-view-state", "available");
}

test("normal product defaults never expose fixture Activity", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: normalUrl, plan: "plus", viewport: { width: 1440, height: 900 } });
  await openExplorer(page, normalUrl);
  const cards = page.locator("[data-market-explorer-active-chip]").first();
  await cards.locator("[data-market-explorer-active-focus]").click();
  await expect(page.locator("[data-market-chart-view='activity']")).toHaveAttribute("data-market-chart-view-state", "unavailable");
  await expect(page.locator("[data-market-activity-pane]")).toHaveCount(0);
  await capture(page, "1440x900-product-default-activity-unavailable");
  await context.close();
});

test("fixture-backed Activity desktop views and synchronized inspection", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport: { width: 1440, height: 900 } });
  await openExplorer(page, URLS.v2);
  await focusCards(page);
  await capture(page, "1440x900-activity-off");
  await page.locator("[data-market-chart-view='activity']").click();
  await expect(page.locator("[data-market-activity-chart]")).toBeVisible();
  await expect(page.locator("[data-activity-sales-bar]").first()).toBeVisible();
  expect(await page.locator("[data-activity-supply-marker]").count()).toBeGreaterThan(0);
  await expect(page.locator("[data-activity-supply-line]")).toHaveCount(0);
  await expect(page.locator("[data-market-activity-pane]")).toHaveCount(0);
  await capture(page, "1440x900-sales-partial");
  const before = net.requests.length;
  await page.locator("[data-market-activity-chart]").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("[data-market-activity-tooltip]")).toBeVisible();
  expect(net.requests.length).toBe(before);
  await capture(page, "1440x900-synchronized-date-tooltip");
  await expect(page.locator("[data-market-activity-tooltip]")).toContainText("Listings observed");
  await capture(page, "1440x900-listed-supply");
  await page.keyboard.press("Escape");
  await context.close();
});

test("fixture-backed Activity remains readable at laptop and mobile widths", async ({ browser }) => {
  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const mobile = viewport.width === 390;
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport, mobile });
    await openExplorer(page, URLS.v2);
    await focusCards(page);
    await page.locator("[data-market-chart-view='activity']").click();
    await expect(page.locator("[data-market-activity-chart]")).toBeVisible();
    await capture(page, `${viewport.width}x${viewport.height}-activity`);
    await context.close();
  }
});
