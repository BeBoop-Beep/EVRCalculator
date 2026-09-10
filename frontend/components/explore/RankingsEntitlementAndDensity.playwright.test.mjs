import { expect, test } from "@playwright/test";

// Convention matches components/explore/TimeRangeSelectorMobileParity.playwright.test.mjs:
// a colocated `.playwright.test.mjs` file run via `npx playwright test <path>` (no
// playwright.config.js exists in this repo), pointed at a live dev server via
// PLAYWRIGHT_BASE_URL. Real routes verified against frontend/app/**: the rankings
// leaderboard is /Rankings (lens switching is client-side SegmentedControl state, not
// a URL query string — /explore/rankings?lens=sets does not exist), and the individual
// Set RIP page is /TCGs/Pokemon/Sets/[setSlug] with camelCase canonical keys
// (e.g. "ascendedHeroes" — see lib/pokemon/pokemonBoosterPackAssets.mjs).
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3100";
const RANKINGS_URL = `${BASE_URL}/Rankings`;
// The set-detail route normalizes to a kebab-case URL segment
// ("ascended-heroes") even though the canonical_key used internally
// (lib/pokemon/pokemonBoosterPackAssets.mjs) is camelCase — confirmed by
// following the live redirect from /TCGs/Pokemon/Sets/ascendedHeroes.
const ASCENDED_HEROES_URL = `${BASE_URL}/TCGs/Pokemon/Sets/ascended-heroes`;

// The "Sets"/"Products" lens switch is a SegmentedControl rendered as
// role="radio" buttons (components/ui/SegmentedControl.jsx, variant="primary"),
// not role="button" — the brief's skeleton selector was a guess that does not
// match the real DOM.
async function openSetsLens(page) {
  await page.goto(RANKINGS_URL, { waitUntil: "domcontentloaded" });
  const setsRadio = page.getByRole("radio", { name: "Sets", exact: true });
  await setsRadio.scrollIntoViewIfNeeded();
  await setsRadio.click();
  await expect(setsRadio).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('[data-analytics-table-shell]')).toBeVisible({ timeout: 15000 });
}

async function openProductsLens(page) {
  await page.goto(RANKINGS_URL, { waitUntil: "domcontentloaded" });
  const productsRadio = page.getByRole("radio", { name: "Products", exact: true });
  await productsRadio.scrollIntoViewIfNeeded();
  await productsRadio.click();
  await expect(productsRadio).toHaveAttribute("aria-checked", "true");
}

test.describe("Set Rankings entitlement", () => {
  test("anonymous desktop: Set RIP visible, family/Financial/Chase/Collector locked", async ({ page }) => {
    await openSetsLens(page);
    // "Unavailable" legitimately appears as the public Overall RIP Score for a
    // set with zero scored families (e.g. Pitch Black in the live cohort) --
    // that is a genuine no-data state (ExploreTableClient.jsx UNAVAILABLE_LABEL),
    // not a paywall, and is out of scope here. What Task 3 fixed is that the
    // paid pillar/family cells never show that same bare "Unavailable" text --
    // they must show an Index Plus / Plus RIP lock instead. So this excludes
    // cells that also carry the public "RIP Score" caption and asserts none of
    // the remaining ("Unavailable" with no "RIP Score" context) cells exist.
    const unavailableOutsideRipScore = page
      .locator('[data-analytics-table-shell] td, [data-analytics-table-shell] th')
      .filter({ hasText: "Unavailable" })
      .filter({ hasNotText: "RIP Score" });
    await expect(unavailableOutsideRipScore).toHaveCount(0);
    // A wide-layout and a compact-layout lock button both exist in the DOM at
    // once (CSS toggles which is shown per breakpoint), so .first() alone can
    // resolve to the one that's currently display:none. Intersect with
    // :visible to get the one actually rendered at this viewport.
    await expect(page.getByLabel(/Index Plus/i).and(page.locator(":visible")).first()).toBeVisible();
  });

  test("anonymous mobile: same lock semantics", async ({ page }) => {
    await page.setViewportSize({ width: 412, height: 915 });
    await openSetsLens(page);
    // Below md, ExploreTableClient.jsx renders collapsed article/button rows
    // (styles.mobileRow) showing only rank, identity, and the public Overall
    // RIP score -- the locked Financial/Chase/Collector/family cells live
    // inside the expand-on-tap panel (setExpandedMobileSet), not the
    // collapsed row. Expand the first row to reach them, matching how a real
    // mobile visitor would.
    // Scoped to `article button` specifically: a same-shell "Choose which
    // metric..." sort dropdown also carries aria-expanded and would otherwise
    // be matched (and toggled open) instead of a ranking row.
    await page.locator('[data-analytics-table-shell] article button[aria-expanded="false"]').first().click();
    await expect(page.getByLabel(/Index Plus/i).and(page.locator(":visible")).first()).toBeVisible();
  });

  // No authenticated-session Playwright fixture exists in this repo (no
  // storageState/cookie/test-bypass convention was found anywhere under
  // frontend/**). Real auth goes through Supabase cookies set by the login
  // flow, which this test-only spec should not fabricate. The reconciliation
  // fix itself (Task 6, useSetRipBootstrapController) is covered by
  // hooks/pokemon/useSetRipBootstrapController.chaseReconciliation.test.mjs;
  // this case is intentionally skipped pending real login-session E2E
  // infrastructure rather than faking entitlement.
  test.skip("logged-in Set RIP page shows Chase public score for Ascended Heroes", async ({ page }) => {
    await page.goto(ASCENDED_HEROES_URL);
    await expect(page.getByText(/Unavailable/).filter({ hasText: "Chase" })).toHaveCount(0);
  });

  test("anonymous Set RIP page for Ascended Heroes still loads (unauth baseline)", async ({ page }) => {
    await page.goto(ASCENDED_HEROES_URL, { waitUntil: "domcontentloaded" });
    // "Ascended Heroes" is rendered in more than one hero variant
    // (PokemonSetMobileHero vs. the desktop rich-context chrome), only one of
    // which is visible per viewport width, so match whichever is actually
    // shown rather than assuming a specific element.
    await expect(page.locator(':visible', { hasText: "Ascended Heroes" }).first()).toBeVisible({ timeout: 20000 });
  });
});

test.describe("All Products layout", () => {
  for (const width of [1440, 1366, 768, 412]) {
    test(`All Products renders without page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openProductsLens(page);
      await page.waitForTimeout(500);
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = await page.evaluate(() => window.innerWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
    });
  }

  test("1440 desktop shows Format Strength without needing horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openProductsLens(page);
    await expect(page.getByText("Format Strength")).toBeInViewport();
  });
});
