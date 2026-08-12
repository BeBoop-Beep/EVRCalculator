import { chromium } from "@playwright/test";

const BASE = "http://127.0.0.1:3210";
const SET = "paldeaEvolved";

const browser = await chromium.launch();

// click -> the destination's own primary content is on screen
const PATHS = {
  "Home -> Rankings": {
    from: `${BASE}/`,
    click: "Rankings",
    ready: () => document.body.innerText.includes("RIP RANK") || /#\s*1\b/.test(document.body.innerText),
  },
  "Home -> Market": {
    from: `${BASE}/`,
    click: "Market",
    ready: () => /Movers|Market/.test(document.body.innerText) && document.querySelectorAll("a,button").length > 20,
  },
  "Rankings -> Set": {
    from: `${BASE}/Rankings`,
    clickFirstSetLink: true,
    ready: () => /TOTAL CARDS/.test(document.body.innerText),
  },
  "Market -> Set": {
    from: `${BASE}/Market`,
    clickFirstSetLink: true,
    ready: () => /TOTAL CARDS/.test(document.body.innerText),
  },
  "RIP -> Cards": {
    from: `${BASE}/TCGs/Pokemon/Sets/${SET}`,
    click: "Cards & Products",
    ready: () => (document.body.innerText.match(/No\. \d+\//g) || []).length > 0,
  },
  "Market -> Cards": {
    from: `${BASE}/TCGs/Pokemon/Sets/${SET}?tab=market`,
    click: "Cards & Products",
    ready: () => (document.body.innerText.match(/No\. \d+\//g) || []).length > 0,
  },
  "Pull Rates -> Cards": {
    from: `${BASE}/TCGs/Pokemon/Sets/${SET}?tab=pull-rates`,
    click: "Cards & Products",
    ready: () => (document.body.innerText.match(/No\. \d+\//g) || []).length > 0,
  },
};

async function measure(page, spec) {
  await page.goto(spec.from, { waitUntil: "load" });
  await page.waitForTimeout(5500); // let the origin page fully settle first
  const t0 = Date.now();
  if (spec.clickFirstSetLink) {
    await page.locator('a[href*="/TCGs/Pokemon/Sets/"]').first().click({ timeout: 10000 });
  } else {
    await page.getByText(spec.click, { exact: true }).first().click({ timeout: 10000 });
  }
  const clickMs = Date.now() - t0;
  try {
    await page.waitForFunction(spec.ready, null, { timeout: 30000, polling: 120 });
  } catch {
    return { clickMs, totalMs: null };
  }
  return { clickMs, totalMs: Date.now() - t0 };
}

const out = {};
for (const [name, spec] of Object.entries(PATHS)) {
  const runs = [];
  for (let i = 0; i < 4; i++) {
    const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
    try {
      runs.push(await measure(page, spec));
    } catch (e) {
      runs.push({ totalMs: null, err: String(e).slice(0, 80) });
    }
    await page.close();
  }
  out[name] = runs;
  const cold = runs[0].totalMs;
  const warm = runs.slice(1).map((r) => r.totalMs).filter((n) => n != null).sort((a, b) => a - b);
  const median = warm.length ? warm[Math.floor(warm.length / 2)] : null;
  console.log(
    `${name.padEnd(22)} cold=${String(cold).padStart(6)}ms  warm=[${runs.slice(1).map((r) => r.totalMs).join(", ")}]  warmMedian=${median}ms`
  );
}

await browser.close();
