import { chromium } from "playwright";
import fs from "node:fs/promises";

const tokenPath = process.argv[2];
if (!tokenPath) throw new Error("Temporary token path is required");
const token = (await fs.readFile(tokenPath, "utf8")).trim();
if (!token) throw new Error("Temporary token file is empty");

const origin = "http://127.0.0.1:3001";
const output = "../backend/artifacts/market_explorer_acceptance/refinement_final_browser_20260908";
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addCookies([{ name: "token", value: token, url: origin, httpOnly: true, sameSite: "Lax" }]);
const page = await context.newPage();
const requests = [];
const consoleErrors = [];
page.on("request", (request) => {
  if (!["fetch", "xhr"].includes(request.resourceType())) return;
  const url = new URL(request.url());
  requests.push({ method: request.method(), path: url.pathname, query: url.search, at: Date.now() });
});
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

const evidence = { auth: {}, screens: {}, exact: {}, lifecycle: {}, keyboard: {}, network: {}, constituents: {}, consoleErrors, failures: [] };
const check = (condition, message) => { if (!condition) { evidence.failures.push(message); throw new Error(message); } };
const countPath = (path, from = 0) => requests.slice(from).filter((item) => item.path === path).length;
const screenshot = (name) => page.screenshot({ path: `${output}/${name.endsWith(".png") ? name : `${name}.png`}`, fullPage: true });
const toggle = (id) => page.locator(`[data-explorer-disclosure-toggle="${id}"]`);
const ensureOpen = async (id) => { const root = page.locator(`[data-explorer-disclosure="${id}"]`); if (await root.getAttribute("data-explorer-disclosure-open") !== "true") await toggle(id).click(); };

