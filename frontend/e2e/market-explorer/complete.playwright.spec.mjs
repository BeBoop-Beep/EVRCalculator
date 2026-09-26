// COMPLETE UI RECONCILIATION acceptance (FIXTURE mode). Plans are fixture identities
// (`token=fixture-plus|premium` cookies resolved by the fixture backend), never real auth.
//   - entitlement limits (Basic 1 / Index+ 3 / Premium 10), one upgrade path
//   - Sealed IA parity (V1 vs V2), Sealed Types incl. Cases, awaiting-data states
//   - Rare Holo GX (V2 PREPARED_CANDIDATE) end to end
//   - focus tools (Demand Pressure / Fair Value controls, no fabricated values)
//   - constituents: reopen, active-market chips, paging, Raw V1 network truthfulness
//   - images: broken URL fallback; search behaviour; Clear All keeps the Builder draft; mobile
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { closeDirectory, dismissNotice, newSession, openExplorer, pickRow, chooseCategory, ensureTools, shot, URLS, VIEWPORTS, OUT_DIR, fixtureRequests, resetFixtureRequests } from "./helpers.mjs";

const chips = (page) => page.locator("[data-market-explorer-active-strip] [data-market-explorer-active-chip]");
const chip = (page, fragment) => page.locator(`[data-market-explorer-active-chip*="${fragment}"]`);
const limitMessage = (page) => page.locator("[data-market-explorer-limit-message]");
const preparedPosts = (net) => net.requests.filter((r) => r.method === "POST" && r.url === "/api/market/explorer/prepared").map((r) => JSON.parse(r.body));
const MEASURE_FILE = path.join(OUT_DIR, "complete-measurements.json");
const record = (key, value) => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const existing = fs.existsSync(MEASURE_FILE) ? JSON.parse(fs.readFileSync(MEASURE_FILE, "utf8")) : {};
  fs.writeFileSync(MEASURE_FILE, JSON.stringify({ ...existing, [key]: value }, null, 2));
};
const clearAll = async (page) => { await page.click("[data-market-explorer-active-clear-all]"); await expect(page.locator("[data-market-explorer-active-chip]")).toHaveCount(0); };
async function addRow(page, category, label, expectFragment, expectCount) {
  await pickRow(page, category, label);
  await expect(chip(page, expectFragment)).toHaveCount(1, { timeout: 30000 });
  if (expectCount) await expect(chips(page)).toHaveCount(expectCount);
}
const layer = (page, id) => page.locator(`[data-market-directory-asset="${id}"]`);

// ---------------------------------------------------------------------------------------------
test("BASIC: one market; switches never prompt; exceeding shows ONE upgrade path and keeps the market", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2 });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chips(page)).toHaveCount(1);
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  await pickRow(page, "sets", "Jungle");
  await expect(chip(page, "set-jungle")).toHaveCount(1, { timeout: 30000 });
  await expect(chips(page)).toHaveCount(1);
  // The single-market switch never surfaced a login/Index+ prompt.
  await expect(page.locator("[data-market-explorer-compare-upgrade]")).toHaveCount(0);
  for (const post of preparedPosts(net)) expect(post.contextMarketKeys).toEqual([]);
  // Attempting a SECOND simultaneous capability (a build-only rarity) shows ONE clear upgrade path.
  await ensureTools(page);
  await page.click("[data-rarity-market-trigger]");
  await page.locator("[data-rarity-market='rareHoloV']").click();
  await expect(page.locator("[data-market-explorer-compare-upgrade]")).toHaveCount(1);
  await expect(page.locator("[data-market-explorer-compare-upgrade-link]")).toHaveCount(1);
  await expect(chips(page)).toHaveCount(1);
  await shot(page, "basic-one-upgrade-path");
  // Focus tools for Basic: both locked with the plan requirement, no values.
  await page.locator("[data-market-explorer-compare-upgrade] button", { hasText: "Dismiss" }).click();
  await chip(page, "set-jungle").locator("[data-market-explorer-active-focus]").click();
  const strip = page.locator("[data-market-explorer-focus-strip]");
  await expect(strip.locator("[data-focus-tool-state='locked']")).toHaveCount(2);
  await expect(strip).toContainText("Demand Pressure requires Index+.");
  await expect(strip).toContainText("Premium");
  await shot(page, "basic-focus-tools-locked");
  await context.close();
});

