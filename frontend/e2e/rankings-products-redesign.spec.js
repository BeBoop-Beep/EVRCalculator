import { expect, test } from "@playwright/test";

const identity = (id, name, setName, familyKey, familyName) => ({ sealedProductId: id, productName: name, setId: `s-${id}`, setName, setCanonicalKey: setName.toLowerCase().replaceAll(" ", "-"), familyKey, familyName, packCount: 1 });
const scores = { status: "available", marketDate: "2026-09-28", rows: [
  { ...identity("box", "Temporal Forces Booster Box", "Temporal Forces", "booster_box", "Booster Box"), rank: 1, rankScope: "full_market", cohortSize: 3, ripScore: { score: 7.38, tier: "A", rank: 1, cohortSize: 3, benchmarkPosition: "above", deltaVsBenchmark: 2.38 }, financialRip: 31.4, setChaseAccessibility: 6.2, parentSetCollector: 5.9 },
  { ...identity("pack", "Twilight Masquerade Booster Pack", "Twilight Masquerade", "loose_booster_pack", "Booster Pack"), rank: 2, rankScope: "full_market", cohortSize: 3, ripScore: { score: 4.4, tier: "D", rank: 2, cohortSize: 3, benchmarkPosition: "below", deltaVsBenchmark: -0.6 }, financialRip: 18.2, setChaseAccessibility: 4.8, parentSetCollector: 5.1 },
  { ...identity("etb", "Paldea Evolved Elite Trainer Box", "Paldea Evolved", "elite_trainer_box", "Elite Trainer Box"), rank: 3, rankScope: "full_market", cohortSize: 3, ripScore: { score: 5.1, tier: "C", rank: 3, cohortSize: 3, benchmarkPosition: "above", deltaVsBenchmark: 0.1 }, financialRip: 20, setChaseAccessibility: 5, parentSetCollector: 5.2 },
] };
const economics = { status: "available", marketDate: "2026-09-28", rows: [
  { ...identity("box", "Temporal Forces Booster Box", "Temporal Forces", "booster_box", "Booster Box"), unitPrice: 312.94, bestOpenPrice: 281.5, bestOpenStatus: "resolved_below_market", bestOpenPriceGapDollars: 31.44, bestOpenPriceGapPercent: .1005, bestOpenSourceMarketDate: "2026-09-08", bestOpenFreshnessStatus: "older", expectedValuePerPack: 5.5, modeledReturnOnSpend: .516, chanceToRecoverCost: .072 },
  { ...identity("pack", "Twilight Masquerade Booster Pack", "Twilight Masquerade", "loose_booster_pack", "Booster Pack"), unitPrice: 6, bestOpenPrice: 7.5, bestOpenStatus: "current_number_one_with_headroom", bestOpenPriceGapDollars: 1.5, bestOpenPriceGapPercent: .25, bestOpenSourceMarketDate: "2026-09-08", bestOpenFreshnessStatus: "older", expectedValuePerPack: 3.5, modeledReturnOnSpend: .583, chanceToRecoverCost: .09 },
  { ...identity("etb", "Paldea Evolved Elite Trainer Box", "Paldea Evolved", "elite_trainer_box", "Elite Trainer Box"), unitPrice: 50, bestOpenPrice: null, bestOpenStatus: "unavailable", bestOpenPriceGapDollars: null, bestOpenPriceGapPercent: null, bestOpenSourceMarketDate: "2026-09-08", bestOpenFreshnessStatus: "older", expectedValuePerPack: 4.2, modeledReturnOnSpend: .42, chanceToRecoverCost: .05 },
] };

async function mockPlus(page, calls) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "plus", email: "plus@example.test", index_plan: "plus" } }) }));
  await page.route("**/api/explore/product-rankings/scores", (route) => { calls.scores += 1; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scores) }); });
  await page.route("**/api/explore/product-rankings/economics", (route) => { calls.economics += 1; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(economics) }); });
}
async function openAsPlus(page) { const auth = page.waitForResponse((response) => response.url().endsWith("/api/auth/me") && response.status() === 200); await page.goto("http://127.0.0.1:3017/Rankings", { waitUntil: "networkidle" }); await auth; }

