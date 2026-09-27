// LIVE-ANONYMOUS spot checks: real Next frontend against a REAL backend, anonymous only
// (no credentials, no paid states). Gated: EXPLORER_LIVE=1 EXPLORER_LIVE_URL=http://127.0.0.1:3200
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, pickRow, chooseCategory, shot, URLS } from "./helpers.mjs";

test.skip(process.env.EXPLORER_LIVE !== "1", "set EXPLORER_LIVE=1 to run against a live backend");

test("live anonymous: V1 Sealed IA, locked constituents, Raw truthfulness, single Clear All", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.liveAnon });
  await openExplorer(page, URLS.liveAnon);
  await page.locator('[data-market-directory-asset="sealed"]').click();
  const cats = await page.locator("[data-market-directory-category]").evaluateAll((els) => els.map((el) => el.textContent.replace(/[▾\s]+$/g, "").trim()));
  expect(cats[0]).toBe("Sealed Markets");
  expect(cats.join("|")).not.toMatch(/Sets|Eras|Sealed Types/);
  await shot(page, "live-anon-sealed-v1");
  await page.locator('[data-market-directory-asset="cards"]').click();
  await pickRow(page, "sets", "Fossil");
  await expect(page.locator('[data-market-explorer-active-chip*="set:"]')).toContainText("Fossil — Cards", { timeout: 60000 });
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituents-state=locked]")).toBeVisible({ timeout: 60000 });
  await shot(page, "live-anon-constituents-locked");
  await page.click("[data-market-explorer-hide-details]");
  await expect(page.locator("[data-market-explorer-active-clear-all]")).toHaveCount(1);
  await page.click("[data-market-explorer-active-clear-all]");
  await expect(page.locator("[data-market-explorer-active-chip]")).toHaveCount(0);
  const failed = net.failed.filter((f) => f.url.startsWith("/api/market/explorer/prepared"));
  // Only the anonymous constituents 401 (a deliberate locked state) may remain.
  expect(failed.every((f) => f.status === 401 && f.url.includes("kind=constituents"))).toBe(true);
  console.log("LIVE FAILED REQUESTS", JSON.stringify(net.failed));
  await context.close();
});

test("live anonymous: Raw Card Market shows the truthful not-available state (default Raw chip)", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.liveAnon });
  await openExplorer(page, URLS.liveAnon);
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituents-not-inspectable-item='raw']")).toContainText("not available in the current published generation");
  await expect(page.locator("[data-market-constituents-page-loading]")).toHaveCount(0);
  await shot(page, "live-anon-raw-not-available");
  await context.close();
});