test("INDEX+: up to 3 active markets; hidden counts, focus does not; 4th blocked cleanly; tools states", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await addRow(page, "sets", "Fossil", "set-fossil", 1);
  await addRow(page, "sets", "Jungle", "set-jungle", 2);
  await addRow(page, "sets", "Base Set 2", "set-bs2", 3);
  await shot(page, "plus-three-active-markets");
  await pickRow(page, "sets", "HeartGold");
  await expect(limitMessage(page)).toHaveText("Index+ supports up to 3 active comparison markets.");
  await expect(page.locator("[data-market-explorer-compare-upgrade-link]")).toContainText("Upgrade to Premium");
  await expect(chips(page)).toHaveCount(3);
  await expect(chip(page, "set-hgss")).toHaveCount(0);
  await shot(page, "plus-fourth-blocked");
  const hgssRequests = preparedPosts(net).filter((post) => post.marketKeys.includes("set:set-hgss"));
  expect(hgssRequests, "the blocked 4th market never reaches the network").toEqual([]);
  await dismissNotice(page);
  // HIDDEN active markets still occupy a slot.
  await page.locator("[data-market-explorer-active-visibility='set:set-jungle']").click();
  await pickRow(page, "sets", "HeartGold");
  await expect(chips(page)).toHaveCount(3);
  await expect(limitMessage(page)).toContainText("up to 3");
  // FOCUS does not free or consume a slot.
  await chip(page, "set-fossil").locator("[data-market-explorer-active-focus]").click();
  await pickRow(page, "sets", "HeartGold");
  await expect(chips(page)).toHaveCount(3);
  // Removing one frees exactly one slot (never auto-removed).
  await page.locator("[data-market-explorer-compare-upgrade] button", { hasText: "Dismiss" }).click();
  await page.locator("[data-market-explorer-active-remove='set:set-bs2']").click();
  await expect(chips(page)).toHaveCount(2);
  await pickRow(page, "sets", "HeartGold");
  await expect(chip(page, "set-hgss")).toHaveCount(1, { timeout: 30000 });
  // Focus tools: Demand Pressure unavailable (entitled, no authority); Fair Value Premium-locked.
  const strip = page.locator("[data-market-explorer-focus-strip]");
  await expect(strip.locator("[data-market-explorer-focus-tool='demand-pressure']")).toHaveAttribute("data-focus-tool-state", "unavailable");
  await expect(strip).toContainText("Demand Pressure data is not available for this market yet.");
  await expect(strip.locator("[data-market-explorer-focus-tool='fair-value']")).toHaveAttribute("data-focus-tool-state", "locked");
  await expect(strip.locator("[data-market-explorer-focus-tool-button]").first()).toBeDisabled();
  await shot(page, "plus-focus-tools");
  // Builder stays Premium for Index+.
  await page.click("[data-market-explorer-build-trigger]");
  await expect(page.getByRole("tab", { name: /Custom Filters/ })).toContainText("Premium");
  await context.close();
});

