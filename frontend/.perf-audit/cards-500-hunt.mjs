import { chromium } from "@playwright/test";

const BASE = process.env.PERF_BASE || "http://127.0.0.1:3211";
const SETS = ["paldeaEvolved", "obsidianFlames"];
const ITERATIONS = Number(process.env.ITER || 12);

const browser = await chromium.launch();
const failures = [];
let totalCardsReqs = 0;
const inflight = new Map();

function attach(page, ctx) {
  page.on("request", (r) => {
    if (!/\/cards\/page/.test(r.url())) return;
    totalCardsReqs += 1;
    inflight.set(r.url(), (inflight.get(r.url()) || 0) + 1);
    r._startedAt = Date.now();
    r._concurrent = inflight.get(r.url());
  });
  page.on("response", async (r) => {
    const url = r.url();
    if (!/\/cards\/page/.test(url)) return;
    inflight.set(url, Math.max(0, (inflight.get(url) || 1) - 1));
    if (r.status() === 200) return;
    let body = null;
    try { body = (await r.text()).slice(0, 600); } catch (e) { body = "<unreadable>"; }
    const q = Object.fromEntries(new URL(url).searchParams);
    failures.push({
      ...ctx,
      status: r.status(),
      elapsedMs: r.request()._startedAt ? Date.now() - r.request()._startedAt : null,
      concurrentSameUrl: r.request()._concurrent ?? null,
      path: new URL(url).pathname,
      query: q,
      body,
      timing: r.request().timing?.() ?? null,
    });
    console.log("!! FAILURE", JSON.stringify(failures[failures.length - 1]));
  });
}

async function tilesVisible(page) {
  return page.evaluate(() => (document.body.innerText.match(/No\. \d+\//g) || []).length);
}
async function clickText(page, t) {
  await page.getByText(t, { exact: true }).first().click({ timeout: 8000 });
}

for (let i = 0; i < ITERATIONS; i++) {
  const set = SETS[i % SETS.length];
  const other = SETS[(i + 1) % SETS.length];
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });

  try {
    // A direct
    attach(page, { iter: i, scenario: "A direct ?tab=cards", set });
    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${set}?tab=cards`, { waitUntil: "load" });
    await page.waitForTimeout(3500);

    // B RIP -> Cards  (and E: repeat the round trip)
    for (const round of [1, 2]) {
      await page.goto(`${BASE}/TCGs/Pokemon/Sets/${set}`, { waitUntil: "load" });
      await page.waitForTimeout(3000);
      await clickText(page, "Cards & Products").catch(() => {});
      await page.waitForTimeout(3000);
    }

    // C Market -> Cards
    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${set}?tab=market`, { waitUntil: "load" });
    await page.waitForTimeout(3000);
    await clickText(page, "Cards & Products").catch(() => {});
    await page.waitForTimeout(3000);

    // D Pull Rates -> Cards
    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${set}?tab=pull-rates`, { waitUntil: "load" });
    await page.waitForTimeout(3000);
    await clickText(page, "Cards & Products").catch(() => {});
    await page.waitForTimeout(3000);

    // G set A -> set B on cards
    await page.goto(`${BASE}/TCGs/Pokemon/Sets/${other}?tab=cards`, { waitUntil: "load" });
    await page.waitForTimeout(3000);

    const tiles = await tilesVisible(page);
    console.log(`iter ${i} set=${set} finalTiles=${tiles} failuresSoFar=${failures.length} cardsReqs=${totalCardsReqs}`);
  } catch (e) {
    console.log(`iter ${i} ERROR ${String(e).slice(0, 120)}`);
  }
  await page.close();
}

console.log("\n==== HUNT SUMMARY ====");
console.log("cards/page requests:", totalCardsReqs);
console.log("non-200 responses:", failures.length);
if (failures.length) console.log(JSON.stringify(failures, null, 1));
await browser.close();
