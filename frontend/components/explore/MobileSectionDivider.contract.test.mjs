// Mobile feed section dividers: two treatments, one attribute contract.
//
// The density pass replaced main's quiet `[data-mobile-feed] > * + *` border
// with an explicit `[data-mobile-section]` marker plus a flat 3px fill. The
// flat fill read as a solid gray bar, and directly beneath a 7D Movers ticker
// it read as a second slab of chrome competing with the ticker itself.
//
// This pass keeps the explicit markers and splits the treatment:
//   - ordinary sections get a STATIC luminous hairline (1px cool white-gray
//     core + soft bloom, faded at both ends) inside the same 3px box;
//   - the first ordinary section after either Movers ticker opts into
//     `data-mobile-section-variant="after-movers"` and gets main's 1px rule.
//
// RipStatisticsPageClient.jsx and Explore/page.js use bundler-only "@/..."
// specifiers, so these are source assertions like every other contract test
// for this feed. RipStatisticsPageClient.jsx carries mixed CRLF/LF.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.resolve(here, rel), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const explore = read("../../app/Explore/page.js");
const client = read("RipStatisticsPageClient.jsx");

const ordinaryRule = /\[data-mobile-section\]::before \{[\s\S]*?\n  \}/.exec(css)[0];
const afterMoversRule = /\[data-mobile-section\]\[data-mobile-section-variant="after-movers"\]::before \{[\s\S]*?\n  \}/.exec(css)[0];
const ordinarySpacing = /\[data-mobile-section\] \{[\s\S]*?\n  \}/.exec(css)[0];
const afterMoversSpacing = /\[data-mobile-section\]\[data-mobile-section-variant="after-movers"\] \{[\s\S]*?\n  \}/.exec(css)[0];

test("Explore Top Rankings takes the after-movers variant and Best Sets to Rip does not", () => {
  const rankings = explore.slice(explore.indexOf("<div data-mobile-section"), explore.indexOf("<ExploreTopRankings"));
  assert.match(rankings, /data-mobile-section data-mobile-section-variant="after-movers"/);

  // ExploreTableClient is "Best Sets to Rip" — ordinary luminous divider.
  const tableWrapper = explore.slice(
    explore.lastIndexOf("<div data-mobile-section", explore.indexOf("<ExploreTableClient")),
    explore.indexOf("<ExploreTableClient")
  );
  assert.match(tableWrapper, /<div data-mobile-section>/);
  assert.doesNotMatch(tableWrapper, /after-movers/);

  // Exactly one after-movers boundary on Explore.
  assert.equal((explore.match(/after-movers/g) || []).length, 1);
});

test("the 7D Movers tickers are never themselves section-marked", () => {
  const moversWrapper = explore.slice(
    explore.lastIndexOf("<div className=", explore.indexOf("<ExploreMarketMovers")),
    explore.indexOf("<ExploreMarketMovers")
  );
  assert.doesNotMatch(moversWrapper, /data-mobile-section/);

  // Set-level ticker: the module immediately preceding the RIP Summary, which
  // is now the first marked section on Overview.
  const beforeSummary = client.slice(
    client.indexOf("retryMarketMoversModule"),
    client.indexOf('sectionName="overview-rip-summary"')
  );
  // Exactly one marker sits in this span, and it is the RIP Summary's own
  // wrapper, which opens immediately before the boundary. The ticker's wrapper
  // — everything before that marker — carries none.
  const markerAt = beforeSummary.indexOf("data-mobile-section");
  assert.ok(markerAt > 0, "the RIP Summary wrapper must be marked");
  assert.doesNotMatch(
    beforeSummary.slice(0, markerAt),
    /data-mobile-section/,
    "the movers ticker itself must never be section-marked"
  );
  assert.match(
    beforeSummary.slice(markerAt),
    /data-mobile-section data-mobile-section-variant="after-movers"/,
    "the first section under the ticker takes the quiet after-movers rule"
  );
});

test("the RIP Summary takes the after-movers variant, and only it", () => {
  // The variant moved from Set Value Trend to the RIP Summary, because the RIP
  // Summary is now the module directly under the movers ticker. Set Value is a
  // later analytical section and takes the ordinary luminous divider.
  const summary = client.slice(
    client.indexOf('sectionName="overview-rip-summary"') - 400,
    client.indexOf('sectionName="overview-rip-summary"')
  );
  assert.match(summary, /data-mobile-section data-mobile-section-variant="after-movers"/);

  const setValue = client.slice(
    client.indexOf('id="set-detail-set-value-trend"'),
    client.indexOf('id="set-detail-set-value-trend"') + 260
  );
  assert.doesNotMatch(setValue, /after-movers/, "Set Value no longer leads the feed");
  assert.match(setValue, /data-mobile-section/, "but it is still a marked section");

  assert.equal((client.match(/after-movers/g) || []).length, 1, "exactly one boundary is quiet");
});