test("PREMIUM: 10 active markets fit, the 11th is blocked with Premium copy and no upgrade CTA", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  const sets = [["Fossil", "set-fossil"], ["Jungle", "set-jungle"], ["Base Set 2", "set-bs2"], ["HeartGold", "set-hgss"], ["Neo Genesis", "set-neo-genesis"], ["Neo Discovery", "set-neo-discovery"], ["Neo Revelation", "set-neo-revelation"], ["Neo Destiny", "set-neo-destiny"]];
  let n = 0;
  for (const [label, frag] of sets) await addRow(page, "sets", label, frag, ++n);
  await addRow(page, "eras", "Base/WOTC", "era-base", ++n);
  await addRow(page, "eras", "Neo", "era-neo", ++n);
  await expect(chips(page)).toHaveCount(10);
  await pickRow(page, "eras", "HeartGold");
  await expect(limitMessage(page)).toHaveText("Premium supports up to 10 active comparison markets.");
  await expect(page.locator("[data-market-explorer-compare-upgrade-link]")).toHaveCount(0);
  await expect(chips(page)).toHaveCount(10);
  await shot(page, "premium-eleventh-blocked");
  await page.locator("[data-market-explorer-compare-upgrade] button", { hasText: "Dismiss" }).click();
  // Premium focus tools: both unavailable (no server authority), never a value.
  await chip(page, "set-fossil").locator("[data-market-explorer-active-focus]").click();
  const strip = page.locator("[data-market-explorer-focus-strip]");
  await expect(strip.locator("[data-market-explorer-focus-tool='demand-pressure']")).toHaveAttribute("data-focus-tool-state", "unavailable");
  await expect(strip.locator("[data-market-explorer-focus-tool='fair-value']")).toHaveAttribute("data-focus-tool-state", "unavailable");
  await expect(strip).toContainText("inDex Fair Value is not available for this market yet.");
  await expect(page.locator("[data-market-performance-overlay]")).toHaveCount(0);
  await context.close();
});

