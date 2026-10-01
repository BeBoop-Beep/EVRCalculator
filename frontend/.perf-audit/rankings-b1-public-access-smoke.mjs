import { chromium } from "@playwright/test";

const origin = process.env.RANKINGS_B1_ORIGIN || "http://127.0.0.1:3107";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on("console", (message) => { if (message.type() === "error") console.error(`browser-console: ${message.text()}`); });
page.on("pageerror", (error) => console.error(`browser-pageerror: ${error.message}`));
const headline = (type) => ({ status: "available", entityType: type, marketDate: "2026-09-28", rows: type === "set" ? [{ entityId: "s1", name: "Alpha Set", canonicalKey: "alpha-set", era: { eraId: "e1", eraName: "Alpha Era" }, overall: { score: 7.2, rank: 1, cohortSize: 1, tier: "S", status: "available" } }] : [{ entityId: "e1", name: "Alpha Era", canonicalKey: "alpha-era", modeledSetCount: 1, overall: { score: 7.1, rank: 1, cohortSize: 1, tier: "S", status: "available" } }] });

await page.route("**/api/auth/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ message: "Not authenticated" }) }));
await page.route("**/api/tcgs/pokemon/rankings/headlines?entity_type=*", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(headline(new URL(route.request().url()).searchParams.get("entity_type"))) }));
await page.route("**/api/tcgs/pokemon/rankings/pack-economics-preview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "available", openingEconomicsMarketDate: "2026-09-28", sets: [{ setId: "s1", setName: "Alpha Set", canonicalKey: "alpha-set", era: { eraName: "Alpha Era" }, productFamilyCount: 2, productCount: 3, averagePackCostPerPack: 4.5 }] }) }));
await page.route("**/api/tcgs/pokemon/rankings/product-catalogue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "available", rows: [{ sealedProductId: "p2", productName: "Zulu Booster Box", setId: "s1", setName: "Alpha Set", familyKey: "booster_box", familyName: "Booster Box" }, { sealedProductId: "p1", productName: "Alpha Elite Trainer Box", setId: "s1", setName: "Alpha Set", familyKey: "elite_trainer_box", familyName: "Elite Trainer Box" }] }) }));

await page.goto(`${origin}/Rankings`, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(1000);
console.log(JSON.stringify({ url: page.url(), title: await page.title(), text: (await page.locator("body").innerText()).slice(0, 500) }));
await page.getByText("Eras", { exact: true }).first().click();
await page.getByText("Alpha Era", { exact: true }).first().waitFor();
await page.getByText("Sets", { exact: true }).first().click();
await page.getByText("Alpha Set", { exact: true }).first().waitFor();
await page.getByText("Pack Economics", { exact: true }).first().click();
await page.locator('[data-pack-economics-entitled="false"]').waitFor();
if (await page.getByText("$4.50", { exact: true }).count() < 1) throw new Error("public average pack cost missing");
if (await page.getByText("Locked", { exact: true }).count() < 1) throw new Error("protected Set metrics are not locked");
await page.getByText("Products", { exact: true }).first().click();
await page.locator("[data-product-public-catalogue]").waitFor();
const names = await page.locator("[data-product-public-catalogue] tbody tr td:first-child").allTextContents();
if (!names[0]?.includes("Alpha") || !names[1]?.includes("Zulu")) throw new Error(`catalogue is not alphabetical: ${names.join(" | ")}`);
await page.getByText("Economics", { exact: true }).first().click();
await page.locator("[data-product-public-catalogue]").waitFor();
if (await page.getByText("Locked", { exact: true }).count() < 1) throw new Error("protected Product metrics are not locked");
console.log(JSON.stringify({ status: "PASS", eras: true, sets: true, packPreview: true, productAlphabetical: names, productLockedCells: true }));
await browser.close();
