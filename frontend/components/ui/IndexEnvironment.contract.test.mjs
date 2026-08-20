// The index environment — a SHARED premium background system.
//
// One class, `.index-environment`, carries a dark branded room, its edge
// falloff, its lighting and its panel elevation. Six roots wear it today:
// /Market, /Rankings, /TCGs/Pokemon, /TCGs/Pokemon/Sets, /Articles and the
// Pokemon set detail page. Only the MURAL differs — the Pokemon wordmark for
// the five Pokemon-wide surfaces, the set's own artwork for a set page.
//
// This file replaced app/Market/MarketAtmosphere.contract.test.mjs, which
// guarded the same rules back when they were a Market-only block. The system
// is shared now, so its contract lives with the shared components.

import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relative) => fs.readFileSync(path.resolve(here, relative), "utf8").replace(/\r\n/g, "\n");

const css = read("../../app/styles/globals.css");
const marketPage = read("../../app/Market/page.js");
const rankingsPage = read("../../app/Explore/page.js");
const tcgPage = read("../../app/TCGs/Pokemon/page.js");
const articlesPage = read("../../app/Articles/page.js");
const setsCatalogPage = read("../../app/TCGs/Pokemon/Sets/page.js");
const setPage = read("../explore/RipStatisticsPageClient.jsx");
const artworkMural = read("./PageArtworkAtmosphere.jsx");

const wordmarkSurfaces = [
  ["Market", marketPage],
  ["Rankings", rankingsPage],
  ["TCGs/Pokemon", tcgPage],
  ["Articles", articlesPage],
  ["Pokemon set catalog", setsCatalogPage],
];

