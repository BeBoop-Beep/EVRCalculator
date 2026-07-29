import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const client = read("RipStatisticsPageClient.jsx");
const scaffold = read("../Profile/PublicProfileLocalScaffold.js");

const mobileBlockStart = css.indexOf("@media (max-width: 1199.98px) {");
const mobileBlock = css.slice(mobileBlockStart, css.indexOf("\n}", mobileBlockStart));

test("the Overview section is marked as the mobile feed", () => {
  assert.ok(client.includes('<section id="set-detail-overview" data-mobile-feed'), "the feed region is explicit");
});

test("outer card chrome is stripped inside the feed below desktop", () => {
  assert.ok(mobileBlock.includes("[data-mobile-feed] .set-glass-surface"));
  for (const declaration of ["border: 0;", "border-radius: 0;", "background: transparent;", "box-shadow: none;"]) {
    assert.ok(mobileBlock.includes(declaration), `${declaration} must be part of the feed reset`);
  }
});

test("sections are separated by dividers rather than by nested boxes", () => {
  assert.ok(mobileBlock.includes("[data-mobile-feed] > * + * {"));
  assert.ok(/\[data-mobile-feed\] > \* \+ \* \{[^}]*border-top: 1px solid var\(--border-subtle\);/s.test(mobileBlock));
});

test("the reset is scoped so desktop and other tabs are untouched", () => {
  // Cards' toolbar also uses .set-glass-surface. Scoping to [data-mobile-feed]
  // keeps this to the Overview, and the media query keeps it off desktop.
  assert.ok(!css.includes("\n.set-glass-surface {\n  border: 0;"), "no unscoped global reset");
  assert.ok(
    client.includes('<div data-cards-toolbar className="set-glass-surface'),
    "the Cards toolbar keeps its own surface and is outside the feed"
  );
  const cardsSection = client.indexOf('<section id="set-detail-cards"');
  const overviewSection = client.indexOf('<section id="set-detail-overview" data-mobile-feed');
  assert.ok(cardsSection >= 0 && overviewSection >= 0);
  assert.ok(
    !client.slice(overviewSection, client.indexOf('{setDetailTab === "cards" ? (')).includes("data-cards-toolbar"),
    "the Cards toolbar is not inside the feed region"
  );
});

test("the feed reset only lands after the desktop glass rules", () => {
  // Media queries add no specificity. If this block preceded the unconditional
  // .set-glass-surface rules, the desktop values would win at every width and
  // the reset would silently do nothing.
  assert.ok(
    css.indexOf(".set-detail-glass-scope .set-glass-surface,") < mobileBlockStart,
    "the mobile override must come after the base glass rules in source order"
  );
});

test("page gutters are 16px on phones and 24px on tablets", () => {
  // Four strings: contentFramed + contentFlat in each of the two recipes.
  assert.equal(
    (scaffold.match(/px-4 pt-3 tab:px-6/g) || []).length,
    4,
    "both breakpoint recipes carry the brief's gutters in both content variants"
  );
  assert.ok(!scaffold.includes("px-3 pt-3 sm:px-6"), "the old gutter is gone from every recipe");
});

test("the tablet content area is capped and centred", () => {
  // Brief section 10: roughly 760-960px of effective content on tablet, not a
  // phone layout stretched edge to edge across 1024px.
  // Stated as a base value with a desk: override rather than `max-desk:`,
  // because `max-*` variants are emitted before `lg:` and would have lost the
  // 1024-1199px band back to lg:max-w-[1440px].
  assert.ok(client.includes("mx-auto w-full max-w-[960px] desk:max-w-[1440px]"));
  assert.ok(
    !client.includes("lg:max-w-[1440px]"),
    "the desktop cap must not leak into the 1024-1199px tablet band"
  );
  assert.ok(client.includes("desk:px-4 2xl:px-5"), "the desktop gutter is gated at 1200px");
  assert.ok(mobileBlock.includes("[data-mobile-feed] {"), "a phone never inherits a stray centring margin");
});
