// Single-market replacement is NOT comparison. Anonymous/basic users must be able
// to switch Set -> Set and Era -> Era with no login/Index+ prompt and no compare call.
import { test, expect } from "@playwright/test";
import { clearDefaults, newSession, openExplorer, pickRow, chooseCategory, shot, URLS, VIEWPORTS } from "./helpers.mjs";

const chips = (page) => page.locator("[data-market-explorer-active-chip]");
const preparedPosts = (net) => net.requests.filter((r) => r.method === "POST" && r.url === "/api/market/explorer/prepared").map((r) => JSON.parse(r.body));

const TARGETS = [
  { name: "fixture-v1", base: URLS.v1 },
  { name: "fixture-v2", base: URLS.v2 },
];
if (process.env.EXPLORER_LIVE === "1") TARGETS.push({ name: "live-anon", base: URLS.liveAnon });

for (const target of TARGETS) {
  for (const [vpName, viewport, mobile] of [["desktop", VIEWPORTS.desktop, false], ["mobile", VIEWPORTS.mobile, true]]) {
    test(`${target.name} ${vpName}: anonymous Set and Era replacement never compares`, async ({ browser }) => {
      const { context, page, net } = await newSession(browser, { base: target.base, viewport, mobile });
      await openExplorer(page, target.base);

      // No per-row Compare-with-Index+ button on ordinary rows for a user who cannot compare;
      // exactly one restrained note explains comparison instead.
      await chooseCategory(page, "sets");
      await expect(page.locator("[data-compare-market]")).toHaveCount(0);
      await expect(page.locator("[data-compare-upsell]")).toHaveCount(1);

      await pickRow(page, "sets", "Fossil");
      await expect(chips(page).first()).toContainText("Fossil", { timeout: 30000 });
      await expect(chips(page)).toHaveCount(1);

      await pickRow(page, "sets", "Jungle");
      await expect(chips(page).first()).toContainText("Jungle", { timeout: 30000 });
      await expect(chips(page)).toHaveCount(1);

      await pickRow(page, "sets", "Base Set 2");
      await expect(chips(page).first()).toContainText("Base Set 2", { timeout: 30000 });
      await expect(chips(page)).toHaveCount(1);
      await shot(page, `${target.name}-${vpName}-basic-set-replacement`);

      await pickRow(page, "eras", "Neo");
      await expect(chips(page).first()).toContainText("Neo", { timeout: 30000 });
      await expect(chips(page)).toHaveCount(1);
      await pickRow(page, "eras", "Base");
      await expect(chips(page).first()).toContainText("Base", { timeout: 30000 });
      await expect(chips(page)).toHaveCount(1);
      await shot(page, `${target.name}-${vpName}-basic-era-replacement`);

      const posts = preparedPosts(net);
      expect(posts.length).toBeGreaterThanOrEqual(5);
      for (const post of posts) {
        expect(post.marketKeys).toHaveLength(1);
        expect(post.contextMarketKeys, "replacement must not send the outgoing market as context").toEqual([]);
      }
      expect(net.failed.filter((f) => f.url.startsWith("/api/market/explorer/prepared"))).toEqual([]);
      const text = await page.locator("[data-market-explorer-workspace]").innerText();
      expect(text).not.toMatch(/Sign in to compare/i);
      expect(text).not.toMatch(/Comparing markets is included/i);
      await context.close();
    });
  }
}

test("fixture-v1: a failed replacement keeps the old market and does not compare", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v1 });
  await openExplorer(page, URLS.v1);
  await pickRow(page, "sets", "Fossil");
  await expect(chips(page)).toHaveCount(1, { timeout: 30000 });
  await page.route("**/api/market/explorer/prepared", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    if ((body.marketKeys || [])[0] === "set:set-jungle") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "PREPARED_PROXY_UNAVAILABLE" }) });
    return route.continue();
  });
  await pickRow(page, "sets", "Jungle");
  await expect(page.locator("[data-market-explorer-prepared-error]")).toBeVisible({ timeout: 30000 });
  await expect(chips(page)).toHaveCount(1);
  await expect(chips(page).first()).toContainText("Fossil");
  for (const post of preparedPosts(net)) expect(post.contextMarketKeys).toEqual([]);
  await context.close();
});

test("fixture-v1: Index+ users still compare and the backend still enforces it", async ({ browser }) => {
  const { context, page, net } = await newSession(browser, { base: URLS.v1, plan: "plus" });
  await openExplorer(page, URLS.v1);
  await clearDefaults(page);
  await pickRow(page, "sets", "Fossil");
  await expect(page.locator('[data-market-explorer-active-chip*="fossil"]')).toHaveCount(1, { timeout: 30000 });
  await page.locator('[data-prepared-market="set:set-jungle"]').click();
  await expect(page.locator('[data-market-explorer-active-chip*="jungle"]')).toHaveCount(1, { timeout: 30000 });
  const jungle = preparedPosts(net).find((p) => p.marketKeys[0] === "set:set-jungle");
  expect(jungle.contextMarketKeys.length).toBeGreaterThan(0); // real comparison keeps its context
  expect(net.failed.filter((f) => f.url.startsWith("/api/market/explorer/prepared"))).toEqual([]);
  await context.close();
  // Enforcement: an unauthenticated real comparison is still rejected by the backend.
  const denied = await fetch(`${URLS.v1}/api/market/explorer/prepared`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ marketKeys: ["set:set-jungle"], contextMarketKeys: ["set:set-fossil"] }) });
  expect(denied.status).toBe(401);
});
