import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const REQUIRED_ERROR = "AUTHENTICATED_ACCEPTANCE_SESSION_REQUIRED";
const DEFAULT_ORIGIN = "http://127.0.0.1:3000";
const OUTPUT = path.resolve(process.cwd(), "../backend/artifacts/market_explorer_acceptance/corrective_authenticated_final_20261002");
const VIEWPORTS = [
  ["1728x1000", 1728, 1000], ["1440x900", 1440, 900],
  ["1024x768", 1024, 768], ["768x1024", 768, 1024],
  ["390x844", 390, 844], ["844x390", 844, 390],
];
const FORBIDDEN_CODES = new Set([
  "PREPARED_COMPARISON_TIMEOUT", "PREPARED_PROXY_TIMEOUT", "PREPARED_DIRECTORY_FAILED",
  "PREPARED_COMPARISON_FAILED", "PREPARED_CONSTITUENTS_FAILED", "GENERATION_MISMATCH",
  "CATALOG_SEARCH_UNAVAILABLE", "ACTIVITY_GENERATION_MISMATCH",
]);

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}
const tokenFile = argument("--token-file") || process.env.EXPLORER_AUTH_TOKEN_FILE;
const origin = (argument("--origin") || process.env.EXPLORER_ACCEPTANCE_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, "");
const fail = (condition, message) => { if (!condition) throw new Error(message); };
const safeMessage = (error) => String(error?.message || error || "UNKNOWN_FAILURE").replace(/[\r\n]+/g, " ").slice(0, 400);
const rgb = (value) => (String(value).match(/[\d.]+/g) || []).slice(0, 3).map(Number);
const looksTeal = (value) => { const [r = 0, g = 0, b = 0] = rgb(value); return g > r * 1.25 && g > b * 0.85; };

const resolvedTokenFile = tokenFile ? path.resolve(tokenFile) : null;
const repositoryRoot = path.resolve(process.cwd(), "..");
const tokenRelativeToRepository = resolvedTokenFile ? path.relative(repositoryRoot, resolvedTokenFile) : "";
const tokenIsInsideRepository = resolvedTokenFile && tokenRelativeToRepository && !tokenRelativeToRepository.startsWith("..") && !path.isAbsolute(tokenRelativeToRepository);
if (!tokenFile || tokenIsInsideRepository) {
  console.error(REQUIRED_ERROR);
  process.exit(2);
}

let token;
try { token = (await fs.readFile(resolvedTokenFile, "utf8")).trim(); } catch { /* fail uniformly below */ }
if (!token) {
  console.error(REQUIRED_ERROR);
  process.exit(2);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1728, height: 1000 } });
await context.addCookies([{ name: "token", value: token, url: origin, httpOnly: true, sameSite: "Lax" }]);
// The secret leaves lexical scope before any evidence object is constructed.
token = undefined;

const page = await context.newPage();
const network = [];
const requestStarted = new WeakMap();
const consoleErrors = [];
const runtimeFailures = [];
const scenarios = {};
const measurements = { viewports: {}, tooltip: {}, builder: {}, paging: {} };
const mark = (number, status, evidence) => { scenarios[number] = { status, evidence }; };

page.on("request", (request) => {
  if (!["xhr", "fetch"].includes(request.resourceType())) return;
  const url = new URL(request.url());
  if (!url.pathname.includes("/api/market/explorer/")) return;
  requestStarted.set(request, Date.now());
});
page.on("response", async (response) => {
  const request = response.request();
  if (!["xhr", "fetch"].includes(request.resourceType())) return;
  const url = new URL(response.url());
  if (!url.pathname.includes("/api/market/explorer/")) return;
  const receipt = { method: request.method(), path: `${url.pathname}${url.search}`, status: response.status(), elapsedMs: Date.now() - (requestStarted.get(request) || Date.now()) };
  network.push(receipt);
  if (response.status() >= 500) runtimeFailures.push(`UNEXPECTED_5XX:${receipt.method}:${url.pathname}:${response.status()}`);
  if (response.status() >= 400) {
    try {
      const payload = await response.json();
      const code = String(payload?.code || payload?.detail?.code || "").toUpperCase();
      if (FORBIDDEN_CODES.has(code) || (code.startsWith("PREPARED_") && code.includes("TIMEOUT"))) runtimeFailures.push(code);
    } catch { /* status receipt is sufficient */ }
  }
});
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text().slice(0, 300)); });
page.on("pageerror", (error) => consoleErrors.push(safeMessage(error)));

