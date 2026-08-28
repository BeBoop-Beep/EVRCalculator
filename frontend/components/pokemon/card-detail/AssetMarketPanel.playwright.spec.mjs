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
    const control = page.getByRole("radio", {
      name: windowLabel === "ALL" ? "All available history" : windowLabel,
      exact: true,
    });
    await control.click();
    await expect(control).toHaveAttribute("aria-checked", "true");
    measurements.push(
      await page.evaluate((label) => {
        const rect = (selector) =>
          document.querySelector(selector)?.getBoundingClientRect();
        const panel = rect("[data-asset-market-panel]");
        const artwork = rect(".card-detail-artwork img");
        const identity = rect("[data-card-identity]");
        const back = rect("[data-card-back-navigation] a");
        return {
          window: label,
          panel: panel?.height,
          artwork: artwork?.height,
          artworkBottom: artwork?.bottom,
          panelBottom: panel?.bottom,
          identityLeft: identity?.left,
          artworkLeft: artwork?.left,
          backLeft: back?.left,
        };
      }, windowLabel),
    );
  }

  console.log(`CARD_DETAIL_HEIGHTS=${JSON.stringify(measurements)}`);
  const spread = (key) =>
    Math.max(...measurements.map((row) => row[key])) -
    Math.min(...measurements.map((row) => row[key]));
  expect(spread("panel")).toBeLessThanOrEqual(2);
  expect(spread("artwork")).toBeLessThanOrEqual(2);
  for (const row of measurements)
    expect(Math.abs(row.artworkBottom - row.panelBottom)).toBeLessThanOrEqual(
      4,
    );
  for (const row of measurements) {
    expect(Math.abs(row.identityLeft - row.artworkLeft)).toBeLessThanOrEqual(4);
    expect(row.backLeft).toBeLessThan(row.identityLeft - 60);
  }
});

test("public lock CTAs remain fully inside content-sized panels", async ({
  page,
}) => {
  test.skip(!cardUrl, "Set CARD_DETAIL_QA_URL to a live card-detail page.");
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(cardUrl, { waitUntil: "domcontentloaded" });
  for (const selector of ["[data-chase-efficiency-lock]", "[data-plus-lock]"]) {
    const panel = page.locator(selector).first();
    const cta = panel.getByRole("link");
    await expect(panel).toBeVisible();
    const [panelBox, ctaBox] = await Promise.all([
      panel.boundingBox(),
      cta.boundingBox(),
    ]);
    expect(ctaBox.y + ctaBox.height).toBeLessThanOrEqual(
      panelBox.y + panelBox.height - 16,
    );
  }
});

test("card market remains overflow-free at target viewports", async ({
  page,
}) => {
  test.skip(!cardUrl, "Set CARD_DETAIL_QA_URL to a live card-detail page.");
  for (const width of [390, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(cardUrl, { waitUntil: "domcontentloaded" });
    await page.locator("[data-asset-market-panel]").waitFor();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(
      1,
    );
  }
});
