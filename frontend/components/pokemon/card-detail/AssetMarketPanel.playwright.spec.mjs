import { expect, test } from "@playwright/test";

const cardUrl = process.env.CARD_DETAIL_QA_URL;

test("card market windows preserve hero geometry", async ({ page }) => {
  test.skip(!cardUrl, "Set CARD_DETAIL_QA_URL to a live card-detail page.");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(cardUrl, { waitUntil: "domcontentloaded" });
  await page.locator("[data-asset-market-panel]").waitFor();
  await page.locator(".card-detail-artwork img").waitFor({ state: "visible" });
  await page.waitForTimeout(500);

  const measurements = [];
  for (const windowLabel of ["1D", "7D", "30D", "3M", "6M", "1Y", "ALL"]) {
    const control = page.getByRole("radio", { name: windowLabel === "ALL" ? "All available history" : windowLabel, exact: true });
    await control.click();
    await expect(control).toHaveAttribute("aria-checked", "true");
    measurements.push(await page.evaluate((label) => {
      const rect = (selector) => document.querySelector(selector)?.getBoundingClientRect();
      const panel = rect("[data-asset-market-panel]");
      const artwork = rect(".card-detail-artwork img");
      const details = rect("[data-card-details-panel]");
      return { window: label, panel: panel?.height, artwork: artwork?.height, detailsBottom: details?.bottom, panelBottom: panel?.bottom };
    }, windowLabel));
  }

  console.log(`CARD_DETAIL_HEIGHTS=${JSON.stringify(measurements)}`);
  const spread = (key) => Math.max(...measurements.map((row) => row[key])) - Math.min(...measurements.map((row) => row[key]));
  expect(spread("panel")).toBeLessThanOrEqual(2);
  expect(spread("artwork")).toBeLessThanOrEqual(2);
  for (const row of measurements) expect(Math.abs(row.detailsBottom - row.panelBottom)).toBeLessThanOrEqual(2);
});

test("card market remains overflow-free at target viewports", async ({ page }) => {
  test.skip(!cardUrl, "Set CARD_DETAIL_QA_URL to a live card-detail page.");
  for (const width of [390, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(cardUrl, { waitUntil: "domcontentloaded" });
    await page.locator("[data-asset-market-panel]").waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(1);
  }
});