test("focus strip sits at the TOP of the graph; other chips AND lines recede; tools never show values", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await addRow(page, "sets", "Fossil", "set-fossil");
  await addRow(page, "sets", "Jungle", "set-jungle");
  await addRow(page, "sets", "Base Set 2", "set-bs2");
  await chip(page, "set-jungle").locator("[data-market-explorer-active-focus]").click();
  const strip = page.locator("[data-market-explorer-focus-strip]");
  await expect(strip).toBeVisible();
  const stripBox = await strip.boundingBox();
  const plotBox = await page.locator("svg polyline[data-market-performance-series]").first().evaluate((el) => { const r = el.ownerSVGElement.getBoundingClientRect(); return { y: r.y }; });
  expect(stripBox.y, "focus tools are above the plot").toBeLessThan(plotBox.y);
  await expect(strip).toContainText("Focused: ");
  await expect(strip.locator("[data-market-explorer-clear-focus]")).toBeVisible();
  const chipStates = await chips(page).evaluateAll((els) => els.map((el) => ({ key: el.getAttribute("data-market-explorer-active-chip"), dimmed: el.getAttribute("data-market-explorer-active-chip-dimmed"), opacity: Number(getComputedStyle(el).opacity), filter: getComputedStyle(el).filter })));
  const focused = chipStates.find((s) => s.key.includes("set-jungle"));
  const others = chipStates.filter((s) => !s.key.includes("set-jungle"));
  expect(focused.dimmed).toBe("false");
  expect(focused.opacity).toBe(1);
  for (const other of others) { expect(other.dimmed).toBe("true"); expect(other.opacity).toBeLessThan(1); expect(other.opacity).toBeGreaterThan(0.3); expect(other.filter).toContain("grayscale"); }
  const lines = await page.locator("polyline[data-market-performance-series]").evaluateAll((els) => els.map((el) => el.getAttribute("data-market-performance-focus")));
  expect(lines.filter((x) => x === "dimmed").length).toBeGreaterThanOrEqual(2);
  record("focus-recede", { chipStates, lines });
  await shot(page, "plus-focus-mode-chips-and-lines");
  // A dimmed chip is still operable (toggles focus to itself).
  await chip(page, "set-bs2").locator("[data-market-explorer-active-focus]").click();
  await expect(chip(page, "set-bs2")).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
  // Clicking the focused chip's magnifier clears focus.
  await chip(page, "set-bs2").locator("[data-market-explorer-active-focus]").click();
  await expect(page.locator("[data-market-explorer-focus-strip]")).toHaveCount(0);
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("Rare Holo GX (V2 PREPARED_CANDIDATE): loads, draws a line, is an Active Market, exposes constituents with images, and switches", async ({ browser }) => {
  await resetFixtureRequests();
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await addRow(page, "sets", "Fossil", "set-fossil");
  await closeDirectory(page);
  await ensureTools(page);
  await page.click("[data-rarity-market-trigger]");
  const gx = page.locator("[data-rarity-market='rareHoloGX']");
  await expect(gx).toHaveAttribute("data-rarity-market-action", "prepared");
  await expect(gx).toBeEnabled();
  await gx.click();
  await expect(chip(page, "rareHoloGx")).toHaveCount(1, { timeout: 30000 });
  await expect(chip(page, "rareHoloGx").locator("[data-market-explorer-active-inspect]")).toContainText("Rare Holo GX — Cards");
  await expect(page.locator("polyline[data-market-performance-series='rarity:rareHoloGx']")).toHaveCount(1);
  await page.click("[data-market-explorer-view-details]");
  await page.locator("[data-market-constituents-target='rarity:rareHoloGx']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Rare Holo GX");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await expect(page.locator("[data-market-constituents-table] img[data-market-constituent-thumb]").first()).toBeVisible();
  const broken = await page.evaluate(() => [...document.querySelectorAll("img[data-market-constituent-thumb]")].filter((img) => img.complete && img.naturalWidth === 0).length);
  expect(broken).toBe(0);
  await shot(page, "v2-rare-holo-gx-constituents");
  // Switch away and back.
  await page.locator("[data-market-constituents-target='set:set-fossil']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Fossil");
  await page.locator("[data-market-constituents-target='rarity:rareHoloGx']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Rare Holo GX");
  expect(preparedPosts(net).some((post) => post.marketKeys.includes("rarity:rareHoloGx"))).toBe(true);
  // The separate CUSTOM_BUILD_AVAILABLE case is a build path (query endpoint is NOT modelled in the fixture: unproven end to end).
  await page.click("[data-market-explorer-hide-details]");
  await context.close();
});

test("all rarity options resolve to a visible truthful state (PREPARED / build / disabled with reason)", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await ensureTools(page);
  await page.click("[data-rarity-market-trigger]");
  const states = await page.locator("[data-rarity-market]").evaluateAll((els) => els.map((el) => ({ id: el.getAttribute("data-rarity-market"), state: el.getAttribute("data-rarity-market-state"), action: el.getAttribute("data-rarity-market-action"), disabled: el.disabled, reason: el.querySelector("[data-rarity-market-reason]")?.textContent || null })));
  expect(states.length).toBeGreaterThanOrEqual(9);
  for (const s of states) {
    if (s.action === "none") { expect(s.disabled).toBe(true); expect(s.reason).toBeTruthy(); }
    else { expect(["prepared", "build"]).toContain(s.action); expect(s.disabled).toBe(false); }
  }
  record("rarity-states", states);
  await shot(page, "v2-rarity-states");
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("Sealed V2: Cards-like IA; every type lands in Sealed Types once; Cases/Displays note; whole market under Sets", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await ensureTools(page);
  await layer(page, "sealed").click();
  await expect(page.locator("[data-market-directory-category]")).toHaveCount(4);
  await expect(page.locator("[data-market-directory-category='types']")).toContainText("Sealed Types");
  await expect(page.locator("[data-market-explorer-rarity-markets]")).toHaveCount(0);
  await expect(page.getByText("Sealed Markets", { exact: true })).toHaveCount(0);
  await shot(page, "v2-sealed-browse");
  const keysIn = async (category) => { await chooseCategory(page, category); return page.locator("[data-prepared-market]").evaluateAll((els) => els.map((el) => el.getAttribute("data-prepared-market"))); };
  const setKeys = await keysIn("sets");
  expect(setKeys).toContain("sealedMarket");
  expect(setKeys.filter((k) => k.startsWith("sealed-set:")).length).toBeGreaterThanOrEqual(4);
  expect(setKeys.some((k) => k.startsWith("sealed-type:") || k.startsWith("sealed-era:"))).toBe(false);
  const eraKeys = await keysIn("eras");
  expect(eraKeys.every((k) => k.startsWith("sealed-era:"))).toBe(true);
  await chooseCategory(page, "quick");
  await expect(page.locator("[data-sealed-quick-empty]")).toContainText("No approved Sealed Quick Markets yet.");
  await chooseCategory(page, "types");
  const wanted = ["booster_box", "elite_trainer_box", "case", "display", "three_pack_blister", "collection_product"];
  for (const type of wanted) await expect(page.locator(`[data-sealed-type='${type}']`)).toHaveCount(1);
  await expect(page.locator("[data-sealed-type='case'] [data-sealed-type-note]")).toContainText("Bulk container — tracked separately from Total Sealed");
  await expect(page.locator("[data-sealed-type='display'] [data-sealed-type-note]")).toContainText("Bulk container — tracked separately from Total Sealed");
  await expect(page.locator("[data-sealed-type='half_booster_box'] [data-sealed-type-reason]")).toHaveCount(1);
  await shot(page, "v2-sealed-types");
  // Cases are a VALID market: selecting one loads it, labelled as Sealed.
  await page.locator("[data-sealed-type-action-button='case']").click();
  await expect(chip(page, "sealed-type:case")).toHaveCount(1, { timeout: 30000 });
  await expect(chip(page, "sealed-type:case").locator("[data-market-explorer-active-inspect]")).toContainText("— Sealed");
  await expect(page.locator("polyline[data-market-performance-series='sealed-type:case']")).toHaveCount(1);
  // No type identity is duplicated in Sets/Eras/Quick.
  for (const category of ["sets", "eras", "quick"]) {
    const keys = await keysIn(category);
    expect(keys.filter((k) => k.startsWith("sealed-type:")), category).toEqual([]);
  }
  await context.close();
});

test("Sealed V1 fallback keeps the SAME designed IA with truthful awaiting states", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v1 });
  await openExplorer(page, URLS.v1);
  await layer(page, "sealed").click();
  await expect(page.locator("[data-market-directory-category]")).toHaveCount(4);
  await expect(page.locator("[data-market-directory-category='sets']")).toContainText("Sets");
  await expect(page.getByText("Sealed Markets", { exact: true })).toHaveCount(0);
  await chooseCategory(page, "sets");
  await expect(page.locator("[data-sealed-awaiting='sets']")).toContainText("Sealed Set markets are awaiting the next prepared market generation.");
  await chooseCategory(page, "eras");
  await expect(page.locator("[data-sealed-awaiting='eras']")).toContainText("Sealed Era markets are awaiting the next prepared market generation.");
  await chooseCategory(page, "quick");
  await expect(page.locator("[data-sealed-quick-empty]")).toContainText("No approved Sealed Quick Markets yet.");
  await chooseCategory(page, "types");
  await expect(page.locator("[data-sealed-v1-formats] [data-prepared-market]")).toHaveCount(2);
  await expect(page.locator("[data-sealed-types-awaiting-more]")).toBeVisible();
  await shot(page, "v1-sealed-same-ia");
  await page.locator("[data-sealed-v1-formats] [data-prepared-market]", { hasText: "Booster Boxes" }).click();
  await expect(page.locator("[data-market-explorer-active-chip*='sealed-format:boosterBox']")).toHaveCount(1, { timeout: 30000 });
  await expect(chips(page)).toHaveCount(1);
  for (const post of preparedPosts(net)) expect(post.contextMarketKeys).toEqual([]);
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("constituents: persistent trigger, reopen restores target + cache, chips list ALL active markets with asset labels", async ({ browser }) => {
  await resetFixtureRequests();
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await addRow(page, "sets", "Fossil", "set-fossil");
  await closeDirectory(page);
  await ensureTools(page);
  await page.click("[data-rarity-market-trigger]");
  await page.locator("[data-rarity-market='rareUltra']").click();
  await expect(chip(page, "rarity:rareUltra")).toHaveCount(1, { timeout: 30000 });
  await layer(page, "sealed").click();
  await chooseCategory(page, "types");
  await page.locator("[data-sealed-type-action-button='booster_box']").click();
  await expect(chip(page, "sealed-type:booster_box")).toHaveCount(1, { timeout: 30000 });
  await expect(page.locator("[data-market-explorer-view-details]")).toBeVisible();
  await page.click("[data-market-explorer-view-details]");
  const switcher = page.locator("[data-market-constituents-picker]");
  await expect(switcher).toContainText("Fossil — Cards");
  await expect(switcher).toContainText("Rare Ultra — Cards");
  await expect(switcher).toContainText("Booster Boxes — Sealed");
  await page.locator("[data-market-constituents-target='rarity:rareUltra']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Rare Ultra");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await shot(page, "v2-constituents-open-chips");
  const constituentCalls = () => net.requests.filter((r) => r.url.includes("prepared-constituents")).length;
  const callsBefore = constituentCalls();
  const seriesBefore = await page.locator("polyline[data-market-performance-series]").count();
  await chip(page, "set-fossil").locator("[data-market-explorer-active-visibility]").click(); // hide one on the chart
  await page.click("[data-market-explorer-hide-details]");
  // Closing never clears markets / hidden state / target.
  await expect(chips(page)).toHaveCount(3);
  await expect(chip(page, "set-fossil")).toHaveAttribute("data-market-explorer-active-chip-hidden", "true");
  await expect(page.locator("[data-market-explorer-workspace]")).toHaveAttribute("data-market-explorer-detail-series", "rarity:rareUltra");
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Rare Ultra");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible();
  expect(constituentCalls(), "reopen restores the cached page: no refetch").toBe(callsBefore);
  // A hidden market stays inspectable.
  await page.locator("[data-market-constituents-target='set:set-fossil']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Fossil");
  // Chip switching changes ONLY the target: no market removed, no extra comparison call.
  await expect(chips(page)).toHaveCount(3);
  expect(await page.locator("polyline[data-market-performance-series]").count()).toBeLessThanOrEqual(seriesBefore);
  expect(preparedPosts(net).length).toBeLessThanOrEqual(3);
  await context.close();
});

