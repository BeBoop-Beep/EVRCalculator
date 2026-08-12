import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

import { TCGS_NAV_HREF, isTopNavRouteActive } from "../lib/navigation/tcgsNav.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const headerSource = read("Header.js");
const stickyNavSource = read("StickyNav.js");
const globalsSource = read("../app/styles/globals.css");
const setsPageSource = read("../app/TCGs/Pokemon/Sets/page.js");
const setsLoadingSource = read("../app/TCGs/Pokemon/Sets/loading.js");

// The header renders its primary nav items in one place; slice it so
// assertions about "the primary nav" cannot be satisfied by markup elsewhere
// in the header (the account menu, the mobile sheet).
const primaryNav = headerSource.slice(
  headerSource.indexOf('<nav className="flex items-center gap-4 whitespace-nowrap">'),
  headerSource.indexOf("</nav>", headerSource.indexOf('<nav className="flex items-center gap-4 whitespace-nowrap">'))
);

test("TCGs is a plain link to the Pokémon Sets catalog", () => {
  assert.equal(TCGS_NAV_HREF, "/TCGs/Pokemon/Sets");

  assert.ok(primaryNav.length > 0, "the primary nav block must be locatable");
  assert.ok(primaryNav.includes("href={TCGS_NAV_HREF}"), "TCGs routes through the shared href constant");
  assert.ok(/<Link\s+href=\{TCGS_NAV_HREF\}[\s\S]*?>\s*TCGs\s*<\/Link>/.test(primaryNav), "TCGs renders as <Link>, not a button");
  assert.ok(headerSource.includes('import { TCGS_NAV_HREF, isTopNavRouteActive } from "@/lib/navigation/tcgsNav.mjs";'));

  // The label is unchanged — the global category is still TCGs, not "Sets".
  assert.ok(primaryNav.includes(">\n                TCGs\n              </Link>"));
});

test("the TCGs dropdown, its chevron and its menu are gone", () => {
  // No trigger state, ref, or handlers survive.
  assert.ok(!headerSource.includes("isTCGsDropdownOpen"), "dropdown open state must be removed");
  assert.ok(!headerSource.includes("setIsTCGsDropdownOpen"), "dropdown setter must be removed");
  assert.ok(!headerSource.includes("tcgsDropdownRef"), "dropdown ref and its outside-click branch must be removed");

  // No popup semantics and no chevron inside the primary nav.
  assert.ok(!primaryNav.includes("aria-haspopup"), "no primary nav item may claim a popup");
  assert.ok(!primaryNav.includes("aria-expanded"), "no primary nav item may claim an expanded state");
  assert.ok(!primaryNav.includes("<svg"), "the dropdown chevron must be gone");
  assert.ok(!primaryNav.includes("rotate-180"), "the chevron rotation must be gone");
  assert.ok(!primaryNav.includes("navDropPanel"), "no menu panel may render in the primary nav");

  // The one-item Pokémon menu entry is gone; nothing links to the bare
  // /TCGs/Pokemon overview from the global nav any more.
  assert.ok(!headerSource.includes('href="/TCGs/Pokemon"'), "the one-item TCG menu link must be removed");
  assert.ok(!headerSource.includes("Pokémon\n                    </Link>"));
});

test("TCGs is active anywhere in the /TCGs route family and nowhere else", () => {
  for (const pathname of [
    "/TCGs",
    "/TCGs/Pokemon",
    "/TCGs/Pokemon/Sets",
    "/TCGs/Pokemon/Sets/chaosRising",
    "/TCGs/Pokemon/Analytics",
  ]) {
    assert.equal(isTopNavRouteActive(pathname, "/TCGs"), true, `${pathname} must light TCGs`);
  }

  for (const pathname of ["/", "/Explore", "/tools", "/my-portfolio", "/TCGsomething"]) {
    assert.equal(isTopNavRouteActive(pathname, "/TCGs"), false, `${pathname} must not light TCGs`);
  }

  // The header wires that rule to the accent underline and to aria-current, so
  // the active state is both seen and announced.
  assert.ok(headerSource.includes("const isTcgsRouteActive = isTopNavActive('/TCGs');"));
  assert.ok(headerSource.includes("const isTopNavActive = (path) => isTopNavRouteActive(pathname, path);"));
  assert.ok(primaryNav.includes('aria-current={isTcgsRouteActive ? "page" : undefined}'));
  assert.ok(primaryNav.includes("isTcgsRouteActive ? navTabActive : navTabInactive"));
  assert.ok(headerSource.includes("after:h-[2px] after:rounded-full after:bg-[var(--accent)]"), "the accent underline treatment is preserved");
});

test("TCGs shares the primary nav typography, spacing and visible focus ring", () => {
  // Explore and TCGs are one set of siblings built from one class recipe.
  // Tools was removed as a destination; the recipe itself is unchanged.
  const tabs = primaryNav.match(/\$\{navTabBase\} inline-flex items-center justify-center/g) || [];
  assert.equal(tabs.length, 4, "Rankings, Market, TCGs, and Research must share the primary tab recipe");
  assert.ok(headerSource.includes("px-3 xl:px-4 py-2 text-sm xl:text-[15px] font-medium"), "primary nav typography and spacing are unchanged");
  assert.ok(
    headerSource.includes("focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"),
    "primary nav items must keep a visible keyboard focus treatment"
  );
});

test("Tools is gone from every header surface", () => {
  assert.ok(!headerSource.includes('href="/tools"'), "no header link may point at /tools");
  assert.ok(!headerSource.includes("isToolsRouteActive"), "the Tools active-route helper must be removed");
  assert.ok(!/>\s*Tools\s*</.test(headerSource), "no header element may render the Tools label");
});