async function screenshot(name) {
  await fs.mkdir(OUTPUT, { recursive: true });
  await page.screenshot({ path: path.join(OUTPUT, `${name}.png`), fullPage: true });
}
async function visible(locator, timeout = 30000) { await locator.waitFor({ state: "visible", timeout }); return locator; }
async function ensureTools() {
  const trigger = page.locator("[data-market-explorer-mobile-tools]");
  if (await trigger.isVisible().catch(() => false) && (await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click();
}
async function closeTools() {
  const trigger = page.locator("[data-market-explorer-mobile-tools]");
  if (await trigger.isVisible().catch(() => false) && (await trigger.getAttribute("aria-expanded")) === "true") await trigger.click();
}
async function openDetails() {
  const mobile = page.locator("[data-market-explorer-mobile-constituents]");
  const trigger = await mobile.isVisible().catch(() => false) ? mobile : page.locator("[data-market-explorer-view-details]");
  if (!(await page.locator("[data-market-explorer-details]").isVisible().catch(() => false))) await trigger.click();
  await visible(page.locator("[data-market-explorer-details]"));
}
async function hideDetails() {
  const hide = page.locator("[data-market-explorer-hide-details]");
  if (await hide.isVisible().catch(() => false)) await hide.click();
}
async function inspectParent(key) {
  await openDetails();
  const desktop = page.locator(`[data-market-explorer-inspect="${key}"]`);
  const mobile = page.locator(`[data-market-explorer-inspect-mobile="${key}"]`);
  const button = await desktop.isVisible().catch(() => false) ? desktop : mobile;
  await visible(button);
  await button.click();
  await visible(page.locator(`[data-market-constituents-target="${key}"][aria-pressed="true"]`));
  await visible(page.locator("[data-market-constituents-page-count]"), 60000);
}
async function constituentIds() {
  return page.locator("[data-market-constituent]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-market-constituent")));
}
async function measureLtAndOneYear() {
  await openDetails();
  const selector = await visible(page.locator("[data-market-constituents-window-selector]"));
  const gap = await selector.evaluate((element) => {
    const last = element.querySelector('[data-market-constituents-window="SinceTracking"]');
    if (!last) return null;
    element.scrollLeft = element.scrollWidth;
    return Math.round(element.getBoundingClientRect().right - last.getBoundingClientRect().right);
  });
  fail(gap !== null && gap >= 0 && gap <= 4, `LT_TRAILING_GAP:${gap}`);
  await hideDetails();
  const oneYear = page.locator('[data-market-window-value="1Y"]');
  await oneYear.click();
  fail((await oneYear.getAttribute("aria-checked")) === "true", "ONE_YEAR_NOT_SELECTED");
  const line = page.locator('polyline[data-market-performance-series="raw"]');
  const geometry = await line.evaluate((node) => {
    const xs = node.getAttribute("points").trim().split(/\s+/).map((point) => Number(point.split(",")[0]));
    return { firstX: xs[0], lastX: xs.at(-1), viewWidth: node.ownerSVGElement.viewBox.baseVal.width, points: xs.length };
  });
  fail(geometry.firstX <= 2.1 && geometry.lastX >= geometry.viewWidth - 2.1, `ONE_YEAR_GEOMETRY:${JSON.stringify(geometry)}`);
  return { trailingGapPx: gap, oneYear: geometry };
}

