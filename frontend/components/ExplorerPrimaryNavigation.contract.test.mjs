import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

import { MARKET_EXPLORER_NAV_HREF, isExplorerNavRouteActive, isMarketNavRouteActive } from "../lib/navigation/marketNav.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const header = fs.readFileSync(path.resolve(here, "Header.js"), "utf8").replace(/\r\n/g, "\n");
const primary = header.slice(header.indexOf('<nav className="flex items-center gap-4 whitespace-nowrap">'), header.indexOf("</nav>", header.indexOf('<nav className="flex items-center gap-4 whitespace-nowrap">')));

test("desktop primary navigation promotes Explorer in the accepted order", () => {
  const labels = [...primary.matchAll(/^\s{16}(Rankings|Market|Explorer|TCGs|Articles)$/gm)].map((match) => match[1]);
  assert.deepEqual(labels, ["Rankings", "Market", "Explorer", "TCGs", "Articles"]);
  assert.equal(MARKET_EXPLORER_NAV_HREF, "/Market/Explorer");
  assert.ok(primary.includes("href={MARKET_EXPLORER_NAV_HREF}"));
  assert.equal((primary.match(/\$\{navTabBase\}/g) || []).length, 5);
});

test("Market and Explorer route families are mutually exclusive", () => {
  assert.equal(isMarketNavRouteActive("/Market"), true);
  assert.equal(isExplorerNavRouteActive("/Market"), false);
  for (const pathname of ["/Market/Explorer", "/Market/Explorer/anything"]) {
    assert.equal(isExplorerNavRouteActive(pathname), true);
    assert.equal(isMarketNavRouteActive(pathname), false);
  }
  for (const pathname of ["/Rankings", "/TCGs/Pokemon/Sets", "/Articles"]) {
    assert.equal(isExplorerNavRouteActive(pathname), false);
  }
});

test("Explorer is ungated, desktop Articles remains, and mobile Articles is discoverable", () => {
  assert.ok(primary.includes('href="/Articles"'));
  const explorer = primary.slice(primary.indexOf("href={MARKET_EXPLORER_NAV_HREF}"), primary.indexOf("</Link>", primary.indexOf("href={MARKET_EXPLORER_NAV_HREF}")));
  assert.doesNotMatch(explorer, /Premium|MembershipNavLink|lock/i);
  assert.match(header, /id="mobile-header-menu"[\s\S]*?<Link href="\/Articles"[\s\S]*?>\s*Articles/);
});