// The slice starts at the block's opening `/*` so comment delimiters stay
// balanced — otherwise stripping comments below mis-pairs and leaves prose.
const env = css.slice(css.lastIndexOf("/*", css.indexOf("THE INDEX ENVIRONMENT")));
const envCode = env.replace(/\/\*[\s\S]*?\*\//g, "");

test("every surface opts into the SAME environment class", () => {
  for (const [name, source] of [...wordmarkSurfaces, ["set detail", setPage]]) {
    assert.match(source, /index-environment/, `${name} must wear the shared environment`);
  }
  // The system is one class, not six copies of a style block.
  assert.equal((css.match(/\.index-environment(?![-\w])/g) || []).length > 0, true);
  assert.doesNotMatch(css, /market-atmosphere-scope/, "no page-specific scope survives");
  // Every root establishes its own stacking context, which is what confines
  // the environment's negative z-indexes to that page.
  for (const [name, source] of [...wordmarkSurfaces, ["set detail", setPage]]) {
    assert.match(source, /relative isolate/, `${name} must establish a stacking context`);
  }
});

test("the room is one shared layer behind everything, at every width", () => {
  const room = env.slice(env.indexOf(".index-environment::before {"));
  assert.match(room, /position: fixed;/);
  assert.match(room, /z-index: -20;/, "below the mural layer, which the murals fix at -10");
  assert.match(room, /pointer-events: none;/);
  // A room is not one wash. It needs walls that fall into shadow, a lit zone
  // where the content sits, and a floor — that tonal STRUCTURE is what reads
  // as space; a single broad gradient reads as a dark page.
  assert.match(room, /Side walls/);
  assert.match(room, /Corner occlusion/);
  assert.match(room, /wall-wash/);
  assert.match(room, /The key light/);
  assert.match(room, /bounce off the floor/);
  assert.match(room, /feTurbulence/, "fine grain against gradient banding");
  // Depth comes from shadow, not from turning the lights up.
  const alphas = [...room.matchAll(/rgba\(\d+, \d+, \d+, (0\.\d+)\)/g)].map((m) => Number(m[1]));
  assert.ok(Math.max(...alphas) > 0.6, "the shadows must be the strong end of the range");
});

test("the wordmark mural is a surface, not an apparition", () => {
  const mural = env.slice(env.indexOf(".index-environment .set-page-atmosphere {"));
  // THE THREE THINGS THAT ONCE MADE IT READ AS A GHOST, each asserted gone.
  // 1. A 58px-blurred duplicate floating behind a softer copy.
  const bloomBlur = Number(mural.match(/--set-artwork-bloom-blur: ([\d.]+)px;/)[1]);
  assert.ok(bloomBlur <= 4, `bloom blur ${bloomBlur}px must stay a contact shadow, not a halo`);
  // 2. Out-of-focus art reads as suspended in air. A painted surface has edges.
  assert.match(env, /\.index-environment\.explore-glass-scope \.set-page-atmosphere-artwork \{[\s\S]*?blur\(0\)/);
  // 3. The two copies must share a scale or every letterform carries a halo.
  assert.equal(
    mural.match(/--set-artwork-scale: ([\d.]+);/)[1],
    mural.match(/--set-artwork-bloom-scale: ([\d.]+);/)[1],
    "the shadow must register with the art it belongs to"
  );
  // Colour is erased on BOTH layers: the wordmark's #ffca02 sat a few points
  // from --accent (#FACC15) and competed with the pills and the chart lines.
  // Safe HERE because every surface in `wordmarkSurfaces` paints the SAME
  // image — see the set-page test below for why it does not generalise.
  assert.match(env, /\.index-environment\.explore-glass-scope \.set-page-atmosphere-artwork \{[\s\S]*?grayscale\(1\)/);
  assert.match(env, /\.index-environment\.explore-glass-scope \.set-page-atmosphere-bloom \{[\s\S]*?grayscale\(1\)/);
  // Quieter than the shared default it overrides (0.09945).
  assert.ok(Number(mural.match(/--set-artwork-opacity: ([\d.]+);/)[1]) < 0.09945);
});

test("mural definition is bought with edge, never with brightness", () => {
  // contrast() steepens the tonal curve so the silhouette separates further
  // from the wall while the fill stays put — a sharper OUTLINE rather than a
  // brighter shape. Raising opacity or brightness instead would have produced
  // the pasted logo this treatment exists to avoid.
  assert.match(env, /\.index-environment\.explore-glass-scope \.set-page-atmosphere-artwork \{[\s\S]*?contrast\(1\.4\)/);
  const brightness = Number(
    env.match(/\.index-environment\.explore-glass-scope \.set-page-atmosphere-artwork \{[\s\S]*?brightness\(([\d.]+)\)/)[1]
  );
  assert.ok(brightness <= 1.25, `the lit face must stay ambient, got brightness(${brightness})`);
});

test("nothing in the environment breathes", () => {
  // The veil inherited a 14s opacity pulse. A slowly breathing haze is the
  // most spectral thing a page can do, and a room does not do it.
  const veil = env.slice(env.indexOf(".index-environment .set-page-atmosphere::after {"));
  assert.match(veil, /animation: none;/);
  const veilRule = veil.slice(0, veil.indexOf("}"));
  assert.doesNotMatch(veilRule, /rgba\(147, 187, 245/, "no centred blue glow above the mural");
});

test("a set page's mural is its own artwork, in its own colours", () => {
  const scope = env.slice(env.indexOf(".index-environment.set-detail-glass-scope .set-page-atmosphere {"));
  const artwork = scope.slice(
    scope.indexOf(".index-environment.set-detail-glass-scope .set-page-atmosphere-artwork {"),
    scope.indexOf(".index-environment.set-detail-glass-scope .set-page-atmosphere-bloom {")
  );
  // A set page paints a DIFFERENT image on every route, and that image's
  // palette IS the identity the reader recognises. The luminance relief the
  // wordmark surfaces use would hand every set the same navy silhouette.
  assert.ok(artwork.length > 0, "the set page must define its own artwork treatment");
  assert.doesNotMatch(
    artwork,
    /(grayscale|sepia|hue-rotate|contrast|saturate|invert)\(/,
    "the set artwork must keep its source colours"
  );
  // The glow lives OUTSIDE the art: the same image, blurred wide and scaled
  // past the crisp copy, so what lands on the wall is the set's own colour.
  const bloomBlur = Number(scope.match(/--set-artwork-bloom-blur: ([\d.]+)px;/)[1]);
  assert.ok(bloomBlur >= 30, `the set bloom is a backlight, not a contact shadow, got ${bloomBlur}px`);
  const base = Number(scope.match(/--set-artwork-scale: ([\d.]+);/)[1]);
  assert.ok(
    Number(scope.match(/--set-artwork-bloom-scale: ([\d.]+);/)[1]) > base,
    "the backlight must spill past the silhouette it sits behind"
  );
  // Oversized and cropped, but not so oversized that a long set logo never
  // resolves as one shape — these were cut 12% from 1.28/1.42 for that reason.
  const desktop = Number(
    scope.slice(scope.indexOf("@media (min-width: 1200px)")).match(/--set-artwork-scale: ([\d.]+);/)[1]
  );
  assert.ok(base > 1 && base <= 1.2, `the base crop must stay environmental but contained, got ${base}`);
  assert.ok(desktop > base && desktop <= 1.3, `the desktop crop must stay contained, got ${desktop}`);
  // Ambient, never foreground.
  assert.ok(Number(scope.match(/--set-artwork-opacity: ([\d.]+);/)[1]) <= 0.16);
});

test("each surface gets exactly one mural, and it is the right one", () => {
  // The Pokemon-wide surfaces: the wordmark, through the shared component.
  for (const [name, source] of wordmarkSurfaces) {
    assert.match(source, /PageArtworkAtmosphere/, `${name} must render the shared mural`);
    assert.match(source, /getExploreBackground\("pokemon"\)/, `${name} must paint the wordmark`);
    assert.equal((source.match(/<PageArtworkAtmosphere/g) || []).length, 1, `${name}: exactly one mural`);
    assert.match(source, /explore-glass-scope/, `${name} must take the wordmark's luminance relief`);
  }
  // Set detail: the SET's own artwork, through the same component.
  assert.match(setPage, /<PageArtworkAtmosphere\s+src=\{ambientSetArtworkUrl\}/);
  assert.equal((setPage.match(/<PageArtworkAtmosphere/g) || []).length, 1, "exactly one mural is rendered");
  // Giant readable set-name typography was tried in that slot and rejected: it
  // read as a word poster, and it discarded the set's real identity.
  assert.doesNotMatch(setPage, /PageEnvironmentMural/);
  assert.doesNotMatch(css, /index-mural/);
  // The shared artwork component was not forked to achieve any of this.
  assert.doesNotMatch(artworkMural, /market|set-detail/i);
});

test("panels are lifted off the room on every surface, without !important", () => {
  const panels = env.slice(env.indexOf(".index-environment.index-environment .set-glass-surface"));
  // Denser ground: the wall must not be legible THROUGH a data surface.
  assert.match(panels, /background: rgba\(8, 16, 30, 0\.78\);/);
  assert.match(panels, /inset 0 1px 0 rgba\(255, 255, 255, 0\.065\)/);
  // Ambient occlusion — what makes the room read as BEHIND the panel rather
  // than beside it. The cast shadows only place it above the floor.
  assert.match(panels, /0 0 0 6px rgba\(0, 2, 8, 0\.16\)/, "occlusion ring");
  assert.match(panels, /0 34px 70px -26px/, "cast shadow");
  // The doubled class is (0,3,0), so it outranks BOTH `.explore-glass-scope
  // .set-glass-surface` and `.set-detail-glass-scope .set-glass-surface`
  // without depending on file order and without force.
  assert.doesNotMatch(envCode, /!important/);
  // Purely a paint change — nothing here can move content. The lookbehind
  // keeps `@media (max-width: …)` from reading as a `width:` declaration.
  assert.doesNotMatch(envCode, /(?<![-\w])(margin|grid-template|flex-direction)\s*:/);
});

test("below desktop the environment simplifies rather than intensifying", () => {
  const mobile = env.slice(env.indexOf("@media (max-width: 1199.98px)"));
  // The grain and the key light are dropped; the walls survive, because they
  // are the part that reads as depth rather than as decoration.
  assert.doesNotMatch(mobile, /feTurbulence/);
  assert.doesNotMatch(mobile, /rgba\(132, 174, 238/);
  assert.match(mobile, /rgba\(0, 2, 6, 0\.5\) 0%/, "softer walls than the desktop 0.92");
  // The pre-existing "no backdrop-filter on mobile" behaviour is preserved.
  assert.match(mobile, /backdrop-filter: none;/);
  // The wordmark mural does not render below desktop at all, and the set
  // page's artwork is pulled back rather than intensified.
  for (const [name, source] of wordmarkSurfaces) {
    assert.match(source, /visibilityClassName="hidden desk:block"/, `${name}: desktop-only mural`);
  }
  // lastIndexOf: the mobile override is the LAST of the three declarations of
  // this selector (base, desktop, mobile) in the file.
  const setMobile = mobile.slice(mobile.lastIndexOf(".index-environment.set-detail-glass-scope .set-page-atmosphere {"));
  assert.ok(Number(setMobile.match(/--set-artwork-opacity: ([\d.]+);/)[1]) <= 0.08);
  assert.ok(Number(setMobile.match(/--set-artwork-scale: ([\d.]+);/)[1]) <= 1.15);
});
