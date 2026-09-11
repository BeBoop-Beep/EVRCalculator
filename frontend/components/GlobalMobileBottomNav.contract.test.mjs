import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

import { TCGS_NAV_HREF } from "../lib/navigation/tcgsNav.mjs";
import { MARKET_EXPLORER_NAV_HREF, isExplorerNavRouteActive, isMarketNavRouteActive } from "../lib/navigation/marketNav.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "GlobalMobileBottomNav.js"), "utf8")
  .replace(/\r\n/g, "\n");
const headerSource = fs.readFileSync(path.resolve(here, "Header.js"), "utf8").replace(/\r\n/g, "\n");

// The destinations live in one `items` useMemo; slice it so assertions about
// "the destinations" cannot be satisfied by markup elsewhere in the file.
const itemsBlock = source.slice(
  source.indexOf("const items = useMemo("),
  source.indexOf("if (shouldHide)")
);

test("the five destinations are Rankings, Market, Explorer, TCGs, Account in order", () => {
  assert.ok(itemsBlock.length > 0, "the items block must be locatable");

  const ids = [...itemsBlock.matchAll(/id: "([a-z]+)"/g)].map((match) => match[1]);
  assert.deepEqual(ids, ["rankings", "market", "explore", "tcgs", "profile"]);

  const labels = [...itemsBlock.matchAll(/label: "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(labels, ["Rankings", "Market", "Explorer", "TCGs", "Account"]);
  assert.equal(ids.length, 5, "a sixth fixed-nav slot must never be introduced");
});

test("Explorer owns the compass slot and Market/Explorer active states are exclusive", () => {
  assert.equal(MARKET_EXPLORER_NAV_HREF, "/Market/Explorer");
  assert.ok(itemsBlock.includes("href: MARKET_EXPLORER_NAV_HREF"));
  assert.ok(itemsBlock.includes("isActive: isExplorerNavRouteActive(normalizedPathname)"));
  assert.ok(itemsBlock.includes("isActive: isMarketNavRouteActive(normalizedPathname)"));
  assert.equal(isMarketNavRouteActive("/Market"), true);
  assert.equal(isExplorerNavRouteActive("/Market"), false);
  for (const route of ["/Market/Explorer", "/Market/Explorer/saved-view"]) {
    assert.equal(isExplorerNavRouteActive(route), true);
    assert.equal(isMarketNavRouteActive(route), false);
  }
});

test("Articles leaves the fixed nav but remains in the mobile menu", () => {
  assert.ok(!itemsBlock.includes('label: "Articles"'));
  assert.ok(!itemsBlock.includes('href: "/Articles"'));
  assert.match(headerSource, /id="mobile-header-menu"[\s\S]*?<Link href="\/Articles"[\s\S]*?>\s*Articles\s*<\/Link>/);
});

test("TCGs routes through the shared href constant and lights the whole /TCGs family", () => {
  assert.equal(TCGS_NAV_HREF, "/TCGs/Pokemon/Sets");
  assert.ok(itemsBlock.includes("href: TCGS_NAV_HREF"), "TCGs must not hardcode its path");
  assert.ok(
    source.includes('import { TCGS_NAV_HREF } from "@/lib/navigation/tcgsNav.mjs";'),
    "the shared constant is imported"
  );
  assert.ok(
    itemsBlock.includes('isActive: isPathMatch(normalizedPathname, ["/TCGs"], { caseInsensitive: true })'),
    "TCGs is active anywhere in the /TCGs route family"
  );
});

test("Tools is gone from the bottom navigation", () => {
  assert.ok(!source.includes('"/tools"'), "no bottom nav item may point at /tools");
  assert.ok(!source.includes('id === "tools"'), "the Tools icon branch must be removed");
  assert.ok(!/label: "Tools"/.test(source), "the Tools label must be removed");
});

test("the bottom navigation preserves its chrome while fitting five destinations", () => {
  assert.ok(
    source.includes(
      'className="fixed inset-x-0 bottom-0 z-[60] border-t border-[var(--border-subtle)] bg-[var(--surface-panel)]/95 backdrop-blur lg:hidden"'
    ),
    "the nav shell classes are unchanged"
  );
  assert.ok(
    source.includes('style={{ paddingBottom: "max(0.6rem, env(safe-area-inset-bottom))" }}'),
    "the safe-area padding is unchanged"
  );
  assert.ok(
    source.includes('className="mx-auto grid max-w-xl grid-cols-5 gap-0.5 px-1.5 pt-2"'),
    "the destinations use a compact five-column grid"
  );
  assert.ok(
    source.includes(
      '"flex min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-0.5 py-2 text-[10px] font-medium transition-colors duration-150 ease-out"'
    ),
    "the item recipe is compact enough for five labels"
  );
});

test("Market and Explorer own their canonical routes and Home is removed", () => {
  assert.ok(itemsBlock.includes('href: "/Market"'));
  assert.ok(itemsBlock.includes("href: MARKET_EXPLORER_NAV_HREF"));
  assert.ok(!source.includes("/Research"), "the retired Research destination must be gone");
  assert.ok(!itemsBlock.includes('label: "Home"'));
  assert.ok(itemsBlock.includes("isMarketNavRouteActive(normalizedPathname)"));
  assert.ok(itemsBlock.includes("isExplorerNavRouteActive(normalizedPathname)"));
});

test("Portfolio is removed and the account slot only lights for account-settings", () => {
  assert.ok(!source.includes('id: "portfolio"'), "the Portfolio bottom-nav item must be removed");
  assert.ok(!source.includes('id === "portfolio"'), "the Portfolio icon branch must be removed");
  assert.ok(!/label: "Portfolio"/.test(source), "the Portfolio label must be removed");
  assert.ok(!source.includes('"/my-collection"'), "no bottom nav item may point at /my-collection");
  assert.ok(!source.includes('"/my-portfolio"'), "no bottom nav item may point at /my-portfolio");
  assert.ok(!source.includes('"/profile"'), "no bottom nav item may point at /profile");
  assert.ok(!source.includes('"/u"'), "no bottom nav item may point at /u");
  assert.ok(itemsBlock.includes('["/account-settings"]'));
});

test("the account slot routes to account-settings when signed in and pricing otherwise", () => {
  assert.ok(source.includes('const accountHref = user ? "/account-settings" : "/pricing";'));
});