test("every later analytical section keeps the ordinary luminous marker", () => {
  // Overview: Perf vs Cost, Top Chase, Sealed Market.
  // Insights: RIP Score Breakdown, Simulation Results. The Collector Profile
  // anchor was removed with its section; Collector Appeal is not a section of
  // its own, it renders inside the RIP Score Breakdown wrapper.
  // Anchored on sectionName, which is unique to each render site (component
  // names also match their import and definition lines).
  const anchors = [
    ["Opening Profit vs Cost", 'sectionName="overview-performance-vs-cost"'],
    ["Top Chase Cards", 'sectionName="overview-top-chase"'],
    ["Sealed Market", 'sectionName="overview-sealed-market"'],
    ["RIP Score Breakdown", 'sectionName="insights-rip-score"'],
    ["Simulation Results", 'sectionName="insights-opening-outcomes"'],
  ];

  for (const [label, anchor] of anchors) {
    const at = client.indexOf(anchor);
    assert.ok(at > 0, `expected to locate ${label}`);
    const marker = client.lastIndexOf("data-mobile-section", at);
    const wrapper = client.slice(marker, at);
    assert.ok(marker > 0, `${label} must sit inside a data-mobile-section`);
    assert.doesNotMatch(wrapper, /after-movers/, `${label} must keep the ordinary luminous divider`);
  }

  // 7: 6 after the Collector Profile wrapper was removed with its section,
  // plus the new Overview RIP Summary wrapper.
  assert.equal((client.match(/data-mobile-section(?!-)/g) || []).length, 7);
  assert.equal((explore.match(/data-mobile-section(?!-)/g) || []).length, 2);
});

test("the after-movers rule is a plain 1px border-subtle line with no glow", () => {
  assert.match(afterMoversRule, /height: 1px;/);
  assert.match(afterMoversRule, /background: var\(--border-subtle\);/);
  assert.match(afterMoversRule, /box-shadow: none;/);
  assert.match(afterMoversRule, /filter: none;/);

  // No gradient, bloom or 3px footprint survives at this boundary, so it can
  // never render a thin line and a luminous line at once.
  assert.doesNotMatch(afterMoversRule, /gradient|3px|drop-shadow/);
});

test("the ordinary divider layers a 1px faded core over a soft bloom", () => {
  // One crisp core line, sized to 1px inside the 3px box.
  assert.match(ordinaryRule, /linear-gradient\(\s*90deg,/);
  assert.match(ordinaryRule, /center \/ 100% 1px no-repeat/);
  // One soft glow layer filling the full 3px box.
  assert.match(ordinaryRule, /radial-gradient\(\s*ellipse 72% 100% at 50% 0%/);
  assert.match(ordinaryRule, /center \/ 100% 3px no-repeat/);
  // Horizontally faded at both ends.
  assert.match(ordinaryRule, /transparent 0%,[\s\S]*?transparent 100%/);
  assert.match(ordinaryRule, /--mobile-section-divider-edge\) 9%/);
  assert.match(ordinaryRule, /--mobile-section-divider-edge\) 91%/);
  // Brighter middle.
  assert.match(ordinaryRule, /--mobile-section-divider-core\) 50%/);
  assert.match(ordinaryRule, /height: 3px;/);
  assert.match(ordinaryRule, /pointer-events: none;/);
});

test("divider tokens are cool neutrals, never a brand accent, and stay restrained", () => {
  assert.match(css, /--mobile-section-divider-core: rgba\(226, 232, 240, 0\.28\);/);
  assert.match(css, /--mobile-section-divider-edge: rgba\(203, 213, 225, 0\.08\);/);
  assert.match(css, /--mobile-section-divider-glow: rgba\(147, 197, 253, 0\.10\);/);

  // Dark-theme core must stay at or below ~0.34 so it never reads as a
  // heavy silver bar.
  const core = Number(/--mobile-section-divider-core: rgba\([\d, ]+ ([\d.]+)\);/.exec(css)[1]);
  assert.ok(core <= 0.34, `dark core opacity ${core} exceeds the 0.34 ceiling`);

  // Light theme is defined and readable rather than inheriting dark values.
  const light = css.slice(css.indexOf('[data-theme="light"] {'));
  const block = light.slice(0, light.indexOf("\n}"));
  assert.match(block, /--mobile-section-divider-core: rgba\(71, 85, 105, 0\.22\);/);
  assert.match(block, /--mobile-section-divider-edge: rgba\(100, 116, 139, 0\.07\);/);
  assert.match(block, /--mobile-section-divider-glow: rgba\(59, 130, 246, 0\.06\);/);

  // Structural, so no accent/tier colour anywhere in either rule.
  for (const rule of [ordinaryRule, afterMoversRule]) {
    assert.doesNotMatch(rule, /--accent|--success|--danger|--warning|--brand|tier/);
  }
});

