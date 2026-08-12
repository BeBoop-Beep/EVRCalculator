// Cold-visit reproduction of the P0-A Market module failures and the P0-B
// opening-odds regression, with a full per-request waterfall.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3100";
const SETS = {
  ascendedHeroes: "Ascended Heroes",
  shroudedFable: "Shrouded Fable",
  prismaticEvolutions: "Prismatic Evolutions",
  scarletAndViolet151: "Scarlet and Violet 151",
};

const MODULE_MATCH = [
  ["overview", /\/overview\?/],
  ["value-history", /\/market\/value-history/],
  ["top-chase", /\/market\/top-chase/],
  ["movers", /\/market\/movers/],
  ["sealed", /\/market\/sealed/],
  ["pull-rates", /\/pull-rates/],
  ["insights-critical", /\/insights\/critical/],
  ["insights-secondary", /\/insights\/secondary/],
];

function classify(url) {
  for (const [name, re] of MODULE_MATCH) if (re.test(url)) return name;
  if (/\/_next\/image/.test(url)) return "_next/image";
  if (/\/_next\/static/.test(url)) return "_next/static";
  if (/\/api\//.test(url)) return "other-api";
  return null;
}

// The four Market failure strings the user reported, plus the sealed retry state.
const FAILURE_TEXT = [
  "set value history request timed out",
  "set top chase cards request timed out",
  "set market movers request timed out",
  "request timed out",
  "Unable to load",
  "timed out while loading",
];

async function visit(context, slug, tab, label) {
  const page = await context.newPage();
  const t0 = Date.now();
  const reqs = new Map();
  const events = [];

  page.on("request", (r) => {
    const kind = classify(r.url());
    if (!kind) return;
    reqs.set(r, { kind, url: r.url(), start: Date.now() - t0 });
  });
  page.on("requestfinished", async (r) => {
    const e = reqs.get(r);
    if (!e) return;
    let status = null;
    try {
      status = (await r.response())?.status();
    } catch {}
    events.push({ ...e, end: Date.now() - t0, dur: Date.now() - t0 - e.start, status });
  });
  page.on("requestfailed", (r) => {
    const e = reqs.get(r);
    if (!e) return;
    events.push({ ...e, end: Date.now() - t0, dur: Date.now() - t0 - e.start, status: "FAILED", err: r.failure()?.errorText });
  });

  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${slug}?tab=${tab}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  // Long settle: the client timeout is 20 s, so a failure needs >20 s to surface.
  await page.waitForTimeout(30000);

  const body = await page.evaluate(() => document.body.innerText);
  const failures = FAILURE_TEXT.filter((t) => body.toLowerCase().includes(t.toLowerCase()));

  // P0-B: does the RIP opening-odds surface render?
  const odds = await page.evaluate(() => {
    const t = document.body.innerText;
    const has = (s) => t.toLowerCase().includes(s.toLowerCase());
    return {
      whatCanIPull: has("What Can I Actually Pull"),
      openingOdds: has("Opening Odds"),
      oneInPattern: /1\s+in\s+[\d,.]+/i.test(t),
      pullRateHeading: has("Pull Rate"),
    };
  });

  const imgs = events.filter((e) => e.kind === "_next/image");
  const api = events.filter((e) => !e.kind.startsWith("_next"));

  console.log(`\n=== ${label} | ${slug} tab=${tab} ===`);
  console.log(`  _next/image requests: ${imgs.length}  (max dur ${Math.max(0, ...imgs.map((i) => i.dur))}ms, non-200: ${imgs.filter((i) => i.status !== 200).length})`);
  console.log("  API waterfall (start -> end, dur, status):");
  for (const e of api.sort((a, b) => a.start - b.start)) {
    console.log(`    ${String(e.start).padStart(6)}ms -> ${String(e.end).padStart(6)}ms  ${String(e.dur).padStart(6)}ms  ${String(e.status).padStart(6)}  ${e.kind}${e.err ? "  " + e.err : ""}`);
    if (e.status !== 200 || e.kind === "top-chase") console.log(`         URL: ${e.url}`);
  }
  console.log(`  UI failure strings present: ${failures.length ? JSON.stringify(failures) : "NONE"}`);
  console.log(`  opening-odds probe: ${JSON.stringify(odds)}`);

  await page.close();
  return { failures, odds, api, imgs };
}

const scenario = process.argv[2] || "cold-market";
const browser = await chromium.launch();
try {
  if (scenario === "cold-market") {
    for (const [slug, name] of Object.entries(SETS)) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await visit(ctx, slug, "market", `COLD BROWSER ${name}`);
      await ctx.close();
    }
  } else if (scenario === "cold-rip") {
    for (const [slug, name] of Object.entries(SETS)) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await visit(ctx, slug, "overview", `COLD RIP ${name}`);
      await ctx.close();
    }
  } else if (scenario === "aba") {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await visit(ctx, "ascendedHeroes", "market", "A (first)");
    await visit(ctx, "scarletAndViolet151", "market", "B");
    await visit(ctx, "ascendedHeroes", "market", "A (return)");
    await ctx.close();
  }
} finally {
  await browser.close();
}
