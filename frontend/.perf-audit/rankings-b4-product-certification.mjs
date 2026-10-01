import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const origin = process.env.RANKINGS_B4_ORIGIN || "http://127.0.0.1:3107";
const evidenceDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/rankings/followup_20260930/b4/evidence");
mkdirSync(evidenceDir, { recursive: true });

const products = Array.from({ length: 60 }, (_, index) => {
  const n = index + 1;
  return { sealedProductId: `p-${String(n).padStart(2, "0")}`, productName: n === 1 ? "A Shrouded Fable Booster Pack" : n === 2 ? "B Tiny Recovery Booster Pack" : `Fixture Product ${String(n).padStart(2, "0")}`, setId: n % 2 ? "set-a" : "set-b", setName: n % 2 ? "Alpha Set" : "Beta Set", setCanonicalKey: n % 2 ? "alpha-set" : "beta-set", familyKey: n % 3 ? "loose_booster_pack" : "booster_box", familyName: n % 3 ? "Loose Booster Pack" : "Booster Box", rank: n, cohortSize: 60, ripScore: { scoreKind: "absolute", scoreScale: "0-100", scoreValue: n === 60 ? 99 : 55 - n / 10 }, financialRip: 40 + n / 10, chaseScore: n === 60 ? 99 : n === 1 ? 50 : 30 + n / 10, collectorAppeal: 70 + n / 10 };
});
const catalogue = [...products].map(({ rank, cohortSize, ripScore, financialRip, chaseScore, collectorAppeal, ...row }) => row).sort((a, b) => a.productName.localeCompare(b.productName));
const families = [{ value: "booster_box", label: "Booster Box" }, { value: "loose_booster_pack", label: "Loose Booster Pack" }];
const measurements = { responses: [], requests: [], timings: [], checks: {} };

function filtered(url, source) {
  const q = url.searchParams.get("search")?.toLowerCase() || "";
  const family = url.searchParams.get("family");
  return source.filter((row) => (!family || row.familyKey === family) && (!q || [row.productName, row.setName, row.familyName].some((v) => v.toLowerCase().includes(q))));
}
function pageContract(requestUrl, view) {
  const url = new URL(requestUrl); let rows = filtered(url, view === "public" ? catalogue : products);
  const sort = url.searchParams.get("sort") || (view === "scores" ? "rank" : "productName"); const direction = url.searchParams.get("direction") || "asc";
  const value = (row) => sort === "ripScore" ? row.ripScore?.scoreValue : row[sort];
  rows.sort((a, b) => { const av = value(a), bv = value(b); const result = typeof av === "string" ? av.localeCompare(bv) : av - bv; return (direction === "desc" ? -result : result) || a.rank - b.rank; });
  const page = Number(url.searchParams.get("page") || 1), pageSize = Number(url.searchParams.get("page_size") || 25), totalPages = Math.max(1, Math.ceil(rows.length / pageSize)), selectedPage = Math.min(page, totalPages);
  rows = rows.slice((selectedPage - 1) * pageSize, selectedPage * pageSize);
  if (view === "economics") rows = rows.map((row) => ({ sealedProductId: row.sealedProductId, productName: row.productName, setId: row.setId, setName: row.setName, setCanonicalKey: row.setCanonicalKey, familyKey: row.familyKey, familyName: row.familyName, unitPrice: row.sealedProductId === "p-01" ? 100 : 20 + row.rank, bestOpenPrice: row.sealedProductId === "p-01" ? 80 : 18 + row.rank, bestOpenMarketPrice: row.sealedProductId === "p-01" ? 100 : 20 + row.rank, bestOpenPriceGapDollars: 20, bestOpenPriceGapPercent: .2, bestOpenStatus: "resolved_below_market", bestOpenSourceMarketDate: "2026-09-29", bestOpenMarketSourceDate: "2026-09-30", bestOpenFreshnessStatus: "older", expectedValuePerPack: 4.25, modeledReturnOnSpend: .8, chanceToRecoverCost: row.sealedProductId === "p-01" ? .099126 : row.sealedProductId === "p-02" ? .000002 : .038 }));
  return { contractVersion: `rankings-products-${view}-v3`, status: "available", view, marketDate: "2026-09-30", page: selectedPage, pageSize, total: filtered(url, view === "public" ? catalogue : products).length, totalPages, families, rows, ...(view === "scores" ? { scoreContract: { scoreKind: "absolute", scoreScale: "0-100" } } : {}) };
}
async function install(page, { paid, delay = 0 }) {
  await page.route("**/api/auth/me", (route) => route.fulfill({ status: paid ? 200 : 401, contentType: "application/json", body: JSON.stringify(paid ? { user: { id: "fixture-plus", email: "plus@example.test", index_plan: "plus" } } : { user: null }) }));
  for (const [pattern, view] of [["**/api/explore/product-rankings/scores?*", "scores"], ["**/api/explore/product-rankings/economics?*", "economics"], ["**/api/tcgs/pokemon/rankings/product-catalogue?*", "public"]]) await page.route(pattern, async (route) => {
    const requestStartedAt = performance.now();
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    const payload = pageContract(route.request().url(), view); const body = JSON.stringify(payload);
    const responseReadyAt = performance.now();
    measurements.requests.push({ view, url: route.request().url(), ids: payload.rows.map((row) => row.sealedProductId), rowCount: payload.rows.length, delay, requestStartedAt, responseReadyAt });
    measurements.responses.push({ view, bytes: Buffer.byteLength(body), rowCount: payload.rows.length, delay });
    await route.fulfill({ contentType: "application/json", body });
  });
}
async function openProducts(page) { await page.goto(`${origin}/Rankings`, { waitUntil: "domcontentloaded", timeout: 30000 }); const clickedAt = performance.now(); await page.getByText("Products", { exact: true }).first().click(); return clickedAt; }

