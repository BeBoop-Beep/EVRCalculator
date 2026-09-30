import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, URLS } from "./helpers.mjs";

const output = path.resolve(process.cwd(), "../backend/artifacts/market_activity_v1/fma3");
const capture = async (page, name) => {
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
};

async function focusCards(page) {
  const cards = page.locator("[data-market-explorer-active-chip]").filter({ has: page.locator("[data-market-explorer-active-focus]") }).first();
  await cards.locator("[data-market-explorer-active-focus]").click();
  await expect(page.locator("[data-market-explorer-focus-tool='market-activity']")).toHaveAttribute("data-focus-tool-state", "available");
}

test("fixture-backed Activity desktop views and synchronized inspection", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport: { width: 1440, height: 900 } });
  await openExplorer(page, URLS.v2);
  await focusCards(page);
  await capture(page, "1440x900-activity-off");
  await page.locator("[data-market-explorer-focus-tool-button='market-activity']").click();
  await expect(page.locator("[data-market-activity-pane]")).toBeVisible();
  await expect(page.locator("[data-market-activity-series='sales']")).toBeVisible();
  await capture(page, "1440x900-sales-partial");
  const before = net.requests.length;
  await page.locator("[data-market-performance-chart]").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator("[data-market-performance-tooltip]")).toBeVisible();
  await expect(page.locator("[data-market-activity-inspection]")).not.toContainText("Move across");
  expect(net.requests.length).toBe(before);
  await capture(page, "1440x900-synchronized-date-tooltip");
  await page.getByRole("tab", { name: "Offered Supply" }).click();
  await expect(page.locator("[data-market-activity-series='supply']")).toBeVisible();
  await capture(page, "1440x900-offered-supply");
  await page.keyboard.press("Escape");
  await page.locator("[data-market-explorer-active-chip]").filter({ hasText: "Sealed Market" }).locator("[data-market-explorer-active-focus]").click();
  await expect(page.locator("[data-market-explorer-focus-tool='market-activity']")).toHaveAttribute("data-focus-tool-state", "unavailable");
  await expect(page.locator("[data-market-activity-pane]")).toHaveCount(0);
  await capture(page, "1440x900-activity-unavailable");
  await context.close();
});

test("fixture-backed Activity remains readable at laptop and mobile widths", async ({ browser }) => {
  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const mobile = viewport.width === 390;
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport, mobile });
    await openExplorer(page, URLS.v2);
    await focusCards(page);
    await page.locator("[data-market-explorer-focus-tool-button='market-activity']").click();
    await expect(page.locator("[data-market-activity-pane]")).toBeVisible();
    await capture(page, `${viewport.width}x${viewport.height}-activity`);
    await context.close();
  }
});
