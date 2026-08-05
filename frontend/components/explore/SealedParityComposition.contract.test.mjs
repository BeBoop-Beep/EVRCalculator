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

// Decision Signals assertions were removed: the Overview Decision Signals card
// scored Profit, Safety, Stability, Opening Experience and Chase Potential, none
// of which are terms of the current model, and the card no longer exists.

test("shared mobile section treatment is explicit, three pixels, and desktop-free", () => {
  assert.match(css, /--mobile-section-divider-core:/);
  assert.match(css, /\[data-mobile-section\]::before\s*\{[^}]*height: 3px;[^}]*var\(--mobile-section-divider-core\)/s);
  assert.doesNotMatch(css, /\[data-mobile-feed\] > \* \+ \*/);
  // `(?!-)` so the after-movers `data-mobile-section-variant` attribute is not
  // double-counted as a second section marker.
  // 7 after the Overview Decision Signals wrapper was removed with its card.
  assert.equal((client.match(/data-mobile-section(?!-)/g) || []).length, 7);
  assert.equal((explore.match(/data-mobile-section(?!-)/g) || []).length, 2);
  const moversWrapper = explore.slice(explore.lastIndexOf("<div className=", explore.indexOf("<ExploreMarketMovers")), explore.indexOf("<ExploreMarketMovers"));
  assert.doesNotMatch(moversWrapper, /data-mobile-section/);
});