try {
  const authResponse = await page.request.get(`${origin}/api/auth/me`);
  const auth = await authResponse.json();
  evidence.auth = { status: authResponse.status(), authenticated: Boolean(auth?.user || auth?.id || auth?.email), plan: auth?.user?.index_plan || auth?.index_plan || auth?.profile?.index_plan || null };
  check(authResponse.status() === 200, "/auth/me did not authenticate");

  await page.goto(`${origin}/Market/Explorer`, { waitUntil: "networkidle", timeout: 60000 });
  await page.locator("[data-market-explorer-workspace]").waitFor({ timeout: 30000 });
  const resolvedAccess = await page.locator("[data-market-explorer-workspace]").getAttribute("data-market-explorer-access-mode");
  check(resolvedAccess === "plus", `Explorer did not resolve Plus access (resolved ${resolvedAccess || "none"})`);
  evidence.auth.plan = "plus";

  // Cards Screens: every Plus entry acts; ranked screens expose results and templates mutate the preview.
  await ensureOpen("cardsScreens");
  const cardsScreenIds = ["rarity-leaders", "momentum-leaders", "largest-drawdowns", "obtainable-market", "intermediate-market", "premium-market", "new-release-market", "established-market"];
  for (const id of cardsScreenIds) {
    const button = page.locator(`[data-market-screen="${id}"]`);
    check(await button.count() === 1, `Missing Cards Screen ${id}`);
    check(await button.getAttribute("data-market-screen-locked") === "false", `Plus Screen ${id} was locked`);
    await button.click();
    const ranked = ["rarity-leaders", "momentum-leaders", "largest-drawdowns"].includes(id);
    const acted = ranked ? await page.locator("[data-market-screen-results]").count() > 0 : await page.locator("[data-market-screen-applied]").count() > 0;
    check(acted, `Cards Screen ${id} did not act immediately`);
    evidence.screens[id] = ranked ? "results" : "applied";
  }
  const selectedSet = page.locator('[data-market-screen="set-top-ten"]');
  check(await selectedSet.getAttribute("data-market-screen-locked") === "true", "Premium selected-set Screen was not locked for Plus");
  check((await page.locator("body").innerText()).includes("Use in Market Builder") === false, "Obsolete Screen handoff is visible");
  await screenshot("16-auth-plus-cards-screens.png");

  // Sealed screen set is asset-specific.
  await toggle("sealedBuilder").click();
  await ensureOpen("sealedScreens");
  const sealedIds = await page.locator('[data-explorer-disclosure="sealedScreens"] [data-market-screen]').evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-market-screen")));
  check(sealedIds.includes("sealed-format-leaders") && sealedIds.includes("momentum-leaders") && sealedIds.includes("largest-drawdowns"), "Sealed Screens are incomplete");
  check(!sealedIds.includes("rarity-leaders") && !sealedIds.includes("premium-market"), "Card-only Screen leaked into Sealed");
  for (const id of sealedIds) {
    await page.locator(`[data-explorer-disclosure="sealedScreens"] [data-market-screen="${id}"]`).click();
    check(await page.locator("[data-market-screen-results]").count() > 0, `Sealed Screen ${id} did not show results`);
  }
  evidence.screens.sealed = sealedIds;
  await screenshot("17-auth-plus-sealed-screens.png");

  // Exact Items is discoverable to Plus but execution remains Premium-gated.
  await toggle("rawCardsBuilder").click();
  const exactMode = page.getByRole("radio", { name: /Exact Items/i });
  await exactMode.focus(); await page.keyboard.press("Space");
  const search = page.getByLabel("Search exact items");
  const searchStart = requests.length;
  await search.fill("Charizard");
  await page.waitForResponse((response) => response.url().includes("/api/market/explorer/instruments/search") && response.status() === 200, { timeout: 30000 });
  await page.locator('[role="listbox"] [role="option"]').first().waitFor();
  const results = page.locator('[role="listbox"] [role="option"]');
  const resultCount = await results.count();
  check(resultCount >= 5, "Charizard search returned fewer than five real instruments");
  const labels = await results.evaluateAll((nodes) => nodes.slice(0, 5).map((node) => node.innerText));
  check(new Set(labels).size >= 4, "Physical Charizard results were not distinguishable");
  await search.press("Enter");
  for (let i = 1; i < 5; i += 1) await results.nth(i).click();
  check((await page.locator("[data-exact-item-count]").innerText()).startsWith("5 of 25"), "Exact selected count did not reach 5 of 25");
  check(await results.first().isDisabled(), "Duplicate exact selection was not prevented");
  await page.locator("[data-exact-selected-items] button").first().focus(); await page.keyboard.press("Enter");
  check((await page.locator("[data-exact-item-count]").innerText()).startsWith("4 of 25"), "Keyboard removal did not update exact selection");
  await results.first().click();
  const selectedBeforeLock = await page.locator("[data-exact-selected-items] li").count();
  const build = page.locator("[data-market-builder-build]");
  check(await build.isDisabled(), "Plus exact Build was not Premium-gated");
  check((await page.locator("[data-current-market-lock]").innerText()).includes("Index Premium"), "Exact Premium requirement was unclear");
  const queryPostsBefore = requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length;
  await build.press("Enter").catch(() => {});
  check(await page.locator("[data-exact-selected-items] li").count() === selectedBeforeLock, "Premium lock discarded the exact draft");
  check(requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length === queryPostsBefore, "Locked exact Build issued a market request");
  evidence.exact = { searchRequests: countPath("/api/market/explorer/instruments/search", searchStart), resultCount, distinctFirstFiveLabels: new Set(labels).size, selectedBeforeLock, duplicatePrevented: true, keyboardRemove: true, buildDisabled: true, queryRequestsFromLockedBuild: 0 };
  await screenshot("18-auth-plus-exact-populated-lock.png");

  // Return to Filters and build one Plus-allowed narrow one-axis market. A
  // single Set is still one canonical scope axis, while keeping live QA work
  // bounded compared with an uncached global price universe.
  await page.getByRole("radio", { name: /^Filters$/ }).click();
  await page.locator("[data-market-builder-clear]").click();
  const selectSet = async (name) => {
    await ensureOpen("cardsEraSets");
    await page.locator('[data-multi-select-trigger="cards-set"]').click();
    const clear = page.locator('[data-multi-select-clear="cards-set"]');
    if (await clear.count() && await clear.isEnabled()) await clear.click();
    const setSearch = page.locator('[data-multi-select-search="cards-set"]');
    if (await setSearch.count()) await setSearch.fill(name);
    const option = page.locator('[data-multi-select-popover="cards-set"] [data-multi-select-option]').filter({ hasText: name }).first();
    await option.waitFor(); await option.click();
    const done = page.locator('[data-multi-select-done="cards-set"]');
    if (await done.count()) await done.click(); else await page.keyboard.press("Escape");
  };
  await selectSet("Gym Challenge");
  check(!(await build.isDisabled()), `One-axis Plus Build remained disabled: ${await page.locator("[data-current-market-preview]").innerText()}`);
  const buildStart = requests.length;
  await build.click();
  await page.waitForFunction(() => document.querySelectorAll('[data-market-explorer-active-chip-source="query"]').length > 0, null, { timeout: 120000 });
  const customChip = page.locator('[data-market-explorer-active-chip-source="query"]').last();
  const originalKey = await customChip.getAttribute("data-market-explorer-active-chip");
  const originalStyle = await customChip.locator("span[aria-hidden=true]").first().getAttribute("style");
  check(countPath("/api/market/explorer/query", buildStart) >= 1, "Custom Build issued no query request");
  evidence.lifecycle.buildRequests = requests.slice(buildStart).filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length;

  // Visibility and timeframe are client-only.
  const noRequestStart = requests.length;
  await page.locator(`[data-market-explorer-active-visibility="${originalKey}"]`).focus(); await page.keyboard.press("Enter");
  await page.locator("[data-market-explorer-active-hide-all]").click();
  await page.locator("[data-market-explorer-active-show-all]").click();
  await page.locator('[data-market-explorer-timeframe="30D"]').click();
  check(requests.slice(noRequestStart).filter((item) => item.path.includes("/api/market/explorer/query")).length === 0, "Visibility/timeframe caused a market request");
  evidence.keyboard.visibilityFocused = await page.locator(`[data-market-explorer-active-visibility="${originalKey}"]`).evaluate((node) => node.matches(":focus-visible") || document.activeElement === node);

  // Edit while old line remains, then update same instance/color.
  await page.locator(`[data-market-explorer-active-edit="${originalKey}"]`).focus(); await page.keyboard.press("Enter");
  check(await page.locator("[data-market-builder-editing=true]").count() === 1, "Edit mode did not open");
  await selectSet("Gym Heroes");
  check(await page.locator(`[data-market-explorer-active-chip="${originalKey}"]`).count() === 1, "Old active line changed before Update success");
  const updateStart = requests.length;
  await page.locator("[data-market-builder-build]").click();
  await page.waitForFunction((key) => document.querySelector(`[data-market-explorer-active-chip="${key}"]`) && !document.querySelector("[data-market-builder-editing=true]"), originalKey, { timeout: 120000 });
  const updatedChip = page.locator(`[data-market-explorer-active-chip="${originalKey}"]`);
  check(await updatedChip.count() === 1, "Update replaced the query instance key");
  check(await updatedChip.locator("span[aria-hidden=true]").first().getAttribute("style") === originalStyle, "Update changed series color");
  evidence.lifecycle.updateRequests = requests.slice(updateStart).filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length;

  // Save as new from a third distinct one-axis definition.
  await page.locator(`[data-market-explorer-active-edit="${originalKey}"]`).click();
  await selectSet("Team Rocket");
  const beforeSaveCount = await page.locator('[data-market-explorer-active-chip-source="query"]').count();
  await page.locator("[data-market-builder-save-as-new]").click();
  await page.waitForFunction((count) => document.querySelectorAll('[data-market-explorer-active-chip-source="query"]').length > count, beforeSaveCount, { timeout: 120000 });
  const keysAfterSave = await page.locator('[data-market-explorer-active-chip-source="query"]').evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-market-explorer-active-chip")));
  check(keysAfterSave.includes(originalKey) && new Set(keysAfterSave).size === keysAfterSave.length, "Save as new did not preserve distinct instances");
  evidence.lifecycle.saveAsNew = { before: beforeSaveCount, after: keysAfterSave.length, distinctKeys: new Set(keysAfterSave).size };
  await screenshot("19-auth-plus-edit-save-lifecycle.png");

  // Cancel edits is local-only and preserves active results.
  const newestKey = keysAfterSave.at(-1);
  await page.locator(`[data-market-explorer-active-edit="${newestKey}"]`).click();
  const cancelStart = requests.length;
  const countBeforeCancel = await page.locator('[data-market-explorer-active-chip-source="query"]').count();
  await page.locator("[data-market-builder-clear]").click();
  check(requests.length === cancelStart && await page.locator('[data-market-explorer-active-chip-source="query"]').count() === countBeforeCancel, "Cancel issued a request or changed active markets");
  evidence.lifecycle.cancelNoRequest = true;

  // Real query constituents: window changes client-side, load-more is exactly one request.
  await page.locator(`[data-market-explorer-active-inspect="${originalKey}"]`).click();
  await page.locator("[data-market-constituents-page-count]").waitFor({ timeout: 60000 });
  const movementValues = {};
  for (const window of ["1D", "7D", "30D", "3M"]) {
    const start = requests.length;
    await page.locator(`[data-market-constituents-window="${window}"]`).focus(); await page.keyboard.press("Enter");
    movementValues[window] = await page.locator("[data-market-constituents-table] tbody tr").first().innerText();
    check(countPath("/api/market/explorer/query/constituents", start) === 0, `Movement ${window} refetched constituents`);
  }
  check(new Set(Object.values(movementValues)).size > 1, "Constituent movement values did not change across windows");
  const loadMore = page.locator("[data-market-constituents-load-more]");
  if (await loadMore.count()) {
    const pagingStart = requests.length;
    await loadMore.click();
    await page.waitForFunction(() => !document.querySelector("[data-market-constituents-load-more]")?.disabled, null, { timeout: 60000 });
    check(countPath("/api/market/explorer/query/constituents", pagingStart) === 1, "Load more did not issue exactly one paged request");
    evidence.constituents.loadMoreRequests = 1;
  } else evidence.constituents.loadMoreRequests = 0;
  evidence.constituents.distinctMovementRows = new Set(Object.values(movementValues)).size;
  await screenshot("20-auth-plus-constituent-movement.png");

  evidence.network = {
    optionsGets: requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "GET").length,
    searchGets: requests.filter((item) => item.path === "/api/market/explorer/instruments/search").length,
    summaryPosts: requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length,
    constituentPosts: requests.filter((item) => item.path === "/api/market/explorer/query/constituents").length,
  };
} catch (error) {
  if (!evidence.failures.includes(error.message)) evidence.failures.push(error.message);
} finally {
  if (!Object.keys(evidence.network).length) evidence.network = {
    optionsGets: requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "GET").length,
    searchGets: requests.filter((item) => item.path === "/api/market/explorer/instruments/search").length,
    summaryPosts: requests.filter((item) => item.path === "/api/market/explorer/query" && item.method === "POST").length,
    constituentPosts: requests.filter((item) => item.path === "/api/market/explorer/query/constituents").length,
  };
  // Token content is intentionally neither serialized nor logged.
  await fs.writeFile(`${output}/authenticated-closure-evidence.json`, JSON.stringify(evidence, null, 2));
  await context.close();
  await browser.close();
}

if (evidence.failures.length) process.exitCode = 1;
