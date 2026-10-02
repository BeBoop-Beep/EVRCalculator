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
  const focus = cards.locator("[data-market-explorer-active-focus]");
  // A fixture capability may establish the first active card market as the
  // current focus before hydration completes. Respect the toggle contract and
  // click only when the chip is not already focused.
  if ((await focus.getAttribute("aria-pressed")) !== "true") await focus.click();
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
  await expect(page.locator("[data-market-activity-crosshair]")).toHaveCount(1);
  await expect(page.locator("[data-market-activity-crosshair]")).toHaveAttribute("stroke", /\S/);
  expect(net.requests.length).toBe(before);
  await capture(page, "1440x900-synchronized-date-tooltip");
  await expect(page.locator("[data-market-activity-tooltip]")).toContainText("Listings observed");
  await capture(page, "1440x900-listed-supply");
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-market-activity-tooltip]")).toHaveCount(0);
  await expect(page.locator("[data-market-activity-crosshair]")).toHaveCount(0);
  await context.close();
});

test("fixture-backed Activity remains readable at laptop and mobile widths", async ({ browser }) => {
  for (const viewport of [{ width: 1728, height: 1000 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }, { width: 834, height: 1194 }, { width: 768, height: 1024 }, { width: 412, height: 915 }, { width: 390, height: 844 }, { width: 844, height: 390 }]) {
    const mobile = viewport.width <= 412;
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport, mobile });
    await openExplorer(page, URLS.v2);
    await focusCards(page);
    await page.locator("[data-market-chart-view='activity']").click();
    await expect(page.locator("[data-market-activity-chart]")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.locator("[data-market-activity-chart]").focus();
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("[data-market-activity-crosshair]")).toHaveCount(1);
    if ([1728, 1024, 390, 844].includes(viewport.width)) await capture(page, `${viewport.width}x${viewport.height}-activity`);
    await context.close();
  }
});
