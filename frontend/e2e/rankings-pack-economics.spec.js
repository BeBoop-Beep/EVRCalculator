import { expect, test } from "@playwright/test";

const metric = { score: 6.2, rank: 1, cohortSize: 1, tier: "B", benchmarkReferenceScore: 5, deltaVsBenchmark: 1.2, benchmarkPosition: "above" };
const scorecards = { status: "available", rows: [{ entityId: "s1", name: "Mega Evolution", canonicalKey: "mega-evolution", era: { eraId: "e1", eraName: "Mega Evolution" }, overall: metric, financial: metric, collector: metric, chase: metric }] };
const contract = { status: "available", openingEconomicsMarketDate: "2026-09-28", bestOpenSourceMarketDate: "2026-09-08", bestOpenFreshnessStatus: "older", sets: [{ setId: "s1", setName: "Mega Evolution", canonicalKey: "mega-evolution", era: { eraId: "e1", eraName: "Mega Evolution" }, productFamilyCount: 2, productCount: 3, averagePackCostPerPack: 13.24, expectedValuePerPack: 8.56, modeledReturnOnSpend: .647, chanceToRecoverCost: .062, entertainmentCostPerPack: 4.68, families: [{ familyKey: "booster_bundle", familyName: "Booster Bundle", productCount: 1, averagePackCostPerPack: 13.24, expectedValuePerPack: 8.56, modeledReturnOnSpend: .647, chanceToRecoverCost: .062, entertainmentCostPerPack: 4.68, bestOpenDisplayMode: "single", products: [{ sealedProductId: "p1", productName: "Ascended Heroes Booster Bundle", marketPrice: 90.62, bestOpenPrice: 79.41, bestOpenSourceMarketDate: "2026-09-08", bestOpenFreshnessStatus: "older" }] }, { familyKey: "elite_trainer_box", familyName: "Elite Trainer Box", productCount: 2, averagePackCostPerPack: 8, expectedValuePerPack: 5, modeledReturnOnSpend: .625, chanceToRecoverCost: .05, entertainmentCostPerPack: 3, bestOpenDisplayMode: "multiple", products: [{ sealedProductId: "p2", productName: "Mega Evolution ETB A", marketPrice: 60, bestOpenPrice: 54.31 }, { sealedProductId: "p3", productName: "Mega Evolution ETB B", marketPrice: 61, bestOpenPrice: 55.29 }] }] }] };

async function mockPlus(page, counts) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: "plus", email: "plus@example.test", index_plan: "plus" } }) }));
  await page.route("**/api/tcgs/pokemon/rankings/scorecards?entity_type=set", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scorecards) }));
  await page.route("**/api/tcgs/pokemon/rankings/pack-economics", (route) => { counts.pack += 1; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(contract) }); });
}

async function openRankingsAsPlus(page) {
  const authReady = page.waitForResponse((response) => response.url().endsWith("/api/auth/me") && response.status() === 200);
  await page.goto("http://127.0.0.1:3016/Rankings", { waitUntil: "networkidle" });
  await authReady;
}

test("desktop hierarchy aligns and reuses one Pack Economics payload", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const counts = { pack: 0 }; await mockPlus(page, counts);
  await openRankingsAsPlus(page);
  await page.getByRole("radio", { name: "Sets", exact: true }).click();
  await page.getByRole("button", { name: "Pack Economics", exact: true }).click();
  await expect(page.getByPlaceholder("Search Sets…")).toBeVisible();
  await expect(page.getByText("Best-Open as of 2026-09-08 · independently dated")).toBeVisible();
  await page.getByRole("button", { name: "View Product Families for Mega Evolution" }).click();
  const table = page.getByRole("table");
  await expect(table.getByText("2 prices", { exact: true })).toBeVisible();
  await expect(table.getByText("$79.41", { exact: true }).first()).toBeVisible();
  await expect(table.getByText("$54.31", { exact: true })).toBeVisible();
  await expect(table.getByText("$55.29", { exact: true })).toBeVisible();
  const positions = await page.evaluate(() => ["[data-set-pack-parent-row]", "[data-pack-family-row]", "[data-pack-product-row]"].map((selector) => [...document.querySelector(selector).children].map((cell) => Math.round(cell.getBoundingClientRect().x))));
  expect(positions[1]).toEqual(positions[0]); expect(positions[2]).toEqual(positions[0]);
  await page.getByRole("button", { name: "Modeled Return", exact: true }).click();
  await page.getByPlaceholder("Search Sets…").fill("Mega");
  await page.getByRole("button", { name: "Financial", exact: true }).click();
  await page.getByRole("button", { name: "Pack Economics", exact: true }).click();
  expect(counts.pack).toBe(1);
  await expect(page.locator("body")).not.toContainText("Typical Opening");
  await expect(page.locator("body")).not.toContainText("Typical Retention");
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

test("mobile hierarchy remains readable without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const counts = { pack: 0 }; await mockPlus(page, counts);
  await openRankingsAsPlus(page);
  await page.getByRole("radio", { name: "Sets", exact: true }).click();
  await page.getByRole("button", { name: "Pack Economics", exact: true }).click();
  await page.getByRole("button", { name: "View Product Families for Mega Evolution" }).click();
  for (const value of ["$79.41", "$54.31", "$55.29"]) await expect(page.getByText(value, { exact: true }).last()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(counts.pack).toBe(1);
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

test("anonymous access locks before any Pack Economics request", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 }); let calls = 0;
  page.on("request", (request) => { if (request.url().includes("/rankings/pack-economics")) calls += 1; });
  await page.goto("http://127.0.0.1:3016/Rankings", { waitUntil: "networkidle" });
  await page.getByRole("radio", { name: "Sets", exact: true }).click();
  await expect(page.getByText("Benchmark Set Rankings are available with Index Plus or Premium.")).toBeVisible();
  expect(calls).toBe(0);
});
