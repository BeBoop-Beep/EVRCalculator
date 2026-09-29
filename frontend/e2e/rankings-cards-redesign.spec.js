import { expect, test } from "@playwright/test";

const collectorFacets = { status: "available", lens: "collector", eras: [
  { eraId: "vintage", eraName: "Wizards", canonicalKey: "wizards" },
  { eraId: "modern", eraName: "Scarlet & Violet", canonicalKey: "scarlet-violet" },
], sets: [
  { setId: "base", setName: "Base Set", canonicalKey: "base-set", eraId: "vintage" },
  { setId: "prismatic", setName: "Prismatic Evolutions", canonicalKey: "prismatic-evolutions", eraId: "modern" },
], rarities: [{ key: "Rare", name: "Rare" }, { key: "SIR", name: "Special Illustration Rare" }], subjectTypes: ["pokemon", "trainer", "neutral_functional"] };
const chaseFacets = { status: "available", lens: "chase", eras: [{ eraId: "modern", eraName: "Scarlet & Violet" }], sets: [{ setId: "prismatic", setName: "Prismatic Evolutions", canonicalKey: "prismatic-evolutions", eraId: "modern" }], rarities: [{ key: "SIR", name: "Special Illustration Rare" }] };
const overallRows = [
  { canonicalCardId: "giovanni", cardName: "Giovanni's Charisma", setId: "base", setName: "Base Set", setCanonicalKey: "base-set", rank: 1, collectorAppeal: 100, rarity: "Rare" },
  { canonicalCardId: "gengar", cardName: "Gengar ex", setId: "prismatic", setName: "Prismatic Evolutions", setCanonicalKey: "prismatic-evolutions", rank: 2, collectorAppeal: 98.4, rarity: "SIR" },
];
const componentRow = (lens) => ({ canonicalCardId: `${lens}-card`, cardName: lens === "pokemon" ? "Sylveon ex" : `${lens} card`, setId: "prismatic", setName: "Prismatic Evolutions", setCanonicalKey: "prismatic-evolutions", rank: 61, cohortSize: 15639, componentScore: 97.1, rarity: "SIR", artistNames: lens === "artist" ? ["Miki Tanaka"] : [] });
const chaseRows = [{ cardVariantId: "variant", canonicalCardId: "chase", cardName: "Umbreon ex", setId: "prismatic", rarity: "SIR", currentNearMintMarketPrice: 400, exactPullProbability: .001, chaseSpend50: 693, costMultiple50: 1.73, chaseEfficiency: .86, ranks: { overall: { rank: 7 } } }];

async function mockPlan(page, plan, calls) {
  await page.route("**/api/auth/me", (route) => plan === "anonymous"
    ? route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ user: null }) })
    : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: { id: plan || "basic", email: "fixture@example.test", index_plan: plan } }) }));
  await page.route("**/api/explore/card-ranking-facets?*", (route) => { const lens = new URL(route.request().url()).searchParams.get("lens"); calls[`${lens}Facets`]++; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(lens === "collector" ? collectorFacets : chaseFacets) }); });
  await page.route("**/api/explore/card-collector-appeal?*", (route) => { calls.collectorRows++; const url = new URL(route.request().url()); const lens = url.searchParams.get("lens") || "overall"; const rows = lens === "overall" ? overallRows : [componentRow(lens)]; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ available: true, lens, rankSemantics: lens === "overall" ? "published_global_overall" : "global_component_cohort", page: 1, total: rows.length, totalPages: 1, rows }) }); });
  await page.route("**/api/explore/card-chase-efficiency?*", (route) => { calls.chaseRows++; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ available: true, page: 1, total: 1, totalPages: 1, rows: chaseRows }) }); });
}
async function openCards(page) {
  await page.goto("http://127.0.0.1:3018/Rankings", { waitUntil: "networkidle" });
  await page.getByRole("radio", { name: "Cards", exact: true }).click();
}

test("Plus Collector desktop keeps canonical ranks and vintage authority", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const calls = { collectorFacets: 0, chaseFacets: 0, collectorRows: 0, chaseRows: 0 };
  await mockPlan(page, "plus", calls); await openCards(page);
  await expect(page.getByRole("radio", { name: "Overall", exact: true })).toBeChecked();
  await expect(page.getByRole("link", { name: "Giovanni's Charisma", exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Pokémon", exact: true }).click();
  await expect(page.getByRole("link", { name: "Sylveon ex", exact: true })).toBeVisible(); await expect(page.getByText("#61").first()).toBeVisible();
  await page.locator('[data-multi-select-trigger="card-set"]').click();
  await page.locator('[data-multi-select-search="card-set"]').fill("Base Set");
  await expect(page.locator('[data-multi-select-option="base"]')).toContainText("Base Set");
  await page.keyboard.press("Escape");
  await page.locator('[data-multi-select-trigger="card-set"]').click(); await page.locator('[data-multi-select-option="prismatic"]').click(); await page.keyboard.press("Escape");
  await expect(page.getByText("#61").first()).toBeVisible();
  await expect.poll(() => calls.collectorRows).toBe(3);
  expect(calls).toEqual({ collectorFacets: 1, chaseFacets: 0, collectorRows: 3, chaseRows: 0 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

test("Premium mobile uses separate Chase facets without Collector vintage sets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = { collectorFacets: 0, chaseFacets: 0, collectorRows: 0, chaseRows: 0 };
  await mockPlan(page, "premium", calls); await openCards(page);
  await page.getByRole("radio", { name: "Chase Efficiency", exact: true }).click();
  await expect(page.locator(".desk\\:hidden h3", { hasText: "Umbreon ex" })).toBeVisible();
  await page.locator('[data-multi-select-trigger="card-set"]').click();
  await expect(page.locator('[data-multi-select-popover="card-set"]')).not.toContainText("Base Set");
  expect(calls.collectorFacets).toBe(1); expect(calls.chaseFacets).toBe(1); expect(calls.chaseRows).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
});

for (const [name, plan] of [["Anonymous", "anonymous"], ["Basic", null]]) test(`${name} makes zero paid Card requests`, async ({ page }) => {
  const calls = { collectorFacets: 0, chaseFacets: 0, collectorRows: 0, chaseRows: 0 };
  await mockPlan(page, plan, calls); await openCards(page);
  await expect(page.locator("[data-card-collector-appeal-locked]")).toBeVisible();
  await page.getByRole("radio", { name: "Chase Efficiency", exact: true }).click();
  await expect(page.locator("[data-card-chase-efficiency-locked]")).toBeVisible();
  expect(calls).toEqual({ collectorFacets: 0, chaseFacets: 0, collectorRows: 0, chaseRows: 0 });
});
