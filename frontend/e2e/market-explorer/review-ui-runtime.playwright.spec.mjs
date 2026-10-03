import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, chooseCategory, URLS } from "./helpers.mjs";

const evidenceDir = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/explorer_review_ui_runtime_20261003");
fs.mkdirSync(evidenceDir, { recursive: true });

test("Rankings surfaces emit no controlled-input, nesting, or hydration errors", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${URLS.v2}/Explore/rip-statistics`, { waitUntil: "networkidle" });
  await expect(page.locator("body")).toContainText(/Rankings|Product Lens|Opening Economics/i);
  await page.screenshot({ path: path.join(evidenceDir, "rankings-runtime.png"), fullPage: true });
  expect(errors.filter((message) => /value prop.*onChange|descendant of <p>|nested <div>|hydration/i.test(message))).toEqual([]);
  await context.close();
});

test("Explorer corrective UI behavior and naming", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium", viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await openExplorer(page, URLS.v2);

  const rarity = page.locator("[data-rarity-market-trigger]");
  const rarityPanel = page.locator('[data-market-asset-selector-popover="rarities"]');
  await rarity.click(); await expect(rarityPanel).toBeVisible();
  await rarity.click(); await expect(rarityPanel).toBeHidden();
  await rarity.click(); await page.keyboard.press("Escape"); await expect(rarityPanel).toBeHidden();
  await rarity.click();
  await rarityPanel.locator("input").click();
  await rarityPanel.locator("[data-market-asset-selector-scroll-region]").dispatchEvent("wheel", { deltaY: 120 });
  await expect(rarityPanel).toBeVisible();
  await page.locator("[data-market-explorer-chart-workspace]").click({ position: { x: 5, y: 5 } });
  await expect(rarityPanel).toBeHidden();

  await chooseCategory(page, "sets");
  const cardRow = page.locator('[data-prepared-market="set:set-prismatic"]');
  await expect(cardRow).toContainText("Prismatic Evolutions Card Market");
  await cardRow.click();
  await expect(page.locator('[data-market-explorer-active-chip="set:set-prismatic"]')).toContainText("Prismatic Evolutions Card Market");

  await page.locator('[data-market-directory-asset="sealed"]').click();
  const sealedTypes = page.locator("[data-sealed-types-trigger]");
  await sealedTypes.click(); await expect(page.locator('[data-market-asset-selector-popover="sealed-types"]')).toBeVisible();
  await sealedTypes.click(); await expect(page.locator('[data-market-asset-selector-popover="sealed-types"]')).toBeHidden();
  await chooseCategory(page, "sets");
  const sealedRow = page.locator('[data-prepared-market="sealed-set:set-prismatic"]');
  await expect(sealedRow).toContainText("Prismatic Evolutions Sealed Market");

  await page.locator("[data-market-explorer-build-trigger]").click();
  await expect(page.locator('[data-market-explorer-build-path="exact"]')).toBeVisible();
  await expect(page.getByText("Cards & Products", { exact: true })).toBeVisible();
  await expect(page.getByText("Custom Filters", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Demand Pressure", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Performance", exact: true })).toHaveCount(1);
  await page.screenshot({ path: path.join(evidenceDir, "explorer-corrective-ui.png"), fullPage: true });
  expect(errors.filter((message) => !message.startsWith("Failed to load resource:"))).toEqual([]);
  await context.close();
});
