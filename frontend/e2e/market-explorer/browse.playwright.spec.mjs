// Browse / search / Sealed IA / rarity / Raw / labels / artwork in a real browser.
// V1 = what production serves today (fixture V1 backend, plus optional live-anonymous).
// V2 = FIXTURE ONLY: proves the intended UI before a V2 serving generation exists.
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, pickRow, chooseCategory, shot, URLS, VIEWPORTS } from "./helpers.mjs";

const chip = (page, fragment) => page.locator(`[data-market-explorer-active-chip*="${fragment}"]`);
const preparedPosts = (net) => net.requests.filter((r) => r.method === "POST" && r.url === "/api/market/explorer/prepared").map((r) => JSON.parse(r.body));
const categories = (page) => page.locator("[data-market-directory-category]").evaluateAll((els) => els.map((el) => el.textContent.replace(/[▾\s]+$/g, "").trim()));
const layer = (page, id) => page.locator(`[data-market-directory-asset="${id}"]`);

for (const [name, base] of [["V1 fixture", URLS.v1], ["V2 fixture", URLS.v2]]) {
  test(`${name}: asset selector with ONE contextual search directly beneath; Graded is truthfully unavailable`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base });
    await openExplorer(page, base);
    const group = page.locator("[data-market-directory-asset-layer]");
    await expect(group.locator("[data-market-directory-asset]")).toHaveCount(3);
    const search = page.locator("[data-market-explorer-search-input]");
    await expect(search).toHaveCount(1);
    const g = await group.boundingBox();
    const s = await search.boundingBox();
    expect(s.y).toBeGreaterThanOrEqual(g.y + g.height - 1);
    expect(s.y - (g.y + g.height)).toBeLessThan(40); // directly underneath
    await expect(search).toHaveAttribute("placeholder", "Search cards or card markets…");
    await expect(page.locator("[data-market-explorer-contextual-search] [data-market-directory-asset]")).toHaveCount(0);
    await shot(page, `${name.replace(" ", "-")}-search-cards`);

    await layer(page, "sealed").click();
    await expect(search).toHaveAttribute("placeholder", "Search sealed products or sealed markets…");
    await expect(page.locator("[data-market-explorer-search-input]")).toHaveCount(1);
    await shot(page, `${name.replace(" ", "-")}-search-sealed`);

    await layer(page, "graded").click();
    await expect(page.locator("[data-market-directory-state=graded-unavailable]")).toContainText("Graded markets are unavailable");
    await expect(page.locator("[data-market-explorer-search-input]")).toHaveCount(1);
    await shot(page, `${name.replace(" ", "-")}-search-graded`);
    await context.close();
  });
}

test("Sealed V1 fixture: coherent flat Sealed Markets list, no invented Set/Era/Type markets", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v1 });
  await openExplorer(page, URLS.v1);
  await layer(page, "sealed").click();
  const cats = await categories(page);
  expect(cats[0]).toBe("Sealed Markets");
  expect(cats.filter((c) => /^(Sets|Eras|Quick Markets|Sealed Types)$/.test(c))).toEqual([]);
  await expect(page.locator('[data-market-directory-category="types"]')).toHaveCount(0);
  await expect(page.locator('[data-market-directory-category="sets"]')).toHaveCount(0);
  await chooseCategory(page, "sealed");
  await expect(page.locator("[data-prepared-market]")).toHaveCount(2);
  await shot(page, "v1-fixture-sealed-ia");
  await pickRow(page, "sealed", "Booster Boxes");
  await expect(chip(page, "sealed-format").first()).toBeVisible({ timeout: 30000 });
  await context.close();
});

