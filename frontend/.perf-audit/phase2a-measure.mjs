// Phase 2A + P1-B measurement: per-tab initial API waterfall.
// Request count, response bytes, duplicates, failures — one fresh context per route.
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3101";
const SETS = {
  ascendedHeroes: "Ascended Heroes",
  shroudedFable: "Shrouded Fable",
  prismaticEvolutions: "Prismatic Evolutions",
  scarletAndViolet151: "151",
};
const TABS = ["overview", "market", "cards", "pull-rates"];

const MODULE_MATCH = [
  ["overview", /\/overview\?/],
  ["value-history", /\/market\/value-history/],
  ["top-chase", /\/market\/top-chase/],
  ["movers", /\/market\/movers/],
  ["sealed", /\/market\/sealed/],
  ["pull-rates", /\/pull-rates/],
  ["insights-critical", /\/insights\/critical/],
  ["insights-secondary", /\/insights\/secondary/],
  ["cards-page", /\/cards\/page/],
  ["cards-validation", /\/cards\/validation/],
  ["cards", /\/sets\/[^/]+\/cards(\?|$)/],
  ["set-page", /\/sets\/[^/]+\/page/],
  ["shell", /\/sets\/[^/]+\/shell/],
];

function classify(url) {
  if (!/\/api\//.test(url)) return null;
  for (const [name, re] of MODULE_MATCH) if (re.test(url)) return name;
  return "other-api";
}

async function visit(browser, slug, tab) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const pending = new Map();
  const done = [];
  const t0 = Date.now();

  page.on("request", (r) => {
    const kind = classify(r.url());
    if (kind) pending.set(r, { kind, url: r.url(), start: Date.now() - t0 });
  });
  page.on("requestfinished", async (r) => {
    const e = pending.get(r);
    if (!e) return;
    let status = null;
    let bytes = 0;
    try {
      const resp = await r.response();
      status = resp?.status();
      bytes = (await resp.body()).length;
    } catch {}
    done.push({ ...e, dur: Date.now() - t0 - e.start, status, bytes });
  });
  page.on("requestfailed", (r) => {
    const e = pending.get(r);
    if (e) done.push({ ...e, dur: Date.now() - t0 - e.start, status: "FAILED", bytes: 0, err: r.failure()?.errorText });
  });

  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${slug}?tab=${tab}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(12000);

  // Aborted duplicates (ERR_ABORTED) are not transferred payloads; count them separately.
  const real = done.filter((e) => e.status !== "FAILED");
  const aborted = done.filter((e) => e.status === "FAILED");

  const byKind = new Map();
  for (const e of real) {
    if (!byKind.has(e.kind)) byKind.set(e.kind, []);
    byKind.get(e.kind).push(e);
  }
  const dupes = [...byKind.entries()].filter(([, v]) => v.length > 1);
  const bytes = real.reduce((a, e) => a + e.bytes, 0);
  const failed = real.filter((e) => e.status !== 200);

  await ctx.close();
  return { slug, tab, count: real.length, bytes, byKind, dupes, failed, aborted };
}

const browser = await chromium.launch();
const rows = [];
try {
  for (const tab of TABS) {
    for (const slug of Object.keys(SETS)) {
      rows.push(await visit(browser, slug, tab));
    }
  }
} finally {
  await browser.close();
}

const kb = (n) => (n / 1024).toFixed(1) + " kB";
for (const tab of TABS) {
  console.log(`\n########## TAB: ${tab} ##########`);
  for (const r of rows.filter((x) => x.tab === tab)) {
    console.log(`\n  ${SETS[r.slug]}  — ${r.count} API requests, ${kb(r.bytes)}`);
    for (const [kind, list] of [...r.byKind.entries()].sort()) {
      const flag = list.length > 1 ? `  <== DUPLICATE x${list.length}` : "";
      console.log(
        `     ${kind.padEnd(20)} n=${list.length} ${kb(list.reduce((a, e) => a + e.bytes, 0)).padStart(10)}  ` +
          `statuses=${list.map((e) => e.status).join(",")}  durs=${list.map((e) => e.dur + "ms").join(",")}${flag}`
      );
    }
    const vh = r.byKind.has("value-history");
    console.log(`     value-history requested: ${vh ? "YES" : "NO"}`);
    if (r.failed.length) console.log(`     FAILED: ${r.failed.map((e) => e.kind + "=" + e.status).join(", ")}`);
    if (r.aborted.length) console.log(`     aborted(client-cancelled): ${r.aborted.map((e) => e.kind).join(", ")}`);
  }
}

console.log("\n\n===== SUMMARY (requests / bytes / value-history / dupes / failures) =====");
for (const tab of TABS) {
  const t = rows.filter((x) => x.tab === tab);
  const avgReq = (t.reduce((a, r) => a + r.count, 0) / t.length).toFixed(1);
  const avgBytes = t.reduce((a, r) => a + r.bytes, 0) / t.length;
  const vh = t.filter((r) => r.byKind.has("value-history")).length;
  const dup = t.reduce((a, r) => a + r.dupes.length, 0);
  const fail = t.reduce((a, r) => a + r.failed.length, 0);
  console.log(
    `${tab.padEnd(12)} avgReq=${avgReq.padStart(5)}  avgBytes=${kb(avgBytes).padStart(10)}  ` +
      `value-history=${vh}/${t.length} sets  duplicateKinds=${dup}  failures=${fail}`
  );
}
