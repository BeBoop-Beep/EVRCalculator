import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3131";
const SET_URL = `${BASE}/TCGs/Pokemon/Sets/prismatic-evolutions`;

const isRsc = (request) => {
  const headers = request.headers();
  return request.url().includes("_rsc=") || headers.rsc === "1" || headers["next-router-state-tree"] !== undefined;
};

async function runMatrix(browser, label, width, transitions) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  const records = [];
  const errors = [];
  let requests = [];
  page.on("request", (request) => requests.push(request));
  page.on("pageerror", (error) => errors.push(error.stack || error.message));
  page.on("console", (message) => {
    if (/hydration|did not match/i.test(message.text())) errors.push(message.text());
  });
  await page.goto(SET_URL, { waitUntil: "networkidle", timeout: 90000 });
  // Let global-shell viewport prefetches finish before attributing requests to
  // a Set-view action. The gate below remains strict for each transition.
  await page.waitForTimeout(1000);
  for (const tab of transitions) {
    requests = [];
    const startedAt = performance.now();
    await page.getByRole("radiogroup", { name: "Section view" }).locator(`[data-segment-value="${tab}"]`).click();
    await page.waitForFunction((value) => document.querySelector('[role="radiogroup"][aria-label="Section view"]')?.querySelector(`[data-segment-value="${value}"]`)?.getAttribute("aria-checked") === "true", tab);
    await page.waitForTimeout(500);
    records.push({
      transition: tab,
      readyMs: Math.round(performance.now() - startedAt),
      rsc: requests.filter(isRsc).map((request) => request.url()),
      documents: requests.filter((request) => request.resourceType() === "document").map((request) => request.url()),
      api: requests.filter((request) => request.url().includes("/api/")).map((request) => request.url()),
      scripts: requests.filter((request) => request.resourceType() === "script").map((request) => request.url()),
    });
  }
  const failures = records.filter((record) => record.rsc.length || record.documents.length);
  if (failures.length || errors.length) throw new Error(`${label}: ${JSON.stringify({ failures, errors }, null, 2)}`);
  console.log(`${label} PASS`, JSON.stringify(records));
  await page.close();
}

async function runHistory(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  let requests = [];
  page.on("request", (request) => requests.push(request));
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(SET_URL, { waitUntil: "networkidle", timeout: 90000 });
  for (const tab of ["market", "cards", "pull-rates"]) await page.getByRole("radiogroup", { name: "Section view" }).locator(`[data-segment-value="${tab}"]`).click();
  requests = [];
  for (const expected of ["cards", "market", "overview", "market", "cards"]) {
    if (["cards", "market", "overview"].includes(expected) && page.url().includes("pull-rates")) await page.goBack();
    else if (expected === "market" && !page.url().includes("tab=cards")) await page.goForward();
    else if (expected === "cards") await page.goForward();
    else await page.goBack();
    await page.waitForFunction((value) => document.querySelector('[role="radiogroup"][aria-label="Section view"]')?.querySelector(`[data-segment-value="${value}"]`)?.getAttribute("aria-checked") === "true", expected);
  }
  if (requests.some(isRsc) || requests.some((request) => request.resourceType() === "document") || errors.length) throw new Error(`history failed: ${JSON.stringify({ rsc: requests.filter(isRsc).map((r) => r.url()), errors })}`);
  console.log("back/forward PASS");
  await page.close();
}

async function runCardsSections(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const requests = [];
  await page.goto(`${SET_URL}?tab=cards`, { waitUntil: "networkidle", timeout: 90000 });
  page.on("request", (request) => requests.push(request));
  await page.getByRole("radio", { name: "Market Movers" }).click();
  await page.getByRole("radio", { name: "All Cards" }).click();
  await page.goBack();
  await page.waitForFunction(() => new URL(location.href).searchParams.get("section") === "market-movers");
  if (requests.some(isRsc) || requests.some((request) => request.resourceType() === "document")) throw new Error("Cards subsection emitted RSC/document request");
  console.log("Cards subsection history PASS");
  await page.close();
}

const browser = await chromium.launch();
try {
  await runMatrix(browser, "desktop 1440", 1440, ["market", "cards", "pull-rates", "overview"]);
  await runMatrix(browser, "mobile 412", 412, ["market", "cards", "pull-rates", "overview"]);
  await runMatrix(browser, "boundary 1199", 1199, ["market", "cards", "overview"]);
  await runHistory(browser);
  await runCardsSections(browser);
  console.log("set rich zero-RSC navigation PASS");
} finally {
  await browser.close();
}