test("Sealed V2 fixture: Search, Sets, Eras, Quick Markets, Sealed Types, Screens, Build; no flat Sealed Markets", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v2 });
  await openExplorer(page, URLS.v2);
  await layer(page, "sealed").click();
  const cats = await categories(page);
  expect(cats.slice(0, 4)).toEqual(["Sets", "Eras", "Quick Markets", "Sealed Types"]);
  expect(cats.join("|")).not.toMatch(/Sealed Markets/);
  await expect(page.locator("[data-market-explorer-search-input]")).toHaveCount(1);
  await expect(page.locator("[data-market-explorer-build-trigger]")).toHaveCount(1);
  await expect(page.getByText("Screens", { exact: true }).first()).toBeVisible();
  await shot(page, "v2-fixture-sealed-ia");

  await chooseCategory(page, "quick");
  await expect(page.locator("[data-sealed-quick-empty]")).toContainText("No approved Sealed Quick Markets yet.");
  await shot(page, "v2-fixture-sealed-quick-empty");

  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "sealed-set:set-fossil")).toHaveCount(1, { timeout: 30000 });
  await expect(chip(page, "sealed-set:set-fossil")).toContainText("Fossil — Sealed");
  await pickRow(page, "eras", "Base");
  await expect(chip(page, "sealed-era:era-base")).toHaveCount(1, { timeout: 30000 });
  await expect(chip(page, "sealed-era:era-base")).toContainText("— Sealed");

  await chooseCategory(page, "types");
  const panel = page.locator("[data-market-directory-sealed-types]");
  await expect(panel).toContainText("Cases");
  await expect(panel).toContainText("Displays");
  await expect(panel.locator("[data-sealed-type-note]").first()).toContainText("Bulk container");
  await expect(panel.locator("[data-sealed-type-state='INVALID']")).toHaveCount(0);
  await shot(page, "v2-fixture-sealed-types");
  for (const type of ["case", "display", "booster_box"]) {
    await panel.locator(`[data-sealed-type="${type}"] [data-sealed-type-action-button]`).click();
    await expect(chip(page, `sealed-type:${type}`)).toHaveCount(1, { timeout: 30000 });
  }
  // sealedMarket parent through contextual search
  const search = page.locator("[data-market-explorer-search-input]");
  await search.fill("Total");
  await page.locator("[data-search-market='sealedMarket'], [data-search-primary]").first().click();
  await expect(chip(page, "sealedMarket")).toHaveCount(1, { timeout: 30000 });
  const keys = preparedPosts(net).map((p) => p.marketKeys[0]);
  for (const k of ["sealed-set:set-fossil", "sealed-era:era-base", "sealed-type:case", "sealed-type:display", "sealed-type:booster_box", "sealedMarket"]) expect(keys).toContain(k);
  for (const post of preparedPosts(net)) expect(post.contextMarketKeys).toEqual([]);
  expect(net.failed.filter((f) => f.url.startsWith("/api/market/explorer/prepared"))).toEqual([]);
  await context.close();
});

test("asset labels: Cards / Sealed context on Set and Era chips (published asset, not key parsing)", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set:set-fossil")).toContainText("Fossil — Cards", { timeout: 30000 });
  await layer(page, "sealed").click();
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "sealed-set:set-fossil")).toContainText("Fossil — Sealed", { timeout: 30000 });
  await layer(page, "cards").click();
  await pickRow(page, "sets", "Base Set 2");
  await expect(chip(page, "set:set-bs2")).toContainText("Base Set 2 — Cards", { timeout: 30000 });
  await pickRow(page, "eras", "Base");
  await expect(chip(page, "era:era-base")).toContainText("— Cards", { timeout: 30000 });
  await shot(page, "v2-fixture-asset-labels");
  await expect(chip(page, "raw")).not.toContainText("— Cards");
  await context.close();
});

test("rarity V2 fixture: every option resolves to exactly ONE truthful state; no click-to-nothing", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await page.locator("[data-rarity-market-trigger]").click();
  const wanted = ["Rare Holo GX", "Rare Holo EX", "Rare Holo V", "Rare Holo VMAX", "Rare Holo VSTAR", "Rare Ultra", "Rare Secret", "Ultra Rare", "Special Illustration Rare"];
  const options = page.locator("[data-rarity-market]");
  const labels = await options.evaluateAll((els) => els.map((el) => el.querySelector("span span")?.textContent));
  for (const label of wanted) expect(labels).toContain(label);
  const summary = [];
  for (const label of wanted) {
    const option = options.filter({ hasText: label }).first();
    const state = await option.getAttribute("data-rarity-market-state");
    const action = await option.getAttribute("data-rarity-market-action");
    const disabled = await option.isDisabled();
    const before = await page.locator("[data-market-explorer-active-chip]").count();
    if (disabled) {
      await expect(option.locator("[data-rarity-market-reason]")).not.toHaveText("");
      summary.push({ label, state, action, outcome: "blocked-with-reason" });
      continue;
    }
    const posts = page.waitForRequest((r) => r.url().includes("/api/market/explorer/"), { timeout: 15000 }).catch(() => null);
    await option.click();
    await posts;
    await page.waitForTimeout(800);
    const after = await page.locator("[data-market-explorer-active-chip]").count();
    const upgrade = await page.locator("[data-market-explorer-compare-upgrade]").count();
    const alert = await page.locator("[data-market-explorer-rarity-markets] [role=alert]").count();
    const outcome = after > before ? "market-added" : upgrade ? "upgrade-prompt" : alert ? "truthful-message" : "NOTHING";
    summary.push({ label, state, action, outcome });
    expect(outcome, `${label} must not click-to-nothing`).not.toBe("NOTHING");
  }
  test.info().annotations.push({ type: "rarity-summary", description: JSON.stringify(summary) });
  console.log("RARITY", JSON.stringify(summary));
  await shot(page, "v2-fixture-rarity");
  await context.close();
});