test("desktop Products split loads each authority once and filters locally", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 }); const calls = { scores: 0, economics: 0 }; await mockPlus(page, calls); await openAsPlus(page);
  const productsStart = Date.now(); await page.getByRole("radio", { name: "Products", exact: true }).click(); await expect(page.getByRole("heading", { name: "Product Scores" })).toBeVisible(); const scoresMs = Date.now() - productsStart;
  expect(calls).toEqual({ scores: 1, economics: 0 }); await expect(page.getByText("7.4", { exact: true }).first()).toBeVisible(); await expect(page.getByText("#1 Full Market", { exact: true })).toHaveCount(0); await expect(page.locator("body")).not.toContainText("Above Full Market benchmark");
  const economicsStart = Date.now(); await page.getByRole("radio", { name: "Economics", exact: true }).click(); await expect(page.getByRole("heading", { name: "Product Economics" })).toBeVisible(); const economicsMs = Date.now() - economicsStart;
  expect(calls).toEqual({ scores: 1, economics: 1 }); await expect(page.getByText("$281.50", { exact: true }).first()).toBeVisible(); await expect(page.getByText("Best-Open as of Sep 8, 2026 · independently dated")).toBeVisible();
  await page.getByRole("radio", { name: "Scores", exact: true }).click(); await page.getByRole("radio", { name: "Economics", exact: true }).click(); await page.getByPlaceholder("Search Products…").fill("Temporal"); await page.getByRole("button", { name: "Booster Box", exact: true }).click(); await page.getByRole("button", { name: "Unit Price", exact: true }).click(); expect(calls).toEqual({ scores: 1, economics: 1 });
  console.log(`[product-performance] Products→Scores ${scoresMs}ms; Scores→Economics ${economicsMs}ms; repeat switches 0 requests`);
  await expect(page.locator("body")).not.toContainText("Typical Opening"); await expect(page.locator("body")).not.toContainText("Typical Retention"); await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

test("mobile Scores and Economics cards have no page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); const calls = { scores: 0, economics: 0 }; await mockPlus(page, calls); await openAsPlus(page); await page.getByRole("radio", { name: "Products", exact: true }).click(); await expect(page.locator("[data-product-score-card]").first()).toBeVisible(); await page.getByRole("radio", { name: "Economics", exact: true }).click(); await expect(page.locator("[data-product-economics-card]").first()).toBeVisible(); await expect(page.getByText("$281.50", { exact: true }).last()).toBeVisible(); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); expect(calls).toEqual({ scores: 1, economics: 1 }); await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

test("anonymous Products lock before either paid request", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 }); const calls = { scores: 0, economics: 0 }; page.on("request", (request) => { if (request.url().includes("/product-rankings/scores")) calls.scores += 1; if (request.url().includes("/product-rankings/economics")) calls.economics += 1; }); await page.goto("http://127.0.0.1:3017/Rankings", { waitUntil: "networkidle" }); await page.getByRole("radio", { name: "Products", exact: true }).click(); await expect(page.locator("[data-product-rankings-locked]")).toBeVisible(); expect(calls).toEqual({ scores: 0, economics: 0 });
});

test("Basic Products lock before either paid request", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 }); const calls = { scores: 0, economics: 0 }; await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "basic", email: "basic@example.test", index_plan: null } }) })); page.on("request", (request) => { if (request.url().includes("/product-rankings/scores")) calls.scores += 1; if (request.url().includes("/product-rankings/economics")) calls.economics += 1; }); const auth = page.waitForResponse((response) => response.url().endsWith("/api/auth/me") && response.status() === 200); await page.goto("http://127.0.0.1:3017/Rankings", { waitUntil: "networkidle" }); await auth; await page.getByRole("radio", { name: "Products", exact: true }).click(); await expect(page.locator("[data-product-rankings-locked]")).toBeVisible(); expect(calls).toEqual({ scores: 0, economics: 0 });
});
