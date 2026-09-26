// View/Hide geometry, constituent entitlement states, the constituent switcher,
// artwork/preview, Focus mode and the single red Clear All -- all measured in a
// real browser against the FIXTURE V2 backend (paid plans are fixture identities).
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { newSession, openExplorer, pickRow, shot, URLS, VIEWPORTS, OUT_DIR, resetFixtureRequests } from "./helpers.mjs";

const chip = (page, fragment) => page.locator(`[data-market-explorer-active-chip*="${fragment}"]`);
const centerX = async (locator) => { const b = await locator.boundingBox(); return b.x + b.width / 2; };
const MEASURE_FILE = path.join(OUT_DIR, "measurements.json");
const record = (key, value) => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const existing = fs.existsSync(MEASURE_FILE) ? JSON.parse(fs.readFileSync(MEASURE_FILE, "utf8")) : {};
  fs.writeFileSync(MEASURE_FILE, JSON.stringify({ ...existing, [key]: value }, null, 2));
};

async function compareAdd(page, label, fragment) {
  await page.locator("li[role=option]", { hasText: label }).first().locator("[data-compare-market]").click();
  await expect(chip(page, fragment)).toHaveCount(1, { timeout: 30000 });
}

for (const [vpName, viewport] of [["1440x900", VIEWPORTS.desktop], ["1366x768", { width: 1366, height: 768 }], ["1920x1080", { width: 1920, height: 1080 }]]) {
  test(`V2 fixture ${vpName}: View and Hide Constituents & Comparison are centred on the chart/details pane and reopen`, async ({ browser }) => {
    const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport });
    await openExplorer(page, URLS.v2);
    await pickRow(page, "sets", "Fossil");
    await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
    const workspace = page.locator("[data-market-explorer-chart-workspace]");
    const view = page.locator("[data-market-explorer-view-details]");
    await view.scrollIntoViewIfNeeded();
    const paneCenter = await centerX(workspace);
    const viewOffset = Math.abs((await centerX(view)) - paneCenter);
    await shot(page, `v2-${vpName}-view-button`);
    const glow = await view.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(glow).toContain("139, 92, 246");

    await view.click();
    const hide = page.locator("[data-market-explorer-hide-details]");
    await expect(hide).toBeVisible();
    const details = page.locator("[data-market-explorer-compare-results]");
    const hideOffset = Math.abs((await centerX(hide)) - (await centerX(details)));
    const hideVsWorkspace = Math.abs((await centerX(hide)) - paneCenter);
    const hideGlow = await hide.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(hideGlow).toContain("139, 92, 246");
    await shot(page, `v2-${vpName}-hide-button`);
    record(`center-offset-px-${vpName}`, { viewVsChartPane: +viewOffset.toFixed(2), hideVsDetailsPane: +hideOffset.toFixed(2), hideVsChartPane: +hideVsWorkspace.toFixed(2) });
    expect(viewOffset).toBeLessThanOrEqual(4);
    expect(hideOffset).toBeLessThanOrEqual(4);
    expect(hideVsWorkspace).toBeLessThanOrEqual(4);

    for (let i = 0; i < 2; i += 1) {
      await hide.click();
      await expect(view).toBeVisible();
      await expect(details).toHaveCount(0);
      await view.click();
      await expect(details).toBeVisible();
    }
    await context.close();
  });
}

test("V2 fixture mobile 390: View and Hide are centred", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus", viewport: VIEWPORTS.mobile, mobile: true });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  const workspace = page.locator("[data-market-explorer-chart-workspace]");
  const view = page.locator("[data-market-explorer-view-details]");
  await view.scrollIntoViewIfNeeded();
  const viewOffset = Math.abs((await centerX(view)) - (await centerX(workspace)));
  await view.click();
  const hide = page.locator("[data-market-explorer-hide-details]");
  await expect(hide).toBeVisible();
  const hideOffset = Math.abs((await centerX(hide)) - (await centerX(page.locator("[data-market-explorer-compare-results]"))));
  await shot(page, "v2-mobile-390-hide-button");
  record("center-offset-px-mobile-390", { viewVsChartPane: +viewOffset.toFixed(2), hideVsDetailsPane: +hideOffset.toFixed(2) });
  expect(viewOffset).toBeLessThanOrEqual(4);
  expect(hideOffset).toBeLessThanOrEqual(4);
  await context.close();
});

