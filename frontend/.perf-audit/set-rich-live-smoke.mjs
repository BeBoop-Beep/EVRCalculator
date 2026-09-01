import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3131";
const cases = [
  ["prismatic-evolutions", 1440, "market"],
  ["prismatic-evolutions", 412, "market"],
  ["ascended-heroes", 1440, "market"],
];
const browser = await chromium.launch();
try {
  for (const [set, width, tab] of cases) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.stack || error.message));
    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${set}?tab=${tab}`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForSelector("[data-set-context-shell]", { timeout: 90000 });
    await page.waitForSelector("#set-detail-market-top-chase", { timeout: 90000 });
    await page.waitForFunction(() => {
      const text = document.querySelector("#set-detail-market-top-chase")?.innerText || "";
      return text.includes("#10") || text.includes("View Top 10");
    }, { timeout: 30000 });
    if (errors.length) throw new Error(`${set}/${width}: ${errors.join(" | ")}`);
    console.log(`live smoke PASS ${set} ${width}px`);
    await page.close();
  }
} finally { await browser.close(); }
