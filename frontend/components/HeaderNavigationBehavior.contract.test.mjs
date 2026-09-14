import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");
const header = read("Header.js");
const bottomNav = read("GlobalMobileBottomNav.js");
const searchBar = read("Search/SitewideSearchBar.jsx");
const articlePrimitives = read("articles/ArticlePrimitives.jsx");

// A normal left click on an internal global-navigation destination must stay
// in the current tab. This locks the source-level contract that keeps it
// that way: plain next/link (or router.push) with no target/window.open.

test("internal desktop header links carry no target attribute and open no new browsing context", () => {
  assert.doesNotMatch(header, /target=\{?["']_blank/);
  assert.doesNotMatch(header, /window\.open\(/);
  assert.doesNotMatch(header, /globalThis\.open\(/);
  // Every primary nav destination is a plain next/link Link with an href,
  // immediately followed (within the recipe interpolation) by no target prop.
  const primaryNavBlock = header.slice(header.indexOf('data-desktop-primary-nav'), header.indexOf('</nav>'));
  assert.doesNotMatch(primaryNavBlock, /target=/);
  assert.equal((primaryNavBlock.match(/data-primary-nav-item/g) || []).length, 5, "Rankings, Market, Explorer, TCGs, Articles");
});

test("the inDex logo link carries no target attribute", () => {
  const logoBlock = header.slice(header.indexOf('data-header-logo'), header.indexOf('data-header-logo') + 900);
  assert.doesNotMatch(logoBlock, /target=/);
});

test("membership/account links use plain client navigation, not a new tab or auth-popup side effect", () => {
  assert.doesNotMatch(header, /MembershipNavLink[\s\S]{0,80}target=/);
  // Login opens an in-page popover, not a navigation/new-tab action.
  assert.match(header, /setIsAuthOpen\(\(value\) => !value\)/);
  assert.doesNotMatch(header, /Login[\s\S]{0,40}window\.open/);
});

test("bottom-nav links carry no target attribute and use plain next/link", () => {
  assert.doesNotMatch(bottomNav, /target=/);
  assert.doesNotMatch(bottomNav, /window\.open\(/);
  assert.match(bottomNav, /import Link from "next\/link"/);
  assert.equal((bottomNav.match(/<Link\b/g) || []).length, 1, "the five destinations render from one Link recipe inside items.map");
});

test("search results navigate via router.push, not window.open or a synthesized anchor", () => {
  assert.match(searchBar, /const choose = \(item\) => \{ setOpen\(false\); setActiveIndex\(-1\); router\.push\(item\.href\); \};/);
  assert.doesNotMatch(searchBar, /window\.open\(/);
  assert.doesNotMatch(searchBar, /target=/);
});

test("external article citations may still open in a new tab — this contract is scoped to internal nav only", () => {
  assert.match(articlePrimitives, /target="_blank"/);
  assert.match(articlePrimitives, /rel="[^"]*noreferrer[^"]*"/);
});

test("no global click handler intercepts or redirects ordinary navigation clicks", () => {
  // RouteTransitionFeedback listens for clicks (capture) purely to drive a
  // loading-bar UI; it must never preventDefault or redirect the click.
  const routeTransitionFeedback = read("navigation/RouteTransitionFeedback.jsx");
  assert.doesNotMatch(routeTransitionFeedback, /\.preventDefault\(\)/);
  assert.doesNotMatch(routeTransitionFeedback, /window\.open\(/);
  assert.match(routeTransitionFeedback, /event\.metaKey \|\| event\.ctrlKey \|\| event\.shiftKey \|\| event\.altKey/, "modifier clicks are left alone, not blocked or intercepted");
});
