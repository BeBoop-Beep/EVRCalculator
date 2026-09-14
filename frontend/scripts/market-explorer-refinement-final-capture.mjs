import { chromium } from "playwright";
import fs from "node:fs/promises";

const origin = "http://127.0.0.1:3001";
const output = "../backend/artifacts/market_explorer_acceptance/refinement_final_browser_20260908";
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true });
const evidence = { authenticated: false, reason: "No approved QA token was present in the local process environment.", captures: [], consoleErrors: [], pageErrors: [], requests: [] };

async function open(viewport, name, pathname = "/Market/Explorer") {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.on("console", (message) => { if (message.type() === "error") evidence.consoleErrors.push({ name, text: message.text() }); });
  page.on("pageerror", (error) => evidence.pageErrors.push({ name, text: error.message }));
  page.on("request", (request) => {
    if (["fetch", "xhr"].includes(request.resourceType())) evidence.requests.push({ name, method: request.method(), path: new URL(request.url()).pathname });
  });
  const started = performance.now();
  const response = await page.goto(`${origin}${pathname}`, { waitUntil: "networkidle", timeout: 60000 });
  const interactiveMs = Math.round(performance.now() - started);
  const file = `${output}/${name}.png`;
  await page.screenshot({ path: file, fullPage: true });
  evidence.captures.push({ name, viewport, pathname, status: response?.status(), interactiveMs, scrollWidth: await page.evaluate(() => document.documentElement.scrollWidth), clientWidth: await page.evaluate(() => document.documentElement.clientWidth) });
  return { context, page };
}

for (const [name, viewport] of [
  ["01-explorer-default-1440", { width: 1440, height: 1000 }],
  ["03-explorer-wide-1728", { width: 1728, height: 1050 }],
  ["11-explorer-tablet-768", { width: 768, height: 1024 }],
  ["12-explorer-mobile-390", { width: 390, height: 844 }],
]) {
  const { context } = await open(viewport, name);
  await context.close();
}

{
  const { context, page } = await open({ width: 1440, height: 1000 }, "02-explorer-interaction-base-1440");
  const builderToggle = page.locator("[data-market-builder-mobile-toggle]");
  if (await builderToggle.isVisible()) await builderToggle.click();
  const myMarkets = page.locator('[data-explorer-disclosure="myMarkets"] button').first();
  if (await myMarkets.count()) await myMarkets.click();
  await page.screenshot({ path: `${output}/15-my-markets-foundation.png`, fullPage: true });
  const raw = page.locator('[data-explorer-disclosure="rawCardsBuilder"] button').first();
  if (await raw.count()) await raw.click();
  const exact = page.getByRole("radio", { name: /Exact Items/i });
  if (await exact.count()) await exact.click();
  await page.screenshot({ path: `${output}/14-plus-premium-lock-exact-items.png`, fullPage: true });
  const screens = page.locator('[data-explorer-disclosure="cardsScreens"] button').first();
  if (await screens.count()) await screens.click();
  await page.screenshot({ path: `${output}/07-screens.png`, fullPage: true });
  await context.close();
}

for (const label of ["7D", "30D"]) {
  const { context, page } = await open({ width: 1440, height: 900 }, `market-${label.toLowerCase()}-base`, "/Market");
  const option = page.getByRole("button", { name: new RegExp(`^${label}$`) }).first();
  if (await option.count()) await option.click();
  await page.screenshot({ path: `${output}/13-market-${label.toLowerCase()}.png`, fullPage: true });
  await context.close();
}

await fs.writeFile(`${output}/browser-evidence.json`, JSON.stringify(evidence, null, 2));
await browser.close();
