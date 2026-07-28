// The shared RIP tier presentation. These assertions are on helper OUTPUT
// rather than on class strings, so a retune of the palette stays free while the
// invariants that make the treatment premium (and honest) stay pinned.
//
// The module is imported directly: it is dependency-free precisely so it can
// run under `node --test` / `tsx --test` without the Next bundler's "@/"
// resolution. The tier -> colour mapping it consumes still lives in
// RANK_CONFIG, reached via getRipTierPresentation in interpretationTone.js.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  RIP_OUTLOOK_WASH_STOPS,
  RIP_TIER_NEUTRAL_RGB,
  buildRipTierPresentation,
  toRgbTriplet,
} from "./ripTierPresentation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const readSource = (relative) => fs.readFileSync(path.join(here, relative), "utf8").replace(/\r\n/g, "\n");

// The live tier colours, read from the single source of truth rather than
// copied, so this file cannot become a second mapping.
function tierColorsFromRankConfig() {
  const config = readSource("../../constants/rankConfig.js");
  const colors = {};
  for (const [, tier, color] of config.matchAll(/^ {2}([SABCDF]): \{[\s\S]*?\n {4}color: "([^"]+)"/gm)) {
    colors[tier] = color;
  }
  return colors;
}

const TIER_COLORS = tierColorsFromRankConfig();

function alphaOf(rgbaString) {
  const match = String(rgbaString).match(/rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\s*\)/);
  assert.ok(match, `expected an rgba() string, got ${rgbaString}`);
  return Number(match[1]);
}

function tripletOf(rgbaString) {
  return toRgbTriplet(String(rgbaString).match(/rgba?\([^)]*\)/)[0]);
}

test("every tier in RANK_CONFIG resolves to its own presentation", () => {
  assert.deepEqual(Object.keys(TIER_COLORS).sort(), ["A", "B", "C", "D", "F", "S"]);

  const seen = new Map();
  for (const [tier, color] of Object.entries(TIER_COLORS)) {
    const presentation = buildRipTierPresentation({ tier, accentColor: color });
    assert.equal(presentation.tier, tier);
    assert.equal(presentation.rgb, toRgbTriplet(color), `${tier} must carry its own RANK_CONFIG colour`);
    assert.ok(!seen.has(presentation.rgb), `${tier} must not reuse ${seen.get(presentation.rgb)}'s colour`);
    seen.set(presentation.rgb, tier);
  }

  // The B-tier green is one entry among six, never a baked-in default.
  assert.notEqual(buildRipTierPresentation({ tier: "C", accentColor: TIER_COLORS.C }).rgb, toRgbTriplet(TIER_COLORS.B));
});

