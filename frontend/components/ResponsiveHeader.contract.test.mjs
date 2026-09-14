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

test("wide primary navigation and search participate in one normal-flow row", () => {
  assert.doesNotMatch(header, /right-\[calc\(|absolute left-1\/2/);
  assert.match(header, /hidden xl:flex shrink-0 items-center/);
  assert.match(header, /flex flex-1 min-w-0 xl:min-w-\[240px\] xl:max-w-\[420px\]/);
});

test("one mounted search preserves query state across the CSS breakpoint", () => {
  assert.equal((header.match(/<SitewideSearchBar/g) || []).length, 1);
  assert.doesNotMatch(header, /innerWidth|matchMedia|addEventListener\(["']resize/);
});

test("all responsive navigation surfaces share the established xl breakpoint", () => {
  assert.doesNotMatch(tailwind, /nav:\s*["']/);
  assert.match(header, /className="xl:hidden inline-flex/);
  assert.match(header, /className="hidden xl:flex items-center"/);
  assert.match(header, /className="xl:hidden absolute/);
  assert.match(bottomNav, /backdrop-blur xl:hidden/);
  assert.match(layout, /xl:pb-0/);
  assert.doesNotMatch(bottomNav, /lg:hidden/);
  assert.doesNotMatch(layout, /lg:pb-0/);
});

test("the compact bottom nav keeps exactly five primary destinations and Articles stays in the menu", () => {
  const itemIds = [...bottomNav.matchAll(/^\s+id: "([^"]+)"/gm)].map((match) => match[1]);
  assert.deepEqual(itemIds, ["rankings", "market", "explore", "tcgs", "profile"]);
  assert.match(header, /id="mobile-header-menu"[\s\S]*href="\/Articles"/);
});
