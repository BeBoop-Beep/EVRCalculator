import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const client = readFileSync(new URL("./RipStatisticsPageClient.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../app/styles/globals.css", import.meta.url), "utf8");
const explore = readFileSync(new URL("../../app/Explore/page.js", import.meta.url), "utf8");

test("Top Chase renders one ten-row list and exposes disclosure only below desktop", () => {
  const module = client.slice(client.indexOf("function TopChaseCardsModule("), client.indexOf("function hasMarketMoverRows("));
  assert.match(module, /maxRows=\{10\}/);
  assert.match(module, /mobileExpanded=\{showAllChaseCards\}/);
  assert.match(module, /hidden justify-center max-desk:flex/);
  assert.doesNotMatch(module, /maxRows=\{showAllChaseCards/);
});

test("Overview right column stacks Sealed Market then unchanged Decision Signals props", () => {
  const overview = client.slice(client.indexOf('id="set-detail-overview"'), client.indexOf('{setDetailMode && !isDesktopHeroComposition'));
  const chase = overview.indexOf("<TopChaseCardsModule");
  const sealed = overview.indexOf("<SealedMarketTrendCard");
  const signals = overview.indexOf("<DecisionSignalsCard");
  assert.ok(chase >= 0 && sealed > chase && signals > sealed);
  for (const prop of ["pillarSignals", "summary", "setIntelligenceMeta", "trackedSignals", "requestTimeout"]) {
    assert.match(overview.slice(signals, signals + 600), new RegExp(`${prop}=`));
  }
  assert.match(overview, /lg:grid-cols-3/);
  assert.match(overview, /lg:col-span-2/);
});

test("shared mobile section treatment is explicit, three pixels, and desktop-free", () => {
  assert.match(css, /--mobile-section-divider-core:/);
  assert.match(css, /\[data-mobile-section\]::before\s*\{[^}]*height: 3px;[^}]*var\(--mobile-section-divider-core\)/s);
  assert.doesNotMatch(css, /\[data-mobile-feed\] > \* \+ \*/);
  // `(?!-)` so the after-movers `data-mobile-section-variant` attribute is not
  // double-counted as a second section marker.
  assert.equal((client.match(/data-mobile-section(?!-)/g) || []).length, 8);
  assert.equal((explore.match(/data-mobile-section(?!-)/g) || []).length, 2);
  const moversWrapper = explore.slice(explore.lastIndexOf('<div className="mb-5">', explore.indexOf("<ExploreMarketMovers")), explore.indexOf("<ExploreMarketMovers"));
  assert.doesNotMatch(moversWrapper, /data-mobile-section/);
});