test("constituent entitlement: anonymous sees a deliberate LOCKED state, Index+/Premium load rows", async ({ browser }) => {
  let s = await newSession(browser, { base: URLS.v2 });
  await openExplorer(s.page, URLS.v2);
  await pickRow(s.page, "sets", "Fossil");
  await expect(chip(s.page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  await s.page.click("[data-market-explorer-view-details]");
  const locked = s.page.locator("[data-market-constituents-state=locked]");
  await expect(locked).toBeVisible({ timeout: 30000 });
  await expect(locked).toContainText("Index+");
  await expect(s.page.locator("[data-market-constituents-page-loading]")).toHaveCount(0);
  await expect(s.page.locator("[data-market-constituent]")).toHaveCount(0);
  await shot(s.page, "v2-anonymous-constituents-locked");
  await s.context.close();

  for (const plan of ["plus", "premium"]) {
    s = await newSession(browser, { base: URLS.v2, plan });
    await openExplorer(s.page, URLS.v2);
    await pickRow(s.page, "sets", "Fossil");
    await expect(chip(s.page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
    await s.page.click("[data-market-explorer-view-details]");
    await expect(s.page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
    await expect(s.page.locator("[data-market-constituents-state=locked]")).toHaveCount(0);
    await shot(s.page, `v2-${plan}-constituents-set`);
    await s.page.click("[data-market-explorer-hide-details]");
    await pickRow(s.page, "eras", "Base");
    await expect(chip(s.page, "era-base")).toHaveCount(1, { timeout: 30000 });
    await s.page.locator("[data-market-explorer-active-inspect*='era-base']").click();
    await s.page.click("[data-market-explorer-view-details]");
    await expect(s.page.locator("[data-market-constituents-active]")).toContainText("Base", { timeout: 30000 });
    await expect(s.page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
    await s.context.close();
  }
});

test("constituent switcher: A/B/C stay active, cached A is not refetched, hidden B is inspectable", async ({ browser }) => {
  await resetFixtureRequests();
  const { context, page, net } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  await compareAdd(page, "Jungle", "set-jungle");
  await compareAdd(page, "Base Set 2", "set-bs2");
  const seriesBefore = await page.locator("polyline[data-market-performance-series]").count();
  await page.locator("[data-market-explorer-active-inspect*='set-fossil']").click();
  await page.click("[data-market-explorer-view-details]");
  const active = page.locator("[data-market-constituents-active]");
  await expect(active).toContainText("Fossil", { timeout: 30000 });
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  const pageOneA = () => net.requests.filter((r) => r.url.includes("marketKey=set%3Aset-fossil") && r.url.includes("afterRank=0")).length;
  const aBefore = pageOneA();

  await page.locator("[data-market-constituents-target='set:set-jungle']").click();
  await expect(active).toContainText("Jungle", { timeout: 30000 });
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await page.locator("[data-market-explorer-active-visibility='set:set-jungle']").click();
  await expect(page.locator("[data-market-constituents-target='set:set-jungle']")).toBeVisible();
  await expect(active).toContainText("Jungle");
  await page.locator("[data-market-constituents-target='set:set-bs2']").click();
  await expect(active).toContainText("Base Set 2", { timeout: 30000 });
  await shot(page, "v2-switcher-C");
  await page.locator("[data-market-constituents-target='set:set-fossil']").click();
  await expect(active).toContainText("Fossil");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible();
  expect(pageOneA(), "cached A page 1 must not refetch").toBe(aBefore);
  for (const frag of ["set-fossil", "set-jungle", "set-bs2"]) await expect(chip(page, frag)).toHaveCount(1);
  expect(await page.locator("polyline[data-market-performance-series]").count()).toBeLessThanOrEqual(seriesBefore);
  record("switcher", { fossilPage1RequestsAfterReturn: pageOneA(), fossilPage1RequestsBeforeSwitching: aBefore });
  await context.close();
});

test("images: artwork, hover preview, keyboard preview, new-tab detail link", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  await page.click("[data-market-explorer-view-details]");
  const thumb = page.locator("[data-market-constituents-table] [data-market-constituent-link]").first();
  await expect(thumb).toBeVisible({ timeout: 30000 });
  await expect(thumb).toHaveAttribute("target", "_blank");
  await thumb.hover();
  await expect(page.locator("[data-market-constituent-preview-image]")).toBeVisible();
  const preview = await page.locator("[data-market-constituent-preview]").boundingBox();
  expect(preview.height).toBeGreaterThan(200);
  await shot(page, "v2-image-hover-preview");
  await page.mouse.move(5, 5);
  await expect(page.locator("[data-market-constituent-preview]")).toHaveCount(0);
  await page.keyboard.press("Tab"); // keyboard focus lands somewhere; drive to the link
  await thumb.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(page.locator("[data-market-constituent-preview]")).toBeVisible();
  await shot(page, "v2-image-keyboard-preview");
  const broken = await page.evaluate(() => [...document.querySelectorAll("[data-market-constituent-thumb]")].filter((img) => img.offsetParent !== null && img.getBoundingClientRect().top < window.innerHeight && img.getBoundingClientRect().bottom > 0).filter((img) => !img.complete || img.naturalWidth === 0).length);
  expect(broken).toBe(0);
  const [popup] = await Promise.all([context.waitForEvent("page"), thumb.click()]);
  expect(popup.url()).toMatch(/\/(TCGs|cards)\//i);
  await popup.close();
  await context.close();
});

test("focus mode: magnifier left of chip, hover/keyboard/touch, dims others, Clear Focus", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  const fossil = chip(page, "set-fossil");
  const magnifier = fossil.locator("[data-market-explorer-active-focus]");
  const label = fossil.locator("[data-market-explorer-active-inspect]");
  const mBox = await magnifier.boundingBox();
  const lBox = await label.boundingBox();
  expect(mBox.x + mBox.width).toBeLessThanOrEqual(lBox.x + 1);
  expect(await magnifier.evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
  await fossil.hover();
  await expect.poll(() => magnifier.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await shot(page, "v2-focus-hover-magnifier");
  await magnifier.click();
  await expect(fossil).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
  const states = await page.evaluate(() => [...document.querySelectorAll("polyline[data-market-performance-series]")].map((el) => ({ key: el.getAttribute("data-market-performance-series"), focus: el.getAttribute("data-market-performance-focus"), stroke: el.getAttribute("stroke"), opacity: el.getAttribute("stroke-opacity") || getComputedStyle(el).strokeOpacity })));
  const focused = states.find((x) => x.focus === "focused");
  const dimmed = states.filter((x) => x.focus === "dimmed");
  expect(focused.key).toBe("set:set-fossil");
  expect(dimmed.length).toBeGreaterThanOrEqual(2);
  for (const d of dimmed) { expect(Number(d.opacity)).toBeLessThan(1); expect(Number(d.opacity)).toBeGreaterThan(0); }
  await expect(page.locator("[data-market-explorer-focus-strip]")).toBeVisible();
  await expect(chip(page, "raw")).toHaveCount(1);
  await shot(page, "v2-focus-active");
  record("focus", { focused, dimmed });
  await page.click("[data-market-explorer-clear-focus]");
  await expect(page.locator("[data-market-performance-focus]")).toHaveCount(0);
  await magnifier.focus();
  await page.mouse.move(2, 2);
  await expect.poll(() => magnifier.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await context.close();

  const touch = await newSession(browser, { base: URLS.v2, plan: "plus", viewport: VIEWPORTS.mobile, mobile: true });
  await openExplorer(touch.page, URLS.v2);
  const rawMagnifier = touch.page.locator("[data-market-explorer-active-focus]").first();
  await rawMagnifier.scrollIntoViewIfNeeded();
  expect(await rawMagnifier.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await rawMagnifier.tap();
  await expect(touch.page.locator("[data-market-explorer-active-chip-focused=true]")).toHaveCount(1);
  await shot(touch.page, "v2-focus-touch-mobile");
  await touch.context.close();
});

test("single red Clear All: clears markets, focus, panel and target; no Clear Graph", async ({ browser }) => {
  const { context, page } = await newSession(browser, { base: URLS.v2, plan: "plus" });
  await openExplorer(page, URLS.v2);
  await pickRow(page, "sets", "Fossil");
  await expect(chip(page, "set-fossil")).toHaveCount(1, { timeout: 30000 });
  await expect(page.locator("[data-market-explorer-active-clear-all]")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Clear Graph/i })).toHaveCount(0);
  const color = await page.locator("[data-market-explorer-active-clear-all]").evaluate((el) => getComputedStyle(el).color);
  expect(color).toMatch(/rgb\(248, 113, 113\)/);
  await chip(page, "set-fossil").locator("[data-market-explorer-active-focus]").click();
  await page.click("[data-market-explorer-view-details]");
  await expect(page.locator("[data-market-constituent]").first()).toBeVisible({ timeout: 30000 });
  await shot(page, "v2-clear-all-before");
  await page.click("[data-market-explorer-active-clear-all]");
  await expect(page.locator("[data-market-explorer-active-chip]")).toHaveCount(0);
  await expect(page.locator("[data-market-explorer-compare-results]")).toHaveCount(0);
  await expect(page.locator("[data-market-explorer-focus-strip]")).toHaveCount(0);
  await expect(page.locator("[data-market-explorer-workspace]")).toHaveAttribute("data-market-explorer-detail-series", "");
  await shot(page, "v2-clear-all-after");
  await context.close();
});