test("the old flat divider implementation is gone", () => {
  assert.doesNotMatch(css, /background: var\(--mobile-section-divider\)/);
  assert.doesNotMatch(css, /--mobile-section-divider:/);
  // main's generic direct-child feed rule stays retired.
  assert.doesNotMatch(css, /\[data-mobile-feed\] > \* \+ \*/);
});

test("both dividers are static and confined to the mobile feed breakpoint", () => {
  for (const rule of [ordinaryRule, afterMoversRule]) {
    assert.doesNotMatch(rule, /animation|transition|@keyframes/);
  }
  assert.doesNotMatch(css, /@keyframes[\s\S]{0,400}mobile-section/);

  // Both rules live inside the existing mobile/tablet media query, so desktop
  // shows neither divider.
  const scope = css.indexOf("@media (max-width: 1199.98px)");
  assert.ok(scope > 0, "the mobile feed breakpoint must still exist");
  assert.ok(css.indexOf(ordinaryRule) > scope);
  assert.ok(css.indexOf(afterMoversRule) > scope);
  // No divider rule escaped to root scope.
  assert.equal((css.match(/\[data-mobile-section\](\[|\)|::before)/g) || []).length, 3);
});

test("ordinary sections carry the tightened 16px/20px spacing", () => {
  assert.match(ordinarySpacing, /margin-top: 1rem;/);
  assert.match(ordinarySpacing, /padding-top: 1\.25rem;/);
});

test("the after-movers boundary is considerably tighter than an ordinary one", () => {
  assert.match(afterMoversSpacing, /margin-top: 0\.5rem;/);
  assert.match(afterMoversSpacing, /padding-top: 0\.75rem;/);

  // Spacing only — the variant must never restate divider paint here.
  assert.doesNotMatch(afterMoversSpacing, /background|height|filter|box-shadow/);

  // And it must win the cascade, so it follows the ordinary rule in source.
  assert.ok(css.indexOf(afterMoversSpacing) > css.indexOf(ordinarySpacing));
});

test("the Explore Movers wrapper drops its mobile margin but keeps the desktop one", () => {
  const wrapper = explore.slice(
    explore.lastIndexOf("<div className=", explore.indexOf("<ExploreMarketMovers")),
    explore.indexOf("<ExploreMarketMovers")
  );
  // Desktop-first, deliberately: the original desktop mb-5 is the
  // unconditional base and mobile subtracts it. Written the other way round
  // (`mb-0 desk:mb-5`) the desktop value depends on the mobile utility losing
  // a source-order tie, which is how desktop regressed to zero spacing.
  assert.match(wrapper, /className="mb-5 max-desk:mb-0"/);
  // The mobile removal must stay breakpoint-qualified — an unprefixed mb-0
  // token here would flatten desktop again.
  const classes = /className="([^"]*)"/.exec(wrapper)[1].split(/\s+/);
  assert.ok(!classes.includes("mb-0"), "mb-0 must always carry the max-desk: prefix");
  assert.ok(classes.includes("mb-5"));
  assert.ok(classes.includes("max-desk:mb-0"));
});

test("desktop Explore spacing is exactly what it was before the mobile pass", () => {
  // The mobile pass must not have moved any desktop-scoped value. These are
  // the five the regression report named: page top padding, container width,
  // horizontal padding, the gap below Movers, and the gap between the tables.
  const root = explore.slice(explore.indexOf("<div className={`${styles.dashboard}"), explore.indexOf("<PageArtworkAtmosphere"));
  assert.match(root, /\bpt-5\b/, "page top padding");
  assert.match(root, /\bmax-w-7xl\b/, "container width");
  assert.match(root, /\bpx-4\b/, "horizontal padding");
  assert.match(root, /\bsm:px-6\b/);
  assert.match(root, /\blg:px-8\b/);

  const grid = explore.slice(explore.indexOf('<div className="grid grid-cols-1'));
  assert.match(grid, /\bgap-4\b/, "gap between the two desktop tables");
  assert.match(
    grid,
    /xl:grid-cols-\[minmax\(19rem,1fr\)_minmax\(0,2fr\)\]/,
    "desktop column sizes"
  );
});

test("the tightened mobile divider spacing never reaches desktop", () => {
  // The whole point of the fix: mobile values stay untouched, and they stay
  // sealed inside the sub-1200px feed scope. If these rules ever escaped that
  // media query they would re-open the desktop regression from the CSS side.
  const scopeStart = css.indexOf("@media (max-width: 1199.98px)");
  assert.ok(scopeStart > -1, "the mobile feed scope must exist");
  assert.ok(css.indexOf(ordinarySpacing) > scopeStart);
  assert.ok(css.indexOf(afterMoversSpacing) > scopeStart);
});
