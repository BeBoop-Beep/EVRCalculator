import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3130";
const FIXTURE_BASE = process.env.FIXTURE_BASE || "http://127.0.0.1:8011";
const ROOT = join(process.cwd(), ".perf-audit", "baselines", process.env.SET_VISUAL_BASELINE || "active-release-v1");
const allViewports = [
  ["desktop", { width: 1440, height: 900 }],
  ["tablet", { width: 768, height: 1024 }],
  ["mobile", { width: 412, height: 915 }],
];
const viewports = process.env.ACTIVE_CASE_FILTER
  ? allViewports.filter(([name]) => new RegExp(process.env.ACTIVE_CASE_FILTER).test(name))
  : allViewports;

mkdirSync(ROOT, { recursive: true });
const browser = await chromium.launch();
const results = {};

try {
  for (const [name, viewport] of viewports) {
    await fetch(`${FIXTURE_BASE}/__fixture__/reset-browser`, { method: "POST" });
    const context = await browser.newContext({ viewport });
    await context.addCookies([{ name: "token", value: "fixture-premium", url: BASE }]);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const authResolved = page.waitForResponse((response) => response.url().includes("/api/auth/me") && response.status() === 200, { timeout: 90000 });
    await page.goto(`${BASE}/Rankings`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await authResolved;
    await page.getByRole("radio", { name: "Sets", exact: true }).click();
    try {
      await page.waitForFunction(() => document.body.innerText.includes("Ascended Heroes") && (document.body.innerText.includes("Best Sets to Rip Right Now") || document.body.innerText.includes("Compare all sets")), null, { timeout: 90000 });
    } catch (error) {
      const body = await page.locator("body").innerText().catch(() => "<body unavailable>");
      const network = await (await fetch(`${FIXTURE_BASE}/__fixture__/report`)).json();
      throw new Error(`${name}: Sets lens did not become ready\n${body.slice(0, 1800)}\n${JSON.stringify(network)}`, { cause: error });
    }
    if (name === "mobile") {
      await page.locator("article").filter({ hasText: "Ascended Heroes" }).getByRole("button").click();
      await page.locator("[data-chase-accessibility-mobile]").last().waitFor();
    }
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await page.evaluate(() => document.fonts?.ready).catch(() => {});

    const evidence = await page.evaluate(() => {
      const text = document.body.innerText;
      const table = document.querySelector("table");
      const headers = [...document.querySelectorAll("table th")];
      const duplicateIds = [...document.querySelectorAll("[id]")]
        .map((node) => node.id).filter((id, index, ids) => ids.indexOf(id) !== index);
      return {
        pathname: location.pathname,
        text,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        hasTable: Boolean(table),
        allHeadersAssociated: headers.length > 0 && headers.every((node) => node.getAttribute("scope") === "col" || node.hasAttribute("aria-label")),
        duplicateIds,
        controls: [...document.querySelectorAll("button,select,input")].map((node) => node.getAttribute("aria-label") || node.textContent?.trim()).filter(Boolean),
      };
    });
    if (evidence.pathname.toLowerCase() !== "/rankings") throw new Error(`${name}: wrong pathname ${evidence.pathname}`);
    for (const label of [name === "mobile" ? "rip score" : "set rip score", "financial rip", "chase accessibility", "collector appeal", "set #21 of 22"]) {
      if (!evidence.text.toLowerCase().includes(label)) throw new Error(`${name}: missing ${label}\n${evidence.text.slice(0, 2000)}`);
    }
    if (evidence.text.includes("Market-Based")) throw new Error(`${name}: retired Market-Based grouping rendered`);
    if (evidence.text.includes("temporarily unavailable") || evidence.text.includes("Unavailable")) {
      const at = evidence.text.indexOf("Unavailable");
      throw new Error(`${name}: false unavailable state rendered: ${evidence.text.slice(Math.max(0, at - 120), at + 240)}`);
    }
    if (evidence.overflow > 1) throw new Error(`${name}: page overflow ${evidence.overflow}px`);
    if (!evidence.hasTable && viewport.width >= 768) throw new Error(`${name}: semantic table missing`);
    if (evidence.hasTable && !evidence.allHeadersAssociated) throw new Error(`${name}: table header association missing`);
    if (evidence.duplicateIds.length) throw new Error(`${name}: duplicate ids ${evidence.duplicateIds.join(",")}`);
    if (errors.length) throw new Error(`${name}: page errors ${errors.join(" | ")}`);

    const screenshotPath = join(ROOT, `set-rankings__${name}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" });
    const network = await (await fetch(`${FIXTURE_BASE}/__fixture__/report`)).json();
    if (network.unexpectedBrowserRequests.length || network.unusedBrowserCriticalFixtures.length) {
      throw new Error(`${name}: fixture consumption ${JSON.stringify(network)}`);
    }
    results[`set-rankings__${name}`] = { viewport, screenshotPath, overflow: evidence.overflow, network, accessibility: { allHeadersAssociated: evidence.allHeadersAssociated, duplicateIds: evidence.duplicateIds } };
    console.log(`accepted set-rankings__${name}`);
    await context.close();
  }
} finally {
  await browser.close();
}

writeFileSync(join(ROOT, "acceptance.json"), `${JSON.stringify(results, null, 2)}\n`);
