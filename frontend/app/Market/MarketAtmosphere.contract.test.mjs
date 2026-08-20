// The Market page environment.
//
// The page should read as an interface placed inside a dimly lit branded room,
// not as a graphic pasted onto a document. This file guards the four things
// that made that true, and the one thing that must stay false: the treatment
// is SCOPED, so /Explore, /Rankings and the set pages — which share the same
// artwork component and the same `--set-artwork-*` defaults — are untouched.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(new URL(import.meta.url).pathname.slice(1));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");

const page = read("page.js");
const css = read("../styles/globals.css");
const artwork = read("../../components/ui/PageArtworkAtmosphere.jsx");

// Everything scoped to the Market page lives after this marker. The slice
// starts at the block's opening `/*` so comment delimiters stay balanced —
// otherwise stripping comments below mis-pairs and leaves prose behind.
const marketEnv = css.slice(css.lastIndexOf("/*", css.indexOf("MARKET PAGE ENVIRONMENT")));

test("the environment is opted into by the Market page root and nowhere else", () => {
  assert.match(page, /explore-glass-scope market-atmosphere-scope/);
  // One class on one root. No new elements, no wrapper, no layout change.
  assert.equal((page.match(/market-atmosphere-scope/g) || []).length, 1);
  // The scope root still establishes its own stacking context, which is what
  // confines every negative z-index below to this page.
  assert.match(page, /relative isolate/);
});

test("the shared artwork component was not touched to achieve this", () => {
  assert.match(artwork, /set-page-atmosphere pointer-events-none fixed inset-0 -z-10/);
  assert.match(artwork, /set-page-atmosphere-bloom/);
  assert.match(artwork, /set-page-atmosphere-artwork/);
  // No Market-specific branch leaked into the shared component.
  assert.doesNotMatch(artwork, /market/i);
});