test("the primary public architecture and account destinations are present", () => {
  assert.ok(primaryNav.includes('href="/Rankings"'));
  assert.ok(primaryNav.includes('href="/Market"'));
  assert.ok(primaryNav.includes('href="/Research"'));
  assert.ok(headerSource.includes('href="/my-portfolio"'));
  assert.ok(headerSource.includes('href="/my-portfolio/collection"'));
  assert.ok(headerSource.includes('href="/my-portfolio/wishlist"'));
  assert.ok(headerSource.includes('href="/login"'));
  assert.ok(headerSource.includes('href="/account-settings"'));
  assert.ok(headerSource.includes('src="/images/inDex.png"'));
  assert.ok(headerSource.includes('aria-controls="mobile-header-menu"'), "the mobile menu toggle is preserved");
});

test("the shared dropdown primitives survive for the menus that still use them", () => {
  // My Portfolio and the account menu are untouched, so their trigger, panel
  // and item classes must all remain — only the TCGs usage was removed.
  for (const token of ["navDropTrigger", "navDropPanel", "navDropItem", "navDropTriggerActive", "navDropTriggerClosed"]) {
    assert.ok(headerSource.includes(token), `${token} is still used by the remaining menus`);
  }
  assert.ok(headerSource.includes("isCollectionDropdownOpen"));
  assert.ok(headerSource.includes("isUserDropdownOpen"));
  assert.ok(globalsSource.includes(".dropdown-enter"), "the shared dropdown entrance stays for the remaining menus");
});

test("the Pokémon Sets route no longer renders a secondary Overview / Sets bar", () => {
  for (const [label, source] of [
    ["page", setsPageSource],
    ["loading", setsLoadingSource],
  ]) {
    assert.ok(!source.includes("SecondaryNav"), `${label} must not import or render SecondaryNav`);
    assert.ok(!source.includes("basePath="), `${label} must not keep the secondary nav's props`);
    assert.ok(!source.includes(">Overview<"), `${label} must not keep an Overview tab`);
    // Content starts straight under the global navbar — no leftover spacer.
    assert.ok(
      source.includes('<main className="w-full px-2 md:px-6 lg:px-10 py-8">'),
      `${label} content begins directly beneath the global navbar`
    );
  }
});

test("the Sets page keeps its heading, route and content structure", () => {
  assert.ok(setsPageSource.includes("Pokémon TCG Sets"), "the visible page title stays");
  assert.ok(/<h1[^>]*>\s*\n\s*Pokémon TCG Sets/.test(setsPageSource), "the title is still the semantic h1");
  assert.ok(setsPageSource.includes("<main "), "the page keeps a main landmark");
  assert.ok(setsPageSource.includes("<section"), "era groups stay sectioned for screen readers");
  assert.ok(setsPageSource.includes("export default async function SetsPage()"), "the route entry point is unchanged");
  // The catalog now links to the BARE canonical set URL. It used to default to
  // `?tab=cards`, which pointed a few hundred internal links — the site's
  // largest single source of them — at a query variant of the URL the set page
  // declares as its canonical. Cards is unchanged and one click away.
  assert.ok(
    setsPageSource.includes("const setHref = slug ? `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}` :"),
    "set links point at the canonical set URL"
  );
  assert.ok(
    !/\$\{encodeURIComponent\(slug\)\}\?tab=/.test(setsPageSource),
    "set links must not default to a tab query variant"
  );
});

test("the navbar carries one restrained, static, non-interactive bottom glow", () => {
  assert.ok(stickyNavSource.includes("index-nav-shell sticky top-0 z-50"), "the glow hangs off the sticky shell");
  assert.ok(stickyNavSource.includes("bg-[var(--surface-header)] border-b border-[var(--border-subtle)]"), "existing shell chrome is preserved");

  const glowStart = globalsSource.indexOf(".index-nav-shell::after {");
  const glowEnd = globalsSource.indexOf("}", glowStart);
  assert.ok(glowStart >= 0, "the glow layer must exist");
  const glow = globalsSource.slice(glowStart, glowEnd);

  // A decorative pseudo-element below the navbar, behind the header and its menus.
  assert.ok(glow.includes('content: "";'));
  assert.ok(glow.includes("top: 100%;"), "the glow sits below the navbar, not inside it");
  assert.ok(glow.includes("pointer-events: none;"), "the glow must never intercept clicks");
  assert.ok(glow.includes("z-index: -1;"), "the glow stays behind the header and its dropdowns");
  assert.ok(/height: 2\dpx;/.test(glow), "the glow band stays narrow");

  // Soft radial falloff that reaches full transparency — light, not a rule.
  assert.ok(glow.includes("radial-gradient("), "a radial falloff reads as light rather than a divider");
  assert.ok(/rgba\(214, 228, 250, 0\)\s*100%/.test(glow), "the glow must fade fully to transparent");
  const alphas = [...glow.matchAll(/rgba\(214, 228, 250, ([\d.]+)\)/g)].map((m) => Number(m[1]));
  assert.ok(alphas.length >= 3, "the falloff needs several stops");
  assert.ok(Math.max(...alphas) <= 0.06, `peak glow opacity must stay restrained (found ${Math.max(...alphas)})`);

  // Static: no animation, no blur filter, no repaint cost.
  assert.ok(!glow.includes("animation"), "the glow must not pulse or animate");
  assert.ok(!glow.includes("transition"), "the glow must not animate");
  assert.ok(!/@keyframes[^}]*index-nav-shell/.test(globalsSource));

  assert.ok(globalsSource.includes('[data-theme="light"] .index-nav-shell::after'), "the light theme gets its own restrained value");
});
