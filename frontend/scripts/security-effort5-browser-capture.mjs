import { chromium } from "playwright";

const origin = "http://127.0.0.1:3001";
const identities = [
  ["anonymous", null],
  ["base", process.env.BASE_TEST_TOKEN],
  ["premium", process.env.PREMIUM_TEST_TOKEN],
];
const pages = [
  "/Rankings",
  "/Explore/rip-statistics",
  "/Market",
  "/Market/Explorer",
  "/TCGs/Pokemon/Sets/ascendedheroes",
  "/TCGs/Pokemon/Sets/ascendedheroes/analysis",
];
const paidStructures = [
  /["\\]financialRipV4["\\]\s*:\s*\{/i,
  /["\\]collectorAppealV4["\\]\s*:\s*\{/i,
  /["\\]marketBreadth["\\]\s*:\s*\{/i,
  /["\\]packsFor(?:50|90)PercentChance["\\]\s*:\s*\d/i,
  /["\\]cardAppealMarketPriceCorrelation["\\]\s*:\s*[-\d]/i,
  /["\\]chaseEfficiencyScore["\\]\s*:\s*[-\d]/i,
  /["\\]overallRipScore["\\]\s*:\s*[-\d]/i,
  /["\\]familyEconomics["\\]\s*:\s*\[/i,
];

const browser = await chromium.launch({ headless: true });
for (const [identity, token] of identities) {
  const context = await browser.newContext();
  if (token) await context.addCookies([{ name: "token", value: token, url: origin, httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  const captures = [];
  page.on("response", async (response) => {
    const type = response.request().resourceType();
    const contentType = response.headers()["content-type"] || "";
    if (!["document", "fetch", "xhr"].includes(type) && !contentType.includes("text/x-component")) return;
    try {
      const body = await response.text();
      captures.push({ url: response.url(), status: response.status(), type, contentType, body });
    } catch {}
  });
  for (const pathname of pages) {
    await page.goto(`${origin}${pathname}`, { waitUntil: "networkidle", timeout: 30000 });
  }
  const matches = paidStructures.map((pattern) => ({
    pattern: pattern.source,
    count: captures.reduce((sum, capture) => sum + (pattern.test(capture.body) ? 1 : 0), 0),
  }));
  const byType = Object.groupBy(captures, (capture) => capture.contentType.includes("text/x-component") ? "flight" : capture.type);
  console.log(JSON.stringify({
    identity,
    pages: pages.length,
    captures: captures.length,
    responseTypes: Object.fromEntries(Object.entries(byType).map(([key, value]) => [key, value.length])),
    non2xx: captures.filter((capture) => capture.status < 200 || capture.status >= 300).map((capture) => ({ status: capture.status, path: new URL(capture.url).pathname })),
    paidStructureMatches: matches,
  }));
  await context.close();
}

if (process.env.PREMIUM_TEST_TOKEN) {
  const context = await browser.newContext();
  await context.addCookies([{ name: "token", value: process.env.PREMIUM_TEST_TOKEN, url: origin, httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  await page.goto(`${origin}/Rankings`, { waitUntil: "networkidle" });
  await context.clearCookies();
  const postSignoutBodies = [];
  page.on("response", async (response) => {
    if (["document", "fetch", "xhr"].includes(response.request().resourceType()) || (response.headers()["content-type"] || "").includes("text/x-component")) {
      try { postSignoutBodies.push(await response.text()); } catch {}
    }
  });
  await page.goto(`${origin}/Market`, { waitUntil: "networkidle" });
  await page.goto(`${origin}/Rankings`, { waitUntil: "networkidle" });
  await page.goBack({ waitUntil: "networkidle" });
  await page.goForward({ waitUntil: "networkidle" });
  const combined = postSignoutBodies.join("\n");
  console.log(JSON.stringify({
    identity: "premium-to-anonymous",
    captures: postSignoutBodies.length,
    paidStructureMatches: paidStructures.map((pattern) => ({ pattern: pattern.source, present: pattern.test(combined) })),
  }));
  await context.close();
}
await browser.close();