test("the room is a real layer behind everything, at every width", () => {
  assert.match(marketEnv, /\.market-atmosphere-scope::before \{/);
  const room = marketEnv.slice(marketEnv.indexOf(".market-atmosphere-scope::before {"));
  assert.match(room, /position: fixed;/);
  assert.match(room, /z-index: -20;/);
  assert.match(room, /pointer-events: none;/);
  // It sits BELOW the mural layer, which the shared component fixes at -10.
  assert.ok(-20 < -10);
  // A room is not one wash. It needs walls that fall into shadow, a lit
  // zone where the content sits, and a floor — that tonal STRUCTURE is what
  // reads as space; a single broad gradient reads as a dark page.
  assert.match(room, /Side walls/, "left and right walls");
  assert.match(room, /rgba\(0, 2, 6, 0\.78\) 0%/, "the walls genuinely fall to near-black");
  assert.match(room, /Ceiling and floor shadow/, "closed on all four sides");
  assert.match(room, /wall-wash/, "a lit zone behind the content column");
  assert.match(room, /The key light/, "one directional light");
  assert.match(room, /rgba\(140, 182, 246/, "cool-toned, upper centre-right");
  assert.match(room, /bounce off the floor/, "the floor is not a dead black band");
  assert.match(room, /feTurbulence/, "fine grain against gradient banding");
  // Depth comes from shadow, not from turning the lights up: every lift is
  // under 0.13 alpha while the shadows run past 0.6.
  const lifts = [...room.matchAll(/rgba\(\d+, \d+, \d+, (0\.\d+)\)/g)]
    .map((m) => Number(m[1]));
  assert.ok(Math.max(...lifts) > 0.6, "the shadows must be the strong end of the range");
});

test("the mural is ghosted to luminance — the logo palette never reaches the UI", () => {
  const mural = marketEnv.slice(marketEnv.indexOf(".market-atmosphere-scope .set-page-atmosphere {"));
  // grayscale(1) FIRST: the wordmark's #ffca02 sat a few points from --accent
  // (#FACC15) and competed with the pills, the gain/loss figures and the chart.
  assert.match(marketEnv, /\.market-atmosphere-scope \.set-page-atmosphere-artwork \{\s*\n\s*filter:\s*\n?\s*grayscale\(1\)/);
  assert.match(marketEnv, /\.market-atmosphere-scope \.set-page-atmosphere-bloom \{\s*\n\s*filter:\s*\n?\s*grayscale\(1\)/);
  // Re-tinted cool rather than left neutral, so it belongs to the room.
  assert.match(marketEnv, /sepia\(0\.45\) hue-rotate\(176deg\)/);
  // Quieter than the shared treatment it overrides (0.09945 / 0.0459).
  const opacity = Number(mural.match(/--set-artwork-opacity: ([\d.]+);/)[1]);
  const bloom = Number(mural.match(/--set-artwork-bloom-opacity: ([\d.]+);/)[1]);
  assert.ok(opacity < 0.09945, `mural opacity ${opacity} must be under the shared 0.09945`);
  assert.ok(bloom < 0.0459, `bloom opacity ${bloom} must be under the shared 0.0459`);
  // Softer, so it reads as a wall graphic rather than a crisp watermark.
  assert.match(marketEnv, /blur\(2\.4px\)/);
});

test("the mural is revealed in negative space, not behind the numbers", () => {
  const mural = marketEnv.slice(marketEnv.indexOf(".market-atmosphere-scope .set-page-atmosphere {"));
  const mask = mural.slice(mural.indexOf("--set-artwork-mask:"));
  // Peaks through the open band at the top, then falls away down the page as
  // the analysis surfaces get dense.
  assert.match(mask, /#000 16%/);
  assert.match(mask, /rgba\(0, 0, 0, 0\.08\) 100%/);
  // And a veil above the mural sinks its periphery into the corners.
  assert.match(marketEnv, /\.market-atmosphere-scope \.set-page-atmosphere::after \{/);
});

test("panels are lifted off the room without !important or a layout change", () => {
  const panels = marketEnv.slice(marketEnv.indexOf(".explore-glass-scope.market-atmosphere-scope .set-glass-surface"));
  // Denser ground than the shared rgba(8,17,31,0.40), so the mural genuinely
  // recedes behind dense data instead of showing through it.
  assert.match(panels, /background: rgba\(8, 16, 30, 0\.7\);/);
  // A top-edge highlight AND a two-stage cast shadow — a tight contact shadow
  // plus a long soft one, which is what separates "a card" from "a card in a
  // room" now that the room's own edges are genuinely dark.
  assert.match(panels, /inset 0 1px 0 rgba\(255, 255, 255, 0\.06\)/);
  assert.match(panels, /0 10px 24px -12px/, "contact shadow");
  assert.match(panels, /0 34px 70px -26px/, "cast shadow");
  // Specificity, not force: both classes are on the same root element.
  // Comments stripped first — the prose in this block legitimately explains
  // why no rule needs !important, and would otherwise match the assertion.
  const envCode = marketEnv.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(envCode, /!important/);
  // Purely a paint change — nothing here can move content. The lookbehind
  // keeps `@media (max-width: …)` from reading as a `width:` declaration.
  assert.doesNotMatch(envCode, /(?<![-\w])(margin|padding|width|height|display|grid-template|flex-direction)\s*:/);
});

test("below desktop the treatment simplifies rather than intensifying", () => {
  const mobile = marketEnv.slice(marketEnv.indexOf("@media (max-width: 1199.98px)"));
  // The grain, the key light, the wall-wash and the floor bounce are all
  // dropped. What remains is the base gradient plus the four-sided shadow
  // frame — the cheapest half of the treatment and the half that carries the
  // depth.
  assert.doesNotMatch(mobile, /feTurbulence/);
  assert.doesNotMatch(mobile, /rgba\(132, 174, 238/);
  assert.match(mobile, /linear-gradient\(180deg, #081220/);
  // The walls survive, because they are the part that reads as depth rather
  // than as decoration, and they cost one gradient. They are softer than the
  // desktop pair (0.5 against 0.78).
  assert.match(mobile, /rgba\(0, 2, 6, 0\.5\) 0%/);
  // And the pre-existing "no backdrop-filter on mobile" behaviour is restored,
  // since there is no mural down here to blur.
  assert.match(mobile, /backdrop-filter: none;/);
});