test("Raw V2: chip enabled, first page loads, next page loads, away-and-back works", async ({ browser }) => {
  await resetFixtureRequests();
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await pickRow(page, "sets", "Raw Card Market");
  await addRow(page, "sets", "Fossil", "set-fossil");
  await page.click("[data-market-explorer-view-details]");
  const rawChip = page.locator("[data-market-constituents-target='raw']");
  await expect(rawChip).toBeEnabled();
  await rawChip.click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Raw Card Market");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  const before = await page.locator("[data-market-constituent]").count();
  await page.locator("[data-market-constituents-load-more], button:has-text('Load more')").first().click();
  await expect.poll(() => page.locator("[data-market-constituent]").count(), { timeout: 30000 }).toBeGreaterThan(before);
  await page.locator("[data-market-constituents-target='set:set-fossil']").click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Fossil");
  await rawChip.click();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Raw Card Market");
  const server = await fixtureRequests(URLS.backend);
  const rawPages = server.filter((r) => r.route === "/market/explorer/prepared-constituents" && r.query?.marketKey === "raw");
  expect(rawPages).toHaveLength(2); // first page + next page; switching back uses the cache
  await context.close();
});

test("Raw V1: selectable market, deliberate unavailable message, NO fake constituent reconstruction calls", async ({ browser }) => {
  await resetFixtureRequests(URLS.backendV1);
  const { context, page, net } = await newSession(browser, { base: URLS.v1, plan: "plus" });
  await openExplorer(page, URLS.v1);
  await expect(chip(page, "raw")).toHaveCount(1);
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituents-not-inspectable-item='raw']")).toContainText("Raw Card Market composition is not available in the current published generation.");
  await expect(page.locator("[data-market-constituents-page-loading]")).toHaveCount(0);
  await expect(page.locator("[data-market-constituents-not-inspectable-item='raw']")).toBeVisible();
  await shot(page, "v1-raw-unavailable");
  expect(net.requests.filter((r) => r.url.includes("prepared-constituents") || r.url.includes("marketKey=raw"))).toEqual([]);
  const server = await fixtureRequests(URLS.backendV1);
  expect(server.filter((r) => r.route === "/market/explorer/prepared-constituents")).toEqual([]);
  await context.close();
});

