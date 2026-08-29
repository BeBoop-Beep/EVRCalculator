import { chromium } from "playwright";

const BASE = process.env.BASE || "http://127.0.0.1:3100";
const SET_SLUG = process.env.SET_SLUG || "ascendedHeroes";
const CYCLES = Math.max(2, Number.parseInt(process.env.CYCLES || "4", 10));
const HEAP_GROWTH_LIMIT_MB = Math.max(32, Number.parseInt(process.env.HEAP_GROWTH_LIMIT_MB || "96", 10));

const formatMb = (bytes) => `${(Number(bytes || 0) / 1024 / 1024).toFixed(1)} MB`;

async function discoverDetailRoutes(page) {
  const routes = [];
  await page.goto(`${BASE}/TCGs/Pokemon/Sets/${SET_SLUG}?tab=cards`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(3000);

  const cardHref = await page.locator('a[href*="/Cards/"]').first().getAttribute("href").catch(() => null);
  const productHref = await page.locator('a[href*="/sealed-products/"]').first().getAttribute("href").catch(() => null);
  if (cardHref) routes.push(cardHref);
  if (productHref) routes.push(productHref);
  return routes;
}

async function sample(page, session, label) {
  await session.send("HeapProfiler.collectGarbage").catch(() => {});
  const heap = await session.send("Runtime.getHeapUsage").catch(() => ({ usedSize: null, totalSize: null }));
  const metrics = await session.send("Performance.getMetrics").catch(() => ({ metrics: [] }));
  const metric = Object.fromEntries((metrics.metrics || []).map((entry) => [entry.name, entry.value]));
  const dom = await page.evaluate(() => ({
    nodes: document.getElementsByTagName("*").length,
    bodyText: document.body?.innerText?.length || 0,
  })).catch(() => ({ nodes: null, bodyText: null }));
  return {
    label,
    usedHeap: heap.usedSize,
    totalHeap: heap.totalSize,
    jsHeapUsed: metric.JSHeapUsedSize ?? null,
    nodes: dom.nodes,
    bodyText: dom.bodyText,
  };
}

async function runViewport(browser, name, viewport, isMobile = false) {
  const context = await browser.newContext({ viewport, isMobile });
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  await session.send("Performance.enable").catch(() => {});
  await session.send("HeapProfiler.enable").catch(() => {});

  const crashes = [];
  const pageErrors = [];
  const failedRequests = [];
  let transferredBytes = 0;

  page.on("crash", () => crashes.push({ at: Date.now(), url: page.url() }));
  page.on("pageerror", (error) => pageErrors.push({ url: page.url(), message: error.message }));
  page.on("requestfailed", (request) => failedRequests.push({ url: request.url(), error: request.failure()?.errorText || "failed" }));
  page.on("response", async (response) => {
    try {
      const headers = await response.allHeaders();
      const length = Number(headers["content-length"] || 0);
      if (Number.isFinite(length) && length > 0) transferredBytes += length;
    } catch {}
  });

  const dynamicDetailRoutes = await discoverDetailRoutes(page);
  const routes = [
    "/Market",
    "/Rankings",
    `/TCGs/Pokemon/Sets/${SET_SLUG}`,
    `/TCGs/Pokemon/Sets/${SET_SLUG}?tab=market`,
    `/TCGs/Pokemon/Sets/${SET_SLUG}?tab=cards`,
    `/TCGs/Pokemon/Sets/${SET_SLUG}?tab=pull-rates`,
    ...dynamicDetailRoutes,
  ];

  const samples = [];
  await page.goto(`${BASE}/Market`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(2500);
  samples.push(await sample(page, session, "baseline"));

  for (let cycle = 1; cycle <= CYCLES; cycle += 1) {
    for (const route of routes) {
      if (crashes.length) break;
      await page.goto(new URL(route, BASE).toString(), { waitUntil: "domcontentloaded", timeout: 90000 });
      await page.waitForTimeout(1800);
    }
    if (crashes.length) break;
    samples.push(await sample(page, session, `cycle-${cycle}`));
  }

  const first = samples[0]?.usedHeap ?? 0;
  const last = samples.at(-1)?.usedHeap ?? first;
  const retainedGrowth = Math.max(0, last - first);
  const growthLimit = HEAP_GROWTH_LIMIT_MB * 1024 * 1024;

  console.log(`\n===== ${name} renderer soak =====`);
  for (const entry of samples) {
    console.log(`${entry.label.padEnd(10)} heap=${formatMb(entry.usedHeap).padStart(10)} total=${formatMb(entry.totalHeap).padStart(10)} nodes=${String(entry.nodes).padStart(7)} text=${String(entry.bodyText).padStart(8)}`);
  }
  console.log(`routes/cycle=${routes.length} cycles=${CYCLES} transferred(content-length)=${formatMb(transferredBytes)}`);
  console.log(`retained heap growth after forced GC: ${formatMb(retainedGrowth)} (limit ${HEAP_GROWTH_LIMIT_MB} MB)`);
  console.log(`renderer crashes=${crashes.length} pageerrors=${pageErrors.length} failedRequests=${failedRequests.length}`);
  if (pageErrors.length) console.log("page errors:", pageErrors.slice(0, 10));
  if (failedRequests.length) console.log("failed requests:", failedRequests.slice(0, 10));

  await context.close();

  if (crashes.length) throw new Error(`${name}: renderer crashed at ${crashes[0].url}`);
  if (pageErrors.length) throw new Error(`${name}: ${pageErrors.length} uncaught page error(s)`);
  if (retainedGrowth > growthLimit) {
    throw new Error(`${name}: retained heap grew ${formatMb(retainedGrowth)}, above ${HEAP_GROWTH_LIMIT_MB} MB guardrail`);
  }
}

const browser = await chromium.launch();
try {
  await runViewport(browser, "desktop", { width: 1440, height: 900 });
  await runViewport(browser, "mobile", { width: 412, height: 915 }, true);
} finally {
  await browser.close();
}