async function paidRun(delay = 0) {
  const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); await install(page, { paid: true, delay });
  const scoresClickAt = await openProducts(page); await page.locator("[data-product-scores-table] tbody tr").first().waitFor(); const scoresVisible = performance.now(); const scoresRequest = measurements.requests.find((x) => x.view === "scores" && x.delay === delay);
  const scoreRows = await page.locator("[data-product-scores-table] tbody tr").count(); const body = await page.locator("body").innerText();
  if (scoreRows !== 25 || !body.includes("Showing 1–25 of 60 ranked Products") || !body.includes("50.0") || body.includes("Set Chase") || body.includes("Set Collector")) throw new Error("desktop Scores acceptance failed");
  if (!delay) await page.screenshot({ path: `${evidenceDir}/product-scores-desktop.png`, fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Chase", exact: true }).click(); await page.getByRole("button", { name: "Chase", exact: true }).click(); await page.getByText("Fixture Product 60", { exact: false }).first().waitFor();
  const page2ClickAt = performance.now(); await page.getByRole("button", { name: "Next", exact: true }).click(); await page.getByText("Page 2 of 3", { exact: true }).waitFor(); const page2VisibleAt = performance.now(); await page.getByRole("button", { name: "Previous", exact: true }).click();
  await page.getByRole("button", { name: "Booster Box", exact: true }).click(); await page.getByText("Page 1 of 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "All Products", exact: true }).click(); await page.getByText("Page 1 of 3", { exact: true }).waitFor();
  const search = page.getByRole("searchbox", { name: "Search Products" }); await search.fill("Shrouded"); await page.waitForFunction(() => document.querySelectorAll("[data-product-scores-table] tbody tr").length === 1); await page.getByText("A Shrouded Fable Booster Pack", { exact: true }).first().waitFor(); await search.fill(""); await page.getByText("Page 1 of 3", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Next", exact: true }).click(); await page.getByText("Page 2 of 3", { exact: true }).waitFor(); await page.getByRole("button", { name: "Next", exact: true }).click(); await page.getByText("Page 3 of 3", { exact: true }).waitFor(); if (!(await page.getByRole("button", { name: "Next", exact: true }).isDisabled())) throw new Error("last-page bound"); await page.getByRole("button", { name: "Previous", exact: true }).click(); await page.getByRole("button", { name: "Previous", exact: true }).click();
  const economicsClickAt = performance.now(); await page.getByText("Economics", { exact: true }).first().click(); await page.locator("[data-product-economics-table] tbody tr").first().waitFor(); const economicsVisible = performance.now(); const economicsRequest = measurements.requests.find((x) => x.view === "economics" && x.delay === delay);
  const econBody = await page.locator("body").innerText(); if (!econBody.includes("9.9%") || !econBody.includes("0.0002%")) throw new Error(`exact Recover Cost acceptance failed: ${econBody.slice(-2500)}`);
  if (!delay) { await page.screenshot({ path: `${evidenceDir}/product-economics-desktop.png`, fullPage: true, animations: "disabled" }); const tiny = page.locator("tr").filter({ hasText: "Tiny Recovery Booster Pack" }); await tiny.screenshot({ path: `${evidenceDir}/tiny-positive-recover-cost.png`, animations: "disabled" }); }
  const info = page.getByLabel("Best-Open details for A Shrouded Fable Booster Pack").first(); await info.click(); const popover = await page.locator("body").innerText(); if (!popover.includes("Current market") || !popover.includes("+$20.00") || !popover.includes("+20.0%") || !popover.includes("MSRP\nUnavailable")) throw new Error("Best-Open popover acceptance failed"); await page.keyboard.press("Escape");
  const warmClickAt = performance.now(); await page.getByText("Scores", { exact: true }).first().click(); await page.locator("[data-product-scores-table] tbody tr").first().waitFor(); const warmVisibleAt = performance.now();
  measurements.timings.push({ delay, scores: { clickToRequestMs: scoresRequest.requestStartedAt - scoresClickAt, requestToResponseMs: scoresRequest.responseReadyAt - scoresRequest.requestStartedAt, responseToRowsMs: scoresVisible - scoresRequest.responseReadyAt, totalMs: scoresVisible - scoresClickAt }, economics: { clickToRequestMs: economicsRequest.requestStartedAt - economicsClickAt, requestToResponseMs: economicsRequest.responseReadyAt - economicsRequest.requestStartedAt, responseToRowsMs: economicsVisible - economicsRequest.responseReadyAt, totalMs: economicsVisible - economicsClickAt }, paginationPage1To2Ms: page2VisibleAt - page2ClickAt, warmEconomicsToScoresMs: warmVisibleAt - warmClickAt });
  await browser.close();
}

async function mobileRun() { const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 390, height: 844 } }); await install(page, { paid: true }); await openProducts(page); await page.locator("[data-product-score-card]").first().waitFor(); if (await page.locator("[data-product-score-card]").count() !== 25) throw new Error("mobile page size"); await page.screenshot({ path: `${evidenceDir}/product-scores-mobile.png`, fullPage: true, animations: "disabled" }); await page.getByRole("button", { name: "Next" }).click(); await page.getByText("Page 2 of 3").waitFor(); await browser.close(); }
async function publicRun() { const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); await install(page, { paid: false }); await openProducts(page); await page.locator("[data-product-public-catalogue] tbody tr").first().waitFor(); const text = await page.locator("body").innerText(), attrs = await page.locator("body").evaluate((body) => [...body.querySelectorAll("*")].flatMap((node) => [...node.attributes].map((a) => a.value)).join("\n")); if (await page.locator("[data-product-public-catalogue] tbody tr").count() !== 25 || !text.includes("Locked")) throw new Error("public catalogue pagination"); const forbidden = ["ripScore", "financialRip", "chaseScore", "collectorAppeal", "chanceToRecoverCost", "bestOpenPrice", "Full Market rank"]; if (forbidden.some((key) => text.includes(key) || attrs.includes(key))) throw new Error("public DOM leak"); await page.screenshot({ path: `${evidenceDir}/anonymous-product-catalogue.png`, fullPage: true, animations: "disabled" }); measurements.checks.publicLeakScan = "PASS"; await browser.close(); }

await paidRun(0); await paidRun(250); await mobileRun(); await publicRun();
const publicBodies = measurements.responses.filter((x) => x.view === "public" && x.delay === 0), scoresBodies = measurements.responses.filter((x) => x.view === "scores" && x.delay === 0), economicsBodies = measurements.responses.filter((x) => x.view === "economics" && x.delay === 0);
measurements.bytes = { publicPage1: publicBodies[0]?.bytes, paidScoresPage1: scoresBodies[0]?.bytes, paidEconomicsPage1: economicsBodies[0]?.bytes };
measurements.status = "PASS"; writeFileSync(`${evidenceDir}/browser-acceptance.json`, `${JSON.stringify(measurements, null, 2)}\n`); console.log(JSON.stringify(measurements, null, 2));
