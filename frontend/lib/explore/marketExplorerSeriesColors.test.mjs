import assert from "node:assert/strict";
import test from "node:test";

import {
  MARKET_EXPLORER_SERIES_COLORS,
  colorForSeriesFingerprint,
  isReservedHue,
  resolveSeriesIdentityColor,
  seriesColorForKey,
  softSeriesColor,
} from "./marketExplorerSeriesColors.mjs";

// The whole point of the registry: two markets a user is likely to chart
// together must not be the same color.
test("every registered series color is unique, apart from the graded alias", () => {
  // `graded` and `gradedMarket` are the same placeholder under the two ids it
  // is known by — the Market Overview row and the Explorer rail option — and
  // are deliberately the same color. Nothing else may share one.
  const values = Object.entries(MARKET_EXPLORER_SERIES_COLORS)
    .filter(([key]) => key !== "gradedMarket")
    .map(([, color]) => color);
  assert.equal(new Set(values).size, values.length);
  assert.equal(
    MARKET_EXPLORER_SERIES_COLORS.graded,
    MARKET_EXPLORER_SERIES_COLORS.gradedMarket
  );
});

test("a parent and its own children do not share a hue family", () => {
  // The readability failure this module exists to fix.
  const cluster = [
    "raw",
    "card:raw:specialIllustrationRare",
    "card:raw:illustrationRare",
    "card:raw:ultraRare",
  ].map(seriesColorForKey);
  assert.equal(new Set(cluster).size, cluster.length);

  const sealedCluster = [
    "sealedMarket",
    "sealed:eliteTrainerBox",
    "sealed:boosterBox",
    "sealed:boosterBundle",
  ].map(seriesColorForKey);
  assert.equal(new Set(sealedCluster).size, sealedCluster.length);
});

test("an unregistered key returns null rather than a silent fallback", () => {
  assert.equal(seriesColorForKey("card:topChase:specialIllustrationRare"), null);
  assert.equal(seriesColorForKey(""), null);
  assert.equal(seriesColorForKey(undefined), null);
});

test("a custom query's color is a pure function of its fingerprint", () => {
  const first = colorForSeriesFingerprint("abc123");
  assert.equal(first, colorForSeriesFingerprint("abc123"));
  assert.notEqual(first, colorForSeriesFingerprint("def456"));
});

test("generated colors never land in a reserved gain/loss/interaction band", () => {
  for (let index = 0; index < 500; index += 1) {
    const color = colorForSeriesFingerprint(`query-${index}`);
    const hue = Number(color.match(/^hsl\((\d+(?:\.\d+)?)/)[1]);
    assert.equal(isReservedHue(hue), false, `${color} is reserved`);
  }
});

test("the loss band wraps past 360 correctly", () => {
  assert.equal(isReservedHue(355), true);
  assert.equal(isReservedHue(5), true);
  assert.equal(isReservedHue(40), false);
});

test("resolveSeriesIdentityColor prefers the registry and falls back deterministically", () => {
  assert.equal(resolveSeriesIdentityColor("raw"), MARKET_EXPLORER_SERIES_COLORS.raw);
  const custom = resolveSeriesIdentityColor("query:xyz", "fingerprint-1");
  assert.equal(custom, colorForSeriesFingerprint("fingerprint-1"));
  // With no fingerprint the key itself is the stable input.
  assert.equal(
    resolveSeriesIdentityColor("query:xyz"),
    colorForSeriesFingerprint("query:xyz")
  );
});

function hueOf(color) {
  return Number(String(color).match(/^hsl\((\d+(?:\.\d+)?)/)[1]);
}

test("no registered identity sits in a reserved gain/loss/interaction band", () => {
  for (const [key, color] of Object.entries(MARKET_EXPLORER_SERIES_COLORS)) {
    assert.equal(isReservedHue(hueOf(color)), false, `${key} (${color}) is reserved`);
  }
});

test("registered identities are spread, not clustered in hue families", () => {
  // The failure mode this replaces: Raw/SIR/IR/Ultra Rare all within a few
  // degrees of violet, and all five sealed families within a few degrees of
  // amber, so four selected lines were one indistinguishable smear.
  const hues = Object.entries(MARKET_EXPLORER_SERIES_COLORS)
    // Graded is a desaturated placeholder that is never drawn on the chart.
    .filter(([key]) => key !== "graded" && key !== "gradedMarket")
    .map(([, color]) => hueOf(color))
    .sort((left, right) => left - right);
  for (let index = 1; index < hues.length; index += 1) {
    assert.ok(
      hues[index] - hues[index - 1] >= 9,
      `hues ${hues[index - 1]} and ${hues[index]} are too close to tell apart`
    );
  }
});

test("softSeriesColor keeps the hue and only lowers alpha", () => {
  assert.equal(softSeriesColor("rgb(1,2,3)"), "rgba(1,2,3,0.16)");
  assert.equal(softSeriesColor("hsl(200 70% 62%)", 0.2), "hsla(200,70%,62%,0.2)");
});

test("colors are assigned by key, never by selection order", () => {
  const first = ["sealed:packs", "raw"].map((key) => resolveSeriesIdentityColor(key));
  const reordered = ["raw", "sealed:packs"].map((key) => resolveSeriesIdentityColor(key));
  assert.deepEqual(first, [reordered[1], reordered[0]]);
});
