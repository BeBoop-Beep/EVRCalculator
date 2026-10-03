import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { ensureTools, newSession, openExplorer, URLS } from "./helpers.mjs";

const output = path.resolve(
  process.cwd(),
  "../backend/artifacts/market_explorer_acceptance/corrective_interactions_20261002",
);

async function capture(page, name) {
  fs.mkdirSync(output, { recursive: true });
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
}

function record(name, receipt) {
  fs.mkdirSync(output, { recursive: true });
  const target = path.join(output, "measurements.json");
  const current = fs.existsSync(target) ? JSON.parse(fs.readFileSync(target, "utf8")) : {};
  fs.writeFileSync(target, JSON.stringify({ ...current, [name]: receipt }, null, 2));
}

async function addSealedParent(page, { proveDirectoryToggle = false } = {}) {
  await ensureTools(page);
  await page.locator('[data-market-directory-asset="sealed"]').click();
  await page.locator('[data-market-directory-category="sets"]').click();
  const row = page.locator('[data-prepared-market="sealedMarket"]');
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.locator('[data-market-explorer-active-chip="sealedMarket"]')).toBeVisible({ timeout: 30000 });
  await expect(row).toHaveAttribute("aria-pressed", "true");
  if (proveDirectoryToggle) {
    await row.click();
    await expect(page.locator('[data-market-explorer-active-chip="sealedMarket"]')).toHaveCount(0);
    await expect(row).toHaveAttribute("aria-pressed", "false");
    await row.click();
    await expect(page.locator('[data-market-explorer-active-chip="sealedMarket"]')).toBeVisible({ timeout: 30000 });
    await expect(row).toHaveAttribute("aria-pressed", "true");
  }
  const mobileToggle = page.locator("[data-market-explorer-mobile-tools]");
  if (await mobileToggle.isVisible().catch(() => false)) await mobileToggle.click();
}

async function openDetails(page, mobile) {
  const trigger = mobile
    ? page.locator("[data-market-explorer-mobile-constituents]")
    : page.locator("[data-market-explorer-view-details]");
  await trigger.click();
  await expect(page.locator("[data-market-explorer-details]" )).toBeVisible();
}

for (const fixture of [
  { name: "desktop", viewport: { width: 1440, height: 900 }, mobile: false },
  { name: "mobile", viewport: { width: 390, height: 844 }, mobile: true },
]) {
  test(`${fixture.name}: parent interactions, Inspect controls, LT fit, and 1Y plot`, async ({ browser }) => {
    const { context, page, net } = await newSession(browser, {
      base: URLS.v2,
      plan: "premium",
      viewport: fixture.viewport,
      mobile: fixture.mobile,
    });
    await openExplorer(page, URLS.v2);
    const performance = page.locator('button[data-market-chart-view="performance"]');
    await expect(performance).toBeVisible();
    await addSealedParent(page, { proveDirectoryToggle: true });

    const raw = page.locator('[data-market-explorer-active-chip="raw"]');
    const sealed = page.locator('[data-market-explorer-active-chip="sealedMarket"]');
    await performance.click();
    await expect(performance).toHaveAttribute("aria-pressed", "true");
    await sealed.locator('[data-market-explorer-active-chip-body="sealedMarket"]').click();
    await expect(performance).toHaveAttribute("aria-pressed", "true");
    await sealed.locator('[data-market-explorer-active-chip-body="sealedMarket"]').click();
    await raw.locator('[data-market-explorer-active-chip-body="raw"]').click();
    await expect(raw).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
    await expect(raw).toHaveAttribute("data-market-explorer-active-chip-selected", "true");
    await capture(page, `${fixture.name}-raw-chip-focused-inspecting`);
    await raw.locator('[data-market-explorer-active-chip-body="raw"]').click();
    await expect(raw).toHaveAttribute("data-market-explorer-active-chip-focused", "false");

    await sealed.locator('[data-market-explorer-active-chip-body="sealedMarket"]').click();
    await expect(sealed).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
    await expect(sealed).toHaveAttribute("data-market-explorer-active-chip-selected", "true");
    await capture(page, `${fixture.name}-sealed-chip-focused-inspecting`);
    await sealed.locator('[data-market-explorer-active-chip-body="sealedMarket"]').click();
    await expect(sealed).toHaveAttribute("data-market-explorer-active-chip-focused", "false");

    await raw.locator('[data-market-explorer-active-chip-body="raw"]').click();
    await sealed.locator('[data-market-explorer-active-remove="sealedMarket"]').click();
    await expect(sealed).toHaveCount(0);
    await expect(raw).toHaveAttribute("data-market-explorer-active-chip-focused", "true");
    await expect(raw).toHaveAttribute("data-market-explorer-active-chip-selected", "true");
    await capture(page, `${fixture.name}-remove-isolation`);

    await addSealedParent(page);
    await openDetails(page, fixture.mobile);
    const inspectAttribute = fixture.mobile
      ? "data-market-explorer-inspect-mobile"
      : "data-market-explorer-inspect";
    const rawInspect = page.locator(`[${inspectAttribute}="raw"]`);
    const sealedInspect = page.locator(`[${inspectAttribute}="sealedMarket"]`);
    await expect(rawInspect).toBeVisible();
    await expect(sealedInspect).toBeVisible();
    await sealedInspect.click();
    await expect(sealedInspect).toHaveText("Inspecting");
    await expect(page.locator("[data-market-constituents-active]")).toContainText("Total Sealed");
    await capture(page, `${fixture.name}-parent-detail-inspect`);

    const selector = page.locator("[data-market-constituents-window-selector]");
    const lt = selector.locator('[data-market-constituents-window="SinceTracking"]');
    await expect(lt).toBeVisible();
    const trailingGap = await selector.evaluate((element) => {
      const last = element.querySelector('[data-market-constituents-window="SinceTracking"]');
      element.scrollLeft = element.scrollWidth;
      return Math.round(element.getBoundingClientRect().right - last.getBoundingClientRect().right);
    });
    expect(trailingGap).toBeGreaterThanOrEqual(0);
    expect(trailingGap).toBeLessThanOrEqual(4);
    await capture(page, `${fixture.name}-constituent-lt-fit`);

    await page.locator("[data-market-explorer-hide-details]").click();
    const clearFocus = page.locator("[data-market-explorer-clear-focus]");
    if (await clearFocus.isVisible().catch(() => false)) await clearFocus.click();
    const oneYear = page.locator('[data-market-window-value="1Y"]');
    await oneYear.click();
    await expect(oneYear).toHaveAttribute("aria-checked", "true");
    const widthReceipt = await page.locator('polyline[data-market-performance-series="raw"]').evaluate((line) => {
      const points = line.getAttribute("points").trim().split(/\s+/).map((point) => Number(point.split(",")[0]));
      return { firstX: points[0], lastX: points.at(-1), viewWidth: line.ownerSVGElement.viewBox.baseVal.width };
    });
    expect(widthReceipt.firstX).toBeLessThanOrEqual(2.1);
    expect(widthReceipt.lastX).toBeGreaterThanOrEqual(widthReceipt.viewWidth - 2.1);
    record(fixture.name, { trailingGapPx: trailingGap, oneYear: widthReceipt });
    await capture(page, `${fixture.name}-one-year-full-plot`);
    await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
    expect(net.consoleErrors.filter((message) => !message.includes("status of 404"))).toEqual([]);

    await context.close();
  });
}
