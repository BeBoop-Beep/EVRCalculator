import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, URLS } from "./helpers.mjs";

const output = path.resolve(
  process.cwd(),
  "../backend/artifacts/market_explorer_acceptance/final_correction_20261002",
);

async function capture(page, name) {
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
}

test("Lifetime/All toolbar remains complete at desktop and mobile widths", async ({ browser }) => {
  for (const fixture of [
    { name: "desktop", viewport: { width: 1440, height: 900 }, mobile: false },
    { name: "mobile", viewport: { width: 390, height: 844 }, mobile: true },
  ]) {
    const { context, page } = await newSession(browser, {
      base: URLS.v2,
      plan: "premium",
      viewport: fixture.viewport,
      mobile: fixture.mobile,
    });
    await openExplorer(page, URLS.v2);
    const all = page.locator('[data-market-window-value="All"]');
    await expect(all).toBeVisible();
    await all.click();
    await expect(all).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("[data-market-explorer-all-span-note]")).toBeVisible();
    await capture(page, `${fixture.name}-all-history-toolbar`);
    await context.close();
  }
});

test("exact-market edit footer presents neutral secondary actions", async ({ browser }) => {
  const { context, page } = await newSession(browser, {
    base: URLS.v2,
    plan: "premium",
    viewport: { width: 1440, height: 900 },
  });
  await openExplorer(page, URLS.v2);
  await page.route("**/api/market/explorer/instruments/search**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            asset: "cards",
            instrumentId: "var-gengar",
            name: "Fixture Gengar",
            setName: "Fossil",
            cardNumber: "5",
            rarity: "Rare Holo",
          },
        ],
      }),
    }),
  );
  await page.locator("[data-market-explorer-build-trigger]").click();
  await page.locator("[data-market-exact-search]").fill("gengar");
  const result = page.getByRole("option").first();
  await expect(result).toBeVisible();
  await result.click();
  await page.getByRole("button", { name: "Build Market", exact: true }).click();
  const edit = page.locator("[data-market-explorer-active-edit]").first();
  await expect(edit).toBeVisible();
  await edit.click();
  const cancel = page.locator("[data-market-exact-cancel-edit]");
  const save = page.locator("[data-market-exact-save-as-new]");
  const update = page.getByRole("button", { name: "Update Market", exact: true });
  await expect(cancel).toBeVisible();
  await expect(save).toBeVisible();
  await expect(update).toBeVisible();
  await expect(cancel).toHaveCSS("color", "rgb(232, 238, 247)");
  await expect(save).toHaveCSS("color", "rgb(232, 238, 247)");
  await expect(update).toHaveCSS("color", "rgb(45, 212, 191)");
  await capture(page, "desktop-edit-footer-actions");
  await context.close();
});