test("a missing or unparseable tier colour falls back to the neutral, not to a tier", () => {
  for (const input of [undefined, null, "", "not-a-colour", "#86efac", 42]) {
    const presentation = buildRipTierPresentation({ accentColor: input });
    assert.equal(presentation.rgb, RIP_TIER_NEUTRAL_RGB);
    assert.equal(presentation.tier, null);
    // Still a complete, renderable treatment — nothing is undefined.
    assert.ok(presentation.outlookWash.startsWith("linear-gradient(90deg,"));
    for (const key of ["tierPill", "rankPill", "verdictPill"]) {
      assert.deepEqual(Object.keys(presentation[key]).sort(), ["backgroundColor", "borderColor", "color"]);
      for (const value of Object.values(presentation[key])) {
        assert.match(String(value), /^rgba\(/);
      }
    }
  }
  assert.notEqual(RIP_TIER_NEUTRAL_RGB, toRgbTriplet(TIER_COLORS.B));
});

test("buildRipTierPresentation() with no arguments is safe", () => {
  const presentation = buildRipTierPresentation();
  assert.equal(presentation.rgb, RIP_TIER_NEUTRAL_RGB);
  assert.equal(presentation.tier, null);
});

// ---------------------------------------------------------------------------
// Opening Outlook — a rail and a fade, never a filled banner
// ---------------------------------------------------------------------------

test("the outlook wash is monotonically decreasing and reaches zero before the right edge", () => {
  const offsets = RIP_OUTLOOK_WASH_STOPS.map((stop) => Number(stop.offset.replace("%", "")));
  const alphas = RIP_OUTLOOK_WASH_STOPS.map((stop) => stop.alpha);

  for (let i = 1; i < RIP_OUTLOOK_WASH_STOPS.length; i += 1) {
    assert.ok(offsets[i] > offsets[i - 1], "wash stops must advance left to right");
    assert.ok(alphas[i] < alphas[i - 1], "the wash must never get stronger further right");
  }
  assert.equal(offsets[0], 0, "the wash is strongest against the rail");
  assert.equal(alphas.at(-1), 0, "the wash must end fully transparent");
  assert.ok(offsets.at(-1) <= 90, "the colour must disappear before the right edge, leaving no visible edge");
  // Restrained: even at its strongest the wash is a tint, not a fill.
  assert.ok(alphas[0] <= 0.14, `the leading tint must stay subtle, got ${alphas[0]}`);
  // Already faint where the sentence begins.
  assert.ok(alphas[1] <= alphas[0] / 2, "the wash must drop off sharply behind the copy");
});

test("the wash renders as one horizontal gradient in the active tier colour", () => {
  const presentation = buildRipTierPresentation({ tier: "C", accentColor: TIER_COLORS.C });
  const expectedRgb = toRgbTriplet(TIER_COLORS.C);

  assert.ok(presentation.outlookWash.startsWith("linear-gradient(90deg, "), "the fade must run left to right");
  const stops = presentation.outlookWash
    .slice("linear-gradient(90deg, ".length, -1)
    .split(/,\s(?=rgba)/);
  assert.equal(stops.length, RIP_OUTLOOK_WASH_STOPS.length);
  for (const [index, stop] of stops.entries()) {
    assert.equal(tripletOf(stop), expectedRgb, "every stop uses the active tier's colour");
    assert.equal(alphaOf(stop), RIP_OUTLOOK_WASH_STOPS[index].alpha);
    assert.ok(stop.endsWith(RIP_OUTLOOK_WASH_STOPS[index].offset));
  }
  // The final stop is a transparent tier colour, not the `transparent` keyword,
  // so nothing interpolates through black.
  assert.ok(!presentation.outlookWash.includes("transparent"));
  assert.equal(alphaOf(stops.at(-1)), 0);
});

test("the rail is bright and its glow is clipped to the left of the rail", () => {
  const presentation = buildRipTierPresentation({ tier: "S", accentColor: TIER_COLORS.S });

  assert.equal(tripletOf(presentation.outlookRail.borderLeftColor), toRgbTriplet(TIER_COLORS.S));
  assert.ok(alphaOf(presentation.outlookRail.borderLeftColor) >= 0.85, "the rail is the bright element");
  // The rail is far brighter than the strongest point of the wash beside it.
  assert.ok(alphaOf(presentation.outlookRail.borderLeftColor) > RIP_OUTLOOK_WASH_STOPS[0].alpha * 5);

  const [offsetX, offsetY, blur, spread] = presentation.outlookRail.boxShadow
    .split(" ")
    .slice(0, 4)
    .map((token) => Number(token.replace("px", "")));
  assert.ok(offsetX < 0, "the glow must be offset toward the rail, not centred on the box");
  assert.equal(offsetY, 0, "a vertical offset would read as a drop shadow under a card");
  assert.ok(spread < 0 && blur + spread <= 0, "the glow must not extend past the box on the trailing side");
  assert.ok(alphaOf(presentation.outlookRail.boxShadow) <= 0.6, "the glow stays restrained, never neon");
  assert.ok(!presentation.outlookRail.boxShadow.includes("inset"), "an inset ring would outline all four sides");
  // `blur + spread <= 0` is what keeps this a rail halo. With a blur wider than
  // the inset, the shadow reaches back out over the top and bottom edges across
  // the FULL width of the callout — a perimeter outline, which is exactly the
  // "neon outlined box" this treatment must never become.
  assert.ok(Math.abs(offsetX) > 0, "some x-offset is needed or the halo is clipped away entirely");
});

test("the localized edge highlight is a tier colour the callout can mask", () => {
  const presentation = buildRipTierPresentation({ tier: "A", accentColor: TIER_COLORS.A });

  // The upper-left edge highlight (drawn by `.rip-outlook-callout::before` and
  // faded out by a gradient mask) takes its colour from the same resolved
  // accent as the rail, so the lit corner can never be a different tier's
  // colour than the rail beside it.
  assert.equal(tripletOf(presentation.outlookEdge), toRgbTriplet(TIER_COLORS.A));
  assert.ok(alphaOf(presentation.outlookEdge) <= 0.6, "a 1px edge line stays restrained");
  assert.ok(
    alphaOf(presentation.outlookEdge) < alphaOf(presentation.outlookRail.borderLeftColor),
    "the rail stays the brighter of the two, so the corner reads as a highlight and not a second rail"
  );

  // Every tier resolves its own edge colour; none falls back to the neutral.
  for (const [tier, color] of Object.entries(TIER_COLORS)) {
    const tierPresentation = buildRipTierPresentation({ tier, accentColor: color });
    assert.equal(tripletOf(tierPresentation.outlookEdge), toRgbTriplet(color), `${tier} resolves its own edge colour`);
  }
});

// ---------------------------------------------------------------------------
// Title card — one hierarchy, three weights
// ---------------------------------------------------------------------------

test("tier outranks verdict outranks rank, in the same colour family", () => {
  const presentation = buildRipTierPresentation({ tier: "D", accentColor: TIER_COLORS.D });
  const expectedRgb = toRgbTriplet(TIER_COLORS.D);

  const border = (key) => alphaOf(presentation[key].borderColor);
  assert.ok(border("tierPill") > border("verdictPill"), "the tier carries the strongest border");
  assert.ok(border("verdictPill") > border("rankPill"), "the rank is the quietest pill");

  assert.ok(
    alphaOf(presentation.tierPill.color) > alphaOf(presentation.verdictPill.color),
    "the tier text is the most emphatic"
  );

  // Same semantic family everywhere the tier colour is used…
  for (const key of ["tierPill", "verdictPill"]) {
    assert.equal(tripletOf(presentation[key].borderColor), expectedRgb);
    assert.equal(tripletOf(presentation[key].color), expectedRgb);
    assert.equal(tripletOf(presentation[key].backgroundColor), expectedRgb);
  }
  assert.equal(tripletOf(presentation.rankPill.borderColor), expectedRgb);
  assert.equal(tripletOf(presentation.rankPill.backgroundColor), expectedRgb);
  // …but the rank's own text is deliberately more neutral than the tier's.
  assert.notEqual(tripletOf(presentation.rankPill.color), expectedRgb);
});

test("pill backgrounds stay faint tints so the pills read as outlined, not filled", () => {
  const presentation = buildRipTierPresentation({ tier: "A", accentColor: TIER_COLORS.A });

  for (const key of ["tierPill", "rankPill", "verdictPill"]) {
    const background = alphaOf(presentation[key].backgroundColor);
    assert.ok(background > 0, `${key} keeps a trace of tone`);
    assert.ok(background <= 0.12, `${key} background must stay a wash, got ${background}`);
    assert.ok(
      alphaOf(presentation[key].borderColor) > background,
      `${key} must read as an outline rather than a filled chip`
    );
  }
});

test("switching modes to a different tier repaints every shared surface", () => {
  // RIP Score B vs RIP Core C — the case the title card and the breakdown must
  // never disagree on.
  const ripScore = buildRipTierPresentation({ tier: "B", accentColor: TIER_COLORS.B });
  const ripCore = buildRipTierPresentation({ tier: "C", accentColor: TIER_COLORS.C });

  const surfaces = [
    (p) => p.outlookRail.borderLeftColor,
    (p) => p.outlookRail.boxShadow,
    (p) => p.outlookWash,
    (p) => p.tierPill.borderColor,
    (p) => p.tierPill.color,
    (p) => p.tierPill.backgroundColor,
    (p) => p.rankPill.borderColor,
    (p) => p.rankPill.backgroundColor,
    (p) => p.verdictPill.borderColor,
    (p) => p.verdictPill.color,
    (p) => p.verdictPill.backgroundColor,
  ];

  for (const read of surfaces) {
    assert.notEqual(read(ripScore), read(ripCore), "no surface may keep the previous mode's colour");
  }
  // The rank text is intentionally neutral, so it is the one value that does
  // not change with the tier.
  assert.equal(ripScore.rankPill.color, ripCore.rankPill.color);
});

// ---------------------------------------------------------------------------
// One source, not two
// ---------------------------------------------------------------------------

test("the title card and the RIP breakdown read the same helper, and no surface hard-codes a tier", () => {
  const client = readSource("../../components/explore/RipStatisticsPageClient.jsx");
  const tone = readSource("./interpretationTone.js");

  assert.ok(tone.includes('import { buildRipTierPresentation } from "./ripTierPresentation.mjs";'));
  assert.ok(tone.includes("export function getRipTierPresentation("), "one exported entry point");

  // Both surfaces call it; neither builds its own mapping.
  assert.equal((client.match(/getRipTierPresentation\(/g) || []).length, 2);
  assert.ok(client.includes("getRipTierPresentation({ label: verdict, rankTier })"), "Opening Outlook");
  assert.ok(client.includes("const setContextRipPresentation = getRipTierPresentation({"), "title card");

  // The RANK_CONFIG tier colours may not be transcribed into either file.
  for (const [tier, color] of Object.entries(TIER_COLORS)) {
    const triplet = toRgbTriplet(color).replace(/,/g, ",\\s*");
    const pattern = new RegExp(`rgba?\\(\\s*${triplet}`);
    assert.ok(!pattern.test(client), `${tier}'s colour must not be hard-coded in the page client`);
    assert.ok(!pattern.test(readSource("./ripTierPresentation.mjs")), `${tier}'s colour must not be duplicated here`);
  }
});