test("broken image URL falls back to the neutral placeholder; no broken-image icon", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await clearAll(page);
  await addRow(page, "sets", "Neo Genesis", "set-neo-genesis");
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await expect(page.locator("[data-market-constituents-table] [data-market-constituent-image-placeholder]").first()).toBeVisible({ timeout: 15000 });
  const brokenIcons = await page.evaluate(() => [...document.querySelectorAll("img[data-market-constituent-thumb]")].filter((img) => img.complete && img.naturalWidth === 0).length);
  expect(brokenIcons).toBe(0);
  await shot(page, "v2-broken-image-fallback");
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("search: Cards / Sealed / Graded behave truthfully; stale aborted responses never overwrite newer ones", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  const input = page.locator("[data-market-explorer-search-input]");
  const results = page.locator("[data-market-explorer-search-panel] [role=option]");
  const kinds = async (text) => {
    const response = page.waitForResponse((r) => r.url().includes("/api/market/explorer/catalog-search") && r.url().includes(`q=${encodeURIComponent(text).replace(/%20/g, "+")}`));
    await input.fill(text);
    await response;
    await expect(results.first()).toBeVisible({ timeout: 15000 });
    return results.evaluateAll((els) => els.map((el) => el.textContent));
  };
  expect((await kinds("Fossil")).join(" ")).toContain("Fossil");
  expect((await kinds("Base/WOTC")).join(" ")).toContain("Base/WOTC");
  expect((await kinds("Rare Ultra")).join(" ")).toContain("Rare Ultra");
  expect((await kinds("Rare Holo GX")).join(" ")).toContain("Rare Holo GX");
  // Specific card: instrument result -> Exact Basket offered, card detail HIDDEN without canonicalCardId.
  const gengar = await kinds("Gengar");
  expect(gengar.join(" ")).toContain("Fixture Gengar");
  await expect(page.locator("[data-search-secondary='basket']").first()).toBeVisible();
  await expect(page.locator("[data-search-primary='detail']")).toHaveCount(0);
  await shot(page, "search-card-instrument");
  // A market result loads through the same prepared loader (one chip, replace semantics for the workspace).
  await input.fill("Jungle");
  await page.locator("[data-search-primary='activate']").first().click();
  await expect(chip(page, "set-jungle")).toHaveCount(1, { timeout: 30000 });
  // No duplicate asset selector inside search.
  await expect(page.locator("[data-market-explorer-contextual-search] [data-market-directory-asset]")).toHaveCount(0);
  // Sealed.
  await layer(page, "sealed").click();
  await input.fill("");
  expect((await kinds("Fossil")).join(" ")).toContain("Fossil");
  expect((await kinds("Case")).join(" ")).toContain("Cases");
  expect((await kinds("Booster Box")).join(" ")).toContain("Booster Box");
  await input.fill("product");
  await expect(page.locator("[data-search-result-kind='instrument']").first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator("[data-search-primary='detail']").first()).toHaveAttribute("target", "_blank");
  await shot(page, "search-sealed");
  // Graded: a truthful insufficient-authority state, nothing activatable.
  await layer(page, "graded").click();
  await input.fill("psa");
  await expect(page.locator("[data-search-result-reason]").first()).toContainText("not available");
  await expect(page.locator("[data-search-primary='activate']")).toHaveCount(0);
  // Stale responses: type a slow query then a fast one; only the fast results may show.
  await layer(page, "cards").click();
  await input.fill("slow");
  await page.waitForTimeout(350); // let the slow request become in-flight before superseding it
  await input.fill("Fossil");
  await expect(results.first()).toContainText("Fossil", { timeout: 15000 });
  await page.waitForTimeout(2200);
  await expect(page.getByText("STALE RESULT")).toHaveCount(0);
  const slow = net.requests.filter((r) => r.url.includes("catalog-search") && r.url.includes("q=slow"));
  expect(slow.length).toBeGreaterThanOrEqual(1);
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("Clear All: one red control; keeps the Builder draft and the Browse context; clears everything else", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "premium" });
  await openExplorer(page, URLS.v2);
  await addRow(page, "sets", "Fossil", "set-fossil");
  await layer(page, "sealed").click();
  await page.click("[data-market-explorer-build-trigger]");
  const draft = page.locator("[data-market-exact-search]");
  await expect(draft).toBeVisible();
  await draft.fill("gengar draft");
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-market-explorer-builder-overlay]")).toBeHidden();
  await expect(page.locator("[data-market-explorer-active-clear-all]")).toHaveCount(1);
  await page.click("[data-market-explorer-active-clear-all]");
  await expect(page.locator("[data-market-explorer-active-chip]")).toHaveCount(0);
  // Browse context is unchanged.
  await expect(layer(page, "sealed")).toHaveAttribute("aria-pressed", "true");
  // The Builder draft survived.
  await page.click("[data-market-explorer-build-trigger]");
  await expect(page.locator("[data-market-exact-search]")).toHaveValue("gengar draft");
  await shot(page, "premium-clear-all-keeps-builder-draft");
  await context.close();
});