test("Raw Card Market: V1 is truthfully NOT inspectable; V2 (index_and_composition + available) is inspectable", async ({ browser }) => {
  // V1: Index+ user, default Raw chip present.
  let s = await newSession(browser, { base: URLS.v1, plan: "plus" });
  await openExplorer(s.page, URLS.v1);
  await s.page.click("[data-market-explorer-view-details]");
  const item = s.page.locator("[data-market-constituents-not-inspectable-item='raw']");
  await expect(item).toContainText("Raw Card Market composition is not available in the current published generation.");
  await expect(s.page.locator("[data-market-constituents-target-unavailable='raw']")).toBeDisabled();
  await expect(s.page.locator("[data-market-constituents-page-loading]")).toHaveCount(0);
  await shot(s.page, "v1-fixture-raw-not-available");
  await s.context.close();

  // V2 fixture: activate the V2 Raw parent through contextual search.
  s = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(s.page, URLS.v2);
  await s.page.locator("[data-market-explorer-search-input]").fill("Raw");
  await s.page.locator("[data-search-primary]").first().click();
  await expect(s.page.locator("[data-market-explorer-active-chip='raw']")).toHaveCount(1, { timeout: 30000 });
  await s.page.click("[data-market-explorer-view-details]");
  await expect(s.page.locator("[data-market-constituents-not-inspectable-item='raw']")).toHaveCount(0);
  await expect(s.page.locator("[data-market-constituents-target='raw']")).toBeEnabled();
  await s.page.locator("[data-market-constituents-target='raw']").click();
  await expect(s.page.locator("[data-market-constituents-active]")).toContainText("Raw Card Market");
  await expect(s.page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await shot(s.page, "v2-fixture-raw-inspectable");
  await s.context.close();
});

test("artwork across Set/Rarity markets; missing artwork is an intentional placeholder", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set:set-fossil")).toHaveCount(1, { timeout: 30000 });
  for (const [label, frag] of [["HeartGold", "set:set-hgss"], ["Base Set 2", "set:set-bs2"], ["Jungle", "set:set-jungle"]]) {
    await page.locator("li[role=option]", { hasText: label }).first().locator("[data-compare-market]").click();
    await expect(chip(page, frag)).toHaveCount(1, { timeout: 30000 });
  }
  await page.keyboard.press("Escape");
  await page.mouse.click(700, 500);
  for (const label of ["Rare Ultra", "Rare Secret"]) {
    await page.locator("[data-rarity-market-trigger]").scrollIntoViewIfNeeded();
    if ((await page.locator("[data-rarity-market-trigger]").getAttribute("aria-expanded")) !== "true") await page.locator("[data-rarity-market-trigger]").click();
    await page.locator("[data-rarity-market]", { hasText: label }).first().click();
    await expect(chip(page, `rarity:${label === "Rare Ultra" ? "rareUltra" : "rareSecret"}`)).toHaveCount(1, { timeout: 30000 });
  }
  await page.click("[data-market-explorer-view-details]");
  const withArt = ["set:set-fossil", "set:set-hgss", "set:set-bs2", "rarity:rareUltra", "rarity:rareSecret"];
  for (const key of [...withArt, "set:set-jungle"]) {
    await page.locator(`[data-market-constituents-target='${key}']`).click();
    await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
    await page.waitForTimeout(400);
    const visible = await page.evaluate(() => {
      const inView = (el) => el.offsetParent !== null && el.getBoundingClientRect().top < window.innerHeight && el.getBoundingClientRect().bottom > 0;
      const thumbs = [...document.querySelectorAll("[data-market-constituent-thumb]")].filter(inView);
      return { thumbs: thumbs.length, broken: thumbs.filter((i) => !i.complete || i.naturalWidth === 0).length, placeholders: [...document.querySelectorAll("[data-market-constituent-image-placeholder]")].filter(inView).length };
    });
    if (withArt.includes(key)) { expect(visible.thumbs, key).toBeGreaterThan(0); expect(visible.broken, key).toBe(0); }
    else { expect(visible.thumbs, key).toBe(0); expect(visible.placeholders, key).toBeGreaterThan(0); }
  }
  await shot(page, "v2-fixture-placeholder-jungle");
  await context.close();
});

test("basic ordinary rows: switch-to-market is primary; ONE restrained Index+ note; no locked-looking rows (mobile too)", async ({ browser }) => {
  for (const [viewport, mobile] of [[VIEWPORTS.desktop, false], [VIEWPORTS.mobile, true]]) {
    const { context, page } = await newSession(browser, { base: URLS.v1, viewport, mobile });
    await openExplorer(page, URLS.v1);
    await chooseCategory(page, "sets");
    await expect(page.locator("[data-prepared-market]").first()).toBeVisible();
    await expect(page.locator("[data-compare-market]")).toHaveCount(0);
    await expect(page.locator("[data-compare-upsell]")).toHaveCount(1);
    expect(await page.locator("[data-market-directory-popover]").innerText()).not.toMatch(/Compare with Index\+/);
    await shot(page, `v1-fixture-basic-browse-rows-${mobile ? "mobile" : "desktop"}`);
    await context.close();
  }
});
