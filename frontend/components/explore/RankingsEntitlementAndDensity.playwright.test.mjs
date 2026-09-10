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

// The "family-specific product ranking view" is not a separate route: inside
// the same Products lens, `nav[aria-label="Product family"]`
// (RankingsProductLensClient.jsx) has an "◇ All Products" tab plus one tab per
// product family. Clicking any non-"All Products" tab re-renders the SAME
// table (same styles.colProduct/.colFormat <col> widths) filtered to that
// family -- this is the density reference Task 9 measured.
async function waitForRenderedProductRows(page) {
  // The desktop table and the <768px card list both render
  // `a[href^="/sealed-products/"]` links at all times; only one of the two is
  // actually shown per viewport (the other is display:none via CSS), so this
  // must intersect with :visible rather than trust DOM order via .first().
  await page
    .locator('a[href^="/sealed-products/"]')
    .and(page.locator(":visible"))
    .first()
    .waitFor({ state: "visible", timeout: 15000 });
}

async function openFirstFamilyProductView(page) {
  await openProductsLens(page);
  const familyNav = page.getByRole("navigation", { name: "Product family" });
  await expect(familyNav).toBeVisible({ timeout: 15000 });
  const familyTabs = familyNav.getByRole("button").filter({ hasNotText: "All Products" });
  await expect(familyTabs.first()).toBeVisible({ timeout: 15000 });
  await familyTabs.first().click();
  await expect(familyTabs.first()).toHaveAttribute("aria-pressed", "true");
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

  // Same missing-infrastructure reason as the Chase case above: rendering a
  // real "entitled=true" pass through ExploreTableClient/RankingsProductLensClient
  // needs an actual authenticated session, which this repo has no Playwright
  // fixture for. Covered at the unit level instead by the "entitled=true
  // renders real value, not lock" cases in
  // components/explore/ExploreTableClient.contract.test.js and
  // components/explore/SetRipFamilyBreakdown.test.mjs.
  test.skip("Index+ authenticated view shows real unlocked scores, not locks", async ({ page }) => {
    await openSetsLens(page);
    await expect(page.getByLabel(/Index Plus/i)).toHaveCount(0);
  });

  // Same missing-infrastructure reason: verifying a logout actually clears
  // paid values requires logging in first. Covered at the unit level by
  // components/explore/RankingsLazyClient.authDowngrade.contract.test.mjs,
  // which asserts the requestKey/cacheIdentity invalidation wiring drops paid
  // fields on a downgrade -- this spec should not fabricate a fake auth
  // transition just to re-assert the same regex check in a browser.
  test.skip("auth downgrade (logout) clears paid values", async ({ page }) => {
    await openSetsLens(page);
    await expect(page.getByLabel(/Index Plus/i).first()).toBeVisible();
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
      // Wait on an explicit render signal -- a real product row link --
      // rather than a fixed sleep. A column-header text check is unreliable
      // here: the desktop table's price header reads "Unit Price" for the
      // overall view but "Market Price" for a family view, and neither
      // header exists at all in the <768px card layout.
      await waitForRenderedProductRows(page);
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

test.describe("Family-specific product ranking density", () => {
  for (const width of [1440, 768, 412]) {
    test(`family product view renders without page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openFirstFamilyProductView(page);
      await waitForRenderedProductRows(page);
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = await page.evaluate(() => window.innerWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
    });
  }

  test("family product view keeps product art size consistent and identity column not oversized at 1440px", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openFirstFamilyProductView(page);
    await waitForRenderedProductRows(page);

    // Task 8/9 fixed .colProduct from an oversized 22rem down to 13rem (see
    // RankingsProductLensClient.contract.test.jsx). Assert that measured width
    // directly in the live layout rather than re-reading the CSS text, so a
    // regression that only shows up after cascade/specificity resolution
    // (e.g. another rule overriding .colProduct) would still be caught.
    // The `md:hidden` mobile card list also renders `[data-ranked-product-artwork]`
    // markup even while display:none at this desktop width, so every
    // measurement below is filtered to elements with a non-zero rendered box.
    const identityColumnWidth = await page.evaluate(() => {
      const cells = Array.from(document.querySelectorAll("td"))
        .filter((td) => td.querySelector('[data-ranked-product-artwork]'))
        .map((td) => td.getBoundingClientRect())
        .filter((rect) => rect.width > 0 && rect.height > 0);
      return cells.length ? cells[0].width : null;
    });
    expect(identityColumnWidth).not.toBeNull();
    // 13rem @ 16px/rem = 208px; allow slack for cell padding around the <col> width.
    expect(identityColumnWidth).toBeLessThan(260);

    const artworkSizes = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-ranked-product-artwork] img'))
        .map((img) => {
          const rect = img.getBoundingClientRect();
          return { width: Math.round(rect.width), height: Math.round(rect.height) };
        })
        .filter((size) => size.width > 0 && size.height > 0),
    );
    expect(artworkSizes.length).toBeGreaterThan(0);
    const firstSize = artworkSizes[0];
    for (const size of artworkSizes) {
      // Same artwork treatment for every row in the family view -- no product
      // rendering at a wildly different scale than its neighbors.
      expect(Math.abs(size.width - firstSize.width)).toBeLessThanOrEqual(2);
      expect(Math.abs(size.height - firstSize.height)).toBeLessThanOrEqual(2);
    }
  });
});