let plan = null;
let finalError = null;
try {
  // AUTH GATE: no Explorer scenario or navigation occurs before this succeeds.
  const authResponse = await context.request.get(`${origin}/api/auth/me`);
  let auth = null;
  try { auth = await authResponse.json(); } catch { /* handled by gate */ }
  const authenticated = Boolean(auth?.user || auth?.id || auth?.profile);
  plan = String(auth?.user?.index_plan || auth?.index_plan || auth?.profile?.index_plan || "").toLowerCase();
  if (authResponse.status() !== 200 || !authenticated || !["plus", "premium"].includes(plan)) throw new Error(REQUIRED_ERROR);

  await page.goto(`${origin}/Market/Explorer`, { waitUntil: "networkidle", timeout: 180000 });
  const workspace = await visible(page.locator("[data-market-explorer-workspace]"), 60000);
  const renderedPlan = String(await workspace.getAttribute("data-market-explorer-access-mode") || "").toLowerCase();
  fail(renderedPlan === plan, `PLAN_RESOLUTION_MISMATCH:${renderedPlan}`);
  await visible(page.locator('[data-market-explorer-active-chip="raw"]'));
  await visible(page.locator('[data-market-explorer-active-chip="sealedMarket"]'));

  // 2: add the current catalog market and wait for the prepared response to settle.
  await ensureTools();
  const search = page.locator("[data-market-explorer-search-input]");
  await search.fill("prismatic");
  const marketResult = await visible(page.locator('[data-market-explorer-search-panel] [data-search-primary="market"]'));
  await marketResult.click();
  const prismatic = await visible(page.locator('[data-market-explorer-active-chip-asset="cards"]', { hasText: "Prismatic Evolutions" }), 60000);
  const prismaticKey = await prismatic.getAttribute("data-market-explorer-active-chip");
  fail(Boolean(prismaticKey), "PRISMATIC_MARKET_KEY_MISSING");
  fail(!(await workspace.innerText()).match(/timed out|took too long/i), "PREPARED_TIMEOUT_BANNER");
  mark(2, "PASS", { marketKey: prismaticKey, prepared: true });
  await closeTools();

  // 4: body click focuses + inspects; repeat clears focus while retaining inspection.
  const body = prismatic.locator(`[data-market-explorer-active-chip-body="${prismaticKey}"]`);
  await body.click();
  fail((await prismatic.getAttribute("data-market-explorer-active-chip-focused")) === "true", "PRISMATIC_NOT_FOCUSED");
  fail((await workspace.getAttribute("data-market-explorer-detail-series")) === prismaticKey, "PRISMATIC_NOT_INSPECTION_TARGET");
  fail(await page.locator('[data-market-performance-focus="dimmed"]').count() >= 1, "OTHER_LINES_DID_NOT_RECEDE");
  await body.click();
  fail((await prismatic.getAttribute("data-market-explorer-active-chip-focused")) === "false", "SECOND_CLICK_DID_NOT_CLEAR_FOCUS");
  mark(4, "PASS", { focusToggle: true, inspectionTarget: true, dimmedLines: true });

  // 5/6: serving capability controls availability; enter and leave without losing workspace/cache.
  await body.click();
  const activity = page.locator('[data-market-chart-view="activity"]');
  await visible(activity);
  fail((await activity.getAttribute("data-market-chart-view-state")) === "available", "PRISMATIC_ACTIVITY_NOT_AVAILABLE");
  mark(5, "PASS", { capability: "available" });
  await openDetails();
  await visible(page.locator("[data-market-constituents-page-count]"), 60000);
  const beforeActivityIds = await constituentIds();
  await hideDetails();
  const activeBefore = await page.locator("[data-market-explorer-active-chip]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-market-explorer-active-chip")));
  await activity.click();
  await visible(page.locator("[data-market-activity-chart]"), 60000);
  await page.locator('[data-market-chart-view="index"]').click();
  await visible(page.locator("[data-market-performance-chart]"));
  const activeAfter = await page.locator("[data-market-explorer-active-chip]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-market-explorer-active-chip")));
  fail(JSON.stringify(activeAfter) === JSON.stringify(activeBefore), "ACTIVITY_EXIT_LOST_ACTIVE_MARKETS");
  fail((await workspace.getAttribute("data-market-explorer-detail-series")) === prismaticKey, "ACTIVITY_EXIT_LOST_INSPECTION_TARGET");
  await openDetails();
  fail(JSON.stringify(await constituentIds()) === JSON.stringify(beforeActivityIds), "ACTIVITY_EXIT_LOST_CONSTITUENT_CACHE");
  mark(6, "PASS", { activeMarketsRetained: activeAfter.length, inspectionTargetRetained: true, cacheRetained: true });

  // 7/8/9: real parent inspection and append-only continuation.
  const parentEvidence = {};
  for (const key of ["raw", "sealedMarket"]) {
    await inspectParent(key);
    parentEvidence[key] = { marketKey: key, rows: (await constituentIds()).length };
  }
  mark(7, "PASS", parentEvidence.raw);
  mark(8, "PASS", parentEvidence.sealedMarket);
  for (const key of ["raw", "sealedMarket"]) {
    await inspectParent(key);
    const first = await constituentIds();
    const more = page.locator("[data-market-constituents-load-more]").first();
    fail(await more.isVisible().catch(() => false), `CONSTITUENT_CONTINUATION_MISSING:${key}`);
    await more.click();
    await page.waitForFunction(({ count }) => document.querySelectorAll("[data-market-constituent]").length > count, { count: first.length }, { timeout: 60000 });
    const appended = await constituentIds();
    fail(appended.length > first.length, `CONSTITUENTS_DID_NOT_APPEND:${key}`);
    fail(new Set(appended).size === appended.length, `DUPLICATE_CONSTITUENTS:${key}`);
    measurements.paging[key] = { page1: first.length, appended: appended.length, unique: new Set(appended).size };
  }
  mark(9, "PASS", measurements.paging);

  const firstVisual = await measureLtAndOneYear();
  mark(10, "PASS", { measured: true, trailingGapPx: firstVisual.trailingGapPx });
  mark(11, "PASS", firstVisual.oneYear);

  // 16: the non-parent catalog market must disambiguate its asset in the chip.
  fail(/cards/i.test(await prismatic.innerText()), "GENERIC_MARKET_ASSET_SUFFIX_MISSING");
  mark(16, "PASS", { label: (await prismatic.innerText()).split(/\r?\n/)[0] });

  // 17: create one bounded one-axis market, enter edit mode, and measure current styling/autocomplete.
  await hideDetails();
  await ensureTools();
  await page.locator("[data-market-explorer-build-trigger]").click();
  const setTrigger = page.locator('[data-multi-select-trigger="cards-set"]');
  await visible(setTrigger);
  await setTrigger.click();
  const setSearch = page.locator('[data-multi-select-search="cards-set"]');
  if (await setSearch.count()) await setSearch.fill("Gym Challenge");
  await page.locator('[data-multi-select-popover="cards-set"] [data-multi-select-option]').filter({ hasText: "Gym Challenge" }).first().click();
  const done = page.locator('[data-multi-select-done="cards-set"]');
  if (await done.count()) await done.click(); else await page.keyboard.press("Escape");
  await page.locator("[data-market-builder-build]").click();
  const queryChip = await visible(page.locator('[data-market-explorer-active-chip-source="query"]').last(), 120000);
  const queryKey = await queryChip.getAttribute("data-market-explorer-active-chip");
  const remove = queryChip.locator(`[data-market-explorer-active-remove="${queryKey}"]`);
  await queryChip.locator(`[data-market-explorer-active-edit="${queryKey}"]`).click();
  const cancel = page.locator("[data-market-builder-clear]");
  const saveNew = page.locator("[data-market-builder-save-as-new]");
  const update = page.locator("[data-market-builder-build]");
  await visible(saveNew);
  const styles = await Promise.all([remove, cancel, saveNew, update].map((locator) => locator.evaluate((node) => {
    const style = getComputedStyle(node); return { text: node.textContent.trim(), color: style.color, borderColor: style.borderColor, backgroundColor: style.backgroundColor };
  })));
  fail(!looksTeal(styles[1].color) && !looksTeal(styles[2].color), "SECONDARY_ACTIONS_ARE_GREEN");
  fail(looksTeal(styles[3].color) || looksTeal(styles[3].borderColor), "UPDATE_MARKET_NOT_PRIMARY_TEAL");
  const autocomplete = await page.locator("input").evaluateAll((nodes) => nodes.filter((node) => node.offsetParent !== null).map((node) => ({ autocomplete: node.autocomplete, role: node.getAttribute("role") })));
  fail(autocomplete.every((entry) => entry.autocomplete === "off" || entry.autocomplete === "new-password" || entry.role !== "combobox"), "BROWSER_AUTOCOMPLETE_ENABLED");
  measurements.builder = { remove: styles[0], cancel: styles[1], saveAsNew: styles[2], update: styles[3], autocomplete };
  mark(17, "PASS", { neutralSecondary: true, tealPrimary: true, autocompleteDisabled: true, removeControl: true });
  await cancel.click();
  await closeTools();

  // 18: keyboard inspection searches for a carried-forward authoritative point.
  await hideDetails();
  const chart = page.locator("[data-market-performance-chart]");
  await chart.focus();
  let carried = null;
  for (let index = 0; index < 370 && !carried; index += 1) {
    await page.keyboard.press("ArrowLeft");
    const source = page.locator("[data-market-performance-carried-source]").first();
    if (await source.count()) carried = { text: await source.innerText(), tooltip: await page.locator("[data-market-performance-tooltip]").innerText() };
  }
  fail(Boolean(carried), "NO_CARRIED_FORWARD_TOOLTIP_DATE_FOUND");
  fail(/Last observed/i.test(carried.text) && !/Market Index —/.test(carried.tooltip), "TOOLTIP_DID_NOT_USE_PRIOR_AUTHORITATIVE_POINT");
  measurements.tooltip = carried;
  mark(18, "PASS", { carriedForward: true, noInventedValue: true });

  // Required rendered evidence at every viewport, reusing the authenticated workspace.
  for (const [name, width, height] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    await hideDetails();
    const currentChip = page.locator(`[data-market-explorer-active-chip="${prismaticKey}"]`);
    if ((await currentChip.getAttribute("data-market-explorer-active-chip-focused")) !== "true") await currentChip.locator(`[data-market-explorer-active-chip-body="${prismaticKey}"]`).click();
    await screenshot(`${name}-chip-focus-inspection`);
    await inspectParent("raw");
    await inspectParent("sealedMarket");
    await screenshot(`${name}-parent-inspect`);
    const visual = await measureLtAndOneYear();
    measurements.viewports[name] = visual;
    await screenshot(`${name}-lt-1y-geometry`);
  }

  fail(runtimeFailures.length === 0, runtimeFailures[0] || "UNEXPECTED_RUNTIME_FAILURE");
  fail(consoleErrors.length === 0, `UNEXPECTED_CONSOLE_ERRORS:${consoleErrors.length}`);
  mark(19, "PASS", { unexpected5xx: 0, forbiddenCodes: 0 });
  mark(20, "PASS", { consoleErrors: 0 });
} catch (error) {
  finalError = safeMessage(error);
} finally {
  const timingValues = network.map((entry) => entry.elapsedMs);
  const timingSummary = {
    requests: network.length,
    minMs: timingValues.length ? Math.min(...timingValues) : null,
    maxMs: timingValues.length ? Math.max(...timingValues) : null,
    averageMs: timingValues.length ? Math.round(timingValues.reduce((sum, value) => sum + value, 0) / timingValues.length) : null,
  };
  if (plan) {
    await fs.mkdir(OUTPUT, { recursive: true });
    await fs.writeFile(path.join(OUTPUT, "network.json"), JSON.stringify(network, null, 2));
    await fs.writeFile(path.join(OUTPUT, "measurements.json"), JSON.stringify(measurements, null, 2));
    await fs.writeFile(path.join(OUTPUT, "authenticated-final-evidence.json"), JSON.stringify({
      verdict: finalError ? "BLOCKED" : "COMPLETE — READY FOR MERGE REVIEW",
      plan, scenarios, timingSummary, unexpected5xx: runtimeFailures, consoleErrors, failure: finalError,
      security: { tokenLogged: false, tokenPersisted: false, tokenPathPersisted: false },
    }, null, 2));
  }
  await context.close();
  await browser.close();
}

if (finalError) {
  console.error(finalError === REQUIRED_ERROR ? REQUIRED_ERROR : `AUTHENTICATED_ACCEPTANCE_FAILED:${finalError}`);
  process.exitCode = 1;
} else {
  console.log(`Authenticated Market Explorer acceptance complete (${plan}).`);
}
