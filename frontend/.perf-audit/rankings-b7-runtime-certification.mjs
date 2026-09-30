import { chromium } from "@playwright/test";

const origin = process.env.RANKINGS_B7_ORIGIN || "http://127.0.0.1:3107";
const evidence = "../docs/rankings/closure_20260930/b7/evidence";
const samples = [];

const headline = (type) => ({
  status: "available",
  entityType: type,
  marketDate: "2026-09-28",
  rows: type === "set"
    ? [{ entityId: "s1", name: "Alpha Set", canonicalKey: "alpha-set", era: { eraId: "e1", eraName: "Alpha Era" }, artwork: { logoUrl: "/images/pokemon/sets/alpha.png", symbolUrl: null }, overall: { score: 7.2, rank: 1, cohortSize: 1, tier: "S", status: "available" } }]
    : [{ entityId: "e1", name: "Alpha Era", canonicalKey: "alpha-era", modeledSetCount: 1, overall: { score: 7.1, rank: 1, cohortSize: 1, tier: "S", status: "available" } }],
});

const publicResponses = [];
const surfaceResponses = [];
async function installAnonymousRoutes(page) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ message: "Not authenticated" }) }));
  await page.route("**/api/tcgs/pokemon/rankings/headlines?entity_type=*", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(headline(new URL(route.request().url()).searchParams.get("entity_type"))) }));
  await page.route("**/api/tcgs/pokemon/rankings/pack-economics-preview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "available", openingEconomicsMarketDate: "2026-09-28", sets: [{ setId: "s1", setName: "Alpha Set", canonicalKey: "alpha-set", era: { eraName: "Alpha Era" }, productFamilyCount: 2, productCount: 3, averagePackCostPerPack: 4.5 }] }) }));
  await page.route("**/api/tcgs/pokemon/rankings/product-catalogue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "available", rows: [{ sealedProductId: "p2", productName: "Zulu Booster Box", setId: "s1", setName: "Alpha Set", familyKey: "booster_box", familyName: "Booster Box" }, { sealedProductId: "p1", productName: "Alpha Elite Trainer Box", setId: "s1", setName: "Alpha Set", familyKey: "elite_trainer_box", familyName: "Elite Trainer Box" }] }) }));
  page.on("response", async (response) => {
    if (response.url().includes("/Rankings") && ["document", "fetch"].includes(response.request().resourceType())) {
      const body = await response.text().catch(() => "");
      surfaceResponses.push({ url: response.url(), status: response.status(), bytes: Buffer.byteLength(body), body });
    }
    if (!response.url().includes("/api/tcgs/pokemon/rankings/")) return;
    const text = await response.text().catch(() => "");
    publicResponses.push({ url: response.url(), status: response.status(), bytes: Buffer.byteLength(text), text });
  });
}

async function certify(viewport, label) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport });
  await installAnonymousRoutes(page);
  const pageStarted = performance.now();
  await page.goto(`${origin}/Rankings`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(1_000);
  const initialPageMs = performance.now() - pageStarted;
  const overviewUnavailableCount = await page.getByText("Temporarily unavailable.", { exact: true }).count();
  const graphLocked = await page.locator("[data-financial-rip-history-locked]").count();
  if (label === "desktop") await page.screenshot({ path: `${evidence}/anonymous-desktop-overview.png`, fullPage: true });
  await page.getByText("Eras", { exact: true }).first().click();
  await page.locator("[data-era-rankings]").waitFor({ state: "attached" });
  if (label === "desktop") await page.screenshot({ path: `${evidence}/anonymous-desktop-eras.png`, fullPage: true });
  await page.getByText("Sets", { exact: true }).first().click();
  await page.locator("[data-set-rankings-hub]").waitFor({ state: "attached" });
  if (label === "desktop") await page.screenshot({ path: `${evidence}/anonymous-desktop-sets.png`, fullPage: true });
  const scoresStarted = performance.now();
  await page.getByText("Products", { exact: true }).first().click();
  await page.locator("[data-product-public-catalogue]").waitFor({ state: "attached" });
  await page.getByRole("heading", { name: "Product Scores", exact: true }).waitFor();
  const scoresMs = performance.now() - scoresStarted;
  const names = await page.locator("[data-product-public-catalogue] tbody tr td:first-child").allTextContents();
  const economicsStarted = performance.now();
  await page.getByText("Economics", { exact: true }).first().click();
  await page.getByRole("heading", { name: "Product Economics", exact: true }).waitFor();
  const economicsMs = performance.now() - economicsStarted;
  const warmScoresStarted = performance.now();
  await page.getByText("Scores", { exact: true }).first().click();
  await page.getByRole("heading", { name: "Product Scores", exact: true }).waitFor();
  const warmScoresMs = performance.now() - warmScoresStarted;
  const warmEconomicsStarted = performance.now();
  await page.getByText("Economics", { exact: true }).first().click();
  await page.getByRole("heading", { name: "Product Economics", exact: true }).waitFor();
  const warmEconomicsMs = performance.now() - warmEconomicsStarted;
  await page.screenshot({ path: `${evidence}/anonymous-${label}-products.png`, fullPage: true });
  const dom = await page.locator("body").innerText();
  const attributes = await page.locator("body").evaluate((body) => [...body.querySelectorAll("*")].flatMap((element) => [...element.attributes].map((attribute) => `${attribute.name}=${attribute.value}`)).join("\n"));
  const attributeLeaks = ["financialRip", "collectorAppeal", "chaseAccessibility", "ripScore", "expectedValuePerPack", "modeledReturnOnSpend", "chanceToRecoverCost", "bestOpenPrice"].filter((key) => attributes.includes(key));
  samples.push({ label, initialPageMs, scoresMs, economicsMs, warmScoresMs, warmEconomicsMs, overviewUnavailableCount, graphLocked, names, selectedControl: await page.locator('[aria-label="Product Rankings view"] [aria-checked="true"]').textContent(), lockedCells: await page.getByText("Locked", { exact: true }).count(), domLength: dom.length, attributesLength: attributes.length, attributeLeaks });
  await browser.close();
}

await certify({ width: 1440, height: 1000 }, "desktop");
await certify({ width: 390, height: 844 }, "mobile");

const forbiddenKeys = ["financialRip", "collectorAppeal", "chaseAccessibility", "ripScore", "expectedValuePerPack", "modeledReturnOnSpend", "chanceToRecoverCost", "bestOpenPrice"];
const responseLeaks = publicResponses.flatMap((response) => forbiddenKeys.filter((key) => response.text.includes(`\"${key}\"`)).map((key) => ({ url: response.url, key })));
const surfaceLeaks = surfaceResponses.flatMap((response) => forbiddenKeys.filter((key) => response.body.includes(`\"${key}\"`)).map((key) => ({ url: response.url, key })));
console.log(JSON.stringify({ status: responseLeaks.length || surfaceLeaks.length ? "FAIL" : "PASS", samples, publicResponses: publicResponses.map(({ url, status, bytes }) => ({ url, status, bytes })), surfaceResponses: surfaceResponses.map(({ url, status, bytes }) => ({ url, status, bytes })), responseLeaks, surfaceLeaks }, null, 2));
