import { chromium } from "@playwright/test";

const BASE = process.env.PERF_BASE || "http://127.0.0.1:3210";
const SET = process.argv[2] || "paldeaEvolved";
const SET2 = process.argv[3] || "obsidianFlames";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });

let events = [];
let t0 = Date.now();
const rel = () => Date.now() - t0;
const short = (u) => u.replace(/^https?:\/\/[^/]+/, "").slice(0, 150);

page.on("request", (r) => {
  if (r.resourceType() === "fetch" || r.resourceType() === "xhr") events.push({ t: rel(), k: "REQ", url: short(r.url()) });
});
page.on("response", async (r) => {
  const rt = r.request().resourceType();
  if (rt !== "fetch" && rt !== "xhr") return;
  let n;
  try { const j = await r.json(); if (Array.isArray(j?.cards)) n = j.cards.length; } catch {}
  events.push({ t: rel(), k: "RES", s: r.status(), cards: n, url: short(r.url()) });
});
page.on("pageerror", (e) => events.push({ t: rel(), k: "PAGEERR", m: String(e).slice(0, 200) }));
page.on("console", (m) => { if (m.type() === "error") events.push({ t: rel(), k: "CERR", m: m.text().slice(0, 160) }); });

async function state() {
  return page.evaluate(() => {
    const txt = document.body.innerText;
    const m = txt.match(/([\d,]+) of ([\d,]+) cards/);
    // card tiles carry a "No. x/y" label
    const tiles = (txt.match(/No\. \d+\//g) || []).length;
    return {
      tiles,
      counter: m ? m[0] : null,
      loading: txt.includes("Loading cards"),
      empty: txt.includes("No cards found for this set"),
      noMatch: txt.includes("No cards match this movement filter"),
      error: txt.includes("Unable to load cards"),
    };
  });
}

async function click(name) {
  await page.getByText(name, { exact: true }).first().click({ timeout: 8000 });
}

async function scenario(label, fn, settle = 9000) {
  events = [];
  t0 = Date.now();
  let err = null;
  try { await fn(); } catch (e) { err = String(e).slice(0, 120); }
  await page.waitForTimeout(settle);
  const s = await state();
  const ok = s.tiles > 0;
  console.log(`\n${ok ? "PASS" : "FAIL"}  ${label}`);
  console.log("   url:", page.url().replace(BASE, ""));
  console.log("   state:", JSON.stringify(s));
  if (err) console.log("   clickErr:", err);
  const cardsCalls = events.filter((e) => /card/i.test(e.url || ""));
  console.log("   cardsCalls:", cardsCalls.length ? JSON.stringify(cardsCalls) : "NONE");
  const bad = events.filter((e) => e.k === "PAGEERR" || e.k === "CERR" || (e.k === "RES" && e.s >= 400));
  if (bad.length) console.log("   errors:", JSON.stringify(bad.slice(0, 4)));
  return ok;
}

const results = {};

// A: direct ?tab=cards
results.A = await scenario("A  direct ?tab=cards", async () => {
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET}?tab=cards`, { waitUntil: "load" });
});

// B: RIP -> Cards
results.B = await scenario("B  RIP -> Cards", async () => {
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET}`, { waitUntil: "load" });
  await page.waitForTimeout(6000);
  await click("Cards & Products");
});

// C: Market -> Cards
results.C = await scenario("C  Market -> Cards", async () => {
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET}?tab=market`, { waitUntil: "load" });
  await page.waitForTimeout(6000);
  await click("Cards & Products");
});

// D: Pull Rates -> Cards
results.D = await scenario("D  Pull Rates -> Cards", async () => {
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET}?tab=pull-rates`, { waitUntil: "load" });
  await page.waitForTimeout(6000);
  await click("Cards & Products");
});

// E: Cards -> Market Movers
results.E = await scenario("E  Cards -> Market Movers", async () => {
  await click("Market Movers");
});

// F: Market Movers -> All Cards
results.F = await scenario("F  Market Movers -> All Cards", async () => {
  await click("All Cards");
});

// G: set A cards -> set B cards
results.G = await scenario("G  setA cards -> setB cards", async () => {
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET2}?tab=cards`, { waitUntil: "load" });
});

console.log("\n==== SUMMARY ====");
for (const [k, v] of Object.entries(results)) console.log(k, v ? "PASS" : "FAIL");

await browser.close();
