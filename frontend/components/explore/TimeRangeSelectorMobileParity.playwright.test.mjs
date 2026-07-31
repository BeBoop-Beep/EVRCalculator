import { expect, test } from "@playwright/test";

const SET_SLUG = process.env.EVR_SET_SLUG || "ascended-heroes";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3001";
const TARGET_URL = `${BASE_URL}/TCGs/Pokemon/Sets/${SET_SLUG}?tab=overview`;

const EXPECTED_LABELS = ["1D", "7D", "30D", "3M", "6M", "1Y", "LT"];
const MOBILE_WIDTHS = [320, 360, 375, 390, 430];
const SUBPIXEL_TOLERANCE = 0.75;

test.describe("Mobile time-range selector parity", () => {
  for (const width of MOBILE_WIDTHS) {
    test(`selectors match at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1200 });
      await page.goto(TARGET_URL, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.body.textContent?.includes("Set Value Trend") && document.body.textContent?.includes("Opening Profit vs Cost") && document.body.textContent?.includes("Top Chase Cards"));

      const setValueGroup = page
        .locator("article")
        .filter({ has: page.getByText("Set Value Trend", { exact: true }) })
        .first()
        .locator('[role="radiogroup"][aria-label="Time range"]')
        .first();
      const topChaseGroup = page
        .locator("article")
        .filter({ has: page.getByText("Top Chase Cards", { exact: true }) })
        .first()
        .locator('[role="radiogroup"][aria-label="Time range"]')
        .first();
      const opvcGroup = page.locator('[role="radiogroup"][aria-label="Opening profit versus cost time range"]').first();

      await expect(setValueGroup).toBeVisible({ timeout: 15000 });
      await expect(topChaseGroup).toBeVisible({ timeout: 15000 });
      await expect(opvcGroup).toBeVisible();

      for (const group of [setValueGroup, opvcGroup, topChaseGroup]) {
        const labels = await group.locator('xpath=.//span[contains(@class,"max-desk:hidden")]').allInnerTexts();
        expect(labels).toEqual(EXPECTED_LABELS);
        expect(labels.at(-1)).toBe("LT");
      }

      const selectedBefore = {
        setValue: await setValueGroup.locator('[role="radio"][aria-checked="true"]').getAttribute("data-time-range-value"),
        opvc: await opvcGroup.locator('[role="radio"][aria-checked="true"]').getAttribute("data-time-range-value"),
        topChase: await topChaseGroup.locator('[role="radio"][aria-checked="true"]').getAttribute("data-time-range-value"),
      };

      await setValueGroup.locator('[role="radio"][data-time-range-value="7D"]').click();
      await expect(setValueGroup.locator('[role="radio"][aria-checked="true"]')).toHaveAttribute("data-time-range-value", "7D");
      await expect(opvcGroup.locator('[role="radio"][aria-checked="true"]')).toHaveAttribute("data-time-range-value", selectedBefore.opvc || "30D");
      await expect(topChaseGroup.locator('[role="radio"][aria-checked="true"]')).toHaveAttribute("data-time-range-value", selectedBefore.topChase || "30D");

      const measureGroup = async (group) => group.evaluate((element) => {
        const toNumber = (value) => {
          const parsed = Number(value);
          return Number.isFinite(parsed) ? parsed : null;
        };

        const radios = Array.from(element.querySelectorAll('[role="radio"]'));
        const buttonByLabel = (label) => radios.find((button) => button.querySelector("span.max-desk\\:hidden")?.textContent?.trim() === label) || null;
        const buttonMetrics = (button) => {
          if (!button) {
            return null;
          }
          const rect = button.getBoundingClientRect();
          const style = window.getComputedStyle(button);
          return {
            width: rect.width,
            height: rect.height,
            paddingTop: toNumber(style.paddingTop.replace("px", "")),
            paddingBottom: toNumber(style.paddingBottom.replace("px", "")),
            paddingLeft: toNumber(style.paddingLeft.replace("px", "")),
            paddingRight: toNumber(style.paddingRight.replace("px", "")),
            fontSize: toNumber(style.fontSize.replace("px", "")),
            borderRadius: toNumber(style.borderRadius.replace("px", "")),
          };
        };

        const groupRect = element.getBoundingClientRect();
        const firstRect = radios[0]?.getBoundingClientRect() || null;
        const secondRect = radios[1]?.getBoundingClientRect() || null;

        return {
          groupWidth: groupRect.width,
          groupLeft: groupRect.left,
          groupRight: groupRect.right,
          overflowX: element.scrollWidth - element.clientWidth,
          interButtonGap: firstRect && secondRect ? secondRect.left - firstRect.right : null,
          oneD: buttonMetrics(buttonByLabel("1D")),
          thirtyD: buttonMetrics(buttonByLabel("30D")),
          lt: buttonMetrics(buttonByLabel("LT")),
          labels: radios.map((button) => button.querySelector("span.max-desk\\:hidden")?.textContent?.trim() || ""),
        };
      });

      const viewportWidth = await page.evaluate(() => window.innerWidth);
      const metrics = {
        viewportWidth,
        setValue: await measureGroup(setValueGroup),
        opvc: await measureGroup(opvcGroup),
        topChase: await measureGroup(topChaseGroup),
      };

      const variants = [metrics.setValue, metrics.opvc, metrics.topChase];
      for (const variant of variants) {
        expect(variant).toBeTruthy();
        expect(variant.overflowX).toBeLessThanOrEqual(1);
        expect(variant.labels).toEqual(EXPECTED_LABELS);
        expect(variant.labels.at(-1)).toBe("LT");
      }

      const compareButton = (left, right, field) => {
        expect(Math.abs((left?.[field] ?? 0) - (right?.[field] ?? 0))).toBeLessThanOrEqual(SUBPIXEL_TOLERANCE);
      };

      const compareGroup = (left, right) => {
        for (const field of ["groupWidth", "interButtonGap"]) {
          expect(Math.abs((left?.[field] ?? 0) - (right?.[field] ?? 0))).toBeLessThanOrEqual(1.0);
        }
      };

      compareGroup(metrics.setValue, metrics.topChase);
      compareGroup(metrics.opvc, metrics.topChase);

      for (const field of ["width", "height", "paddingTop", "paddingBottom", "fontSize", "borderRadius"]) {
        compareButton(metrics.setValue.oneD, metrics.topChase.oneD, field);
        compareButton(metrics.opvc.oneD, metrics.topChase.oneD, field);
        compareButton(metrics.setValue.thirtyD, metrics.topChase.thirtyD, field);
        compareButton(metrics.opvc.thirtyD, metrics.topChase.thirtyD, field);
        compareButton(metrics.setValue.lt, metrics.topChase.lt, field);
        compareButton(metrics.opvc.lt, metrics.topChase.lt, field);
      }

      if (width === 390) {
        compareButton(metrics.setValue.thirtyD, metrics.topChase.thirtyD, "width");
        compareButton(metrics.setValue.thirtyD, metrics.topChase.thirtyD, "height");
        compareButton(metrics.opvc.thirtyD, metrics.topChase.thirtyD, "width");
        compareButton(metrics.opvc.thirtyD, metrics.topChase.thirtyD, "height");
      }
    });
  }
});
