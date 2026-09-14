import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");
const header = read("Header.js");
const bottomNav = read("GlobalMobileBottomNav.js");
const layout = read("../app/layout.js");
const tailwind = read("../tailwind.config.js");

test("wide header uses three normal-flow grid regions with equal side tracks", () => {
  assert.doesNotMatch(header, /right-\[calc\(|absolute left-1\/2/);
  assert.match(header, /data-header-layout[^>]+hdr:grid/);
  assert.match(header, /hdr:grid-cols-\[minmax\(0,1fr\)_clamp\(280px,calc\(100vw-1000px\),420px\)_minmax\(0,1fr\)\]/);
  assert.doesNotMatch(header, /data-header-left-wing[^>]+(xl|hdr):justify-between/);
  assert.match(header, /data-header-logo[\s\S]+data-desktop-primary-nav[\s\S]+data-header-search[\s\S]+data-header-account/);
  assert.doesNotMatch(header, /className="hidden (xl|hdr):contents"/);
  assert.doesNotMatch(header, /data-desktop-primary-nav className="contents whitespace-nowrap"/);
  assert.match(header, /data-desktop-primary-nav className="flex items-center gap-4 whitespace-nowrap"/);
  assert.equal((header.match(/data-primary-nav-item/g) || []).length, 5);
  assert.doesNotMatch(header, /(xl|hdr):ml-auto/);
  assert.match(header, /data-header-account[^>]+hdr:justify-end/);
});

test("one mounted search preserves query state across the CSS breakpoint", () => {
  assert.equal((header.match(/<SitewideSearchBar/g) || []).length, 1);
  assert.doesNotMatch(header, /innerWidth|matchMedia|addEventListener\(["']resize/);
});

test("all responsive navigation surfaces share the established hdr breakpoint", () => {
  assert.doesNotMatch(tailwind, /nav:\s*["']/);
  assert.match(tailwind, /hdr:\s*["']1800px["']/);
  assert.match(header, /className="hdr:hidden inline-flex/);
  assert.match(header, /className="hidden hdr:flex items-center"/);
  assert.match(header, /className="hdr:hidden absolute/);
  assert.match(bottomNav, /backdrop-blur hdr:hidden/);
  assert.match(layout, /hdr:pb-0/);
  assert.doesNotMatch(bottomNav, /lg:hidden/);
  assert.doesNotMatch(layout, /lg:pb-0/);
  // Every desktop/compact toggle in the header must share the one breakpoint —
  // no leftover `xl:` visibility class would silently desync the transition.
  assert.doesNotMatch(header, /className="[^"]*\bxl:(hidden|flex|grid)\b/);
});

test("the compact bottom nav keeps exactly five primary destinations and Articles stays in the menu", () => {
  const itemIds = [...bottomNav.matchAll(/^\s+id: "([^"]+)"/gm)].map((match) => match[1]);
  assert.deepEqual(itemIds, ["rankings", "market", "explore", "tcgs", "profile"]);
  assert.match(header, /id="mobile-header-menu"[\s\S]*href="\/Articles"/);
});