// ---------------------------------------------------------------------------------------------
test("MOBILE 390x844: browse context, search, categories, chips, touch magnifier, centred View, switcher, no page overflow", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport: VIEWPORTS.mobile, mobile: true });
  await openExplorer(page, URLS.v2);
  await ensureTools(page);
  for (const id of ["cards", "sealed", "graded"]) await expect(layer(page, id)).toBeVisible();
  await layer(page, "sealed").tap();
  await expect(page.locator("[data-market-explorer-search-input]")).toBeVisible();
  for (const c of ["sets", "eras", "quick", "types"]) await expect(page.locator(`[data-market-directory-category='${c}']`)).toBeVisible();
  await shot(page, "mobile-sealed-browse");
  await layer(page, "cards").tap();
  await clearAll(page);
  await addRow(page, "sets", "Fossil", "set-fossil");
  await addRow(page, "sets", "Jungle", "set-jungle");
  const magnifier = chip(page, "set-fossil").locator("[data-market-explorer-active-focus]");
  await magnifier.scrollIntoViewIfNeeded();
  expect(await magnifier.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await magnifier.tap();
  await expect(chip(page, "set-fossil")).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
  await shot(page, "mobile-focus");
  await expect(page.locator("[data-market-explorer-active-clear-all]")).toHaveCount(1);
  const view = page.locator("[data-market-explorer-view-details]");
  await view.scrollIntoViewIfNeeded();
  const workspaceBox = await page.locator("[data-market-explorer-chart-workspace]").boundingBox();
  const viewBox = await view.boundingBox();
  expect(Math.abs(viewBox.x + viewBox.width / 2 - (workspaceBox.x + workspaceBox.width / 2))).toBeLessThanOrEqual(8);
  await view.tap();
  await expect(page.locator("[data-market-constituents-picker]")).toBeVisible({ timeout: 30000 });
  await page.locator("[data-market-constituents-target='set:set-jungle']").tap();
  await expect(page.locator("[data-market-constituents-active]")).toContainText("Jungle");
  await shot(page, "mobile-constituents");
  await page.locator("[data-market-explorer-hide-details]").tap();
  await expect(page.locator("[data-market-explorer-compare-results]")).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await context.close();
});

