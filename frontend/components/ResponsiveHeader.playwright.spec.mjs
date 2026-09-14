import { test, expect } from "@playwright/test";

const widths = [320, 390, 430, 600, 768, 900, 1024, 1100, 1199, 1200, 1279, 1280, 1366, 1440, 1536, 1920];
const routes = ["/Market", "/Market/Explorer", "/Rankings", "/TCGs/Pokemon/Sets", "/Articles"];
const baseUrl = "http://127.0.0.1:3000";

test("global navigation has one atomic mode and non-overlapping flow layout", async ({ page }) => {
  await page.goto(`${baseUrl}/Articles`, { waitUntil: "domcontentloaded" });
  const sweep = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    const sample = await page.evaluate((viewportWidth) => {
      const logo = document.querySelector("[data-header-logo]");
      const nav = document.querySelector("[data-desktop-primary-nav]");
      const search = document.querySelector("[data-header-search]");
      const account = document.querySelector("[data-header-account] > div");
      // The authenticated plan + long account control is the widest supported
      // state. Reserve that measured stress width even when local QA is anonymous.
      if (viewportWidth >= 1280 && account) account.style.width = "300px";
      const hamburger = document.querySelector('button[aria-label="Toggle menu"]');
      const bottom = document.querySelector('nav[aria-label="Global navigation"]');
      const isVisible = (element) => element && getComputedStyle(element).display !== "none" && element.getBoundingClientRect().width > 0;
      const rect = (element) => isVisible(element) ? Object.fromEntries(["left", "right", "width"].map((key) => [key, Math.round(element.getBoundingClientRect()[key] * 10) / 10])) : null;
      return {
        width: viewportWidth,
        desktop: isVisible(nav), hamburger: isVisible(hamburger), bottom: isVisible(bottom),
        logo: rect(logo), nav: rect(nav), search: rect(search), account: rect(account),
        scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
        overflowers: [...document.querySelectorAll("body *")].filter((element) => element.getBoundingClientRect().right > window.innerWidth + 0.5).slice(0, 8).map((element) => `${element.tagName}.${element.className}`),
      };
    }, width);
    if (sample.scrollWidth > sample.innerWidth) console.log("RESPONSIVE_OVERFLOW", JSON.stringify(sample));
    expect(sample.scrollWidth).toBeLessThanOrEqual(sample.innerWidth);
    expect(sample.desktop).toBe(width >= 1280);
    expect(sample.hamburger).toBe(width < 1280);
    expect(sample.bottom).toBe(width < 1280);
    if (sample.desktop) {
      expect(sample.logo.right).toBeLessThanOrEqual(sample.nav.left);
      expect(sample.nav.right).toBeLessThanOrEqual(sample.search.left);
      expect(sample.search.right).toBeLessThanOrEqual(sample.account.left);
      expect(sample.search.width).toBeGreaterThanOrEqual(240);
      expect(sample.search.width).toBeLessThanOrEqual(420);
    }
    sweep.push(sample);
  }
  console.log("RESPONSIVE_HEADER_SWEEP", JSON.stringify(sweep));
});

test("the global shell remains correct on every required route", async ({ page }) => {
  for (const route of routes) {
    await page.setViewportSize({ width: 1279, height: 900 });
    await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
    await expect(page.locator('button[aria-label="Toggle menu"]')).toBeVisible();
    await expect(page.locator('nav[aria-label="Global navigation"]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.locator("[data-desktop-primary-nav]")).toBeVisible();
    await expect(page.locator('nav[aria-label="Global navigation"]')).toBeHidden();
  }
});

test("single search retains query, results, and keyboard behavior across the breakpoint", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/search?**", async (route) => {
    requests += 1;
    const query = new URL(route.request().url()).searchParams.get("q");
    const items = query?.includes("evolvng")
      ? [{ category: "Sets", resultType: "set", label: "Evolving Skies", href: "/TCGs/Pokemon/Sets/evolving-skies", imageUrl: "/images/inDex.png" }]
      : [{ category: "Cards", resultType: "card", label: "Dragonite", href: "/cards/dragonite", imageUrl: "/images/inDex.png" }];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items }) });
  });
  await page.setViewportSize({ width: 1279, height: 900 });
  await page.goto(`${baseUrl}/Market`, { waitUntil: "domcontentloaded" });
  const input = page.getByRole("combobox");
  await expect(input).toBeVisible();
  await page.waitForTimeout(500);
  await input.fill("dragonite");
  await expect(page.getByText("Dragonite", { exact: true })).toBeVisible();
  await expect(page.locator('[data-result-thumbnail="card"]')).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(input).toHaveValue("dragonite");
  await page.waitForTimeout(250);
  expect(requests).toBe(1);
  await input.press("ArrowDown");
  await expect(input).toHaveAttribute("aria-activedescendant", /option-0$/);
  await input.press("Escape");
  await expect(input).toHaveAttribute("aria-expanded", "false");
  await input.fill("evolvng skies");
  await expect(page.getByText("Evolving Skies", { exact: true })).toBeVisible();
  await expect(page.locator('[data-result-thumbnail="set"]')).toBeVisible();
  await input.press("ArrowDown");
  await expect(input).toHaveAttribute("aria-activedescendant", /option-0$/);
  await input.press("Enter");
  await expect(page).toHaveURL(/\/TCGs\/Pokemon\/Sets\/evolving-skies$/);
});