// ---------------------------------------------------------------------------------------------
for (const [name, viewport] of [["1440x900", VIEWPORTS.desktop], ["1920x1080", { width: 1920, height: 1080 }]]) {
  test(`${name}: View and Hide Constituents are centred over the workspace (measured) and violet`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport });
    await openExplorer(page, URLS.v2);
    await addRow(page, "sets", "Fossil", "set-fossil");
    const workspace = page.locator("[data-market-explorer-chart-workspace]");
    const cx = async (l) => { const b = await l.boundingBox(); return b.x + b.width / 2; };
    const view = page.locator("[data-market-explorer-view-details]");
    await view.scrollIntoViewIfNeeded();
    const viewOffset = Math.abs((await cx(view)) - (await cx(workspace)));
    await view.click();
    const hide = page.locator("[data-market-explorer-hide-details]");
    const hideOffset = Math.abs((await cx(hide)) - (await cx(workspace)));
    record(`center-${name}`, { viewOffset: +viewOffset.toFixed(2), hideOffset: +hideOffset.toFixed(2) });
    expect(viewOffset).toBeLessThanOrEqual(8);
    expect(hideOffset).toBeLessThanOrEqual(8);
    expect(await view.evaluate((el) => getComputedStyle(el).boxShadow)).toContain("139, 92, 246");
    expect(await hide.evaluate((el) => getComputedStyle(el).boxShadow)).toContain("139, 92, 246");
    await context.close();
  });
}
